"""AI analyst — the single LLM call that drives M8 scanner decisions.

Replaces the rule-heavy chain (momentum / wallet / social / narrative + weighted
aggregate) with a single rich prompt returning a structured ``FullAnalysis``:
per-aspect score + verdict + reasoning, plus a synthesised recommendation.

Design notes:
- One LLM call (not five) — fits free-tier rate limits (see 2026-06-24 pivot doc §3).
- Structured output: ``FullAnalysis`` schema enforced by LLMNode (json_mode + retry).
- Fallback: neutral ``FullAnalysis`` with ``recommendation="skip"`` on LLM failure —
  conservative bias (better skip a gem than buy a rug). The downstream ``finalize``
  node sees ``llm_failed`` and tags the decision accordingly.
- Prompt is built from the full enriched ``TokenInput`` (M7 schema): activity,
  wallet intel, pumpfun curve, twitter sentiment/velocity. The analyst should
  have access to every signal a human analyst would consult.
"""

from __future__ import annotations

from collections.abc import Callable

from trading.schemas import AspectAnalysis, FullAnalysis
from zetryn.core import State
from zetryn.knowledge import KnowledgePack
from zetryn.llm import Message, system, user

_SYSTEM_PROMPT = """You are a senior Solana memecoin analyst working inside an
automated trading agent. For each token you receive a structured fact sheet
(market data, on-chain activity, wallet intelligence, social signals, optionally
pump.fun bonding curve). Your job is to produce a JSON verdict matching the
provided schema.

How to think about each aspect:

SAFETY: Has the contract been de-risked? Bundled supply, dev rug history, mint
or freeze authority still active, honeypot, and high holder concentration are
disqualifying. Burned/locked LP is a plus.

MARKET: Is there real liquidity and volume to support entry and exit? Compare
liquidity_usd, volume_1h, recent activity (volume_5m, txns). Penalise dead
tokens (low activity despite age) and trap tokens (huge social but no liquidity).

WALLETS: Who is actually buying? Smart wallet buys (proven profitable wallets) are
the strongest positive signal in memecoin trading. KOL buys matter. High sniper
counts mean bot-driven launch — exit will be choppy. Bundler counts indicate
coordinated manipulation.

SOCIAL: Real attention vs paid hype. Heavy weight to mention_growth_pct and
velocity (organic momentum), engagement quality, and external sentiment when
present. Penalise dropping growth or bearish sentiment.

SYNTHESIS: Combine the four aspects. Memecoins are noisy — be skeptical by
default. Use these guidelines:
- recommendation="alert" only when multiple aspects are positive AND there are
  no major red flags. Final score >= 0.7.
- recommendation="watch" when interesting but not yet conviction (0.4–0.7).
- recommendation="skip" when uninteresting, dead, or risky (< 0.4).
- If smart_wallet_buys >= 3 AND no safety concerns, lean toward alert even if
  social/narrative are weak — smart money is informed.
- If buy_ratio_5m < 0.4 with meaningful trade count, treat as sell pressure.

Return strictly the JSON schema. Each aspect needs a score, verdict, signals
list (short phrases naming concrete observations), and one-sentence reasoning.
The final reasoning field is your synthesis explaining the recommendation."""


def analyst_prompt(state: State) -> list[Message]:
    t = state.context.token
    m, h, c, a, w, s = (
        t.market, t.holders, t.contract, t.activity, t.wallets, t.social
    )
    tw = s.twitter

    facts: list[str] = [
        f"Symbol: {t.symbol}  Name: {t.name}",
        f"Source: {t.source}  Mint: {t.mint[:16]}...",
        f"Age: {m.age_seconds or (m.age_minutes or 0) * 60:.0f}s",
        "",
        "MARKET",
        f"  mcap=${m.mcap:,.0f}  liquidity=${m.liquidity_usd:,.0f}  "
        f"vol_1h=${m.volume_1h:,.0f}  txns_1h={m.txns_1h}  price={m.price}",
        "",
        "ACTIVITY (last 5m)",
        f"  vol_1m=${a.volume_1m_usd:,.0f}  vol_5m=${a.volume_5m_usd:,.0f}",
        f"  txns_1m={a.txns_1m}  txns_5m={a.txns_5m}",
        f"  buys={a.buys_5m}  sells={a.sells_5m}  buy_ratio={a.buy_ratio_5m:.2f}",
        "",
        "HOLDERS",
        f"  count={h.count}  top10={h.top10_pct:.0%}  dev={h.dev_pct:.0%}",
        "",
        "CONTRACT",
        f"  mint_authority={c.mint_authority_active}  freeze_authority={c.freeze_authority_active}",
        f"  honeypot={c.is_honeypot}  bundled_supply={c.bundled_supply}  "
        f"dev_rug_history={c.dev_rug_history}",
        f"  lp_burned={c.lp_burned}  lp_locked={c.lp_locked}",
        "",
        "WALLET INTEL",
        f"  external_safety_score={w.safety_score} (0-100, RugCheck-style)",
        f"  smart_wallet_buys={w.smart_wallet_buys}  smart_wallets_holding={w.smart_wallet_count}",
        f"  kol_count={w.kol_wallet_count}  sniper_count={w.sniper_wallet_count}  "
        f"bundler_count={w.bundler_wallet_count}  whale_count={w.whale_wallet_count}",
        "",
        "SOCIAL",
        f"  twitter @{tw.handle or '?'}: followers={tw.followers}  tweets_1h={tw.tweets_1h}",
        f"  mentions_1h={tw.mentions_1h}  mention_growth_pct={tw.mention_growth_pct:+.0f}%",
        f"  velocity_tpm={tw.velocity_tpm:.1f}  sentiment={tw.sentiment or 'unknown'}  "
        f"engagement={tw.engagement}",
        f"  telegram: members={s.telegram.members}  alpha_calls={s.telegram.alpha_calls}",
        f"  kol_buying_5m={s.kol_count_5m}",
    ]

    if t.pumpfun is not None:
        p = t.pumpfun
        facts += [
            "",
            "PUMP.FUN",
            f"  bonding_curve={p.bonding_curve_pct:.1f}%  creator_buy={p.creator_sol_buy} SOL",
            f"  mayhem_mode={p.is_mayhem_mode}",
        ]

    return [system(_SYSTEM_PROMPT), user("Token fact sheet:\n" + "\n".join(facts))]


def make_analyst_prompt(
    pack: KnowledgePack | None = None,
) -> Callable[[State], list[Message]]:
    """Return a prompt builder that prepends a knowledge pack's system blocks.

    When `pack` is None this behaves exactly like `analyst_prompt`. When a pack
    is provided, every markdown block under `<pack>/system/` is injected as a
    system message *before* the analyst's own instructions, so deployments can
    layer their own playbook on top of the default analyst persona.
    """
    if pack is None:
        return analyst_prompt

    pack_blocks = pack.system_blocks()
    if not pack_blocks:
        return analyst_prompt

    def fn(state: State) -> list[Message]:
        return pack_blocks + analyst_prompt(state)

    return fn


def neutral_analysis(state: State, exc: Exception) -> FullAnalysis:
    """Conservative fallback when the LLM is unavailable.

    Returns a skip recommendation with neutral aspect scores and a reasoning that
    names the underlying error. Better to skip a good token than to buy on
    incomplete analysis.
    """
    neutral = AspectAnalysis(
        score=0.5,
        verdict="neutral",
        signals=["LLM unavailable"],
        reasoning="No verdict — analyst LLM call failed.",
    )
    return FullAnalysis(
        safety=neutral,
        market=neutral,
        wallets=neutral,
        social=neutral,
        final_score=0.0,
        recommendation="skip",
        reasoning=f"LLM unavailable ({type(exc).__name__}); skipping conservatively.",
    )
