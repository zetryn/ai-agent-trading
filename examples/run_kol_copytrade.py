"""Example: KOL Copy-Trade strategy end-to-end.

Simulates a bot's event loop:
  1. A KOL buy event arrives.
  2. Bot enriches the bought mint into a TokenInput (here: hand-built fixture).
  3. Bot builds KOLContext and calls build_kol_copytrade.run(...).
  4. Bot reads Decision and would execute (or not).

Two modes — switch via env var:
  (default)                                  rule mode, sub-ms, no LLM call
  ZETRYN_KOL_USE_GROQ=1                      confirmed mode with real Groq LLM
                                             analyst veto + size_multiplier
  ZETRYN_GROQ_MODEL=llama-3.3-70b-versatile  optional, default shown

The confirmed-mode path is what makes "AI Agent" in the brand
non-empty for the copy-trade strategy: the LLM sees the full fact
sheet AFTER the rules approved, and can veto qualitatively or scale
size up/down based on observed confluence.
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
from zetryn.llm import GROQ_BASE_URL, OpenAICompatibleClient, ProviderConfig


def _seed_pack(root: pathlib.Path) -> None:
    """Bot writes a kol_whitelist.json into its KnowledgePack.

    Three KOL profiles with deliberately contrasting `exit_pattern` values
    so the analyst has a real qualitative signal to act on:
      - KOL_SMART_ALPHA   — S-tier, scales_out_50pct (clean exit)
      - KOL_DECENT_BETA   — A-tier, mixed
      - KOL_TOXIC_DUMPER  — S-tier hit-rate BUT dumps_into_followers
                             (the analyst should catch this even when rules
                              approve)
    """
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "kol_whitelist.json").write_text(json.dumps({
        "wallets": {
            "KOL_SMART_ALPHA": {
                "name": "smart_money_alpha",
                "hit_rate": 0.65,
                "avg_pnl_pct": 0.45,
                "trades_30d": 31,
                "exit_pattern": "scales_out_50pct",
                "tier": "S",
                "min_sol_to_copy": 0.5,
            },
            "KOL_DECENT_BETA": {
                "name": "decent_kol_beta",
                "hit_rate": 0.50,
                "avg_pnl_pct": 0.22,
                "trades_30d": 18,
                "exit_pattern": "mixed",
                "tier": "A",
                "min_sol_to_copy": 0.3,
            },
            "KOL_TOXIC_DUMPER": {
                "name": "toxic_dumper",
                "hit_rate": 0.70,                       # rule says: looks great
                "avg_pnl_pct": 0.55,
                "trades_30d": 28,
                "exit_pattern": "dumps_into_followers",  # qualitative red flag
                "tier": "S",
                "min_sol_to_copy": 0.5,
            },
        },
        "min_tier_to_copy": "A",
        "min_hit_rate": 0.40,
    }), encoding="utf-8")


# -- token fact-sheet builders ---------------------------------------------
#
# Each helper builds a TokenInput tuned for one analyst behavior we want
# to observe. The rule layer approves all of them — the only difference
# is qualitative, which is exactly what we want to exercise.


def _token_perfect_storm(mint: str) -> TokenInput:
    """Confluence on every dimension. Analyst should boost (multiplier ≥ 1.2)."""
    return TokenInput(
        mint=mint, symbol="GEM", name="Gem with Confluence",
        market=MarketData(mcap=400_000, liquidity_usd=80_000, volume_1h=180_000,
                          volume_24h=900_000, age_seconds=420),
        activity=ActivityData(
            volume_5m_usd=22_000, buys_5m=140, sells_5m=60, buy_ratio_5m=0.70,
        ),
        holders=HolderData(count=900, top10_pct=0.15, dev_pct=0.02),
        contract=ContractData(lp_burned=True),
        wallets=WalletIntel(
            safety_score=92, smart_wallet_buys=8, smart_wallet_count=14,
            kol_wallet_count=5, bundler_wallet_count=0, sniper_wallet_count=2,
        ),
        social=SocialData(
            twitter=TwitterData(
                handle="gem_with_confluence", followers=12_000,
                mentions_1h=320, mention_growth_pct=400.0, velocity_tpm=12.5,
                sentiment="bullish", engagement=8_200,
            ),
            telegram=TelegramData(members=3_400, alpha_calls=4),
            kol_count_5m=5,
        ),
    )


def _token_subtle_bundler(mint: str) -> TokenInput:
    """Liquidity + social fine — but two bundlers (below rule cap of 3).
    Analyst should catch this and downgrade size."""
    return TokenInput(
        mint=mint, symbol="BND", name="Bundle Lurking",
        market=MarketData(mcap=180_000, liquidity_usd=35_000, volume_1h=55_000,
                          age_seconds=300),
        activity=ActivityData(
            volume_5m_usd=8_000, buys_5m=70, sells_5m=45, buy_ratio_5m=0.61,
        ),
        holders=HolderData(count=320, top10_pct=0.22),
        contract=ContractData(lp_burned=True),
        wallets=WalletIntel(
            safety_score=78, smart_wallet_buys=3, kol_wallet_count=2,
            bundler_wallet_count=2,  # under rule cap of 3 but visible
            sniper_wallet_count=4,
        ),
        social=SocialData(
            twitter=TwitterData(
                handle="bnd_lurking", followers=2_500,
                mentions_1h=80, mention_growth_pct=90.0, velocity_tpm=4.0,
                sentiment="neutral", engagement=1_800,
            ),
            telegram=TelegramData(members=900, alpha_calls=1),
            kol_count_5m=2,
        ),
    )


def _token_clean_for_toxic_kol(mint: str) -> TokenInput:
    """Token is perfectly clean. The dangerous signal is the KOL itself
    (toxic exit_pattern). Analyst should ideally veto or sharply downgrade."""
    return TokenInput(
        mint=mint, symbol="CLN", name="Clean But Toxic KOL",
        market=MarketData(mcap=300_000, liquidity_usd=60_000, volume_1h=110_000,
                          age_seconds=600),
        activity=ActivityData(
            volume_5m_usd=14_000, buys_5m=95, sells_5m=55, buy_ratio_5m=0.63,
        ),
        holders=HolderData(count=520, top10_pct=0.17),
        contract=ContractData(lp_burned=True),
        wallets=WalletIntel(
            safety_score=88, smart_wallet_buys=5, kol_wallet_count=3,
            bundler_wallet_count=0, sniper_wallet_count=3,
        ),
        social=SocialData(
            twitter=TwitterData(
                handle="cln_token", followers=6_000,
                mentions_1h=140, mention_growth_pct=180.0, velocity_tpm=6.0,
                sentiment="bullish", engagement=4_400,
            ),
            telegram=TelegramData(members=2_000, alpha_calls=2),
            kol_count_5m=3,
        ),
    )


def _token_kol_alone(mint: str) -> TokenInput:
    """A-tier KOL by themself. No smart-money / KOL confluence.
    Analyst should be cautious — modest multiplier."""
    return TokenInput(
        mint=mint, symbol="ALN", name="KOL Alone",
        market=MarketData(mcap=150_000, liquidity_usd=25_000, volume_1h=30_000,
                          age_seconds=240),
        activity=ActivityData(
            volume_5m_usd=4_500, buys_5m=40, sells_5m=30, buy_ratio_5m=0.57,
        ),
        holders=HolderData(count=200, top10_pct=0.20),
        contract=ContractData(lp_burned=True),
        wallets=WalletIntel(
            safety_score=80, smart_wallet_buys=0,   # zero confluence
            kol_wallet_count=0,
            bundler_wallet_count=0, sniper_wallet_count=2,
        ),
        social=SocialData(
            twitter=TwitterData(
                handle="aln_token", followers=1_200,
                mentions_1h=20, mention_growth_pct=15.0, velocity_tpm=1.0,
                sentiment="neutral", engagement=600,
            ),
            telegram=TelegramData(members=300, alpha_calls=0),
            kol_count_5m=0,
        ),
    )


def _token_sniper_heavy(mint: str) -> TokenInput:
    """Everything clean except many snipers (under rule cap of 10).
    Bot-driven launch — analyst should downgrade for choppy exit risk."""
    return TokenInput(
        mint=mint, symbol="SNP", name="Sniper Frenzy",
        market=MarketData(mcap=220_000, liquidity_usd=45_000, volume_1h=70_000,
                          age_seconds=200),
        activity=ActivityData(
            volume_5m_usd=12_000, buys_5m=110, sells_5m=80, buy_ratio_5m=0.58,
        ),
        holders=HolderData(count=180, top10_pct=0.25),
        contract=ContractData(lp_burned=True),
        wallets=WalletIntel(
            safety_score=82, smart_wallet_buys=4, kol_wallet_count=3,
            bundler_wallet_count=0,
            sniper_wallet_count=8,  # under cap (10) but suspiciously high
        ),
        social=SocialData(
            twitter=TwitterData(
                handle="snp_token", followers=3_500,
                mentions_1h=110, mention_growth_pct=150.0, velocity_tpm=5.5,
                sentiment="bullish", engagement=2_800,
            ),
            telegram=TelegramData(members=1_400, alpha_calls=2),
            kol_count_5m=3,
        ),
    )


def _token_social_hype_no_substance(mint: str) -> TokenInput:
    """Twitter explosion but on-chain confluence is empty.
    Classic 'all talk' pattern — analyst should downgrade sharply."""
    return TokenInput(
        mint=mint, symbol="HYP", name="All Talk",
        market=MarketData(mcap=80_000, liquidity_usd=7_500, volume_1h=8_000,
                          age_seconds=420),
        activity=ActivityData(
            volume_5m_usd=1_200, buys_5m=18, sells_5m=14, buy_ratio_5m=0.56,
        ),
        holders=HolderData(count=120, top10_pct=0.28),
        contract=ContractData(lp_burned=False, lp_locked=True),
        wallets=WalletIntel(
            safety_score=70, smart_wallet_buys=0,   # nobody smart on board
            kol_wallet_count=0,
            bundler_wallet_count=0, sniper_wallet_count=1,
        ),
        social=SocialData(
            twitter=TwitterData(
                handle="hyp_token", followers=18_000,   # big audience
                mentions_1h=600,                         # huge buzz
                mention_growth_pct=420.0, velocity_tpm=24.0,
                sentiment="bullish", engagement=9_000,
            ),
            telegram=TelegramData(members=4_500, alpha_calls=3),
            kol_count_5m=0,    # paradox: huge buzz, no KOL actually buying
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
    print(f"  reasons   : {'; '.join(d.reasons)}")
    nodes = " -> ".join(t.node for t in state.trace)
    print(f"  trace     : {nodes}")


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


def _build_groq_client():
    _load_env_file()
    keys = _discover_keys("GROQ_API_KEY")
    if not keys:
        print("WARN: ZETRYN_KOL_USE_GROQ=1 but no GROQ_API_KEY[_N] found. "
              "Falling back to rule mode.")
        return None, None
    model = os.environ.get("ZETRYN_GROQ_MODEL", "llama-3.3-70b-versatile")
    client = OpenAICompatibleClient(ProviderConfig(
        name="groq", base_url=GROQ_BASE_URL, model=model,
        key_envs=keys, timeout_s=30.0,
    ))
    return client, model


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="zetryn-kol-") as tmp:
        root = pathlib.Path(tmp)
        _seed_pack(root)
        pack = KnowledgePack.from_dir(root)

        use_groq = os.environ.get("ZETRYN_KOL_USE_GROQ") == "1"
        llm = None
        if use_groq:
            llm, model = _build_groq_client()
            if llm is not None:
                print(f"Mode: confirmed (LLM analyst via Groq {model})")
                kol_copytrade = build_kol_copytrade(
                    pack, mode="confirmed", llm_client=llm, model=model,
                )
            else:
                print("Mode: rule (Groq fallback)")
                kol_copytrade = build_kol_copytrade(pack)
        else:
            print("Mode: rule (no LLM call). Set ZETRYN_KOL_USE_GROQ=1 to "
                  "try confirmed mode with real Groq.")
            kol_copytrade = build_kol_copytrade(pack)

        def _ev(wallet: str, mint: str, ts: float = 1000.0,
                sol: float = 2.0, age: float = 4.0) -> KOLBuyEvent:
            return KOLBuyEvent(
                wallet=wallet, mint=mint, sol_amount=sol,
                detected_at_ts=ts, block_age_seconds=age,
            )

        # ── PART 1: rule-layer rejections (cheap, prove the gates work) ──
        print("\n" + "=" * 78)
        print("PART 1 — rule-layer rejections (no LLM call expected)")
        print("=" * 78)

        bad_token = _token_perfect_storm("R-HNY")
        bad_token.contract.is_honeypot = True
        await _decide(
            kol_copytrade,
            KOLContext(event=_ev("KOL_SMART_ALPHA", "R-HNY"), token=bad_token),
            "R1. honeypot token (fast_safety abort)",
        )

        await _decide(
            kol_copytrade,
            KOLContext(event=_ev("KOL_UNKNOWN", "R-UNK"),
                       token=_token_perfect_storm("R-UNK")),
            "R2. unknown KOL wallet (kol_quality skip)",
        )

        await _decide(
            kol_copytrade,
            KOLContext(event=_ev("KOL_SMART_ALPHA", "R-STALE", age=60.0),
                       token=_token_perfect_storm("R-STALE")),
            "R3. signal too stale (kol_quality skip)",
        )

        # ── PART 2: analyst behavior — six contrasting cases ──
        # Each one passes the rule gates so the LLM analyst (in confirmed mode)
        # is what differentiates the outcomes. In rule mode, all six produce
        # the same size — that's the point: see how the LLM changes things.
        print("\n" + "=" * 78)
        print("PART 2 — analyst behavior (each case passes rules; in confirmed")
        print("         mode the LLM verdict differentiates the size / approval)")
        print("=" * 78)

        await _decide(
            kol_copytrade,
            KOLContext(event=_ev("KOL_SMART_ALPHA", "A-STORM"),
                       token=_token_perfect_storm("A-STORM")),
            "A. Perfect Storm — S-tier KOL + smart buys + KOL confluence + "
            "strong social.  Expect: analyst BOOSTS size (multiplier >= 1.0)",
        )

        await _decide(
            kol_copytrade,
            KOLContext(event=_ev("KOL_SMART_ALPHA", "B-BND"),
                       token=_token_subtle_bundler("B-BND")),
            "B. Subtle Bundler — 2 bundlers (under rule cap of 3).  "
            "Expect: analyst NOTICES sub-threshold bundler and reduces size",
        )

        await _decide(
            kol_copytrade,
            KOLContext(event=_ev("KOL_TOXIC_DUMPER", "C-TOX"),
                       token=_token_clean_for_toxic_kol("C-TOX")),
            "C. Toxic KOL pattern — token is clean BUT KOL exit_pattern is "
            "'dumps_into_followers'.  Expect: analyst VETOES or sharply downgrades",
        )

        await _decide(
            kol_copytrade,
            KOLContext(event=_ev("KOL_DECENT_BETA", "D-ALN", sol=1.0),
                       token=_token_kol_alone("D-ALN")),
            "D. KOL alone — no smart-money / KOL confluence, weak social.  "
            "Expect: analyst CAUTIOUS, multiplier well below 1.0",
        )

        await _decide(
            kol_copytrade,
            KOLContext(event=_ev("KOL_SMART_ALPHA", "E-SNP"),
                       token=_token_sniper_heavy("E-SNP")),
            "E. Sniper-heavy launch — 8 snipers (under cap of 10).  "
            "Expect: analyst WARY of bot-driven launch, multiplier < 1.0",
        )

        await _decide(
            kol_copytrade,
            KOLContext(event=_ev("KOL_DECENT_BETA", "F-HYP", sol=0.5),
                       token=_token_social_hype_no_substance("F-HYP")),
            "F. Social hype, no on-chain confluence — big Twitter buzz but "
            "0 smart buys / 0 KOL.  Expect: analyst SCEPTICAL, sharp downgrade",
        )

        if llm is not None:
            await llm.aclose()


if __name__ == "__main__":
    asyncio.run(main())
