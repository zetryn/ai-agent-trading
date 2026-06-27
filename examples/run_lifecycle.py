"""Example: position-lifecycle helpers (v0.13.0 / PL1).

Offline by default (stub LLM). Set ``ZETRYN_LIFECYCLE_USE_GROQ=1`` and provide
``GROQ_API_KEY`` to run with a real Groq client.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from strategies import SAMPLE_TOKENS, build_lifecycle
from trading import LifecycleConfig, PartialExit, PositionContext, PositionState
from zetryn.core import State
from zetryn.llm.types import LLMResult, Message


class _StubLLM:
    async def complete(self, messages: list[Message], **kw) -> LLMResult:
        payload = {
            "action": "hold",
            "size_pct": 0.0,
            "confidence": 0.7,
            "reasoning": "structure intact, holding for next rung",
            "concerns": [],
        }
        return LLMResult(text=json.dumps(payload), model="stub", latency_ms=1.0)

    async def aclose(self) -> None:
        pass


def _llm_client():
    if os.environ.get("ZETRYN_LIFECYCLE_USE_GROQ") != "1":
        return _StubLLM()
    from zetryn.llm import KeyPool, OpenAICompatibleClient, ProviderConfig

    cfg = ProviderConfig(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.1-70b-versatile",
        key_envs=["GROQ_API_KEY"],
    )
    return OpenAICompatibleClient(cfg, KeyPool.from_env(cfg.key_envs))


SCENARIOS = {
    "FLAT": PositionState(
        entry_price=1.0, entry_size=10.0, entry_ts=0.0,
        current_price=1.05, current_size=10.0, pnl_pct=0.05,
        holding_seconds=60.0,
    ),
    "TP_RUNG_1": PositionState(
        entry_price=1.0, entry_size=10.0, entry_ts=0.0,
        current_price=1.55, current_size=10.0, pnl_pct=0.55,
        holding_seconds=300.0,
    ),
    "MID_LADDER": PositionState(
        entry_price=1.0, entry_size=10.0, entry_ts=0.0,
        current_price=2.10, current_size=5.0, pnl_pct=1.10,
        holding_seconds=900.0,
        partial_exits=[PartialExit(sold_at_pnl_pct=0.5, sold_size=5.0, sold_at_ts=300.0)],
    ),
    "HARD_SL": PositionState(
        entry_price=1.0, entry_size=10.0, entry_ts=0.0,
        current_price=0.60, current_size=10.0, pnl_pct=-0.40,
        holding_seconds=180.0,
    ),
    "TRAILING": PositionState(
        entry_price=1.0, entry_size=10.0, entry_ts=0.0,
        current_price=1.40, current_size=10.0, pnl_pct=0.40,
        holding_seconds=600.0, peak_pnl_pct=2.0, drawdown_from_peak_pct=0.55,
    ),
}


async def main() -> None:
    print("=== Pure-rule position lifecycle ===")
    rule_agent = build_lifecycle(llm_client=None)
    for name, ps in SCENARIOS.items():
        ctx = PositionContext(
            token=SAMPLE_TOKENS["GOOD"], position=ps, config=LifecycleConfig()
        )
        state = await rule_agent.run(State(context=ctx))
        d = state.output
        print(f"  {name:12} {d.action.upper():12} size={d.size}")

    print("\n=== Hybrid (LLM inside guardrail) ===")
    hybrid = build_lifecycle(_llm_client())
    cfg = LifecycleConfig(decision_mode="hybrid")
    for name, ps in SCENARIOS.items():
        ctx = PositionContext(token=SAMPLE_TOKENS["GOOD"], position=ps, config=cfg)
        state = await hybrid.run(State(context=ctx))
        d = state.output
        reasons = "; ".join(d.reasons[:2])
        print(f"  {name:12} {d.action.upper():12} size={d.size} | {reasons}")


if __name__ == "__main__":
    asyncio.run(main())
