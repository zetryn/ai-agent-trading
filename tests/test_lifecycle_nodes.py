"""Tests for position-lifecycle rule nodes (v0.13.0 / PL1)."""

from __future__ import annotations

from strategies import SAMPLE_TOKENS, build_lifecycle
from trading import (
    LifecycleConfig,
    PartialExit,
    PositionContext,
    PositionState,
)
from zetryn.core import State


def _pstate(**over) -> PositionState:
    base = dict(
        entry_price=1.0,
        entry_size=10.0,
        entry_ts=0.0,
        current_price=1.0,
        current_size=10.0,
        pnl_pct=0.0,
        holding_seconds=10.0,
        peak_pnl_pct=0.0,
        drawdown_from_peak_pct=0.0,
        partial_exits=[],
    )
    base.update(over)
    return PositionState(**base)


def _ctx(*, position=None, token=None, **cfg) -> PositionContext:
    return PositionContext(
        token=token if token is not None else SAMPLE_TOKENS["GOOD"],
        position=position if position is not None else _pstate(),
        config=LifecycleConfig(**cfg),
    )


# -- emergency_exit ----------------------------------------------------------


async def test_emergency_exit_fires_on_dangerous_contract():
    g = build_lifecycle()
    state = await g.run(State(context=_ctx(token=SAMPLE_TOKENS["RUG"])))
    assert state.output.action == "exit_full"
    assert state.output.flags["rug_risk"] is True
    assert state.output.flags.get("emergency") is True
    assert [t.node for t in state.trace] == ["emergency_exit"]


# -- hard_stop_loss ----------------------------------------------------------


async def test_hard_stop_loss_fires_at_threshold():
    g = build_lifecycle()
    state = await g.run(
        State(context=_ctx(position=_pstate(pnl_pct=-0.30), stop_loss_pct=-0.30))
    )
    assert state.output.action == "exit_full"
    assert "hard_stop_loss" in state.output.reasons[0]


async def test_hard_stop_loss_does_not_fire_above_threshold():
    g = build_lifecycle()
    state = await g.run(
        State(context=_ctx(position=_pstate(pnl_pct=-0.29), stop_loss_pct=-0.30))
    )
    assert state.output.action == "hold"


# -- time_stop ---------------------------------------------------------------


async def test_time_stop_fires_at_threshold():
    g = build_lifecycle()
    state = await g.run(
        State(context=_ctx(
            position=_pstate(holding_seconds=3600.0),
            max_hold_seconds=3600.0,
        ))
    )
    assert state.output.action == "exit_full"
    assert "time_stop" in state.output.reasons[0]


# -- trailing_stop -----------------------------------------------------------


async def test_trailing_stop_not_armed_below_threshold():
    g = build_lifecycle()
    # peak below arms threshold → no trailing fire even on big drawdown
    state = await g.run(
        State(context=_ctx(
            position=_pstate(
                pnl_pct=0.05,
                peak_pnl_pct=0.10,
                drawdown_from_peak_pct=0.90,
            ),
            trailing_arms_at_pnl_pct=0.20,
        ))
    )
    assert state.output.action == "hold"


async def test_trailing_stop_fires_when_armed_and_drawdown_hit():
    g = build_lifecycle()
    state = await g.run(
        State(context=_ctx(
            position=_pstate(
                pnl_pct=0.10,
                peak_pnl_pct=0.50,
                drawdown_from_peak_pct=0.60,
            ),
            trailing_arms_at_pnl_pct=0.20,
            trailing_drawdown_pct=0.50,
        ))
    )
    assert state.output.action == "exit_full"
    assert "trailing_stop" in state.output.reasons[0]


# -- tp_ladder ---------------------------------------------------------------


async def test_tp_ladder_first_rung_take_profit():
    g = build_lifecycle()
    state = await g.run(
        State(context=_ctx(
            position=_pstate(pnl_pct=0.55, current_size=10.0),
            tp_ladder=[(0.5, 0.5), (1.0, 0.5), (3.0, 1.0)],
        ))
    )
    assert state.output.action == "take_profit"
    assert state.output.size == 5.0  # 50% of 10.0


async def test_tp_ladder_skips_already_hit_rungs():
    g = build_lifecycle()
    # First rung already executed
    state = await g.run(
        State(context=_ctx(
            position=_pstate(
                pnl_pct=1.10,
                current_size=5.0,
                partial_exits=[PartialExit(sold_at_pnl_pct=0.5, sold_size=5.0, sold_at_ts=100.0)],
            ),
            tp_ladder=[(0.5, 0.5), (1.0, 0.5), (3.0, 1.0)],
        ))
    )
    # Should now fire second rung (scale_out): 50% of remaining 5.0
    assert state.output.action == "scale_out"
    assert state.output.size == 2.5


async def test_tp_ladder_final_rung_is_exit_full():
    g = build_lifecycle()
    state = await g.run(
        State(context=_ctx(
            position=_pstate(
                pnl_pct=3.50,
                current_size=2.5,
                partial_exits=[
                    PartialExit(sold_at_pnl_pct=0.5, sold_size=5.0, sold_at_ts=100.0),
                    PartialExit(sold_at_pnl_pct=1.0, sold_size=2.5, sold_at_ts=200.0),
                ],
            ),
            tp_ladder=[(0.5, 0.5), (1.0, 0.5), (3.0, 1.0)],
        ))
    )
    assert state.output.action == "exit_full"
    assert state.output.size == 2.5  # 100% of remaining


async def test_tp_ladder_size_uses_current_size_not_entry():
    g = build_lifecycle()
    state = await g.run(
        State(context=_ctx(
            position=_pstate(pnl_pct=0.55, entry_size=10.0, current_size=4.0),
            tp_ladder=[(0.5, 0.5)],
        ))
    )
    # 50% of CURRENT 4.0 = 2.0, NOT 50% of entry 10.0 = 5.0
    assert state.output.action == "exit_full"  # final rung
    assert state.output.size == 2.0


# -- rule_hold + gate ordering ----------------------------------------------


async def test_rule_hold_is_default():
    g = build_lifecycle()
    state = await g.run(State(context=_ctx()))
    assert state.output.action == "hold"


async def test_gate_priority_emergency_beats_sl():
    """Emergency must fire even when SL would also fire."""
    g = build_lifecycle()
    state = await g.run(
        State(context=_ctx(
            position=_pstate(pnl_pct=-0.50),  # would trigger SL
            token=SAMPLE_TOKENS["RUG"],         # but contract is dangerous
        ))
    )
    assert state.output.flags["rug_risk"] is True
    assert [t.node for t in state.trace] == ["emergency_exit"]


async def test_min_sell_size_demotes_small_ladder_sell_to_hold():
    g = build_lifecycle()
    state = await g.run(
        State(context=_ctx(
            position=_pstate(pnl_pct=0.55, current_size=0.01),
            tp_ladder=[(0.5, 0.5)],
            min_sell_size=0.1,
        ))
    )
    # 50% of 0.01 = 0.005 < 0.1 min_sell_size → demoted to hold
    assert state.output.action == "hold"
    assert "min_sell_size" in state.output.reasons[0]
