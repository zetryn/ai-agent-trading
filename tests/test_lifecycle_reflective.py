"""Lifecycle × ReflectiveNode integration tests (v0.13.0 / PL1)."""

from __future__ import annotations

import json

from strategies import SAMPLE_TOKENS, build_lifecycle
from trading import LifecycleConfig, PositionContext, PositionState
from zetryn.core import State
from zetryn.llm.types import LLMResult, Message
from zetryn.memory import DecisionLog, InMemoryStore


def _ctx(**cfg) -> PositionContext:
    return PositionContext(
        token=SAMPLE_TOKENS["GOOD"],
        position=PositionState(
            entry_price=1.0,
            entry_size=10.0,
            entry_ts=0.0,
            current_price=1.10,
            current_size=10.0,
            pnl_pct=0.10,  # mid-flight, no rule gate fires
            holding_seconds=60.0,
        ),
        config=LifecycleConfig(**cfg),
    )


class _CapturingLLM:
    def __init__(self) -> None:
        self.received_messages: list[list[Message]] = []
        self._payload = json.dumps({
            "action": "hold",
            "size_pct": 0.0,
            "confidence": 0.7,
            "reasoning": "still early",
            "concerns": [],
        })

    async def complete(self, messages, **kw) -> LLMResult:
        self.received_messages.append(messages)
        return LLMResult(text=self._payload, model="fake", latency_ms=1.0)

    async def aclose(self):
        pass


async def _seed_losers(log: DecisionLog) -> None:
    for i, (mint, pnl) in enumerate([
        ("LOSER1", -0.25),
        ("LOSER2", -0.30),
        ("LOSER3", -0.18),
    ]):
        run_id = f"loss-{i}"
        await log.log(run_id, {"mint": mint, "exit_pnl": pnl, "action": "exit_full"})
        await log.record_outcome(run_id, {"pnl": pnl})


async def test_seeded_losers_lessons_reach_llm_prompt():
    log = DecisionLog(InMemoryStore())
    await _seed_losers(log)
    llm = _CapturingLLM()
    g = build_lifecycle(llm, decision_log=log)
    state = await g.run(State(context=_ctx(decision_mode="hybrid")))

    assert state.output.action == "hold"
    assert "lessons_text" in state.scratch
    assert "lessons" in state.scratch

    assert len(llm.received_messages) == 1
    system_msgs = [
        m["content"] for m in llm.received_messages[0] if m["role"] == "system"
    ]
    lessons = [c for c in system_msgs if "LESSONS from recent position-lifecycle" in c]
    assert len(lessons) == 1


async def test_empty_log_reflect_still_runs_no_block_breaks():
    log = DecisionLog(InMemoryStore())
    llm = _CapturingLLM()
    g = build_lifecycle(llm, decision_log=log)
    state = await g.run(State(context=_ctx(decision_mode="llm")))
    assert "reflect" in [t.node for t in state.trace]
    assert "lessons_text" in state.scratch
    assert state.output.action == "hold"


async def test_reflect_window_parameter_threading():
    log = DecisionLog(InMemoryStore())
    await _seed_losers(log)
    g = build_lifecycle(_CapturingLLM(), decision_log=log, reflect_window=3)
    reflect_node = g._nodes["reflect"]  # type: ignore[attr-defined]
    assert reflect_node._window == 3  # type: ignore[attr-defined]


async def test_rule_mode_skips_reflect_even_with_log():
    log = DecisionLog(InMemoryStore())
    await _seed_losers(log)
    g = build_lifecycle(_CapturingLLM(), decision_log=log)
    state = await g.run(State(context=_ctx()))  # default rule
    nodes = [t.node for t in state.trace]
    assert "reflect" not in nodes


async def test_hybrid_audit_skips_reflect():
    log = DecisionLog(InMemoryStore())
    await _seed_losers(log)
    g = build_lifecycle(_CapturingLLM(), decision_log=log)
    state = await g.run(State(context=_ctx(decision_mode="hybrid_audit")))
    nodes = [t.node for t in state.trace]
    assert "reflect" not in nodes


async def test_no_llm_client_with_log_skips_reflect():
    log = DecisionLog(InMemoryStore())
    await _seed_losers(log)
    g = build_lifecycle(llm_client=None, decision_log=log)
    state = await g.run(State(context=_ctx()))
    nodes = [t.node for t in state.trace]
    assert "reflect" not in nodes
    assert "lifecycle_decide" not in nodes
