"""Nodes for the auto-snipe agent.

Speed-first: pure-rule gates that can abort in microseconds, plus a sizing node.
Also provides the schema + prompt + guardrail for the optional LLM-decide path,
and the M9 ``audit_dispatch`` node for ``hybrid_audit`` mode (rule decides
instantly, LLM verifies asynchronously without blocking the trading hot path).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from pydantic import BaseModel, Field

from trading.schemas import AuditVerdict, Decision
from zetryn.core import Command, State
from zetryn.knowledge import KnowledgePack
from zetryn.llm import LLMClient, Message, system, user
from zetryn.llm.structured import structured_complete


def _latency_ms(state: State) -> float:
    return round(sum(t.duration_ms for t in state.trace), 4)


# -- pure-rule fast path -----------------------------------------------------


def fast_safety(state: State) -> Command | None:
    """Instant abort on contract danger — the cheapest, most important gate."""
    c = state.context.token.contract
    if c.is_dangerous:
        state.output = Decision(
            action="abort",
            confidence=0.0,
            reasons=["contract unsafe: " + (", ".join(c.notes) or "rug risk")],
            flags={"rug_risk": True, "llm_failed": False},
            meta={"run_id": state.run_id, "latency_ms": _latency_ms(state)},
        )
        return Command(goto="__end__")
    return None


def fast_market(state: State) -> Command | None:
    """Skip if liquidity/volume too thin for a safe entry."""
    m = state.context.token.market
    cfg = state.context.config
    if m.liquidity_usd < cfg.min_liquidity_usd or m.volume_1h < cfg.min_volume_1h:
        state.output = Decision(
            action="skip",
            confidence=0.0,
            reasons=[f"liquidity ${m.liquidity_usd:,.0f} / vol ${m.volume_1h:,.0f} too low"],
            flags={"rug_risk": False, "llm_failed": False},
            meta={"run_id": state.run_id, "latency_ms": _latency_ms(state)},
        )
        return Command(goto="__end__")
    return None


def rule_size_and_buy(state: State) -> None:
    """Deterministic sizing → buy decision (pure-rule fast path)."""
    cfg = state.context.config
    h = state.context.token.holders
    # Scale size down when holders are concentrated; never exceed the hard cap.
    concentration_penalty = max(0.0, h.top10_pct - 0.2)
    size = cfg.base_size * (1.0 - concentration_penalty)
    size = max(0.0, min(size, cfg.max_size))
    state.output = Decision(
        action="buy",
        confidence=0.6,
        size=round(size, 4),
        reasons=["pure-rule entry", f"size {size:.2f} (cap {cfg.max_size})"],
        flags={"rug_risk": False, "llm_failed": False},
        meta={"run_id": state.run_id, "latency_ms": _latency_ms(state)},
    )


# -- LLM-decide / hybrid path ------------------------------------------------


class SnipeDecision(BaseModel):
    """What the LLM is asked to decide for a snipe."""

    action: str = Field(description="one of: buy, skip, abort")
    confidence: float = Field(ge=0, le=1)
    size_pct: float = Field(ge=0, le=1, description="fraction of max_size to deploy")
    reasoning: str = ""


def snipe_prompt(state: State) -> list[Message]:
    t = state.context.token
    return [
        system(
            "You are a fast memecoin snipe decider. Given a token that already passed "
            "safety and liquidity gates, decide buy/skip/abort and a size fraction. "
            "Be decisive but risk-aware."
        ),
        user(
            f"{t.symbol} ({t.name}) mcap=${t.market.mcap:,.0f} "
            f"liq=${t.market.liquidity_usd:,.0f} vol1h=${t.market.volume_1h:,.0f} "
            f"holders={t.holders.count} top10={t.holders.top10_pct:.0%} "
            f"KOL5m={t.social.kol_count_5m}"
        ),
    ]


def make_snipe_prompt(
    pack: KnowledgePack | None = None,
) -> Callable[[State], list[Message]]:
    """Return a snipe prompt builder that prepends a knowledge pack's blocks."""
    if pack is None:
        return snipe_prompt
    pack_blocks = pack.system_blocks()
    if not pack_blocks:
        return snipe_prompt

    def fn(state: State) -> list[Message]:
        return pack_blocks + snipe_prompt(state)

    return fn


def snipe_result(model: SnipeDecision, state: State) -> Decision:
    cfg = state.context.config
    size = max(0.0, min(model.size_pct * cfg.max_size, cfg.max_size))
    return Decision(
        action=model.action if model.action in {"buy", "skip", "abort"} else "skip",
        confidence=model.confidence,
        size=round(size, 4),
        reasons=[f"LLM: {model.reasoning}"],
        flags={"rug_risk": False, "llm_failed": False},
        meta={"run_id": state.run_id, "latency_ms": _latency_ms(state)},
    )


def snipe_guardrail(decision: Decision | None, state: State) -> Decision:
    """Deterministic rails the LLM cannot breach (hybrid mode).

    Forces abort on rug risk, and hard-caps size — rules always win over the LLM.
    """
    cfg = state.context.config
    if decision is None:
        decision = Decision(
            action="skip",
            confidence=0.0,
            reasons=["LLM unavailable; conservative skip"],
            flags={"rug_risk": False, "llm_failed": True},
            meta={"run_id": state.run_id, "latency_ms": _latency_ms(state)},
        )
    if state.context.token.contract.is_dangerous:
        decision.action = "abort"
        decision.size = None
        decision.flags["rug_risk"] = True
        decision.reasons.append("guardrail: forced abort on rug risk")
    if decision.size is not None and decision.size > cfg.max_size:
        decision.size = cfg.max_size
        decision.reasons.append(f"guardrail: size capped at {cfg.max_size}")
    return decision


# -- hybrid_audit: async LLM second-opinion (M9) ----------------------------


def _audit_prompt(state: State) -> list[Message]:
    """Prompt asking the LLM whether it agrees with the rule-based snipe decision."""
    t = state.context.token
    d: Decision = state.output
    return [
        system(
            "You are a memecoin trading auditor. A rule-based sniper has just made a "
            "decision on a token. Your job: do you AGREE with the decision based on "
            "the data? Return JSON: {agrees: bool, confidence: 0..1, concerns: "
            "list of short strings, reasoning: short string}. Be honest — disagree "
            "when warranted. This audit informs future rule tuning, not this trade."
        ),
        user(
            f"DECISION: action={d.action}  size={d.size}  confidence={d.confidence}\n"
            f"Reasons: {d.reasons}\n\n"
            f"TOKEN: {t.symbol} ({t.name}) source={t.source}\n"
            f"market: mcap=${t.market.mcap:,.0f} liq=${t.market.liquidity_usd:,.0f} "
            f"vol1h=${t.market.volume_1h:,.0f} age={t.market.age_seconds or 0:.0f}s\n"
            f"holders: count={t.holders.count} top10={t.holders.top10_pct:.0%} "
            f"dev={t.holders.dev_pct:.0%}\n"
            f"contract: dangerous={t.contract.is_dangerous} "
            f"bundled={t.contract.bundled_supply} rug_history={t.contract.dev_rug_history}\n"
            f"wallets: smart_buys={t.wallets.smart_wallet_buys} "
            f"snipers={t.wallets.sniper_wallet_count} "
            f"bundlers={t.wallets.bundler_wallet_count} "
            f"safety_score={t.wallets.safety_score}\n"
            f"activity 5m: buys={t.activity.buys_5m} sells={t.activity.sells_5m} "
            f"buy_ratio={t.activity.buy_ratio_5m:.2f}"
        ),
    ]


async def _run_audit(
    client: LLMClient, messages: list[Message], model: str | None
) -> AuditVerdict:
    """Background coroutine: call LLM and return parsed AuditVerdict.

    Errors are swallowed into a 'failed' verdict so the background task always
    completes — it must never raise into the event loop and crash the bot.
    """
    try:
        return await structured_complete(client, messages, AuditVerdict, model=model)
    except Exception as exc:  # noqa: BLE001 — bg task must not propagate
        return AuditVerdict(
            agrees=False,
            confidence=0.0,
            concerns=[f"audit_failed: {type(exc).__name__}"],
            reasoning=str(exc)[:200],
        )


def make_audit_dispatch(
    client: LLMClient,
    *,
    model: str | None = None,
    knowledge_pack: KnowledgePack | None = None,
):
    """Build a node function that dispatches the audit task and returns immediately.

    The decision is already in ``state.output`` (set by ``rule_size_and_buy``).
    This node fires a background task that the bot can ``await`` later to get
    the audit verdict (typically write it to ``DecisionLog``). The hot path is
    NOT blocked.

    The task handle is stored in ``state.scratch["audit_task"]``. Calling code
    may also use ``state.scratch["audit_result"]`` if it prefers to await on the
    task and read the parsed verdict.

    When ``knowledge_pack`` is given, its system blocks are prepended to the
    audit prompt so the auditor sees the deployment-specific playbook.
    """
    pack_blocks: list[Message] = (
        knowledge_pack.system_blocks() if knowledge_pack is not None else []
    )

    def audit_dispatch(state: State) -> None:
        # Only audit actual entries — skip / abort decisions are not interesting.
        if state.output is None or state.output.action not in {"buy"}:
            state.scratch["audit_skipped"] = True
            return

        messages = pack_blocks + _audit_prompt(state) if pack_blocks else _audit_prompt(state)
        task = asyncio.create_task(_run_audit(client, messages, model))
        state.scratch["audit_task"] = task
        # Mark decision so observers know an audit is in flight.
        state.output.flags["audit_dispatched"] = True

    audit_dispatch.__name__ = "audit_dispatch"
    return audit_dispatch
