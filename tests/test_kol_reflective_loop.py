"""K7 tests — KOL Copy-Trade x ReflectiveNode integration.

The reflective loop:
  1. Bot writes outcomes to DecisionLog after each trade settles.
  2. On the next KOL signal, a ReflectiveNode runs between fast_market
     and kol_analyst, compiles a lessons_text from recent losers.
  3. kol_analyst_prompt prepends the lessons block to its system
     messages so the LLM conditions on real outcomes.

These tests use scripted fake clients (no network, no real LLM).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from strategies import build_kol_copytrade
from trading import (
    KOLBuyEvent,
    KOLContext,
    KOLCopyTradeConfig,
    TokenInput,
)
from trading.schemas import (
    ActivityData,
    ContractData,
    HolderData,
    MarketData,
    SocialData,
    TwitterData,
    WalletIntel,
)
from zetryn.core import State
from zetryn.knowledge import KnowledgePack
from zetryn.llm.types import LLMResult, Message
from zetryn.memory import DecisionLog, InMemoryStore


def _pack(tmp_path: Path) -> KnowledgePack:
    data = tmp_path / "data" / "kol_whitelist.json"
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text(json.dumps({
        "wallets": {
            "ABC": {"name": "smart_money", "hit_rate": 0.55, "tier": "S",
                    "exit_pattern": "scales_out_50pct"},
        },
        "min_hit_rate": 0.40,
    }), encoding="utf-8")
    return KnowledgePack.from_dir(tmp_path)


def _ctx(wallet: str = "ABC", mint: str = "M1") -> KOLContext:
    return KOLContext(
        event=KOLBuyEvent(
            wallet=wallet, mint=mint, sol_amount=1.5,
            detected_at_ts=1000.0, block_age_seconds=4.0,
        ),
        token=TokenInput(
            mint=mint, symbol="MEME", name="Meme",
            market=MarketData(liquidity_usd=10_000, volume_1h=8_000),
            activity=ActivityData(buys_5m=80, sells_5m=40, buy_ratio_5m=0.67),
            holders=HolderData(top10_pct=0.18, count=300),
            contract=ContractData(),
            wallets=WalletIntel(
                smart_wallet_buys=3, kol_wallet_count=2,
                bundler_wallet_count=0, sniper_wallet_count=2,
            ),
            social=SocialData(
                twitter=TwitterData(
                    handle="meme", followers=2000, mentions_1h=60,
                    mention_growth_pct=120.0, velocity_tpm=4.0,
                    sentiment="bullish", engagement=900,
                ),
                kol_count_5m=2,
            ),
        ),
        config=KOLCopyTradeConfig(),
    )


class _CapturingLLM:
    """Returns a fixed verdict and captures the messages it was called with."""

    def __init__(self) -> None:
        self.received_messages: list[list[Message]] = []
        self._payload = json.dumps({
            "approve": True,
            "size_multiplier": 1.0,
            "confidence": 0.7,
            "concerns": [],
            "reasoning": "Looks fine.",
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
    """Write 3 KOL copy-trade losers with a common 'exit_pattern' feature
    that the analyst should see surface in the lessons block."""
    for i, (wallet, pnl) in enumerate([
        ("ABC", -0.22),
        ("ABC", -0.18),
        ("XYZ", -0.30),
    ]):
        run_id = f"loss-{i}"
        await log.log(run_id, {
            "wallet": wallet,
            "exit_pattern": "scales_out_50pct",
            "action": "buy",
            "size": 1.5,
        })
        await log.record_outcome(run_id, {"pnl": pnl})


def test_decision_log_param_optional_in_rule_mode(tmp_path: Path):
    """Rule mode should accept (and ignore) decision_log without error."""
    pack = _pack(tmp_path)
    log = DecisionLog(InMemoryStore())
    g = build_kol_copytrade(pack, mode="rule", decision_log=log)
    assert g is not None


def test_reflect_node_only_added_in_confirmed_mode(tmp_path: Path):
    """Audit and rule modes must NOT add a reflect node even when log given."""
    pack = _pack(tmp_path)
    log = DecisionLog(InMemoryStore())

    rule_g = build_kol_copytrade(pack, mode="rule", decision_log=log)
    assert "reflect" not in {n for n in rule_g._nodes}  # type: ignore[attr-defined]

    audit_g = build_kol_copytrade(
        pack, mode="audit", llm_client=_CapturingLLM(), decision_log=log,
    )
    assert "reflect" not in {n for n in audit_g._nodes}  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_confirmed_with_log_injects_lessons_into_analyst_prompt(tmp_path: Path):
    """K7 core path: ReflectiveNode runs, analyst sees lessons_text."""
    pack = _pack(tmp_path)
    log = DecisionLog(InMemoryStore())
    await _seed_losers(log)

    llm = _CapturingLLM()
    g = build_kol_copytrade(
        pack, mode="confirmed", llm_client=llm,
        decision_log=log,
        reflect_feature_keys=["wallet", "exit_pattern"],
    )

    state = await g.run(State(context=_ctx()))

    # Decision still produced — pipeline didn't break
    assert state.output.action == "buy"

    # Reflect node actually ran
    nodes_in_trace = [t.node for t in state.trace]
    assert "reflect" in nodes_in_trace
    # Order: fast_market → reflect → kol_analyst → sizing
    assert nodes_in_trace.index("reflect") > nodes_in_trace.index("fast_market")
    assert nodes_in_trace.index("reflect") < nodes_in_trace.index("kol_analyst")

    # lessons_text populated
    assert "lessons_text" in state.scratch
    assert "lessons" in state.scratch

    # Analyst prompt actually received the lessons block
    assert len(llm.received_messages) == 1
    system_messages = [
        m["content"] for m in llm.received_messages[0] if m["role"] == "system"
    ]
    lessons_msg = [c for c in system_messages if "LESSONS from recent" in c]
    assert len(lessons_msg) == 1, (
        f"expected one LESSONS system block; got system messages: {system_messages}"
    )
    # Loser run ids surface somewhere in the prompt
    assert any("loss-" in c for c in system_messages)


@pytest.mark.asyncio
async def test_confirmed_without_log_skips_reflect_node(tmp_path: Path):
    """Backwards-compat: confirmed mode without decision_log runs same as v0.7.0."""
    pack = _pack(tmp_path)
    llm = _CapturingLLM()
    g = build_kol_copytrade(pack, mode="confirmed", llm_client=llm)
    state = await g.run(State(context=_ctx()))

    nodes_in_trace = [t.node for t in state.trace]
    assert "reflect" not in nodes_in_trace
    # And the analyst received NO lessons block
    system_messages = [
        m["content"] for m in llm.received_messages[0] if m["role"] == "system"
    ]
    assert not any("LESSONS from recent" in c for c in system_messages)


@pytest.mark.asyncio
async def test_confirmed_with_empty_log_still_runs_reflect_no_lessons(tmp_path: Path):
    """Empty DecisionLog → reflect runs but produces 'No prior decisions' text.
    The analyst still gets a (mostly empty) block, which is fine."""
    pack = _pack(tmp_path)
    log = DecisionLog(InMemoryStore())  # no records
    llm = _CapturingLLM()
    g = build_kol_copytrade(
        pack, mode="confirmed", llm_client=llm, decision_log=log,
    )
    state = await g.run(State(context=_ctx()))

    assert "reflect" in [t.node for t in state.trace]
    # ReflectionResult is populated even on empty log
    assert "lessons_text" in state.scratch
    # Decision still produced cleanly
    assert state.output.action == "buy"


@pytest.mark.asyncio
async def test_reflect_window_param_threads_through(tmp_path: Path):
    """Custom reflect_window is forwarded to ReflectiveNode."""
    pack = _pack(tmp_path)
    log = DecisionLog(InMemoryStore())
    # Seed 10 losers
    for i in range(10):
        await log.log(f"r{i}", {"wallet": "ABC", "exit_pattern": "scales_out_50pct"})
        await log.record_outcome(f"r{i}", {"pnl": -0.1})

    llm = _CapturingLLM()
    g = build_kol_copytrade(
        pack, mode="confirmed", llm_client=llm, decision_log=log,
        reflect_window=3, reflect_feature_keys=["wallet"],
    )
    state = await g.run(State(context=_ctx()))

    # ReflectionResult should report window=3 (only last 3 considered)
    result = state.scratch["lessons"]
    assert result.window == 3
    assert result.total_decisions == 3


@pytest.mark.asyncio
async def test_reflect_does_not_run_when_hard_gate_rejects(tmp_path: Path):
    """If kol_quality skips (e.g. unknown KOL), reflect should not run —
    no point reflecting on a request the rules already rejected."""
    pack = _pack(tmp_path)
    log = DecisionLog(InMemoryStore())
    await _seed_losers(log)

    llm = _CapturingLLM()
    g = build_kol_copytrade(
        pack, mode="confirmed", llm_client=llm, decision_log=log,
    )

    # Unknown wallet → kol_quality skips, short-circuits
    state = await g.run(State(context=_ctx(wallet="UNKNOWN", mint="M2")))

    assert state.output.action == "skip"
    nodes_in_trace = [t.node for t in state.trace]
    assert "reflect" not in nodes_in_trace
    assert "kol_analyst" not in nodes_in_trace
    # LLM never called either
    assert len(llm.received_messages) == 0