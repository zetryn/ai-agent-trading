"""Agent C — KOL Copy-Trade.

Consumes a `KOLContext` and emits a `Decision`. The bot subscribes to
KOL wallet events outside the framework, enriches the bought token's
`TokenInput`, and hands the framework a `KOLContext` per event. The
framework decides whether to copy and at what size.

Three modes, selected at build time:

  rule (default — v0.6.0)
    fast_safety → kol_quality → fast_market → sizing → END
    Pure rule, no LLM call. Latency <1ms (target for live).

  confirmed (v0.7.0; reflective loop in v0.10.0)
    fast_safety → kol_quality → fast_market → [reflect?] → analyst (LLM) → sizing → END
    An LLM analyst sees the full fact sheet AFTER the rules already
    approved the buy. It can:
      - approve the buy with size_multiplier in [0, 1.5]
      - veto the buy entirely (action=skip)
    The analyst is NOT redoing the decision — it is catching qualitative
    red flags the rules cannot encode (e.g. KOL with a dump-into-followers
    pattern, weak confluence, etc.).
    When a `decision_log` is provided (v0.10.0 / K7), a `ReflectiveNode`
    runs between `fast_market` and `analyst`. It summarises recent
    losing KOL copy-trades into a `lessons_text` block that the analyst
    prompt prepends — closing the learning loop on the strategy.

  audit (v0.9.0 / K6)
    fast_safety → kol_quality → fast_market → sizing → kol_audit_dispatch → END
    Rule sizing runs sub-ms (Decision returned to the bot immediately).
    THEN an LLM audit task is fired async — the bot awaits the task
    later, reads the verdict, and writes it to DecisionLog for offline
    tuning. The hot path is never blocked. Mirrors the sniper's
    `hybrid_audit`.

Boundary recap (see docs/plans/2026-06-25-kol-copytrade-strategy.md §0.5):
the framework defines + decides; the bot fetches and executes. The KOL
whitelist is loaded by the bot into a `KnowledgePack` and wrapped in
`KOLRegistry`, which this builder accepts. Cool-down state is also
bot-owned (passed in via `KOLContext.last_copy_ts`). When
`mode="confirmed"` or `mode="audit"` the bot also supplies an `LLMClient`.
The `decision_log` (when provided for reflection) is also bot-owned —
the bot writes outcomes back via `record_outcome` after the trade
settles; the framework only reads.
"""

from __future__ import annotations

from trading.schemas import KOLAnalystVerdict
from zetryn.core import END, Graph, RuleNode
from zetryn.knowledge import KnowledgePack
from zetryn.llm import LLMClient, LLMNode
from zetryn.memory import DecisionLog, ReflectiveNode

from ..kol_registry import KOLRegistry
from ..nodes import kol_nodes


def build_kol_copytrade(
    knowledge_pack: KnowledgePack | None = None,
    *,
    registry: KOLRegistry | None = None,
    mode: str = "rule",
    llm_client: LLMClient | None = None,
    model: str | None = None,
    decision_log: DecisionLog | None = None,
    reflect_window: int = 20,
    reflect_feature_keys: list[str] | None = None,
    reflect_top_k: int = 5,
) -> Graph:
    """Build and compile the KOL copy-trade graph.

    Args:
        knowledge_pack: A `KnowledgePack` to derive a `KOLRegistry` from.
            Either this or `registry` is required.
        registry: Pre-built `KOLRegistry` (overrides any derived from
            `knowledge_pack` when both are given).
        mode: "rule" (default), "confirmed" (LLM analyst before sizing),
            or "audit" (rule decides instantly + async LLM verify).
            "confirmed" and "audit" require `llm_client`.
        llm_client: Required when `mode` is "confirmed" or "audit". Any
            `LLMClient` implementation, including `LLMRouter`.
        model: Optional model id override forwarded to the LLM client.
        decision_log: Optional `DecisionLog` to enable the K7 reflective
            loop in `confirmed` mode. When provided, a `ReflectiveNode`
            inserted between `fast_market` and `kol_analyst` compiles a
            `lessons_text` summary from the last `reflect_window`
            decisions; the analyst prompt prepends that summary so the
            LLM is loss-pattern-aware. Has no effect in `rule` or
            `audit` mode (those modes don't run the analyst).
        reflect_window: How many of the most recent decisions to consider
            when compiling lessons. Default 20.
        reflect_feature_keys: Which scratch / outcome fields to bucket
            losers by (e.g. ["wallet", "exit_pattern", "top10_pct"]).
            None lets `ReflectiveNode` auto-pick.
        reflect_top_k: Cap on the number of loss patterns surfaced in
            the lessons block. Default 5.

    If the pack contains no `kol_whitelist.json` namespace the resulting
    registry will be empty and every incoming event will be rejected
    with `action="skip"` and a clear reason. The graph still compiles
    and runs — graceful degradation, not a crash.
    """
    if mode not in ("rule", "confirmed", "audit"):
        raise ValueError(
            f"unsupported mode: {mode!r}. Use 'rule', 'confirmed', or 'audit'."
        )
    if mode in ("confirmed", "audit") and llm_client is None:
        raise ValueError(f"mode={mode!r} requires an llm_client")
    if registry is None:
        if knowledge_pack is None:
            raise ValueError(
                "build_kol_copytrade requires either knowledge_pack or registry"
            )
        registry = KOLRegistry.from_pack(knowledge_pack)

    # Reflection only makes sense in confirmed mode (rule has no analyst to
    # condition; audit decides on rules and reflects offline via the bot).
    has_reflect = mode == "confirmed" and decision_log is not None

    g = Graph("kol_copytrade")
    g.add_node(RuleNode("fast_safety", kol_nodes.fast_safety))
    g.add_node(RuleNode("kol_quality", kol_nodes.make_kol_quality(registry)))
    g.add_node(RuleNode("fast_market", kol_nodes.fast_market))
    g.add_node(RuleNode("sizing", kol_nodes.sizing))

    if mode == "confirmed":
        g.add_node(
            LLMNode(
                "kol_analyst",
                llm_client,
                KOLAnalystVerdict,
                kol_nodes.kol_analyst_prompt,
                output_key="kol_analyst",
                fallback_fn=kol_nodes.neutral_kol_verdict,
                model=model,
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
    elif mode == "audit":
        g.add_node(
            RuleNode(
                "kol_audit_dispatch",
                kol_nodes.make_kol_audit_dispatch(
                    llm_client,
                    model=model,
                    knowledge_pack=knowledge_pack,
                ),
            )
        )

    g.set_entry("fast_safety")
    g.add_edge("fast_safety", "kol_quality")
    g.add_edge("kol_quality", "fast_market")
    if mode == "confirmed":
        if has_reflect:
            g.add_edge("fast_market", "reflect")
            g.add_edge("reflect", "kol_analyst")
        else:
            g.add_edge("fast_market", "kol_analyst")
        g.add_edge("kol_analyst", "sizing")
        g.add_edge("sizing", END)
    elif mode == "audit":
        g.add_edge("fast_market", "sizing")
        g.add_edge("sizing", "kol_audit_dispatch")
        g.add_edge("kol_audit_dispatch", END)
    else:
        g.add_edge("fast_market", "sizing")
        g.add_edge("sizing", END)
    return g.compile()