"""Offline runner for the YAML scanner demo.

Loads ``examples/scanner.yaml`` via the M13 YAML loader and runs it against a
few mock token contexts. No LLM, no network — purely a wiring demo.

Run from the repo root::

    python examples/run_yaml_scanner.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make the repo root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zetryn.config import load_graph  # noqa: E402
from zetryn.core.state import Command, State  # noqa: E402


# --- Rule nodes ------------------------------------------------------------


def safety_gate(state: State) -> None:
    token = state.context.get("token", {})
    state.scratch["safety_ok"] = not token.get("is_rug", False)


def market_gate(state: State) -> None:
    token = state.context.get("token", {})
    score = float(token.get("score", 0.0))
    state.scratch["market_ok"] = token.get("lp_burned", False)
    state.scratch["score"] = score


def decide_buy(state: State) -> Command:
    state.output = {"action": "buy", "size": 1.0, "score": state.scratch.get("score")}
    return Command()


def decide_skip(state: State) -> Command:
    reason = "rug" if not state.scratch.get("safety_ok") else "weak_market"
    state.output = {"action": "skip", "reason": reason}
    return Command()


# --- Main ------------------------------------------------------------------


async def main() -> None:
    spec_path = Path(__file__).parent / "scanner.yaml"
    graph = load_graph(spec_path)
    print(f"Loaded graph {graph.name!r}: {len(graph._nodes)} nodes, {len(graph._edges)} edges")

    samples = [
        {"label": "good token", "token": {"is_rug": False, "lp_burned": True, "score": 0.85}},
        {"label": "rug",        "token": {"is_rug": True,  "lp_burned": True, "score": 0.9}},
        {"label": "weak score", "token": {"is_rug": False, "lp_burned": True, "score": 0.3}},
        {"label": "no LP burn", "token": {"is_rug": False, "lp_burned": False, "score": 0.9}},
    ]

    for s in samples:
        result = await graph.run(State(context={"token": s["token"]}))
        print(f"  {s['label']:20s} -> {result.output}")


if __name__ == "__main__":
    asyncio.run(main())
