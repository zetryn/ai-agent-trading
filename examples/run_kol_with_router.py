"""KOL Copy-Trade with multi-model + multi-provider rotation via LLMRouter.

Same six-scenario flow as `run_kol_copytrade.py` — the only difference is
that the `LLMClient` handed to `build_kol_copytrade(...)` is an
`LLMRouter` wrapping multiple `RouterEntry` objects instead of a single
provider. The router transparently:

  1. Tracks local throttle counters (RPM / RPD / TPM / TPD) per entry
     using sliding-window counters. When entry A's quota is exhausted,
     subsequent calls skip A WITHOUT making a network request and go
     straight to entry B.
  2. Falls over on real-world 429s from the provider — cooldown the
     offending entry, try the next, never raise into the caller.
  3. Raises `NoKeysAvailableError` only when every entry is exhausted.
     The `LLMNode` wrapping the analyst catches this as an LLM failure
     and applies `neutral_kol_verdict` — the graph still returns a
     `Decision`, never crashes.

The example is opt-in via env var. Defaults are tuned for free-tier
keys, so you only need GROQ_API_KEY[_N] to get the demo running.

Run:
    cd examples && python run_kol_with_router.py

Optional knobs (env vars):
    ZETRYN_GROQ_API_KEY_*           one or more Groq keys (reuses
                                     GROQ_API_KEY[_N] naming convention)
    ZETRYN_GEMINI_API_KEY_*          optional second provider for true
                                     multi-provider failover
    ZETRYN_KOL_ROUTER_MODELS=...     comma-separated Groq model list
                                     (default: openai/gpt-oss-20b,
                                     llama-3.3-70b-versatile)

If no Groq key is set the script falls back to rule mode so the demo
flow still runs (you just won't see the rotation in action).
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from strategies import build_kol_copytrade
from trading import KOLBuyEvent, KOLContext, TokenInput
from trading.schemas import (
    ActivityData,
    ContractData,
    HolderData,
    MarketData,
    SocialData,
    TelegramData,
    TwitterData,
    WalletIntel,
)
from zetryn.core import State
from zetryn.knowledge import KnowledgePack
from zetryn.llm import (
    GEMINI_BASE_URL,
    GROQ_BASE_URL,
    LLMRouter,
    OpenAICompatibleClient,
    ProviderConfig,
    RouterEntry,
    get_free_tier_limit,
)

# -- env handling (re-used pattern from run_kol_copytrade.py) ---------------


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
    keys = [prefix] if prefix in os.environ else []
    i = 1
    while f"{prefix}_{i}" in os.environ:
        keys.append(f"{prefix}_{i}")
        i += 1
    return keys


# -- build the router --------------------------------------------------------


def _build_router() -> tuple[LLMRouter | None, list[str]]:
    """Construct an LLMRouter from whatever provider keys are present.

    Returns (router, entry_labels). router is None when no provider key
    is configured (caller can fall back to rule mode).
    """
    _load_env_file()
    entries: list[RouterEntry] = []
    labels: list[str] = []

    # --- Groq entries: one RouterEntry per model ---
    groq_keys = _discover_keys("GROQ_API_KEY")
    if groq_keys:
        models_csv = os.environ.get(
            "ZETRYN_KOL_ROUTER_MODELS",
            "openai/gpt-oss-20b,llama-3.3-70b-versatile",
        )
        models = [m.strip() for m in models_csv.split(",") if m.strip()]
        for model in models:
            client = OpenAICompatibleClient(ProviderConfig(
                name=f"groq:{model}", base_url=GROQ_BASE_URL, model=model,
                key_envs=groq_keys, timeout_s=30.0,
            ))
            entries.append(RouterEntry(
                client=client, name=f"groq:{model}",
                limit=get_free_tier_limit("groq", model),
            ))
            labels.append(f"groq:{model} (keys×{len(groq_keys)})")

    # --- Gemini fallback if configured ---
    gemini_keys = _discover_keys("GEMINI_API_KEY")
    if gemini_keys:
        gemini_model = os.environ.get("ZETRYN_GEMINI_MODEL", "gemini-2.5-flash")
        client = OpenAICompatibleClient(ProviderConfig(
            name=f"gemini:{gemini_model}", base_url=GEMINI_BASE_URL,
            model=gemini_model, key_envs=gemini_keys, timeout_s=30.0,
        ))
        entries.append(RouterEntry(
            client=client, name=f"gemini:{gemini_model}",
            limit=get_free_tier_limit("gemini", gemini_model),
        ))
        labels.append(f"gemini:{gemini_model} (keys×{len(gemini_keys)})")

    if not entries:
        return None, []

    # `LLMRouter` enforces per-entry throttle BEFORE making a network call,
    # so an exhausted RPM/RPD/TPM/TPD bucket on entry A simply skips A and
    # tries entry B with no wasted request. Provider-side 429s also fall over.
    return LLMRouter(entries, cooldown_s=30.0), labels


# -- pack + fixtures (slimmed copies from run_kol_copytrade.py) -------------


def _seed_pack(root: pathlib.Path) -> None:
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "kol_whitelist.json").write_text(json.dumps({
        "wallets": {
            "KOL_SMART_ALPHA": {
                "name": "smart_money_alpha",
                "hit_rate": 0.65, "avg_pnl_pct": 0.45,
                "trades_30d": 31, "exit_pattern": "scales_out_50pct",
                "tier": "S", "min_sol_to_copy": 0.5,
            },
            "KOL_TOXIC_DUMPER": {
                "name": "toxic_dumper",
                "hit_rate": 0.70, "avg_pnl_pct": 0.55,
                "trades_30d": 28, "exit_pattern": "dumps_into_followers",
                "tier": "S", "min_sol_to_copy": 0.5,
            },
        },
        "min_tier_to_copy": "A", "min_hit_rate": 0.40,
    }), encoding="utf-8")


def _enriched_token(mint: str) -> TokenInput:
    """Healthy token fact sheet to exercise the analyst (passes all gates)."""
    return TokenInput(
        mint=mint, symbol="MEME", name="Router Demo Token",
        market=MarketData(mcap=300_000, liquidity_usd=60_000, volume_1h=110_000,
                          age_seconds=420),
        activity=ActivityData(volume_5m_usd=14_000, buys_5m=95, sells_5m=55,
                              buy_ratio_5m=0.63),
        holders=HolderData(count=520, top10_pct=0.17),
        contract=ContractData(lp_burned=True),
        wallets=WalletIntel(safety_score=88, smart_wallet_buys=5,
                            kol_wallet_count=3, bundler_wallet_count=0,
                            sniper_wallet_count=3),
        social=SocialData(
            twitter=TwitterData(handle="rtr", followers=6_000, mentions_1h=140,
                                mention_growth_pct=180.0, velocity_tpm=6.0,
                                sentiment="bullish", engagement=4_400),
            telegram=TelegramData(members=2_000, alpha_calls=2),
            kol_count_5m=3,
        ),
    )


async def _decide(graph, ctx: KOLContext, label: str) -> None:
    state = await graph.run(State(context=ctx))
    d = state.output
    print(f"\n[{label}] action={d.action.upper()} confidence={d.confidence}")
    if d.size is not None:
        print(f"  size      : {d.size}")
    if d.scores:
        print(f"  scores    : {d.scores}")
    print(f"  reasons   : {'; '.join(d.reasons[:3])}")  # truncate noise
    if d.flags.get("llm_failed"):
        print("  flags     : llm_failed=True (router exhausted? "
              "neutral verdict used)")
    nodes = " -> ".join(t.node for t in state.trace)
    print(f"  trace     : {nodes}")


# -- main --------------------------------------------------------------------


async def main() -> None:
    router, labels = _build_router()

    with tempfile.TemporaryDirectory(prefix="zetryn-kol-router-") as tmp:
        root = pathlib.Path(tmp)
        _seed_pack(root)
        pack = KnowledgePack.from_dir(root)

        if router is None:
            print("No provider keys found (GROQ_API_KEY[_N] or GEMINI_API_KEY[_N]).\n"
                  "Falling back to rule mode for the demo flow.")
            graph = build_kol_copytrade(pack)
        else:
            print("LLMRouter entries (in failover order):")
            for i, lbl in enumerate(labels, 1):
                print(f"  {i}. {lbl}")
            print(
                "\nHow rotation works:\n"
                "  - Each call checks entry-1's RPM/RPD/TPM/TPD locally.\n"
                "  - If entry-1 is over budget OR returns 429, skip to entry-2.\n"
                "  - If every entry is exhausted, LLMNode's neutral fallback\n"
                "    runs and the Decision is still returned (graph never crashes).\n"
            )
            graph = build_kol_copytrade(
                pack, mode="confirmed", llm_client=router,
            )

        # Three back-to-back calls. Watching the trace + flags shows whether
        # the router stayed on entry-1 or rotated. Compare to
        # `run_kol_copytrade.py` which uses a single client.
        await _decide(
            graph,
            KOLContext(
                event=KOLBuyEvent(
                    wallet="KOL_SMART_ALPHA", mint="M1",
                    sol_amount=2.0, detected_at_ts=1000.0, block_age_seconds=4.0,
                ),
                token=_enriched_token("M1"),
            ),
            "1. Healthy KOL, healthy token — primary entry expected",
        )

        await _decide(
            graph,
            KOLContext(
                event=KOLBuyEvent(
                    wallet="KOL_TOXIC_DUMPER", mint="M2",
                    sol_amount=2.0, detected_at_ts=1100.0, block_age_seconds=4.0,
                ),
                token=_enriched_token("M2"),
            ),
            "2. Toxic KOL — analyst should VETO regardless of which entry serves",
        )

        await _decide(
            graph,
            KOLContext(
                event=KOLBuyEvent(
                    wallet="KOL_SMART_ALPHA", mint="M3",
                    sol_amount=2.0, detected_at_ts=1200.0, block_age_seconds=4.0,
                ),
                token=_enriched_token("M3"),
            ),
            "3. Same healthy signal — useful for spotting rotation if quota hit",
        )

        if router is not None:
            await router.aclose()


if __name__ == "__main__":
    asyncio.run(main())
