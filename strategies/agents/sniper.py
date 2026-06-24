"""Agent B — the auto-snipe agent.

Speed-first. Modes selected via ``SniperConfig.decision_mode``:

- **rule** (default): fast_safety -> fast_market -> rule_size_and_buy. Pure-rule,
  sub-millisecond, no LLM in the hot loop. ``fast_safety`` can abort instantly.
- **llm** / **hybrid**: same gates, then an ``LLMDecisionNode`` decides the entry.
  In hybrid mode a deterministic guardrail clamps/vetoes the LLM (forced abort on
  rug, hard size cap) — rules always win.
- **hybrid_audit** (M9): rule decides instantly (sub-ms) AND an async LLM audit
  is dispatched as a background task. Decision is returned to the bot immediately;
  the audit task lands in ``state.scratch['audit_task']`` for the bot to ``await``
  and persist (e.g. to ``DecisionLog``). The trading hot path is never blocked.
  This is the bridge between speed and AI brand: trades on rules, learns from AI.
"""

from __future__ import annotations

from zetryn.core import END, Graph, RuleNode
from zetryn.knowledge import KnowledgePack
from zetryn.llm import LLMClient, LLMDecisionNode

from ..nodes import sniper_nodes as sn


def build_sniper(
    llm_client: LLMClient | None = None,
    *,
    model: str | None = None,
    knowledge_pack: KnowledgePack | None = None,
) -> Graph:
    """Build and compile the sniper graph.

    If ``llm_client`` is None (or config keeps decision_mode='rule'), the LLM nodes
    are not added and the graph stays a pure-rule fast path.

    Pass ``knowledge_pack`` to layer a deployment-specific playbook on top of
    both the snipe-decide prompt and the hybrid_audit prompt.
    """
    g = Graph("memecoin_sniper")
    g.add_node(RuleNode("fast_safety", sn.fast_safety))
    g.add_node(RuleNode("fast_market", sn.fast_market))
    g.add_node(RuleNode("rule_buy", sn.rule_size_and_buy))

    has_llm = llm_client is not None
    if has_llm:
        g.add_node(
            LLMDecisionNode(
                "snipe_decide",
                llm_client,
                sn.SnipeDecision,
                sn.make_snipe_prompt(knowledge_pack),
                sn.snipe_result,
                guardrail_fn=sn.snipe_guardrail,
                model=model,
            )
        )
        g.add_node(
            RuleNode(
                "audit_dispatch",
                sn.make_audit_dispatch(
                    llm_client, model=model, knowledge_pack=knowledge_pack
                ),
            )
        )

    g.set_entry("fast_safety")
    g.add_edge("fast_safety", "fast_market")

    if has_llm:
        # rule + hybrid_audit go to rule_buy first (instant decision)
        g.add_edge(
            "fast_market",
            "rule_buy",
            when=lambda s: s.context.config.decision_mode in ("rule", "hybrid_audit"),
        )
        # llm / hybrid skip rule_buy and let the LLM decide directly
        g.add_edge(
            "fast_market",
            "snipe_decide",
            when=lambda s: s.context.config.decision_mode in ("llm", "hybrid"),
        )
        g.add_edge("snipe_decide", END)
        # hybrid_audit: after instant rule decide, fire async audit
        g.add_edge(
            "rule_buy",
            "audit_dispatch",
            when=lambda s: s.context.config.decision_mode == "hybrid_audit",
        )
        g.add_edge(
            "rule_buy",
            END,
            when=lambda s: s.context.config.decision_mode == "rule",
        )
        g.add_edge("audit_dispatch", END)
    else:
        g.add_edge("fast_market", "rule_buy")
        g.add_edge("rule_buy", END)

    return g.compile()
