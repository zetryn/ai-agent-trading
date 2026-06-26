"""Sniper × ReflectiveNode integration tests.

The reflective loop on the sniper:
  1. Bot writes outcomes to DecisionLog after each snipe settles.
  2. On the next signal in ``llm`` / ``hybrid`` mode, a ReflectiveNode runs
     between ``fast_market`` and ``snipe_decide``, compiling a lessons_text
     from recent losers.
  3. ``snipe_prompt`` injects the lessons block as an extra system message
     so the LLM conditions on real outcomes.

Reflection is NOT wired into ``rule`` or ``hybrid_audit`` modes — those
have no LLM in the synchronous path (or are explicitly sub-ms). The tests
below verify both the active path and the no-op paths.
"""

from __future__ import annotations

import json

from strategies import SAMPLE_TOKENS, build_sniper
from trading import SniperConfig, TradingContext
from zetryn.core import State
from zetryn.llm.types import LLMResult, Message
from zetryn.memory import DecisionLog, InMemoryStore


def _ctx(mint: str, **cfg) -> TradingContext:
    return TradingContext(token=SAMPLE_TOKENS[mint], config=SniperConfig(**cfg))


class _CapturingLLM:
    """Returns a fixed snipe decision and captures messages it was called with."""

    def __init__(self) -> None:
        self.received_messages: list[list[Message]] = []
        self._payload = json.dumps({
            "action": "buy",
            "size_pct": 0.5,
            "confidence": 0.8,
            "reasoning": "ok",
        })

    async def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        tools: list[dict] | None = None,
    ) -> LLMResult:
        self.received_messages.append(messages)
        return LLMResult(text=self._payload, model="fake", latency_ms=1.0)

    async def aclose(self) -> None:
        pass


async def _seed_losers(log: DecisionLog) -> None:
    """Write 3 snipe losers so the lessons block has something to surface."""
    for i, (mint, pnl) in enumerate([
        ("LOSER1", -0.25),
        ("LOSER2", -0.30),
        ("LOSER3", -0.18),
    ]):
        run_id = f"loss-{i}"
        await log.log(run_id, {
            "mint": mint,
            "top10_pct": 0.35,
            "action": "buy",
        })
        await log.record_outcome(run_id, {"pnl": pnl})


# -- llm / hybrid mode: reflection wired in ----------------------------------


async def test_llm_mode_without_log_skips_reflect_node():
    """Backwards-compat: without decision_log, no reflect node is added."""
    g = build_sniper(_CapturingLLM())
    state = await g.run(State(context=_ctx("GOOD", use_llm=True, decision_mode="llm")))
    nodes = [t.node for t in state.trace]
    assert "reflect" not in nodes
    assert "snipe_decide" in nodes


async def test_llm_mode_with_log_inserts_reflect_before_snipe_decide():
    """Reflect runs between fast_market and snipe_decide in llm mode."""
    log = DecisionLog(InMemoryStore())
    await _seed_losers(log)
    g = build_sniper(_CapturingLLM(), decision_log=log)
    state = await g.run(State(context=_ctx("GOOD", use_llm=True, decision_mode="llm")))

    nodes = [t.node for t in state.trace]
    assert "reflect" in nodes
    assert nodes.index("reflect") > nodes.index("fast_market")
    assert nodes.index("reflect") < nodes.index("snipe_decide")


async def test_hybrid_mode_with_log_injects_lessons_into_snipe_prompt():
    """LLM in hybrid mode receives a LESSONS block compiled from the log."""
    log = DecisionLog(InMemoryStore())
    await _seed_losers(log)
    llm = _CapturingLLM()
    g = build_sniper(llm, decision_log=log)
    state = await g.run(State(context=_ctx("GOOD", use_llm=True, decision_mode="hybrid")))

    # Pipeline produced a decision
    assert state.output.action == "buy"
    # Reflect populated scratch
    assert "lessons_text" in state.scratch
    assert "lessons" in state.scratch

    # The LLM was called and saw a lessons system block
    assert len(llm.received_messages) == 1
    system_messages = [
        m["content"] for m in llm.received_messages[0] if m["role"] == "system"
    ]
    lessons_msg = [c for c in system_messages if "LESSONS from recent" in c]
    assert len(lessons_msg) == 1, (
        f"expected one LESSONS system block; got system messages: {system_messages}"
    )


async def test_llm_mode_with_empty_log_still_runs_reflect_no_lessons():
    """Empty DecisionLog → reflect runs but produces 'No prior decisions' text."""
    log = DecisionLog(InMemoryStore())  # no records
    llm = _CapturingLLM()
    g = build_sniper(llm, decision_log=log)
    state = await g.run(State(context=_ctx("GOOD", use_llm=True, decision_mode="llm")))

    assert "reflect" in [t.node for t in state.trace]
    assert "lessons_text" in state.scratch
    assert state.output.action == "buy"


async def test_reflect_window_threading():
    """``reflect_window`` is forwarded to the ReflectiveNode."""
    log = DecisionLog(InMemoryStore())
    await _seed_losers(log)
    g = build_sniper(_CapturingLLM(), decision_log=log, reflect_window=2)
    # Find the reflect node and verify the window parameter
    reflect_node = g._nodes["reflect"]  # type: ignore[attr-defined]
    assert reflect_node._window == 2  # type: ignore[attr-defined]


# -- rule / hybrid_audit modes: reflect NOT in the graph ---------------------


async def test_rule_mode_skips_reflect_even_when_log_provided():
    """``rule`` mode has no LLM; reflect would be dead weight on the hot path."""
    log = DecisionLog(InMemoryStore())
    await _seed_losers(log)
    g = build_sniper(_CapturingLLM(), decision_log=log)
    state = await g.run(State(context=_ctx("GOOD")))  # default decision_mode="rule"

    nodes = [t.node for t in state.trace]
    assert "reflect" not in nodes
    assert state.output.action == "buy"


async def test_hybrid_audit_mode_skips_reflect_to_preserve_sub_ms_path():
    """``hybrid_audit`` must keep the sync path sub-ms; reflect is intentionally
    excluded. Reflection here is the bot's offline responsibility."""
    log = DecisionLog(InMemoryStore())
    await _seed_losers(log)
    g = build_sniper(_CapturingLLM(), decision_log=log)
    ctx = _ctx("GOOD", use_llm=True, decision_mode="hybrid_audit")
    state = await g.run(State(context=ctx))

    nodes = [t.node for t in state.trace]
    assert "reflect" not in nodes
    # rule_buy + audit_dispatch should still fire
    assert "rule_buy" in nodes
    assert "audit_dispatch" in nodes
    # Decision was set by rule_buy synchronously
    assert state.output is not None and state.output.action == "buy"


async def test_no_llm_client_with_log_skips_reflect():
    """``llm_client=None`` keeps the graph pure-rule; reflect is omitted."""
    log = DecisionLog(InMemoryStore())
    await _seed_losers(log)
    g = build_sniper(llm_client=None, decision_log=log)
    state = await g.run(State(context=_ctx("GOOD")))

    nodes = [t.node for t in state.trace]
    assert "reflect" not in nodes
    assert "snipe_decide" not in nodes
    assert state.output.action == "buy"
