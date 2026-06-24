"""Integration tests: KnowledgePack injection into scanner / sniper prompts."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from strategies import SAMPLE_TOKENS, build_scanner, build_sniper
from strategies.nodes.analyst import make_analyst_prompt
from strategies.nodes.sniper_nodes import make_snipe_prompt
from trading import ScannerConfig, SniperConfig, TradingContext
from zetryn.core import State
from zetryn.knowledge import KnowledgePack
from zetryn.llm.types import LLMResult, Message


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _pack(tmp_path: Path) -> KnowledgePack:
    _write(tmp_path / "system" / "01-house-rules.md", "Never long meme during ATH.")
    _write(tmp_path / "system" / "02-veto.md", "If liquidity < $5k, hard skip.")
    return KnowledgePack.from_dir(tmp_path)


# -- prompt factory level --------------------------------------------------


def test_make_analyst_prompt_without_pack_returns_default(tmp_path: Path):
    from strategies.nodes.analyst import analyst_prompt
    assert make_analyst_prompt(None) is analyst_prompt


def test_make_analyst_prompt_prepends_pack_blocks(tmp_path: Path):
    pack = _pack(tmp_path)
    state = State(context=TradingContext(token=SAMPLE_TOKENS["GOOD"]))
    messages = make_analyst_prompt(pack)(state)

    # First two messages are pack blocks, in filename order
    assert messages[0]["role"] == "system"
    assert "Never long meme during ATH" in messages[0]["content"]
    assert messages[1]["role"] == "system"
    assert "liquidity < $5k" in messages[1]["content"]
    # Followed by the analyst's own system + user message
    assert any("memecoin analyst" in m["content"].lower() for m in messages[2:])
    assert any(m["role"] == "user" for m in messages)


def test_make_snipe_prompt_prepends_pack_blocks(tmp_path: Path):
    pack = _pack(tmp_path)
    ctx = TradingContext(token=SAMPLE_TOKENS["GOOD"], config=SniperConfig())
    messages = make_snipe_prompt(pack)(State(context=ctx))

    assert "Never long meme during ATH" in messages[0]["content"]
    assert any(m["role"] == "user" for m in messages)


def test_empty_pack_returns_default_prompt(tmp_path: Path):
    pack = KnowledgePack.from_dir(tmp_path)  # empty dir
    from strategies.nodes.analyst import analyst_prompt
    assert make_analyst_prompt(pack) is analyst_prompt


# -- scanner end-to-end ----------------------------------------------------


class _RecordingLLM:
    """Captures the messages sent to the LLM so we can assert injection."""

    def __init__(self) -> None:
        self.received: list[list[Message]] = []
        self._payload = {
            "safety": {"score": 0.9, "verdict": "positive", "signals": [], "reasoning": "f"},
            "market": {"score": 0.8, "verdict": "positive", "signals": [], "reasoning": "f"},
            "wallets": {"score": 0.7, "verdict": "positive", "signals": [], "reasoning": "f"},
            "social": {"score": 0.7, "verdict": "positive", "signals": [], "reasoning": "f"},
            "final_score": 0.85,
            "recommendation": "alert",
            "reasoning": "fake",
        }

    async def complete(self, messages: list[Message], **kw) -> LLMResult:
        self.received.append(messages)
        return LLMResult(text=json.dumps(self._payload), model="fake", latency_ms=1.0)

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_scanner_injects_pack_into_analyst_prompt(tmp_path: Path):
    pack = _pack(tmp_path)
    llm = _RecordingLLM()
    g = build_scanner(llm, knowledge_pack=pack)
    ctx = TradingContext(token=SAMPLE_TOKENS["GOOD"], config=ScannerConfig())
    await g.run(State(context=ctx))

    assert llm.received, "analyst should have been called"
    first_call = llm.received[0]
    combined = "\n".join(m["content"] for m in first_call if m["role"] == "system")
    assert "Never long meme during ATH" in combined
    assert "liquidity < $5k" in combined


@pytest.mark.asyncio
async def test_scanner_without_pack_works_as_before():
    llm = _RecordingLLM()
    g = build_scanner(llm)
    ctx = TradingContext(token=SAMPLE_TOKENS["GOOD"], config=ScannerConfig())
    state = await g.run(State(context=ctx))
    assert state.output.action == "alert"
    assert llm.received  # analyst called


# -- sniper end-to-end -----------------------------------------------------


class _SnipeLLM:
    def __init__(self) -> None:
        self.received: list[list[Message]] = []
        self._payload = {
            "action": "buy", "confidence": 0.8, "size_pct": 0.5, "reasoning": "ok"
        }

    async def complete(self, messages: list[Message], **kw) -> LLMResult:
        self.received.append(messages)
        return LLMResult(text=json.dumps(self._payload), model="fake", latency_ms=1.0)

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_sniper_llm_mode_injects_pack(tmp_path: Path):
    pack = _pack(tmp_path)
    llm = _SnipeLLM()
    g = build_sniper(llm, knowledge_pack=pack)
    ctx = TradingContext(
        token=SAMPLE_TOKENS["GOOD"],
        config=SniperConfig(decision_mode="llm"),
    )
    await g.run(State(context=ctx))

    assert llm.received
    sys_msgs = [m["content"] for m in llm.received[0] if m["role"] == "system"]
    assert any("Never long meme during ATH" in c for c in sys_msgs)


@pytest.mark.asyncio
async def test_sniper_hybrid_audit_injects_pack_into_audit(tmp_path: Path):
    pack = _pack(tmp_path)
    llm = _SnipeLLM()
    g = build_sniper(llm, knowledge_pack=pack)
    ctx = TradingContext(
        token=SAMPLE_TOKENS["GOOD"],
        config=SniperConfig(decision_mode="hybrid_audit"),
    )
    state = await g.run(State(context=ctx))

    # rule_buy decides synchronously; audit task is fired async
    task = state.scratch.get("audit_task")
    if task is not None:
        await asyncio.wait_for(task, timeout=2.0)

    assert llm.received, "audit LLM should have been called"
    sys_msgs = [m["content"] for m in llm.received[0] if m["role"] == "system"]
    assert any("Never long meme during ATH" in c for c in sys_msgs)
