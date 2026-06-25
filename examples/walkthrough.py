"""Transparent walkthrough: INPUT -> PROCESSING -> OUTPUT for every dummy case.

M8 update: the scanner is AI-first. The processing is no longer many small rule
scorers — three hard gates instant-abort obvious junk, then a single LLM
analyst produces a structured FullAnalysis, then a finalize rule applies
guardrails and assembles the Decision.

For each token it prints:
  1) INPUT     — signals the bot pushed in (TokenInput)
  2) PROCESSING — which gate stopped it or the full analyst pipeline
  3) ANALYSIS  — the AI's per-aspect verdict (for tokens that reached the analyst)
  4) OUTPUT    — the final Decision the framework returns to the bot

Defaults to a heuristic stub LLM so no API key is needed. To exercise a
real provider, set environment variables:

    ZETRYN_WALKTHROUGH_USE_GROQ=1        # switch from stub to real Groq
    ZETRYN_GROQ_MODEL=llama-3.3-70b-versatile  # optional, default shown
    ZETRYN_WALKTHROUGH_LIMIT=3           # optional, only run first N tokens
                                           (cheap smoke-test before full 16)
    GROQ_API_KEY_1=...                   # at least one Groq key required
    GROQ_API_KEY_2=...                   # optional, multiple keys = key-pool rotation

Real Groq run on the full 16 tokens is ~12 LLM calls (hard-gate rejects
skip the LLM). At median ~1.5s per call this finishes in roughly 20–30s
on a single key.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from dummy_tokens import DUMMY_TOKENS  # noqa: E402

from strategies import build_scanner  # noqa: E402
from trading import ScannerConfig, TradingContext  # noqa: E402
from zetryn.core import State  # noqa: E402
from zetryn.llm import GROQ_BASE_URL, OpenAICompatibleClient, ProviderConfig  # noqa: E402
from zetryn.llm.types import LLMResult, Message  # noqa: E402

# --- heuristic stub LLM ----------------------------------------------------


def _grep_int(text: str, key: str, default: int = 0) -> int:
    m = re.search(rf"{key}=(-?\d+)", text)
    return int(m.group(1)) if m else default


def _grep_float(text: str, key: str, default: float = 0.0) -> float:
    m = re.search(rf"{key}=(-?\d+\.?\d*)", text)
    return float(m.group(1)) if m else default


class _StubLLM:
    """Offline stub that produces a heuristic FullAnalysis from the fact sheet."""

    async def complete(self, messages: list[Message], **kw) -> LLMResult:
        text = messages[-1]["content"]

        smart_buys = _grep_int(text, "smart_wallet_buys")
        sniper = _grep_int(text, "sniper_count")
        bundler = _grep_int(text, "bundler_count")
        safety_score = _grep_float(text, "external_safety_score")
        buy_ratio = _grep_float(text, "buy_ratio", default=0.5)
        mention_growth = _grep_float(text, "mention_growth_pct")
        sentiment_match = re.search(r"sentiment=(\w+)", text)
        sentiment = sentiment_match.group(1) if sentiment_match else "unknown"

        # SAFETY aspect
        if "bundled_supply=True" in text or "dev_rug_history=True" in text:
            safety_score_v = 0.05
            safety_verdict = "negative"
            safety_signals = [
                "bundled supply" if "bundled_supply=True" in text else "dev rug history"
            ]
        elif safety_score >= 70:
            safety_score_v = 0.85
            safety_verdict = "positive"
            safety_signals = [f"external safety {safety_score:.0f}"]
        elif safety_score >= 40:
            safety_score_v = 0.55
            safety_verdict = "neutral"
            safety_signals = ["mid external safety"]
        else:
            safety_score_v = 0.25
            safety_verdict = "negative"
            safety_signals = ["weak external safety"]

        # MARKET aspect (relies on activity)
        vol_5m = _grep_float(text, r"vol_5m=\$")
        if vol_5m >= 20_000 and buy_ratio >= 0.55:
            market_score = 0.85
            market_verdict = "positive"
            market_signals = [f"strong 5m vol ${vol_5m:,.0f}", f"buy ratio {buy_ratio:.2f}"]
        elif vol_5m >= 5_000:
            market_score = 0.6
            market_verdict = "neutral"
            market_signals = ["modest activity"]
        else:
            market_score = 0.35
            market_verdict = "negative"
            market_signals = ["thin activity"]

        # WALLETS aspect
        if smart_buys >= 5:
            wallet_score = 0.9
            wallet_verdict = "positive"
            wallet_signals = [f"{smart_buys} smart-money buys", "alpha pattern"]
        elif smart_buys >= 2:
            wallet_score = 0.65
            wallet_verdict = "positive"
            wallet_signals = [f"{smart_buys} smart-money buys"]
        elif bundler > 3:
            wallet_score = 0.1
            wallet_verdict = "negative"
            wallet_signals = [f"{bundler} bundlers — coordinated launch"]
        elif sniper > 10:
            wallet_score = 0.35
            wallet_verdict = "negative"
            wallet_signals = [f"{sniper} snipers — bot-heavy"]
        else:
            wallet_score = 0.45
            wallet_verdict = "neutral"
            wallet_signals = ["no notable wallet activity"]

        # SOCIAL aspect
        if sentiment == "bullish" and mention_growth > 100:
            social_score = 0.85
            social_verdict = "positive"
            social_signals = [
                f"mention growth +{mention_growth:.0f}%",
                "bullish sentiment",
            ]
        elif sentiment == "bearish" or mention_growth < -10:
            social_score = 0.2
            social_verdict = "negative"
            social_signals = ["mention decay / bearish sentiment"]
        elif "mentions_1h=0" in text:
            social_score = 0.3
            social_verdict = "neutral"
            social_signals = ["no social activity"]
        else:
            social_score = 0.5
            social_verdict = "neutral"
            social_signals = ["modest social presence"]

        # SYNTHESIS
        weights = {"safety": 0.30, "market": 0.25, "wallets": 0.25, "social": 0.20}
        final = (
            safety_score_v * weights["safety"]
            + market_score * weights["market"]
            + wallet_score * weights["wallets"]
            + social_score * weights["social"]
        )
        # smart money override
        if smart_buys >= 3 and safety_score_v >= 0.5:
            final = max(final, 0.75)

        if final >= 0.70:
            rec = "alert"
        elif final >= 0.40:
            rec = "watch"
        else:
            rec = "skip"

        reasoning_bits = []
        if smart_buys >= 3:
            reasoning_bits.append(f"{smart_buys} smart-money buys")
        if sentiment == "bullish" and mention_growth > 100:
            reasoning_bits.append(f"social momentum +{mention_growth:.0f}%")
        if bundler > 3:
            reasoning_bits.append("bundle attack visible")
        if sniper > 10:
            reasoning_bits.append("bot-dominated launch")
        reasoning = (
            "Heuristic stub synthesis. " + "; ".join(reasoning_bits)
            if reasoning_bits
            else "No standout signals; defaulting to mid-band assessment."
        )

        payload = {
            "safety": {
                "score": safety_score_v,
                "verdict": safety_verdict,
                "signals": safety_signals,
                "reasoning": "stub heuristic",
            },
            "market": {
                "score": market_score,
                "verdict": market_verdict,
                "signals": market_signals,
                "reasoning": "stub heuristic",
            },
            "wallets": {
                "score": wallet_score,
                "verdict": wallet_verdict,
                "signals": wallet_signals,
                "reasoning": "stub heuristic",
            },
            "social": {
                "score": social_score,
                "verdict": social_verdict,
                "signals": social_signals,
                "reasoning": "stub heuristic",
            },
            "final_score": round(final, 3),
            "recommendation": rec,
            "reasoning": reasoning,
        }
        return LLMResult(text=json.dumps(payload), model="stub", latency_ms=1.0)

    async def aclose(self) -> None:
        pass


# --- printers --------------------------------------------------------------


def print_input(token) -> None:
    m, h, c, s, w, a = (
        token.market, token.holders, token.contract, token.social,
        token.wallets, token.activity,
    )
    tw = s.twitter
    print("  INPUT (signals pushed by the bot):")
    print(f"    mint      : {token.mint[:16]}...  symbol={token.symbol}  name={token.name}"
          f"  source={token.source}")
    print(f"    market    : mcap=${m.mcap:,.0f}  liq=${m.liquidity_usd:,.0f}  "
          f"vol1h=${m.volume_1h:,.0f}  txns1h={m.txns_1h}  "
          f"age={m.age_seconds or (m.age_minutes or 0) * 60:.0f}s")
    print(f"    activity  : vol5m=${a.volume_5m_usd:,.0f}  buys5m={a.buys_5m}  "
          f"sells5m={a.sells_5m}  buy_ratio={a.buy_ratio_5m:.2f}")
    print(f"    holders   : count={h.count}  top10={h.top10_pct:.0%}  dev={h.dev_pct:.0%}")
    print(
        f"    contract  : mint_auth={c.mint_authority_active}  "
        f"freeze={c.freeze_authority_active}  "
        f"honeypot={c.is_honeypot}  bundled={c.bundled_supply}  "
        f"dev_rug={c.dev_rug_history}  "
        f"lp_burned={c.lp_burned}  lp_locked={c.lp_locked}"
    )
    print(f"    wallets   : safety={w.safety_score}  smart_buys={w.smart_wallet_buys}  "
          f"kol={w.kol_wallet_count}  snipers={w.sniper_wallet_count}  "
          f"bundlers={w.bundler_wallet_count}  whales={w.whale_wallet_count}")
    if token.pumpfun is not None:
        p = token.pumpfun
        print(f"    pumpfun   : curve={p.bonding_curve_pct:.0f}%  "
              f"creator_buy={p.creator_sol_buy} SOL  mayhem={p.is_mayhem_mode}")
    print(f"    social    : tw_followers={tw.followers}  mentions1h={tw.mentions_1h}  "
          f"growth={tw.mention_growth_pct:+.0f}%  sentiment={tw.sentiment or '-'}  "
          f"velocity={tw.velocity_tpm:.1f}tpm  tg_members={s.telegram.members}  "
          f"kol5m={s.kol_count_5m}")


def print_processing(state: State) -> None:
    print("  PROCESSING (path through the graph):")
    for step in state.trace:
        print(f"    node {step.node:14} ({step.duration_ms:.3f}ms) -> next={step.next}")


def print_analysis(decision) -> None:
    a = decision.analysis
    if a is None:
        return
    print("  ANALYSIS (per-aspect AI verdict):")
    for name in ("safety", "market", "wallets", "social"):
        aspect = getattr(a, name)
        signals = ", ".join(aspect.signals) if aspect.signals else "—"
        print(f"    {name:8} {aspect.verdict:8} score={aspect.score:.2f}  signals=[{signals}]")
    print(f"    synthesis: {a.reasoning}")


def print_output(decision) -> None:
    print("  OUTPUT (Decision returned to the bot):")
    print(f"    action     : {decision.action.upper()}")
    print(f"    confidence : {decision.confidence}")
    print(f"    scores     : {decision.scores}")
    print(f"    reasons    : {decision.reasons}")
    print(f"    flags      : {decision.flags}")
    print(f"    latency_ms : {decision.meta.get('latency_ms')}")


# --- LLM wiring ------------------------------------------------------------


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


def _build_llm():
    """Return (llm_client, label, has_aclose).

    Stub by default. Set ZETRYN_WALKTHROUGH_USE_GROQ=1 to swap in a real
    Groq client built from GROQ_API_KEY[_N] env vars.
    """
    if os.environ.get("ZETRYN_WALKTHROUGH_USE_GROQ") != "1":
        return _StubLLM(), "stub (offline heuristic)", False

    _load_env_file()
    keys = _discover_keys("GROQ_API_KEY")
    if not keys:
        print("WARN: ZETRYN_WALKTHROUGH_USE_GROQ=1 but no GROQ_API_KEY[_N] "
              "found in env or .env — falling back to stub.")
        return _StubLLM(), "stub (no Groq key found)", False

    model = os.environ.get("ZETRYN_GROQ_MODEL", "llama-3.3-70b-versatile")
    client = OpenAICompatibleClient(
        ProviderConfig(
            name="groq", base_url=GROQ_BASE_URL, model=model,
            key_envs=keys, timeout_s=30.0,
        )
    )
    return client, f"real Groq | {model} | keys×{len(keys)}", True


# --- main ------------------------------------------------------------------


async def main() -> None:
    llm, label, has_aclose = _build_llm()
    print(f"LLM: {label}")
    scanner = build_scanner(llm)
    config = ScannerConfig()

    items = list(DUMMY_TOKENS.items())
    limit = int(os.environ.get("ZETRYN_WALKTHROUGH_LIMIT", "0"))
    if limit > 0:
        items = items[:limit]
        print(f"LIMIT: only running first {limit} of {len(DUMMY_TOKENS)} tokens "
              "(unset ZETRYN_WALKTHROUGH_LIMIT to run all).")

    # Cache the results so we don't pay for a second LLM round just to print the summary.
    runs: list[tuple[str, str, State]] = []

    for key, (case_label, token) in items:
        print("\n" + "=" * 78)
        print(f"CASE: {key}  —  {case_label}")
        print("=" * 78)
        print_input(token)
        state = await scanner.run(State(context=TradingContext(token=token, config=config)))
        print_processing(state)
        print_analysis(state.output)
        print_output(state.output)
        runs.append((key, case_label, state))

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"  {'case':16} {'action':7} {'conf':>6}  path")
    for key, _case_label, state in runs:
        d = state.output
        path = " -> ".join(t.node for t in state.trace)
        print(f"  {key:16} {d.action.upper():7} {d.confidence:>6}  {path}")

    if has_aclose:
        await llm.aclose()


if __name__ == "__main__":
    asyncio.run(main())
