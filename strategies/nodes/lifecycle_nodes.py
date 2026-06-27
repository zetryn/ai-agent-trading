"""Nodes for the Position Lifecycle Helpers strategy (v0.13.0 / PL1).

First position-management agent. Rule gates evaluate hard exits + TP ladder
deterministically. Optional LLM in llm/hybrid mode decides between
hold / take_profit / scale_out / exit_full INSIDE the safe envelope
(emergency / hard SL / time stop already cleared by deterministic gates).

Design choice: unlike entry agents, hard exits (emergency, stop_loss,
time_stop) ALWAYS fire deterministically — the LLM cannot override them.
Cost of being wrong on an open position is much higher than on entry.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from trading.schemas import (
    AuditVerdict,
    Decision,
    LifecycleVerdict,
)
from zetryn.core import Command, State
from zetryn.knowledge import KnowledgePack
from zetryn.llm import LLMClient, Message, system, user
from zetryn.llm.structured import structured_complete


def _latency_ms(state: State) -> float:
    return round(sum(t.duration_ms for t in state.trace), 4)


def _decision(
    state: State,
    action: str,
    *,
    size: float | None,
    reasons: list[str],
    confidence: float = 1.0,
    flags: dict[str, bool] | None = None,
) -> Decision:
    return Decision(
        action=action,
        confidence=confidence,
        size=size,
        reasons=reasons,
        flags=flags or {"rug_risk": False, "llm_failed": False},
        meta={"run_id": state.run_id, "latency_ms": _latency_ms(state)},
    )


def _hard_short_circuit_target(state: State) -> str:
    """Where a HARD-exit gate (emergency/SL/time) jumps to after emitting.

    hybrid_audit → audit_dispatch (so even hard exits get audited)
    everything else → __end__ (skip LLM in llm/hybrid; finish in rule)
    """
    return (
        "audit_dispatch"
        if state.context.config.decision_mode == "hybrid_audit"
        else "__end__"
    )


def _hard_emit(state: State, action: str, **kwargs) -> Command:
    """Hard exits short-circuit out of the deterministic chain.

    Used by emergency_exit, hard_stop_loss, time_stop — they must bypass
    LLM (in llm/hybrid mode) and bypass the rest of the rule chain
    (in rule/hybrid_audit mode).
    """
    state.output = _decision(state, action, **kwargs)
    return Command(goto=_hard_short_circuit_target(state))


def _soft_emit(state: State, action: str, **kwargs) -> None:
    """Soft exits fall through to the next gate in the chain.

    Used by trailing_stop, tp_ladder — subsequent gates check
    ``state.output is not None`` and skip. The chain ends at rule_hold,
    which routes via static edges to audit_dispatch | END.
    """
    state.output = _decision(state, action, **kwargs)
    return None


# -- rule gates --------------------------------------------------------------


def emergency_exit(state: State) -> Command | None:
    """Force `exit_full` if the contract becomes dangerous after entry.

    Hard exit — short-circuits the chain (skips LLM in llm/hybrid; routes
    to audit_dispatch in hybrid_audit).
    """
    c = state.context.token.contract
    p = state.context.position
    if c.is_dangerous:
        return _hard_emit(
            state,
            "exit_full",
            size=p.current_size,
            reasons=[
                "emergency_exit: contract turned dangerous post-entry",
                "rug_signal: " + (", ".join(c.notes) or "rug risk"),
            ],
            flags={"rug_risk": True, "llm_failed": False, "emergency": True},
        )
    return None


def hard_stop_loss(state: State) -> Command | None:
    """Hard SL: `pnl_pct ≤ stop_loss_pct` → exit_full (hard exit, short-circuits)."""
    if state.output is not None:
        return None
    p = state.context.position
    cfg = state.context.config
    if p.pnl_pct <= cfg.stop_loss_pct:
        return _hard_emit(
            state,
            "exit_full",
            size=p.current_size,
            reasons=[
                f"hard_stop_loss: pnl {p.pnl_pct:+.1%} <= {cfg.stop_loss_pct:+.1%}"
            ],
        )
    return None


def time_stop(state: State) -> Command | None:
    """Time stop: `holding_seconds ≥ max_hold_seconds` → exit_full (hard exit)."""
    if state.output is not None:
        return None
    p = state.context.position
    cfg = state.context.config
    if p.holding_seconds >= cfg.max_hold_seconds:
        return _hard_emit(
            state,
            "exit_full",
            size=p.current_size,
            reasons=[
                f"time_stop: held {p.holding_seconds:.0f}s >= "
                f"max {cfg.max_hold_seconds:.0f}s"
            ],
        )
    return None


def trailing_stop(state: State) -> None:
    """Trailing drawdown stop — soft exit, falls through to rule_hold.

    Arms only after `peak_pnl_pct >= trailing_arms_at_pnl_pct`. Once armed,
    fires `exit_full` on drawdown threshold.
    """
    if state.output is not None:
        return None
    p = state.context.position
    cfg = state.context.config
    if p.peak_pnl_pct < cfg.trailing_arms_at_pnl_pct:
        return None
    if p.drawdown_from_peak_pct >= cfg.trailing_drawdown_pct:
        _soft_emit(
            state,
            "exit_full",
            size=p.current_size,
            reasons=[
                f"trailing_stop: drawdown {p.drawdown_from_peak_pct:.0%} >= "
                f"{cfg.trailing_drawdown_pct:.0%} from peak {p.peak_pnl_pct:+.0%}"
            ],
        )
    return None


def tp_ladder(state: State) -> None:
    """Take-profit ladder — soft exit, falls through to rule_hold.

    Sorted rungs `(pnl_threshold, fraction)`. Skips rungs already hit
    (from `partial_exits`). Fires lowest un-hit rung whose threshold is
    crossed. Final rung → `exit_full` (sells 100% remaining).
    """
    if state.output is not None:
        return None
    p = state.context.position
    cfg = state.context.config
    if not cfg.tp_ladder:
        return None

    sorted_ladder = sorted(cfg.tp_ladder, key=lambda r: r[0])
    hit_thresholds = {round(pe.sold_at_pnl_pct, 6) for pe in p.partial_exits}

    for idx, (threshold, fraction) in enumerate(sorted_ladder):
        if round(threshold, 6) in hit_thresholds:
            continue
        if p.pnl_pct < threshold:
            return None
        sell_size = max(0.0, min(fraction * p.current_size, p.current_size))
        if sell_size < cfg.min_sell_size:
            _soft_emit(
                state,
                "hold",
                size=None,
                reasons=[
                    f"tp_ladder: rung +{threshold:+.0%} would sell {sell_size:.4f} "
                    f"< min_sell_size {cfg.min_sell_size}; holding"
                ],
                confidence=0.5,
            )
            return None
        is_final = idx == len(sorted_ladder) - 1 or fraction >= 1.0
        action = "exit_full" if is_final else "take_profit" if idx == 0 else "scale_out"
        _soft_emit(
            state,
            action,
            size=round(sell_size, 6),
            reasons=[
                f"tp_ladder rung +{threshold:+.0%}: sell {fraction:.0%} of current "
                f"= {sell_size:.4f}",
                f"current pnl {p.pnl_pct:+.1%}",
            ],
        )
        return None
    return None


def rule_hold(state: State) -> None:
    """Default fall-through. Emits `hold` only if no earlier gate emitted."""
    if state.output is not None:
        return None
    p = state.context.position
    state.output = Decision(
        action="hold",
        confidence=0.5,
        size=None,
        reasons=[
            f"hold: pnl {p.pnl_pct:+.1%}, holding {p.holding_seconds:.0f}s, "
            f"no gate triggered"
        ],
        flags={"rug_risk": False, "llm_failed": False},
        meta={"run_id": state.run_id, "latency_ms": _latency_ms(state)},
    )


# -- LLM-decide / hybrid path ------------------------------------------------


_LIFECYCLE_LESSONS_HEADER = (
    "LESSONS from recent position-lifecycle outcomes — use these to avoid "
    "repeating losing exits. The agent ran on the same data sources and "
    "these are real outcomes:"
)


def _lessons_block(state: State) -> Message | None:
    text = state.scratch.get("lessons_text")
    if not text or not isinstance(text, str):
        return None
    return system(f"{_LIFECYCLE_LESSONS_HEADER}\n\n{text}")


def _facts(state: State) -> str:
    p = state.context.position
    cfg = state.context.config
    t = state.context.token
    m, h, w = t.market, t.holders, t.wallets

    rungs_hit = [round(pe.sold_at_pnl_pct, 4) for pe in p.partial_exits]
    ladder_lines = []
    for threshold, fraction in sorted(cfg.tp_ladder, key=lambda r: r[0]):
        hit = round(threshold, 4) in {round(x, 4) for x in rungs_hit}
        ladder_lines.append(
            f"  +{threshold:.0%} sell {fraction:.0%}{'  [HIT]' if hit else ''}"
        )

    return (
        f"POSITION\n"
        f"  pnl={p.pnl_pct:+.1%}  peak={p.peak_pnl_pct:+.1%}  "
        f"drawdown_from_peak={p.drawdown_from_peak_pct:.0%}\n"
        f"  held={p.holding_seconds:.0f}s  current_size={p.current_size:.4f} "
        f"(entry={p.entry_size:.4f})\n"
        f"TP LADDER\n" + "\n".join(ladder_lines) + "\n"
        f"TOKEN snapshot\n"
        f"  mcap=${m.mcap:,.0f}  liq=${m.liquidity_usd:,.0f}  "
        f"vol_1h=${m.volume_1h:,.0f}\n"
        f"  holders: count={h.count} top10={h.top10_pct:.0%}\n"
        f"  wallets: smart_buys={w.smart_wallet_buys} "
        f"snipers={w.sniper_wallet_count} bundlers={w.bundler_wallet_count}"
    )


def lifecycle_prompt(state: State) -> list[Message]:
    messages: list[Message] = [
        system(
            "You are a Solana memecoin position-lifecycle decider. The position "
            "is already open. Hard exit gates (emergency, hard stop_loss, time "
            "stop) have ALREADY been checked by the rule layer — they did not "
            "trigger. You are deciding inside the safe envelope:\n"
            "  hold        — keep the position\n"
            "  take_profit — sell at first ladder rung (early profit-taking)\n"
            "  scale_out   — sell partial at later rung\n"
            "  exit_full   — preemptive full exit (smart wallets selling, "
            "                structure degrading, etc.)\n"
            "size_pct = fraction of CURRENT position to sell (0 for hold)."
        ),
    ]
    lessons = _lessons_block(state)
    if lessons is not None:
        messages.append(lessons)
    messages.append(user("Fact sheet:\n" + _facts(state)))
    return messages


def make_lifecycle_prompt(
    pack: KnowledgePack | None = None,
) -> Callable[[State], list[Message]]:
    if pack is None:
        return lifecycle_prompt
    pack_blocks = pack.system_blocks()
    if not pack_blocks:
        return lifecycle_prompt

    def fn(state: State) -> list[Message]:
        return pack_blocks + lifecycle_prompt(state)

    return fn


def lifecycle_result(model: LifecycleVerdict, state: State) -> Decision:
    p = state.context.position
    cfg = state.context.config
    size = max(0.0, min(model.size_pct * p.current_size, p.current_size))
    if size < cfg.min_sell_size and model.action != "hold":
        # Demote to hold if the sell is smaller than the safety floor.
        return Decision(
            action="hold",
            confidence=model.confidence,
            size=None,
            reasons=[
                f"LLM picked {model.action} size_pct {model.size_pct:.0%} "
                f"= {size:.4f} < min_sell_size {cfg.min_sell_size}; demoted to hold",
                f"LLM reasoning: {model.reasoning}",
            ],
            flags={"rug_risk": False, "llm_failed": False},
            meta={"run_id": state.run_id, "latency_ms": _latency_ms(state)},
        )
    return Decision(
        action=model.action,
        confidence=model.confidence,
        size=round(size, 6) if model.action != "hold" else None,
        reasons=[f"LLM: {model.reasoning}"]
        + [f"concern: {c}" for c in model.concerns],
        flags={"rug_risk": False, "llm_failed": False},
        meta={"run_id": state.run_id, "latency_ms": _latency_ms(state)},
    )


def lifecycle_guardrail(decision: Decision | None, state: State) -> Decision:
    """Hybrid mode guardrail.

    Deterministic exits ALWAYS win — LLM cannot hold past a hard SL, time
    stop, or emergency. Also caps sell size at `current_size`.
    """
    p = state.context.position
    cfg = state.context.config
    t = state.context.token

    if decision is None:
        # LLM unavailable → conservative hold (let rule path handle exits)
        decision = Decision(
            action="hold",
            confidence=0.0,
            reasons=["LLM unavailable; conservative hold"],
            flags={"rug_risk": False, "llm_failed": True},
            meta={"run_id": state.run_id, "latency_ms": _latency_ms(state)},
        )

    # Hard rails — LLM cannot escape these.
    if t.contract.is_dangerous:
        decision.action = "exit_full"
        decision.size = p.current_size
        decision.flags["rug_risk"] = True
        decision.reasons.append("guardrail: forced exit_full on emergency rug")
    elif p.pnl_pct <= cfg.stop_loss_pct:
        decision.action = "exit_full"
        decision.size = p.current_size
        decision.reasons.append("guardrail: forced exit_full on hard stop_loss")
    elif p.holding_seconds >= cfg.max_hold_seconds:
        decision.action = "exit_full"
        decision.size = p.current_size
        decision.reasons.append("guardrail: forced exit_full on time_stop")

    if decision.size is not None and decision.size > p.current_size:
        decision.size = p.current_size
        decision.reasons.append(f"guardrail: size capped at current_size {p.current_size}")
    return decision


# -- hybrid_audit ------------------------------------------------------------


def _audit_prompt(state: State) -> list[Message]:
    d: Decision = state.output
    return [
        system(
            "You are a position-lifecycle auditor. A rule-based bot just made "
            "a hold/TP/scale-out/exit decision on an open Solana memecoin "
            "position. Do you AGREE with the action and size? Return JSON: "
            "{agrees, confidence, concerns[], reasoning}. Be honest — this "
            "audit informs future rule tuning, not this trade."
        ),
        user(
            f"DECISION: action={d.action} size={d.size} confidence={d.confidence}\n"
            f"Reasons: {d.reasons}\n\n"
            + _facts(state)
        ),
    ]


async def _run_audit(
    client: LLMClient, messages: list[Message], model: str | None
) -> AuditVerdict:
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
    pack_blocks: list[Message] = (
        knowledge_pack.system_blocks() if knowledge_pack is not None else []
    )

    def audit_dispatch(state: State) -> None:
        # Audit any non-hold lifecycle action.
        if state.output is None or state.output.action == "hold":
            state.scratch["audit_skipped"] = True
            return
        base = _audit_prompt(state)
        messages = pack_blocks + base if pack_blocks else base
        task = asyncio.create_task(_run_audit(client, messages, model))
        state.scratch["audit_task"] = task
        state.output.flags["audit_dispatched"] = True

    audit_dispatch.__name__ = "audit_dispatch"
    return audit_dispatch
