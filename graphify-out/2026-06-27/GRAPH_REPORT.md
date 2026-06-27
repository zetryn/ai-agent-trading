# Graph Report - ai-agent  (2026-06-27)

## Corpus Check
- 133 files · ~88,714 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2342 nodes · 7071 edges · 103 communities (91 shown, 12 thin omitted)
- Extraction: 76% EXTRACTED · 24% INFERRED · 0% AMBIGUOUS · INFERRED: 1711 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `33bf4591`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_LLM Key Pool & Config|LLM Key Pool & Config]]
- [[_COMMUNITY_LLM Client & Guardrails|LLM Client & Guardrails]]
- [[_COMMUNITY_KOL Copy-Trade Example|KOL Copy-Trade Example]]
- [[_COMMUNITY_KOL Audit Mode Tests|KOL Audit Mode Tests]]
- [[_COMMUNITY_Rate Limit & LLM Router|Rate Limit & LLM Router]]
- [[_COMMUNITY_Knowledge Pack System|Knowledge Pack System]]
- [[_COMMUNITY_KOL Strategy Agent|KOL Strategy Agent]]
- [[_COMMUNITY_Backtester & Runner|Backtester & Runner]]
- [[_COMMUNITY_Core Graph & Edges|Core Graph & Edges]]
- [[_COMMUNITY_State Machine & Memory|State Machine & Memory]]
- [[_COMMUNITY_Examples & Shared Types|Examples & Shared Types]]
- [[_COMMUNITY_Scanner Agent & Analyst|Scanner Agent & Analyst]]
- [[_COMMUNITY_Analyst Prompt Engine|Analyst Prompt Engine]]
- [[_COMMUNITY_Auth & Subscription|Auth & Subscription]]
- [[_COMMUNITY_Router Tier & Tests|Router Tier & Tests]]
- [[_COMMUNITY_Capabilities & Docs|Capabilities & Docs]]
- [[_COMMUNITY_Agent Registry & Graph|Agent Registry & Graph]]
- [[_COMMUNITY_KOL Nodes & Fast Market|KOL Nodes & Fast Market]]
- [[_COMMUNITY_Sniper Agent|Sniper Agent]]
- [[_COMMUNITY_Tool Use Node & Tests|Tool Use Node & Tests]]
- [[_COMMUNITY_KOL Confirmed Mode Tests|KOL Confirmed Mode Tests]]
- [[_COMMUNITY_Decision Log & Reflection|Decision Log & Reflection]]
- [[_COMMUNITY_Sniper Nodes & Decisions|Sniper Nodes & Decisions]]
- [[_COMMUNITY_KOL Reflective Loop Tests|KOL Reflective Loop Tests]]
- [[_COMMUNITY_LLM Router & Entry Tests|LLM Router & Entry Tests]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]
- [[_COMMUNITY_Community 89|Community 89]]
- [[_COMMUNITY_Community 90|Community 90]]
- [[_COMMUNITY_Community 91|Community 91]]
- [[_COMMUNITY_Community 92|Community 92]]
- [[_COMMUNITY_Community 93|Community 93]]
- [[_COMMUNITY_Community 94|Community 94]]
- [[_COMMUNITY_Community 95|Community 95]]
- [[_COMMUNITY_Community 96|Community 96]]
- [[_COMMUNITY_Community 97|Community 97]]
- [[_COMMUNITY_Community 98|Community 98]]
- [[_COMMUNITY_Community 99|Community 99]]
- [[_COMMUNITY_Community 100|Community 100]]
- [[_COMMUNITY_Community 101|Community 101]]
- [[_COMMUNITY_Community 102|Community 102]]

## God Nodes (most connected - your core abstractions)
1. `State` - 218 edges
2. `LLMResult` - 212 edges
3. `Message` - 209 edges
4. `State` - 155 edges
5. `LLMError` - 139 edges
6. `ContractData` - 92 edges
7. `Decision` - 92 edges
8. `MarketData` - 91 edges
9. `HolderData` - 91 edges
10. `WalletIntel` - 85 edges

## Surprising Connections (you probably didn't know these)
- `LLMClient` --uses--> `GrowthVerdict`  [INFERRED]
  strategies/agents/growth_detector.py → trading/schemas.py
- `str` --uses--> `GrowthVerdict`  [INFERRED]
  strategies/agents/growth_detector.py → trading/schemas.py
- `KnowledgePack` --uses--> `GrowthVerdict`  [INFERRED]
  strategies/agents/growth_detector.py → trading/schemas.py
- `DecisionLog` --uses--> `FullAnalysis`  [INFERRED]
  strategies/agents/scanner.py → trading/schemas.py
- `Graph` --uses--> `FullAnalysis`  [INFERRED]
  strategies/agents/scanner.py → trading/schemas.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Closed Learning Loop Pipeline** — readme_decision_log, readme_reflective_node, readme_knowledge_pack, readme_build_scanner [EXTRACTED 0.95]
- **Scanner Hard-Gate Filtering Pipeline** — readme_safety_gate, readme_intel_gate, readme_market_gate, readme_guardrail [EXTRACTED 1.00]
- **LLM Failover and Throttle Stack** — readme_llm_router, capabilities_router_entry, readme_key_pool, capabilities_rate_limit [EXTRACTED 1.00]

## Communities (103 total, 12 thin omitted)

### Community 0 - "LLM Key Pool & Config"
Cohesion: 0.12
Nodes (36): Command, DipBuyVerdict, _abort(), _audit_prompt(), _dip_facts(), dip_gate(), dip_guardrail(), dip_prompt() (+28 more)

### Community 1 - "LLM Client & Guardrails"
Cohesion: 0.09
Nodes (55): DecisionFallbackFn, GuardrailFn, LLMClient, The thin LLM client abstraction.  A single small interface lets nodes stay provi, Minimal completion interface.      ``tools`` accepts a list of OpenAI function-c, LLMDecisionNode, LLMNode, LLMNode — an advisor step backed by an LLM with structured output.  Lives in the (+47 more)

### Community 2 - "KOL Copy-Trade Example"
Cohesion: 0.15
Nodes (44): _build_groq_client(), _decide(), _discover_keys(), _load_env_file(), main(), KOLContext, Path, str (+36 more)

### Community 3 - "KOL Audit Mode Tests"
Cohesion: 0.14
Nodes (46): BaseModel, KOLBuyEvent, test_market_gate_rejects_high_top10(), test_market_gate_rejects_low_liquidity(), KnowledgePack, KOLContext, Path, bool (+38 more)

### Community 4 - "Rate Limit & LLM Router"
Cohesion: 0.13
Nodes (31): RateLimit, Per-model limits. None means unlimited. Real numbers come from the platform., _build_router_client(), LLMClient, Build an LLMRouter covering whichever providers have keys configured.      Retur, LLMRouter, One provider in the router's failover chain., Failover router that satisfies the `LLMClient` protocol. (+23 more)

### Community 5 - "Knowledge Pack System"
Cohesion: 0.08
Nodes (31): Static knowledge injection at agent build time.  A `KnowledgePack` loads markdow, KnowledgePack, KnowledgePackError, Filesystem-backed knowledge pack loader.  Layout (all keys optional — missing su, Raised when a pack cannot be loaded (missing dir, bad JSON, etc.)., An immutable bundle of static knowledge loaded from a directory.      Use `Knowl, One system message per markdown file, in filename order., All markdown blocks merged into a single system message.          Returns None i (+23 more)

### Community 6 - "KOL Strategy Agent"
Cohesion: 0.16
Nodes (26): _audit_payload(), _ctx(), _pack(), K6 tests — KOL copy-trade `audit` mode.  The audit-mode graph runs rule sizing f, Decision is set BEFORE the audit task completes (sub-ms latency)., Awaiting the task returns a parsed KOLAnalystVerdict., An approve=False verdict is informational only — bot already traded., LLM error becomes a verdict with audit_failed concern — never raises. (+18 more)

### Community 7 - "Backtester & Runner"
Cohesion: 0.12
Nodes (38): Backtester, Runs a graph over a dataset and returns a :class:`BacktestResult`., main(), LLMResult, Message, Example: backtest the scanner over a small historical dataset.  Runs offline (st, _StubLLM, HistoricalCase (+30 more)

### Community 8 - "Core Graph & Edges"
Cohesion: 0.13
Nodes (33): Generic backtest harness.  Runs a compiled graph over a dataset of (id, context), Condition, Edge, Conditional transitions between nodes., A directed, optionally conditional transition.      The engine evaluates a node', GraphExecutionError, GraphValidationError, The graph engine: compile nodes + edges into a runnable agent.  Routing rule: if (+25 more)

### Community 9 - "State Machine & Memory"
Cohesion: 0.11
Nodes (32): Data flowing through the graph.      Attributes:         context: Input supplied, State, Emit, main(), Example: scanner + observability (logging hooks) + memory (blacklist, decision l, Observability: structured logging hooks + trace serialization., _default_emit(), logging_hooks() (+24 more)

### Community 10 - "Examples & Shared Types"
Cohesion: 0.09
Nodes (52): ProviderConfig, Provider configuration.  Config stores only the *names* of environment variables, Describes one OpenAI-compatible provider., Resolve keys. Literal ``keys`` win (testing); else read ``key_envs`` from env., LLM layer: provider-agnostic advisor calls with structured output., Mandatory API-key pool with rotation.  Free-tier providers rate-limit aggressive, OpenAICompatibleClient, OpenAI-compatible LLM client.  One adapter covers Groq, OpenRouter, and Gemini's (+44 more)

### Community 11 - "Scanner Agent & Analyst"
Cohesion: 0.15
Nodes (22): build_scanner(), Build and compile the AI-first scanner graph.      With an LLM client the flow i, DecisionLog, Graph, int, KnowledgePack, LLMClient, str (+14 more)

### Community 12 - "Analyst Prompt Engine"
Cohesion: 0.16
Nodes (19): _pack(), Path, Integration tests: KnowledgePack injection into scanner / sniper prompts., When no pack and no lessons are present, output equals analyst_prompt., An empty pack adds no blocks; output equals analyst_prompt., Captures the messages sent to the LLM so we can assert injection., _RecordingLLM, _SnipeLLM (+11 more)

### Community 13 - "Auth & Subscription"
Cohesion: 0.10
Nodes (26): Subscription auth seam that gates access to the Zetryn agent + models., Entitlement, License, LocalSubscriptionAuth, Subscription auth seam.  Gates access to the Zetryn agent + hosted models. The d, Lightweight, cached license validation — NOT per-run.      Validates once, cache, Result of verifying a subscription key., Verifies a subscription key and returns what it entitles. (+18 more)

### Community 14 - "Router Tier & Tests"
Cohesion: 0.08
Nodes (30): build_tier_entries(), get_free_tier_limit(), Look up a preset by provider + model. Returns None if unknown.      For OpenRout, Materialise a tier preset into a list of RouterEntry.      The caller is respons, test_get_free_tier_limit_exact_match(), test_get_free_tier_limit_openrouter_free_suffix(), test_get_free_tier_limit_unknown_returns_none(), _FakeClient (+22 more)

### Community 15 - "Capabilities & Docs"
Cohesion: 0.11
Nodes (24): Agent A — Scanner, Agent B — Sniper, AI-First Design Philosophy, build_scanner, Decision, DecisionLog, Strict Dependency Rule, FullAnalysis (+16 more)

### Community 16 - "Agent Registry & Graph"
Cohesion: 0.13
Nodes (27): Agent C — KOL Copy-Trade.  Consumes a `KOLContext` and emits a `Decision`. The b, Agent B — the auto-snipe agent.  Speed-first. Modes selected via ``SniperConfig., Graph, A directed graph of nodes that runs to produce a final ``State``., Raise on hard errors; return a list of soft warnings., AgentNode, Deterministic step backed by a plain Python function.      The function mutates, Extension point: a node whose work is another graph (sub-agent).      The sub-gr (+19 more)

### Community 17 - "KOL Nodes & Fast Market"
Cohesion: 0.07
Nodes (60): bool, float, KnowledgePack, KOLAnalystVerdict, KOLRegistry, LLMClient, Message, _abort() (+52 more)

### Community 18 - "Sniper Agent"
Cohesion: 0.09
Nodes (32): build_sniper(), Build and compile the sniper graph.      If ``llm_client`` is None (or config ke, main(), Example: the auto-snipe agent in pure-rule (fast) vs LLM/hybrid mode.  Shows the, _StubLLM, Graph, KnowledgePack, LLMClient (+24 more)

### Community 19 - "Tool Use Node & Tests"
Cohesion: 0.16
Nodes (13): test_registry_unknown_tool_is_graceful(), Tool, ToolResult, Generic tool machinery (chain-agnostic). Domain providers live in ``trading``., A registry of tools the caller injects for agent/LLM nodes to use., Holds named tools and runs them by name (safely)., ToolRegistry, Generic tool abstraction.  A tool is an open-ended capability an LLM/agent node (+5 more)

### Community 20 - "KOL Confirmed Mode Tests"
Cohesion: 0.18
Nodes (24): _ctx(), _pack(), K5 tests — KOL copy-trade `confirmed` mode (LLM analyst before sizing).  Uses sc, Analyst approves at multiplier=1.0 → final size = rule size., multiplier=0.5 cuts the rule size in half., multiplier=1.5 boosts above rule size (still clamped at max_size)., approve=False → action becomes 'skip' even though rules approved., LLM error → neutral_kol_verdict fallback (approve True, mult 1.0). (+16 more)

### Community 21 - "Decision Log & Reflection"
Cohesion: 0.18
Nodes (8): Anything the engine can execute as a sub-graph (duck-typed Graph)., Runnable, Protocol, RuleFn, Any, Command, State, str

### Community 22 - "Sniper Nodes & Decisions"
Cohesion: 0.12
Nodes (29): _audit_prompt(), fast_market(), fast_safety(), _latency_ms(), make_audit_dispatch(), make_snipe_prompt(), Nodes for the auto-snipe agent.  Speed-first: pure-rule gates that can abort in, Return a snipe prompt builder that prepends a knowledge pack's blocks. (+21 more)

### Community 23 - "KOL Reflective Loop Tests"
Cohesion: 0.18
Nodes (23): _CapturingLLM, _ctx(), _pack(), DecisionLog, Path, K7 tests — KOL Copy-Trade x ReflectiveNode integration.  The reflective loop:, Write 3 KOL copy-trade losers with a common 'exit_pattern' feature     that the, Rule mode should accept (and ignore) decision_log without error. (+15 more)

### Community 24 - "LLM Router & Entry Tests"
Cohesion: 0.09
Nodes (48): build_confluence(), Build and compile the Smart Money Confluence graph.      Signature mirrors ``bui, SmartWalletAccumulation, _AuditLLM, _ctx(), _event(), _FakeLLM, ConfluenceContext (+40 more)

### Community 25 - "Community 25"
Cohesion: 0.14
Nodes (12): KOLProfile, KOLRegistry, Any, bool, float, int, KnowledgePack, str (+4 more)

### Community 26 - "Community 26"
Cohesion: 0.08
Nodes (44): DecisionLog, A generic decision log built on a MemoryStore.  Stores one record per run (plain, Persistent memory: pluggable key-value store + blacklist + decision log., _infer_feature_keys(), _is_numeric(), Pattern, _quartile_label(), Reflective node: read past decisions, extract loss patterns, inject lessons.  `R (+36 more)

### Community 27 - "Community 27"
Cohesion: 0.16
Nodes (27): build_kol_copytrade(), Build and compile the KOL copy-trade graph.      Args:         knowledge_pack: A, DecisionLog, Graph, int, KnowledgePack, KOLRegistry, LLMClient (+19 more)

### Community 28 - "Community 28"
Cohesion: 0.06
Nodes (67): build_graduation(), Build and compile the graduation snipe graph.      Signature mirrors ``build_sni, _llm_client(), main(), _make_event(), GraduationEvent, LLMResult, Message (+59 more)

### Community 29 - "Community 29"
Cohesion: 0.15
Nodes (16): Integration tests: ReflectiveNode wired into the scanner closes the learning loo, Reflect must not waste a memory read on tokens rejected by hard gates., Layering order: pack blocks first, then lessons, then analyst persona., reflect_window caps how many past records are summarised., Captures the messages the analyst sees so we can assert injection., Backwards-compat: an LLM-only build does not run the reflect node., With an empty log, reflect runs but lessons_text says 'no prior'., Real test: past losing decisions become a lessons block in the prompt. (+8 more)

### Community 30 - "Community 30"
Cohesion: 0.08
Nodes (23): Agent E — Smart Money Confluence (v0.14.0 / S5).  Fires when ≥ N pre-vetted smar, Agent F — Early-Stage Dip Buy (v0.15.0 / S6).  One agent, two events. After a Pu, Agent D — Pump.fun graduation snipe (v0.12.0).  When a Pump.fun token graduates, Agent G — Organic Growth Detector (v0.16.0 / A1).  Triage filter — classifies a, Agent E — Position Lifecycle Helpers (v0.13.0 / PL1).  First position-management, Any, make_confluence_gate(), Factory: binds an optional `SmartWalletRegistry` to the gate node.      When `re (+15 more)

### Community 31 - "Community 31"
Cohesion: 0.19
Nodes (9): _expired(), JSONFileStore, Simple cross-run persistence to a single JSON file.      Loads on init, writes o, test_json_file_store_persists(), Any, bool, float, Path (+1 more)

### Community 32 - "Community 32"
Cohesion: 0.16
Nodes (27): Graph node that runs `tool_use_loop` and stores the result.      By default writ, ToolUseNode, ToolRegistry, Tests for the LLM tool-use loop and ToolUseNode., Tool errors do not crash the loop — they become a tool-role message., A model emitting malformed tool args is reported as tool failure, not crash., Model that never stops calling tools is bounded by max_iterations., Returns canned LLMResult objects in sequence, optionally raising. (+19 more)

### Community 33 - "Community 33"
Cohesion: 0.25
Nodes (7): A-tier — validated, narrower constraints, C-tier — rejected with reason (do NOT re-propose without new evidence), Notes, S-tier — proven by mainstream Solana pro traders, Solana Memecoin Strategy Catalog, Three-question gate for proposing a new strategy, Tier rubric

### Community 34 - "Community 34"
Cohesion: 0.23
Nodes (13): _build_llm(), _discover_keys(), _load_env_file(), main(), print_analysis(), print_input(), print_output(), print_processing() (+5 more)

### Community 35 - "Community 35"
Cohesion: 0.11
Nodes (41): LifecycleVerdict, _audit_prompt(), _decision(), emergency_exit(), _facts(), _hard_emit(), _hard_short_circuit_target(), hard_stop_loss() (+33 more)

### Community 36 - "Community 36"
Cohesion: 0.04
Nodes (55): LLMResult, Message, LLMResult, Message, LLMResult, Message, LLMResult, Message (+47 more)

### Community 37 - "Community 37"
Cohesion: 0.06
Nodes (71): build_lifecycle(), Build and compile the position-lifecycle graph.      Signature mirrors `build_sn, _llm_client(), main(), LLMResult, Message, Example: position-lifecycle helpers (v0.13.0 / PL1).  Offline by default (stub L, _StubLLM (+63 more)

### Community 38 - "Community 38"
Cohesion: 0.17
Nodes (18): _clamp(), intel_gate(), market_gate(), momentum_scorer(), pumpfun_context(), Deterministic rule nodes for the scanner.  Each reads the pushed ``TokenInput``, Score based on smart-money / KOL presence, penalised by sniper density., Compute pumpfun-specific flags. No-op for non-pumpfun tokens. (+10 more)

### Community 39 - "Community 39"
Cohesion: 0.20
Nodes (11): Generic backtest harness: replay a graph over a historical dataset., BacktestResult, _get(), One backtested item: the decision produced and the known outcome (if any)., Domain-agnostic: count decisions by their ``action`` attribute/key., Read ``key`` from a pydantic model, dataclass, dict, or object., RunRecord, MetricsFn (+3 more)

### Community 40 - "Community 40"
Cohesion: 0.19
Nodes (16): _ctx(), _payload(), str, Integration tests: `LLMRouter` is a drop-in `LLMClient` for the scanner.  The sc, After a 429, the primary stays on cooldown for the next scan too., Pack injection works regardless of whether LLMClient is router or bare., An `LLMClient` that returns a fixed text — or raises a scripted error., Single-entry router behaves like a bare LLMClient. (+8 more)

### Community 41 - "Community 41"
Cohesion: 0.23
Nodes (10): _build_router(), _discover_keys(), LLMResult, LLMRouter, Message, str, Example: scanner driven by `LLMRouter` with multi-provider failover.  This is th, Fallback when no provider keys are configured. (+2 more)

### Community 42 - "Community 42"
Cohesion: 0.29
Nodes (12): _build_router(), _decide(), _discover_keys(), _enriched_token(), _load_env_file(), main(), Path, str (+4 more)

### Community 43 - "Community 43"
Cohesion: 0.32
Nodes (8): [0.11.0] — 2026-06-27, [0.12.0] — 2026-06-27, Added, Added, Added, Fixed, Notes, Notes

### Community 44 - "Community 44"
Cohesion: 0.10
Nodes (20): 0. Context, 1. What This Solves, 2. Framework Boundary, 3.1 `GraduationEvent`, 3.2 `GraduationConfig`, 3.3 `GraduationContext`, 3.4 `GraduationVerdict`, 3. Schema (`trading/schemas.py`) (+12 more)

### Community 45 - "Community 45"
Cohesion: 0.14
Nodes (13): 0. Summary, 1. Boundary recap, 2. Schemas (`trading/schemas.py`), 3. Graph design, 4. Decision modes, 5. Open questions resolved, `DipBuyConfig`, `DipBuyContext` (+5 more)

### Community 46 - "Community 46"
Cohesion: 0.29
Nodes (7): _EchoLLM, main(), Path, Example: run the scanner with a deployment-specific KnowledgePack.  A `Knowledge, Stub LLM that echoes the system prompt it received via the reasoning field., Write a minimal pack: two markdown rules + a JSON blacklist., _seed_pack()

### Community 47 - "Community 47"
Cohesion: 0.11
Nodes (18): 1. Capability Matrix, 2. Gap Analysis (before P1–P4), 3. Foundation Work to Do Before P1, 4. Summary, 5. M8 closeout — Scanner v2 hardening, 6. Roadmap, ~~F1. `KnowledgePack` loader~~ — **Done (2026-06-24)**, ~~F2. `ReflectiveNode`~~ — **Done (2026-06-24)** (+10 more)

### Community 48 - "Community 48"
Cohesion: 0.11
Nodes (17): Architecture, Auth seam (`zetryn/auth/`), Backtest (`zetryn/backtest/`), Commands, Commit identity (ROLLING RANDOM — no need to ask), Core engine (`zetryn/core/`), Dependency rules (strict), Documentation conventions (MUST FOLLOW) (+9 more)

### Community 49 - "Community 49"
Cohesion: 0.10
Nodes (33): ConfluenceVerdict, Graph, _abort(), _audit_prompt(), _confluence_facts(), confluence_guardrail(), confluence_prompt(), confluence_result() (+25 more)

### Community 50 - "Community 50"
Cohesion: 0.67
Nodes (4): KeyPool, LLMRouter, OpenAICompatibleClient, ProviderConfig

### Community 51 - "Community 51"
Cohesion: 0.13
Nodes (32): Decision, GraduationVerdict, _abort(), _audit_prompt(), _grad_facts(), _grad_lessons_block(), graduation_gate(), graduation_guardrail() (+24 more)

### Community 52 - "Community 52"
Cohesion: 0.08
Nodes (23): 0. Context, 1. What this solves, 2. Framework Boundary, 3.1 `PositionState`, 3.2 `LifecycleConfig`, 3.3 `PositionContext`, 3.4 `LifecycleVerdict` (LLM structured output for llm/hybrid), 3.5 `Decision` (extend existing) (+15 more)

### Community 53 - "Community 53"
Cohesion: 0.10
Nodes (20): 0. Context, 1. What This Solves, 2. Framework Boundary, 3.1 `GraduationEvent`, 3.2 `GraduationConfig`, 3.3 `GraduationContext`, 3.4 `GraduationVerdict`, 3. Schema (`trading/schemas.py`) (+12 more)

### Community 54 - "Community 54"
Cohesion: 0.23
Nodes (12): _apply_guardrails(), finalize(), _latency_ms(), Reject and finalize nodes that produce the final ``Decision``.  In the M8 AI-fir, Produce a skip Decision when a hard gate fails. Names the failure., Return possibly-demoted analysis + list of guardrail messages.      Guardrails o, Convert the analyst's ``FullAnalysis`` into the final ``Decision``., reject() (+4 more)

### Community 55 - "Community 55"
Cohesion: 0.40
Nodes (4): Return a deep copy of the current scratch for tracing., Apply a ``Command.update`` to scratch (shallow merge)., Any, str

### Community 56 - "Community 56"
Cohesion: 0.67
Nodes (3): Backtester, DataProvider, HistoricalDataProvider

### Community 57 - "Community 57"
Cohesion: 0.67
Nodes (3): State, TokenInput, TradingContext

### Community 59 - "Community 59"
Cohesion: 0.06
Nodes (66): build_organic_detector(), Build and compile the Organic Growth Detector graph.      Signature mirrors othe, DecisionLog, main(), GrowthSnapshot, LLMResult, Message, Example: Organic Growth Detector agent (v0.16.0 / A1).  Offline by default (stub (+58 more)

### Community 71 - "Community 71"
Cohesion: 0.18
Nodes (9): Blacklist, A generic blacklist built on a MemoryStore.  Keys (token mints, dev wallets, any, MemoryStore, Persistent memory: a small key-value interface with pluggable backends.  The fra, Namespaced key-value store., bool, float, MemoryStore (+1 more)

### Community 72 - "Community 72"
Cohesion: 0.08
Nodes (40): KeyPool, Round-robin pool of API keys with per-key cooldown on rate limit., Return the next available key, skipping those still cooling down., Put a key on cooldown after a rate-limit response., user(), _chat_response(), _FakeClient, LLMResult (+32 more)

### Community 74 - "Community 74"
Cohesion: 0.12
Nodes (16): 0. Summary, 1. Boundary recap, 2. Schemas (`trading/schemas.py`), 3. SmartWalletRegistry (`strategies/smart_wallet_registry.py`), 4. Graph design, 5. Decision modes, 6. Open questions resolved, `ConfluenceConfig` (+8 more)

### Community 76 - "Community 76"
Cohesion: 0.12
Nodes (32): AuditVerdict, GrowthVerdict, int, _abort(), _audit_prompt(), _emit(), _growth_facts(), growth_guardrail() (+24 more)

### Community 77 - "Community 77"
Cohesion: 0.24
Nodes (10): InMemoryStore, Zero-setup dict-backed store. Default for tests and ephemeral runs., Tests for the M4 memory layer., test_blacklist(), test_decision_log_and_stats(), test_inmemory_put_get_delete(), test_inmemory_ttl_expiry(), test_query_returns_unexpired() (+2 more)

### Community 78 - "Community 78"
Cohesion: 0.16
Nodes (23): Agent A — the memecoin scanner + scorer (M8 AI-first).  Flow (M8 pivot to AI-fir, system(), analyst_prompt(), _lessons_block(), make_analyst_prompt(), neutral_analysis(), AI analyst — the single LLM call that drives M8 scanner decisions.  Replaces the, Return a system message with the reflection summary, or None if absent. (+15 more)

### Community 79 - "Community 79"
Cohesion: 0.15
Nodes (17): Tests for the M2 generic tool system., test_registry_register_and_call(), test_registry_rejects_duplicate(), test_tool_graceful_on_exception(), test_tool_runs_async_fn(), test_tool_runs_sync_fn(), test_tool_timeout(), test_tool_validates_input_schema() (+9 more)

### Community 80 - "Community 80"
Cohesion: 0.32
Nodes (4): Aggregate counts by action and PnL stats from recorded outcomes., Any, MemoryStore, str

### Community 82 - "Community 82"
Cohesion: 0.12
Nodes (24): Path, str, Tests for K1 (KOL schemas) and K2 (KOLRegistry from KnowledgePack)., _seed_pack(), test_kol_buy_event_rejects_negative_size(), test_kol_buy_event_required_fields(), test_kol_context_round_trip(), test_kol_copytrade_config_defaults() (+16 more)

### Community 83 - "Community 83"
Cohesion: 0.16
Nodes (14): ConfluenceConfig, _build_event(), _build_registry(), main(), ConfluenceEvent, LLMResult, Message, SmartWalletRegistry (+6 more)

### Community 84 - "Community 84"
Cohesion: 0.50
Nodes (4): [0.5.0] — 2026-06-25, Added, Changed, Notes

### Community 85 - "Community 85"
Cohesion: 0.20
Nodes (7): Sliding-window counters for one router entry., Return True if a new request is allowed under current limits., Record a successful request with its token usage., _Throttle, bool, float, int

### Community 86 - "Community 86"
Cohesion: 0.14
Nodes (13): 0. Summary, 1. Boundary recap, 2. Integration pattern, 3. Schemas (`trading/schemas.py`), 4. Graph design, 5. Open questions resolved, A1 — Organic Growth Detector, `GrowthConfig` (+5 more)

### Community 87 - "Community 87"
Cohesion: 0.40
Nodes (5): [0.7.0] — 2026-06-25, Added, Changed, Notes, Verified end-to-end

### Community 88 - "Community 88"
Cohesion: 0.40
Nodes (5): [0.9.0] — 2026-06-26, Added, Backwards compatibility, Notes, Verified end-to-end

### Community 89 - "Community 89"
Cohesion: 0.25
Nodes (7): [0.1.0] — 2026-06-24, [0.6.0] — 2026-06-25, Added, Added, Changed, Changelog, Notes

### Community 90 - "Community 90"
Cohesion: 0.50
Nodes (4): [0.10.0] — 2026-06-26, Added, Notes, Verified end-to-end

### Community 91 - "Community 91"
Cohesion: 0.25
Nodes (8): [0.2.0] — 2026-06-24, [0.3.0] — 2026-06-25, Added, Added, Changed, Changed, Notes, Notes

### Community 92 - "Community 92"
Cohesion: 0.50
Nodes (4): [0.4.0] — 2026-06-25, Added, Changed, Notes

### Community 93 - "Community 93"
Cohesion: 0.24
Nodes (10): _build_provider(), _discover_keys(), _load_env_file(), main(), int, ProviderConfig, str, Latency benchmark for the scanner with a real LLM provider.  Validates M8 accept (+2 more)

### Community 94 - "Community 94"
Cohesion: 0.50
Nodes (4): [0.8.0] — 2026-06-25, Added, Backwards compatibility, Notes

### Community 95 - "Community 95"
Cohesion: 0.21
Nodes (8): check_rug(), main(), Message, Example: LLM-driven tool-use loop wired into an analyst-style decision.  Demonst, Pretend RugCheck lookup. In production this would be a real API call., 3-turn scripted conversation: call rug check → call smart money → emit verdict., _registry(), _ScriptedToolUseLLM

### Community 96 - "Community 96"
Cohesion: 0.07
Nodes (58): build_dip_buy(), Build and compile the Early-Stage Dip Buy graph.      Signature mirrors ``build_, main(), DipBuySnapshot, LLMResult, Message, Example: Early-Stage Dip Buy agent (v0.15.0 / S6).  Offline by default (stub LLM, _run_case() (+50 more)

### Community 97 - "Community 97"
Cohesion: 0.15
Nodes (15): Typed lookup of KOL profiles from a `KnowledgePack`.  The bot ships a `kol_white, str, TokenInput, Sample tokens + an in-memory provider for tests, demos, and (later) backtests., Implements the DataProvider pull protocol over the sample set., SampleProvider, Trading domain contract — the shared schemas both the framework consumers and th, DataProvider (+7 more)

### Community 98 - "Community 98"
Cohesion: 0.25
Nodes (8): [0.14.0] — 2026-06-27, [0.15.0] — 2026-06-27, [0.16.0] — 2026-06-27, Added, Added, Design notes, Design notes, Design notes

### Community 99 - "Community 99"
Cohesion: 0.31
Nodes (10): NarrativeScore, narrative_prompt(), neutral_narrative(), Prompt builder + fallback for the narrative LLM advisor node.  Prompts are kept, Conservative fallback when the LLM is unavailable., Exception, Message, State (+2 more)

### Community 100 - "Community 100"
Cohesion: 0.60
Nodes (3): main(), Example: how a bot calls the zetryn scanner.  Runs fully offline with a stub LLM, _StubLLM

### Community 101 - "Community 101"
Cohesion: 0.67
Nodes (3): [0.13.0] — 2026-06-27, Added, Design notes

## Knowledge Gaps
- **235 isolated node(s):** `Added`, `Design notes`, `Added`, `Design notes`, `Added` (+230 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `State` connect `State Machine & Memory` to `LLM Client & Guardrails`, `KOL Copy-Trade Example`, `KOL Strategy Agent`, `Core Graph & Edges`, `Scanner Agent & Analyst`, `Analyst Prompt Engine`, `Agent Registry & Graph`, `KOL Nodes & Fast Market`, `Sniper Agent`, `KOL Confirmed Mode Tests`, `Decision Log & Reflection`, `Sniper Nodes & Decisions`, `KOL Reflective Loop Tests`, `Community 26`, `Community 27`, `Community 29`, `Community 32`, `Community 34`, `Community 38`, `Community 40`, `Community 41`, `Community 42`, `Community 46`, `Community 54`, `Community 55`, `Community 72`, `Community 78`, `Community 93`, `Community 95`, `Community 99`, `Community 100`, `Community 102`?**
  _High betweenness centrality (0.168) - this node is a cross-community bridge._
- **Why does `State` connect `Community 35` to `Community 96`, `LLM Key Pool & Config`, `KOL Audit Mode Tests`, `Community 37`, `Community 76`, `Community 49`, `KOL Nodes & Fast Market`, `Community 83`, `Community 51`, `LLM Router & Entry Tests`, `Community 59`, `Community 28`, `Community 30`?**
  _High betweenness centrality (0.147) - this node is a cross-community bridge._
- **Why does `LLMResult` connect `Community 36` to `LLM Client & Guardrails`, `KOL Audit Mode Tests`, `Rate Limit & LLM Router`, `KOL Strategy Agent`, `Backtester & Runner`, `State Machine & Memory`, `Examples & Shared Types`, `Scanner Agent & Analyst`, `Analyst Prompt Engine`, `Router Tier & Tests`, `Sniper Agent`, `KOL Confirmed Mode Tests`, `KOL Reflective Loop Tests`, `Community 29`, `Community 32`, `Community 34`, `Community 40`, `Community 41`, `Community 46`, `Community 72`, `Community 78`, `Community 85`, `Community 95`, `Community 100`?**
  _High betweenness centrality (0.093) - this node is a cross-community bridge._
- **Are the 140 inferred relationships involving `State` (e.g. with `_run_case()` and `_run_case()`) actually correct?**
  _`State` has 140 INFERRED edges - model-reasoned connections that need verification._
- **Are the 180 inferred relationships involving `LLMResult` (e.g. with `LLMResult` and `Message`) actually correct?**
  _`LLMResult` has 180 INFERRED edges - model-reasoned connections that need verification._
- **Are the 206 inferred relationships involving `Message` (e.g. with `DecisionFallbackFn` and `LLMResult`) actually correct?**
  _`Message` has 206 INFERRED edges - model-reasoned connections that need verification._
- **Are the 44 inferred relationships involving `State` (e.g. with `Condition` and `Edge`) actually correct?**
  _`State` has 44 INFERRED edges - model-reasoned connections that need verification._