"""Example: run the scanner with a deployment-specific KnowledgePack.

A `KnowledgePack` lets your bot ship its own playbook (rules, KOL whitelist,
blacklists, lessons) without editing the framework. Markdown files under
``<pack>/system/`` are injected as system messages before the analyst's own
instructions; JSON files under ``<pack>/data/`` are exposed via
``pack.lookup(ns, key)``.

This example creates a throwaway pack in a temp directory, runs the scanner
on the sample tokens, and shows that the pack's house rules end up in the LLM
prompt. Uses a stub LLM so no API key is needed.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from strategies import SAMPLE_TOKENS, build_scanner
from trading import ScannerConfig, TradingContext
from zetryn.core import State
from zetryn.knowledge import KnowledgePack
from zetryn.llm.types import LLMResult, Message


class _EchoLLM:
    """Stub LLM that echoes the system prompt it received via the reasoning field."""

    def __init__(self) -> None:
        self.last_system_text: str = ""

    async def complete(self, messages: list[Message], **kw) -> LLMResult:
        self.last_system_text = "\n".join(
            m["content"] for m in messages if m["role"] == "system"
        )
        payload = {
            "safety":  {"score": 0.8, "verdict": "positive", "signals": [], "reasoning": "stub"},
            "market":  {"score": 0.7, "verdict": "positive", "signals": [], "reasoning": "stub"},
            "wallets": {"score": 0.7, "verdict": "positive", "signals": [], "reasoning": "stub"},
            "social":  {"score": 0.7, "verdict": "positive", "signals": [], "reasoning": "stub"},
            "final_score": 0.75,
            "recommendation": "watch",
            "reasoning": "stub: pack-aware analyst",
        }
        return LLMResult(text=json.dumps(payload), model="stub", latency_ms=1.0)

    async def aclose(self) -> None:
        pass


def _seed_pack(root: pathlib.Path) -> None:
    """Write a minimal pack: two markdown rules + a JSON blacklist."""
    sys_dir = root / "system"
    data_dir = root / "data"
    sys_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    (sys_dir / "01-house-rules.md").write_text(
        "House rules for this bot:\n"
        "- Never long a memecoin during BTC ATH unless funding is negative.\n"
        "- Skip anything with top10_pct > 35% even if other signals look great.\n",
        encoding="utf-8",
    )
    (sys_dir / "02-veto-list.md").write_text(
        "Hard vetoes (override the LLM):\n"
        "- liquidity_usd < $5k -> skip\n"
        "- dev_rug_history true -> skip\n",
        encoding="utf-8",
    )
    (data_dir / "kol-whitelist.json").write_text(
        json.dumps({"wallets": ["KOL_AAA", "KOL_BBB"], "min_score": 0.8}),
        encoding="utf-8",
    )


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="zetryn-pack-") as tmp:
        root = pathlib.Path(tmp)
        _seed_pack(root)

        pack = KnowledgePack.from_dir(root)
        print(f"Loaded pack: {len(pack.system_blocks())} system blocks, "
              f"namespaces={pack.namespaces()}")
        print(f"  KOL whitelist sample: {pack.lookup('kol-whitelist', 'wallets')}")

        llm = _EchoLLM()
        scanner = build_scanner(llm, knowledge_pack=pack)

        mint = "GOOD"
        ctx = TradingContext(token=SAMPLE_TOKENS[mint], config=ScannerConfig())
        state = await scanner.run(State(context=ctx))
        d = state.output

        print(f"\n[{mint}] action={d.action.upper()} confidence={d.confidence}")
        print(f"  reasons: {'; '.join(d.reasons)}")

        print("\n--- system text the analyst received ---")
        head = llm.last_system_text.splitlines()
        # Show just the first 12 lines so the demo stays readable.
        print("\n".join(head[:12]))
        if len(head) > 12:
            print(f"... ({len(head) - 12} more lines)")

        await llm.aclose()


if __name__ == "__main__":
    asyncio.run(main())
