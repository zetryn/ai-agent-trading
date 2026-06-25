"""Integration tests: `LLMRouter` is a drop-in `LLMClient` for the scanner.

The scanner doesn't know about routers — it just sees an `LLMClient`.
These tests prove that `build_scanner(router)` works exactly like
`build_scanner(single_client)` and that failover happens transparently
when the first provider rate-limits.
"""

from __future__ import annotations

import json

import pytest

from strategies import SAMPLE_TOKENS, build_scanner
from trading import ScannerConfig, TradingContext
from zetryn.core import State
from zetryn.llm import LLMRouter
from zetryn.llm.types import LLMRateLimitError, LLMResult, Message


def _payload(rec: str = "alert", final: float = 0.85, note: str = "") -> str:
    return json.dumps({
        "safety":  {"score": 0.8, "verdict": "positive", "signals": [], "reasoning": note or "f"},
        "market":  {"score": 0.7, "verdict": "positive", "signals": [], "reasoning": "f"},
        "wallets": {"score": 0.7, "verdict": "positive", "signals": [], "reasoning": "f"},
        "social":  {"score": 0.7, "verdict": "positive", "signals": [], "reasoning": "f"},
        "final_score": final,
        "recommendation": rec,
        "reasoning": note or "fake",
    })


class _ScriptedClient:
    """An `LLMClient` that returns a fixed text — or raises a scripted error."""

    def __init__(self, *, name: str, payload: str | None = None,
                 raises: Exception | None = None) -> None:
        self.name = name
        self.payload = payload
        self.raises = raises
        self.calls = 0
        self.closed = False

    async def complete(self, messages: list[Message], **kw) -> LLMResult:
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return LLMResult(text=self.payload or "", model=self.name, latency_ms=1.0)

    async def aclose(self) -> None:
        self.closed = True


def _ctx(mint: str = "GOOD"):
    return TradingContext(token=SAMPLE_TOKENS[mint], config=ScannerConfig())


# -- Basic drop-in equivalence ---------------------------------------------


@pytest.mark.asyncio
async def test_scanner_works_with_router_holding_one_entry():
    """Single-entry router behaves like a bare LLMClient."""
    primary = _ScriptedClient(name="primary", payload=_payload(rec="alert", final=0.85))
    router = LLMRouter([primary])

    g = build_scanner(router)
    state = await g.run(State(context=_ctx()))

    assert state.output.action == "alert"
    assert primary.calls == 1


@pytest.mark.asyncio
async def test_scanner_fails_over_to_secondary_provider():
    """Primary rate-limits → router transparently uses secondary."""
    primary = _ScriptedClient(name="groq", raises=LLMRateLimitError("429"))
    secondary = _ScriptedClient(name="gemini", payload=_payload(rec="alert", final=0.85))
    router = LLMRouter([primary, secondary])

    g = build_scanner(router)
    state = await g.run(State(context=_ctx()))

    # Scanner saw success — failover was invisible to it.
    assert state.output.action == "alert"
    assert primary.calls == 1   # tried once
    assert secondary.calls == 1  # then secondary succeeded


@pytest.mark.asyncio
async def test_scanner_falls_back_gracefully_when_all_router_entries_fail():
    """Both providers down → analyst fallback kicks in, scanner still returns."""
    a = _ScriptedClient(name="a", raises=LLMRateLimitError("429"))
    b = _ScriptedClient(name="b", raises=LLMRateLimitError("429"))
    router = LLMRouter([a, b])

    g = build_scanner(router)
    state = await g.run(State(context=_ctx()))

    # neutral_analysis kicks in — conservative skip rather than crash
    assert state.output is not None
    assert state.output.action in {"skip", "watch"}
    assert state.output.flags.get("llm_failed") is True
    assert a.calls == 1
    assert b.calls == 1


@pytest.mark.asyncio
async def test_router_remembers_cooldown_across_scans():
    """After a 429, the primary stays on cooldown for the next scan too."""
    primary = _ScriptedClient(name="primary", raises=LLMRateLimitError("429"))
    # Secondary needs to answer twice — once per scan.
    secondary_payload = _payload(rec="alert", final=0.85)
    secondary = _ScriptedClient(name="secondary", payload=secondary_payload)
    router = LLMRouter([primary, secondary], cooldown_s=999.0)

    g = build_scanner(router)

    # Scan 1: primary fails, secondary succeeds.
    await g.run(State(context=_ctx()))
    assert primary.calls == 1
    assert secondary.calls == 1

    # Scan 2: primary still in cooldown — router skips it, hits secondary direct.
    await g.run(State(context=_ctx()))
    assert primary.calls == 1   # unchanged
    assert secondary.calls == 2


# -- KnowledgePack + Router together ---------------------------------------


@pytest.mark.asyncio
async def test_router_passes_through_knowledge_pack_blocks(tmp_path):
    """Pack injection works regardless of whether LLMClient is router or bare."""
    from zetryn.knowledge import KnowledgePack

    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "01-rules.md").write_text("Always check liquidity twice.")
    pack = KnowledgePack.from_dir(tmp_path)

    captured: list[list[Message]] = []

    class _Capturer(_ScriptedClient):
        async def complete(self, messages, **kw):
            captured.append(messages)
            return await super().complete(messages, **kw)

    primary = _Capturer(name="primary", payload=_payload(rec="watch", final=0.6))
    router = LLMRouter([primary])

    g = build_scanner(router, knowledge_pack=pack)
    await g.run(State(context=_ctx()))

    system_text = "\n".join(m["content"] for m in captured[0] if m["role"] == "system")
    assert "Always check liquidity twice." in system_text
