"""Latency benchmark for the scanner with a real LLM provider.

Validates M8 acceptance criterion #6: end-to-end scan completes in ≤ 5s
per token at p95 with a real Groq key.

Skipped automatically if no provider key is set. To run:

    export GROQ_API_KEY_1=...           # at least one key required
    cd examples && python bench_scanner_latency.py

Optional knobs (env vars):
    ZETRYN_BENCH_RUNS       how many scans to time (default: 20)
    ZETRYN_BENCH_MODEL      model id (default: llama-3.3-70b-versatile)
    ZETRYN_BENCH_PROVIDER   groq | gemini | router (default: groq)
                            router = LLMRouter([groq, gemini]) failover

The script reports min / median / p95 / max latency and verifies the
acceptance bar. Exit code is non-zero if p95 > 5.0s.

Comparing modes: run with ZETRYN_BENCH_PROVIDER=groq first to see the
free-tier variance, then with ZETRYN_BENCH_PROVIDER=router to see how
much multi-provider failover tames p95.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from strategies import SAMPLE_TOKENS, build_scanner
from trading import ScannerConfig, TradingContext
from zetryn.core import State
from zetryn.llm import (
    GEMINI_BASE_URL,
    GROQ_BASE_URL,
    LLMRouter,
    OpenAICompatibleClient,
    ProviderConfig,
    RouterEntry,
    get_free_tier_limit,
)
from zetryn.llm.client import LLMClient

P95_TARGET_SECONDS = 5.0


def _load_env_file() -> None:
    """Minimal .env loader so the bench works without python-dotenv."""
    env_file = pathlib.Path(__file__).resolve().parent.parent / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _discover_keys(prefix: str) -> list[str]:
    """Return all env vars matching ``<prefix>`` or ``<prefix>_1..N``."""
    keys: list[str] = []
    if prefix in os.environ:
        keys.append(prefix)
    i = 1
    while f"{prefix}_{i}" in os.environ:
        keys.append(f"{prefix}_{i}")
        i += 1
    return keys


def _build_provider() -> ProviderConfig | None:
    provider = os.environ.get("ZETRYN_BENCH_PROVIDER", "groq").lower()
    if provider == "groq":
        key_envs = _discover_keys("GROQ_API_KEY")
        if not key_envs:
            return None
        return ProviderConfig(
            name="groq",
            base_url=GROQ_BASE_URL,
            model=os.environ.get("ZETRYN_BENCH_MODEL", "llama-3.3-70b-versatile"),
            key_envs=key_envs,
            timeout_s=15.0,
        )
    if provider == "gemini":
        key_envs = _discover_keys("GEMINI_API_KEY")
        if not key_envs:
            return None
        return ProviderConfig(
            name="gemini",
            base_url=GEMINI_BASE_URL,
            model=os.environ.get("ZETRYN_BENCH_MODEL", "gemini-2.5-flash"),
            key_envs=key_envs,
            timeout_s=15.0,
        )
    raise SystemExit(f"unsupported provider: {provider}")


def _build_router_client() -> tuple[LLMClient | None, str]:
    """Build an LLMRouter covering whichever providers have keys configured.

    Returns (client, label). client is None if no provider key is set.
    """
    entries: list[RouterEntry] = []
    label_parts: list[str] = []

    groq_keys = _discover_keys("GROQ_API_KEY")
    if groq_keys:
        groq_model = os.environ.get("ZETRYN_GROQ_MODEL", "llama-3.3-70b-versatile")
        entries.append(
            RouterEntry(
                client=OpenAICompatibleClient(
                    ProviderConfig(
                        name="groq", base_url=GROQ_BASE_URL, model=groq_model,
                        key_envs=groq_keys, timeout_s=15.0,
                    )
                ),
                name=f"groq:{groq_model}",
                limit=get_free_tier_limit("groq", groq_model),
            )
        )
        label_parts.append(f"groq×{len(groq_keys)}")

    gemini_keys = _discover_keys("GEMINI_API_KEY")
    if gemini_keys:
        gemini_model = os.environ.get("ZETRYN_GEMINI_MODEL", "gemini-2.5-flash")
        entries.append(
            RouterEntry(
                client=OpenAICompatibleClient(
                    ProviderConfig(
                        name="gemini", base_url=GEMINI_BASE_URL, model=gemini_model,
                        key_envs=gemini_keys, timeout_s=15.0,
                    )
                ),
                name=f"gemini:{gemini_model}",
                limit=get_free_tier_limit("gemini", gemini_model),
            )
        )
        label_parts.append(f"gemini×{len(gemini_keys)}")

    if not entries:
        return None, ""
    return LLMRouter(entries), " + ".join(label_parts)


async def main() -> int:
    _load_env_file()
    mode = os.environ.get("ZETRYN_BENCH_PROVIDER", "groq").lower()

    if mode == "router":
        llm, label = _build_router_client()
        if llm is None:
            print("SKIP: no provider keys set for router mode.")
            return 0
        bench_label = f"LLMRouter[{label}]"
    else:
        cfg = _build_provider()
        if cfg is None:
            print(
                "SKIP: no provider key set. Set GROQ_API_KEY_1 (or GEMINI_API_KEY_1) "
                "in your environment or .env file."
            )
            return 0
        llm = OpenAICompatibleClient(cfg)
        bench_label = f"{cfg.name} {cfg.model} (keys={len(cfg.key_envs)})"

    runs = int(os.environ.get("ZETRYN_BENCH_RUNS", "20"))
    print(f"Mode: {bench_label}")
    print(f"Running {runs} scans against the 'GOOD' sample token...")
    # Router carries its own model per entry; only pass explicit model in single-provider mode.
    scanner = build_scanner(llm) if mode == "router" else build_scanner(llm, model=cfg.model)

    latencies_ms: list[float] = []
    failures = 0
    for i in range(runs):
        ctx = TradingContext(token=SAMPLE_TOKENS["GOOD"], config=ScannerConfig())
        t0 = time.perf_counter()
        try:
            state = await scanner.run(State(context=ctx))
        except Exception as exc:  # noqa: BLE001 - bench surfaces all errors
            failures += 1
            print(f"  [{i:3d}] FAILED: {type(exc).__name__}: {exc}")
            continue
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies_ms.append(elapsed_ms)
        d = state.output
        print(f"  [{i:3d}] {elapsed_ms:7.0f} ms  {d.action.upper():6s}  conf={d.confidence:.2f}")

    await llm.aclose()

    if not latencies_ms:
        print("\nAll runs failed.")
        return 2

    if len(latencies_ms) >= 20:
        p95 = statistics.quantiles(latencies_ms, n=20)[18]
    else:
        p95 = max(latencies_ms)
    print("\n--- Summary ---")
    print(f"Completed   : {len(latencies_ms)} / {runs}  (failures: {failures})")
    print(f"min         : {min(latencies_ms):7.0f} ms")
    print(f"median      : {statistics.median(latencies_ms):7.0f} ms")
    print(f"p95         : {p95:7.0f} ms")
    print(f"max         : {max(latencies_ms):7.0f} ms")
    print(f"M8 target   : p95 ≤ {P95_TARGET_SECONDS * 1000:.0f} ms")
    if p95 / 1000 <= P95_TARGET_SECONDS:
        print("RESULT      : PASS")
        return 0
    print("RESULT      : FAIL — p95 above target")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
