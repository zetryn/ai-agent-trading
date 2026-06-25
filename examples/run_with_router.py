"""Example: scanner driven by `LLMRouter` with multi-provider failover.

This is the recommended production pattern for free-tier reliability. A
single Groq key can spike to p95 ~11s under rate-limit variance (see
`bench_scanner_latency.py`). Wrapping two providers behind `LLMRouter` —
typically Groq as primary and Gemini Flash as failover — keeps p95 close
to the median by skipping a throttled entry automatically.

Run:
    cd examples && python run_with_router.py

Falls back to a stub LLM when no provider keys are configured, so the
example always exercises the same wiring whether or not you have keys.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys

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
from zetryn.llm.types import LLMResult, Message


def _load_env_file() -> None:
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
    keys: list[str] = []
    if prefix in os.environ:
        keys.append(prefix)
    i = 1
    while f"{prefix}_{i}" in os.environ:
        keys.append(f"{prefix}_{i}")
        i += 1
    return keys


class _StubLLM:
    """Fallback when no provider keys are configured."""

    async def complete(self, messages: list[Message], **kw) -> LLMResult:
        payload = {
            "safety":  {"score": 0.8, "verdict": "positive", "signals": [], "reasoning": "stub"},
            "market":  {"score": 0.7, "verdict": "positive", "signals": [], "reasoning": "stub"},
            "wallets": {"score": 0.7, "verdict": "positive", "signals": [], "reasoning": "stub"},
            "social":  {"score": 0.7, "verdict": "positive", "signals": [], "reasoning": "stub"},
            "final_score": 0.75,
            "recommendation": "watch",
            "reasoning": "stub: no provider keys configured",
        }
        return LLMResult(text=json.dumps(payload), model="stub", latency_ms=1.0)

    async def aclose(self) -> None:
        pass


def _build_router() -> tuple[LLMRouter | _StubLLM, list[str]]:
    """Return (client, entry_names). client implements the LLMClient protocol."""
    entries: list[RouterEntry] = []

    groq_keys = _discover_keys("GROQ_API_KEY")
    if groq_keys:
        groq_model = os.environ.get("ZETRYN_GROQ_MODEL", "llama-3.3-70b-versatile")
        groq_client = OpenAICompatibleClient(
            ProviderConfig(
                name="groq",
                base_url=GROQ_BASE_URL,
                model=groq_model,
                key_envs=groq_keys,
                timeout_s=15.0,
            )
        )
        entries.append(
            RouterEntry(
                client=groq_client,
                name=f"groq:{groq_model}",
                limit=get_free_tier_limit("groq", groq_model),
            )
        )

    gemini_keys = _discover_keys("GEMINI_API_KEY")
    if gemini_keys:
        gemini_model = os.environ.get("ZETRYN_GEMINI_MODEL", "gemini-2.5-flash")
        gemini_client = OpenAICompatibleClient(
            ProviderConfig(
                name="gemini",
                base_url=GEMINI_BASE_URL,
                model=gemini_model,
                key_envs=gemini_keys,
                timeout_s=15.0,
            )
        )
        entries.append(
            RouterEntry(
                client=gemini_client,
                name=f"gemini:{gemini_model}",
                limit=get_free_tier_limit("gemini", gemini_model),
            )
        )

    if not entries:
        return _StubLLM(), ["stub (no provider keys)"]

    router = LLMRouter(entries)
    return router, [e.name for e in entries]


async def main() -> int:
    _load_env_file()
    client, names = _build_router()
    print(f"Router entries (in failover order): {names}")
    print("Running scanner against 'GOOD' sample token...\n")

    scanner = build_scanner(client)
    state = await scanner.run(
        State(context=TradingContext(token=SAMPLE_TOKENS["GOOD"], config=ScannerConfig()))
    )
    d = state.output

    print(f"action      : {d.action.upper()}")
    print(f"confidence  : {d.confidence:.2f}")
    print(f"reasons     : {'; '.join(d.reasons)}")
    if d.analysis is not None:
        a = d.analysis
        print(
            f"analyst     : final_score={a.final_score:.2f} "
            f"rec={a.recommendation} reasoning={a.reasoning[:80]}..."
        )

    await client.aclose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
