"""KOL Copy-Trade with TIER_SPEED / TIER_QUALITY / TIER_VOLUME router presets.

v0.8.0 ships with three opinionated router preset specs:

  TIER_SPEED   — Cerebras (~2,600 tok/s) → Groq (gpt-oss-20b) → Groq (llama 70b)
                 Fastest path; ideal for latency-sensitive sniper-style work.

  TIER_QUALITY — SambaNova (Llama 405B) → Gemini (1M context) → Groq (llama 70b)
                 Heaviest reasoning; ideal for scanner / KOL analyst when
                 latency tolerates 1-3s.

  TIER_VOLUME  — OpenRouter (35+ :free models) → Gemini → Groq
                 Highest free-tier daily throughput; ideal for backtests
                 or volume-heavy bot pipelines.

You only need keys for one provider in any tier — `build_tier_entries`
silently skips missing providers so a tier degrades gracefully into
whatever you have configured.

Run:
    cd examples && python run_kol_tier_router.py
    cd examples && ZETRYN_TIER=quality python run_kol_tier_router.py
    cd examples && ZETRYN_TIER=volume  python run_kol_tier_router.py
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
    CEREBRAS_BASE_URL,
    GEMINI_BASE_URL,
    GROQ_BASE_URL,
    NVIDIA_NIM_BASE_URL,
    OPENROUTER_BASE_URL,
    SAMBANOVA_BASE_URL,
    TIER_QUALITY,
    TIER_SPEED,
    TIER_VOLUME,
    LLMClient,
    LLMRouter,
    OpenAICompatibleClient,
    ProviderConfig,
    build_tier_entries,
)

# -- env helpers -----------------------------------------------------------


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


# -- one OpenAICompatibleClient per provider that has keys ----------------


def _build_clients_by_provider() -> dict[str, LLMClient]:
    """Build a client per provider, only for those with keys in env.

    Returns a dict keyed by the provider names used in the tier presets:
    "cerebras" | "groq" | "gemini" | "openrouter" | "sambanova" | "nvidia_nim".
    """
    _load_env_file()
    clients: dict[str, LLMClient] = {}

    def _add(name: str, base_url: str, key_prefix: str, default_model: str) -> None:
        keys = _discover_keys(key_prefix)
        if not keys:
            return
        clients[name] = OpenAICompatibleClient(ProviderConfig(
            name=name, base_url=base_url, model=default_model,
            key_envs=keys, timeout_s=30.0,
        ))

    _add("cerebras",   CEREBRAS_BASE_URL,   "CEREBRAS_API_KEY",   "llama-3.3-70b")
    _add("groq",       GROQ_BASE_URL,       "GROQ_API_KEY",       "openai/gpt-oss-20b")
    _add("gemini",     GEMINI_BASE_URL,     "GEMINI_API_KEY",     "gemini-2.5-flash")
    _add("openrouter", OPENROUTER_BASE_URL, "OPENROUTER_API_KEY", "deepseek/deepseek-r1:free")
    _add("sambanova",  SAMBANOVA_BASE_URL,  "SAMBANOVA_API_KEY",  "Meta-Llama-3.1-405B-Instruct")
    _add("nvidia_nim", NVIDIA_NIM_BASE_URL, "NVIDIA_NIM_API_KEY", "meta/llama-3.3-70b-instruct")

    return clients


# -- pack + token fixtures -------------------------------------------------


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
        },
        "min_tier_to_copy": "A", "min_hit_rate": 0.40,
    }), encoding="utf-8")


def _healthy_token(mint: str) -> TokenInput:
    return TokenInput(
        mint=mint, symbol="MEME", name="Tier Demo",
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
            twitter=TwitterData(handle="x", followers=6_000, mentions_1h=140,
                                mention_growth_pct=180.0, velocity_tpm=6.0,
                                sentiment="bullish", engagement=4_400),
            telegram=TelegramData(members=2_000, alpha_calls=2),
            kol_count_5m=3,
        ),
    )


# -- main ------------------------------------------------------------------


TIER_LOOKUP = {
    "speed":   TIER_SPEED,
    "quality": TIER_QUALITY,
    "volume":  TIER_VOLUME,
}


async def main() -> None:
    tier_name = os.environ.get("ZETRYN_TIER", "speed").lower()
    tier = TIER_LOOKUP.get(tier_name)
    if tier is None:
        raise SystemExit(f"unknown ZETRYN_TIER={tier_name}. "
                         f"Use one of: {list(TIER_LOOKUP)}")
    print(f"Tier: {tier_name.upper()}")
    print("Tier spec (failover order):")
    for i, spec in enumerate(tier, 1):
        print(f"  {i}. {spec.provider}:{spec.model}")

    clients = _build_clients_by_provider()
    if not clients:
        print("\nNo provider keys configured. Add at least one of "
              "CEREBRAS_API_KEY / GROQ_API_KEY / GEMINI_API_KEY / "
              "OPENROUTER_API_KEY / SAMBANOVA_API_KEY / NVIDIA_NIM_API_KEY.")
        print("Falling back to rule mode.")
        with tempfile.TemporaryDirectory(prefix="zetryn-tier-") as tmp:
            root = pathlib.Path(tmp)
            _seed_pack(root)
            pack = KnowledgePack.from_dir(root)
            graph = build_kol_copytrade(pack)
            state = await graph.run(State(context=KOLContext(
                event=KOLBuyEvent(wallet="KOL_SMART_ALPHA", mint="M",
                                  sol_amount=1.0, detected_at_ts=1000.0,
                                  block_age_seconds=4.0),
                token=_healthy_token("M"),
            )))
            print(f"\nDecision: {state.output.action.upper()} size={state.output.size}")
        return

    entries = build_tier_entries(tier, clients)
    print(f"\nResolved {len(entries)} of {len(tier)} tier specs into router entries:")
    for e in entries:
        print(f"  - {e.name}")

    skipped = len(tier) - len(entries)
    if skipped:
        print(f"  ({skipped} entries skipped due to missing provider keys — graceful degradation)")

    router = LLMRouter(entries)

    with tempfile.TemporaryDirectory(prefix="zetryn-tier-") as tmp:
        root = pathlib.Path(tmp)
        _seed_pack(root)
        pack = KnowledgePack.from_dir(root)

        graph = build_kol_copytrade(pack, mode="confirmed", llm_client=router)
        state = await graph.run(State(context=KOLContext(
            event=KOLBuyEvent(wallet="KOL_SMART_ALPHA", mint="MEME",
                              sol_amount=2.0, detected_at_ts=1000.0,
                              block_age_seconds=4.0),
            token=_healthy_token("MEME"),
        )))
        d = state.output
        print("\n--- Decision ---")
        print(f"  action     : {d.action.upper()}")
        print(f"  size       : {d.size}")
        print(f"  confidence : {d.confidence}")
        print(f"  scores     : {d.scores}")
        if d.reasons:
            for r in d.reasons[:3]:
                print(f"  reason     : {r}")
        print(f"  trace      : {' -> '.join(t.node for t in state.trace)}")

    await router.aclose()


if __name__ == "__main__":
    asyncio.run(main())
