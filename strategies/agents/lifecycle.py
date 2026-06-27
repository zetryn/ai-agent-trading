"""Agent E — Position Lifecycle Helpers (v0.13.0 / PL1).

First position-management agent. Consumes `PositionContext` (bot's open
position + live token snapshot), emits a `Decision` with
`action ∈ {hold, take_profit, scale_out, exit_full}` and a sell `size`.

Boundary recap: framework decides; bot persists position state, executes
sells, manages slippage / MEV. The framework holds NO position state
across calls — the bot pushes a fresh `PositionContext` per tick.

Four modes (selected via `LifecycleConfig.decision_mode`):

  rule (default)
    emergency_exit → hard_stop_loss → time_stop → trailing_stop →
      tp_ladder → rule_hold → END

  llm / hybrid
    emergency_exit → hard_stop_loss → time_stop → [reflect?] →
      lifecycle_decide → END
    Hard exits (emergency / SL / time) STILL fire deterministically;
    `lifecycle_guardrail` in hybrid mode enforces them on the LLM verdict.

  hybrid_audit
    emergency_exit → hard_stop_loss → time_stop → trailing_stop →
      tp_ladder → rule_hold → audit_dispatch → END
    Rule decides instantly; async LLM audit fires for any non-hold action.
"""

from __future__ import annotations

from trading.schemas import LifecycleVerdict
from zetryn.core import END, Graph, RuleNode
from zetryn.knowledge import KnowledgePack
from zetryn.llm import LLMClient, LLMDecisionNode
from zetryn.memory import DecisionLog, ReflectiveNode

from ..nodes import lifecycle_nodes as ln


def build_lifecycle(
    llm_client: LLMClient | None = None,
    *,
    model: str | None = None,
    knowledge_pack: KnowledgePack | None = None,
    decision_log: DecisionLog | None = None,
    reflect_window: int = 20,
    reflect_feature_keys: list[str] | None = None,
    reflect_top_k: int = 5,
) -> Graph:
    """Build and compile the position-lifecycle graph.

    Signature mirrors `build_sniper` / `build_graduation` /
    `build_kol_copytrade` for API consistency.
    """
    g = Graph("position_lifecycle")
    g.add_node(RuleNode("emergency_exit", ln.emergency_exit))
    g.add_node(RuleNode("hard_stop_loss", ln.hard_stop_loss))
    g.add_node(RuleNode("time_stop", ln.time_stop))
    g.add_node(RuleNode("trailing_stop", ln.trailing_stop))
    g.add_node(RuleNode("tp_ladder", ln.tp_ladder))
    g.add_node(RuleNode("rule_hold", ln.rule_hold))

    has_llm = llm_client is not None
    has_reflect = has_llm and decision_log is not None

    if has_llm:
        g.add_node(
            LLMDecisionNode(
                "lifecycle_decide",
                llm_client,
                LifecycleVerdict,
                ln.make_lifecycle_prompt(knowledge_pack),
                ln.lifecycle_result,
                guardrail_fn=ln.lifecycle_guardrail,
                model=model,
            )
        )
        g.add_node(
            RuleNode(
                "audit_dispatch",
                ln.make_audit_dispatch(
                    llm_client, model=model, knowledge_pack=knowledge_pack
                ),
            )
        )
    if has_reflect:
        g.add_node(
            ReflectiveNode(
                "reflect",
                decision_log,
                window=reflect_window,
                feature_keys=reflect_feature_keys,
                top_k=reflect_top_k,
            )
        )

    g.set_entry("emergency_exit")
    g.add_edge("emergency_exit", "hard_stop_loss")
    g.add_edge("hard_stop_loss", "time_stop")

    if has_llm:
        # rule + hybrid_audit go through the full deterministic ladder.
        g.add_edge(
            "time_stop",
            "trailing_stop",
            when=lambda s: s.context.config.decision_mode in ("rule", "hybrid_audit"),
        )
        if has_reflect:
            g.add_edge(
                "time_stop",
                "reflect",
                when=lambda s: s.context.config.decision_mode in ("llm", "hybrid"),
            )
            g.add_edge("reflect", "lifecycle_decide")
        else:
            g.add_edge(
                "time_stop",
                "lifecycle_decide",
                when=lambda s: s.context.config.decision_mode in ("llm", "hybrid"),
            )
        g.add_edge("lifecycle_decide", END)
        g.add_edge("trailing_stop", "tp_ladder")
        g.add_edge("tp_ladder", "rule_hold")
        g.add_edge(
            "rule_hold",
            "audit_dispatch",
            when=lambda s: s.context.config.decision_mode == "hybrid_audit",
        )
        g.add_edge(
            "rule_hold",
            END,
            when=lambda s: s.context.config.decision_mode == "rule",
        )
        g.add_edge("audit_dispatch", END)
    else:
        g.add_edge("time_stop", "trailing_stop")
        g.add_edge("trailing_stop", "tp_ladder")
        g.add_edge("tp_ladder", "rule_hold")
        g.add_edge("rule_hold", END)

    return g.compile()
