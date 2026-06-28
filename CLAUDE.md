# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Documentation conventions (MUST FOLLOW)

Two places, no third:

| Change type | Where to document |
|---|---|
| Roadmap feature (new strategy, new core capability, items in `CAPABILITIES.md §6`) | **One** markdown file in `docs/plans/YYYY-MM-DD-<slug>.md`. Include `**Date:**` and `**Status:**` headers. Also add a row to `docs/plans/README.md`. |
| Anything else (refactor, bugfix, doc cleanup, tooling, dep bump) | Append **one row** to `docs/maintenance-log.md` (newest on top). Columns: Date, Description, Action, Before, After. |
| User-facing release notes (semver tagged) | `CHANGELOG.md` at repo root. |
| Strategy questions ("what's next?", "what exists?", "S-tier ideas?") | Consult `docs/STRATEGIES.md` first — it's the catalog of shipped + planned + rejected strategies. Do NOT propose new strategies without checking it. Update it when a strategy ships or a new one is approved. |

**Hard rule — DO NOT create `docs/superpowers/` or `docs/superpowers/specs/` again.** That layout was retired on 2026-06-27 because it duplicated `docs/plans/` and burned tokens drafting in one place only to move it later. Write the design doc directly in `docs/plans/` from the start.

**Do NOT** create ad-hoc `*.md` files outside these three locations (no `NOTES.md`, no `TODO.md`, no per-feature READMEs scattered through the source tree). If unsure where something belongs, default to `docs/maintenance-log.md`.

## Framework Boundary (NON-NEGOTIABLE — read first, every session)

**Zetryn Trading is an AI Agent Framework / library.** Public users (their
bots) consume it: they push input (already-filtered or not), the framework
returns a `Decision`, and the bot acts on it. Nothing in this repository
should ever try to *fetch data*, *subscribe to feeds*, *hold keys*, *sign
transactions*, *track positions*, or *execute trades*. All of that is the
caller's responsibility.

| The framework DOES | The user's bot DOES |
|---|---|
| Define input/output schemas (`TokenInput`, `KOLContext`, `Decision`, …) | Fetch / stream / enrich the data and fill those schemas |
| Orchestrate the decision graph (nodes, edges, LLM calls, tool-use loops) | Subscribe to Helius / Cielo / GMGN / WS / RPC feeds |
| Run LLM analyst calls and forward `tools` to providers | Implement each `Tool`'s async function against its data source |
| Read `KnowledgePack` files the user shipped | Author & maintain those files (KOL whitelists, rules, lessons) |
| Read `DecisionLog` for reflection / lessons | Call `record_outcome` after the trade is executed |
| Return a `Decision` (action, size, reasons, flags) | Execute the trade, sign tx, manage slippage / MEV / position lifecycle |
| Hold per-run state in `State.scratch` | Hold cross-run state (positions, cooldowns, watchlists) and pass via context |

**Practical implications when designing or coding here:**
- New schema field? Probably yes. New async fetcher inside `zetryn/`? **No.**
- New rule node that reads `state.context.token.X`? Probably yes. New rule
  node that opens a network connection? **No.**
- New `Tool` definition (schema + example stub)? Yes. New `Tool` that
  hard-codes a real API client to Helius? **No** — show the stub in
  `examples/`, never wire production credentials inside the framework.
- "The strategy needs X" is always shorthand for "the framework defines X's
  shape; the bot supplies it". If any code or doc reads otherwise, it's a
  bug — flag it.

This boundary is reaffirmed at design-doc level in
[`docs/plans/2026-06-25-kol-copytrade-strategy.md §0.5`](docs/plans/2026-06-25-kol-copytrade-strategy.md).
If the boundary ever conflicts with an apparent feature request, ask
the user to clarify before crossing it.

## Commit identity (ROLLING RANDOM — no need to ask)

Five GitHub identities are available, all wired via SSH host aliases in `~/.ssh/config`:

| Identity | Email | SSH host |
|---|---|---|
| `aldirrss` | aldialputra@gmail.com | `github_aldi` |
| `cry` | cryptowave3142@gmail.com | `github_cry` |
| `zetryn` | zetrynai@gmail.com | `github_zetryn` |
| `cdexio` | cdexioagent@gmail.com | `github_cdexio` |
| `lema` | lemacoreofficial@gmail.com | `github_lema` |

**Rule:** Always commit and push via `scripts/commit-as.sh random "message"`.
Do NOT ask the user which identity to use — just pick `random` and let the
script roll. No need to confirm before or after.

```bash
./scripts/commit-as.sh random "feat: your message here"
```

The script picks one of the five identities at random, sets both `GIT_AUTHOR_*`
and `GIT_COMMITTER_*` env vars, commits, then pushes via the matching SSH host.
The same identity may appear multiple times in a row — that is expected.

## Commands

```bash
# Activate conda environment (always do this first in a new shell)
conda activate zetryn

# Install in editable dev mode (always do this first)
pip install -e ".[dev]"

# Run all tests
pytest

# Run a specific test file
pytest tests/test_core_graph.py

# Run a specific test
pytest tests/test_core_graph.py::test_simple_graph

# Lint
ruff check .
ruff format .

# Run a walkthrough (offline, no API key needed — uses stub LLM)
cd examples && python walkthrough.py

# Run the scanner example (needs a provider key in .env)
cd examples && python run_scanner.py
```

## Architecture

`zetryn` is a **graph-based AI agent framework**. It decides; the caller executes. It never holds a private key or touches the chain.

```
BOT -> gather data -> decision = agent.run(State(context=ctx)) -> BOT executes
                           |
               ZETRYN (graph engine + advisor LLM)
```

### Dependency rules (strict)

```
zetryn/   ← no imports from trading/ or strategies/
trading/  ← no imports from zetryn/ or strategies/  (pure contract/schemas)
strategies/ ← imports both zetryn/ and trading/
```

**Wheel scope (v1.1.0 onwards):** `zetryn`, `trading`, and `strategies`
all ship in the PyPI wheel. Users can `from trading.schemas import
Decision` and `from strategies.agents.scanner import build_scanner`
straight out of `pip install zetryn-trading`. Prior to v1.1.0 only
`zetryn/` was bundled and the reference code had to be ported into the
bot repo — that created friction without serving the dependency rules
(which only require no I/O inside the wheel, not no domain code).

The dependency rules above remain non-negotiable. The wheel can carry
reference assemblies because they are **pure code** (schemas +
node/edge factories) — they invoke no network and hold no keys. The
"no I/O inside the framework" boundary lives in code, not in packaging.

### Core engine (`zetryn/core/`)

Four primitives that compose everything:

- **`State`** — data flowing through a run: `context` (bot input, opaque), `scratch` (mutable inter-node dict), `output` (final result), `trace` (per-node snapshots), `run_id`.
- **`Node`** — a Protocol with `name: str` and `async run(state) -> Command | None`. Three concrete types: `RuleNode` (pure function), `LLMNode` (in `zetryn/llm/`), `AgentNode` (sub-graph).
- **`Edge`** — conditional transition. Static routing uses declared edges; dynamic routing uses `Command.goto` returned from a node (wins over static edges).
- **`Graph`** — compiles nodes + edges, validates at compile time (before money moves), then runs. `max_steps=100` guards against unbounded loops. `END` sentinel terminates the run.

Node execution pattern: engine snapshots `scratch` before each node → node mutates `scratch` and/or returns `Command` → engine appends `StepTrace` → moves to next node.

### LLM layer (`zetryn/llm/`)

- **`LLMClient`** protocol: `complete(messages, *, model, temperature, json_mode) → LLMResult`.
- **`OpenAICompatibleClient`** — one adapter covers Groq, OpenRouter, Gemini. All free-tier by default.
- **`KeyPool`** — rotates multiple API keys on 429 to multiply free-tier quota.
- **`ProviderConfig`** — stores env var *names* (`key_envs`), never key values. Resolved at build time; missing keys fail fast.
- **`LLMNode`** — wraps an `LLMClient` call with structured output (Pydantic schema), retry/backoff, and graceful fallback (returns neutral score + `llm_failed` flag, never crashes).
- **`LLMRouter`** (`zetryn/llm/router.py`) — satisfies the `LLMClient` protocol; wraps a list of `RouterEntry` and fails over in declaration order on 429 / timeout / quota exhaustion. Each entry carries an optional `RateLimit` enforced locally via sliding-window counters (best-effort; provider 429s remain authoritative). Three tier presets are exposed: `TIER_SPEED` (Cerebras → Groq), `TIER_QUALITY` (SambaNova 405B → Gemini → Groq), `TIER_VOLUME` (OpenRouter :free → Gemini → Groq). `build_tier_entries(tier, clients_by_provider)` materialises a preset; providers absent from the dict are silently skipped. `PROVIDER_FREE_TIER_LIMITS` / `get_free_tier_limit(provider, model)` expose known free-tier caps.
- **`ZetrynClient`** (`zetryn/llm/zetryn_client.py`) — client for hosted Zetryn models (Hardes/Medifus/Easfus). Requires a subscription key; currently backed by `LocalSubscriptionAuth` stub.

### Tools (`zetryn/tools/`)

Read-only capabilities injectable by the bot. Each `Tool` has a Pydantic input schema and an async function. Registered in `ToolRegistry`. LLM decides when to call; the engine executes. Errors are graceful (empty result + flag, never crash).

### Memory (`zetryn/memory/`)

- **`MemoryStore`** protocol: `get/put/delete/query` namespaced by `ns` string.
- **`InMemoryStore`** — zero-setup, for tests and ephemeral runs.
- **`JSONFileStore`** — simple cross-run persistence to a JSON file.
- **`Blacklist`** — known rug tokens/dev wallets → instant `skip`, saves LLM calls.
- **`DecisionLog`** — every decision + outcome, used for backtest metrics.
- **`ReflectiveNode`** (`zetryn/memory/reflective.py`) — deterministic (no LLM) graph node that runs before an analyst node. Loads the last `window` decisions from `DecisionLog`, groups losers by feature buckets (quartile for numeric fields, value-as-string for categoricals), and writes a `lessons` (`ReflectionResult`) and `lessons_text` (human-readable summary) to `state.scratch`. The downstream prompt builder prepends `lessons_text` so the LLM is loss-pattern-aware. The `reflect()` pure function can be used independently of the node.

### Observability (`zetryn/observability/`)

Structured per-node logging as JSON. `Hooks` protocol (`on_node_start`, `on_node_end`, `on_node_error`) passed into `graph.run(state, hooks=...)`. `trace_to_dicts()` serializes trace for logging/backtest.

### Auth seam (`zetryn/auth/`)

`SubscriptionAuth` protocol → `LocalSubscriptionAuth` (stub, validates any non-empty key) → `RemoteSubscriptionAuth` (future, calls Zetryn platform). `License` wraps auth with TTL caching and grace-period on transient failures. Plan tiers: free / basic / pro / max, each with per-model rate limits (TPM/RPM/RPD) for Easfus/Medifus/Hardes.

### Backtest (`zetryn/backtest/`)

`Backtester.run(items)` runs the compiled graph over a list of `(id, context)` pairs and returns `BacktestResult`. Test/backtest/live are identical graph runs — just different `DataProvider` implementations injected by the bot.

### Knowledge pack (`zetryn/knowledge/`)

- **`KnowledgePack`** — immutable bundle of static facts loaded from a directory at startup. Layout: `pack_dir/system/*.md` (sorted → system-prompt blocks) and `pack_dir/data/*.json` (structured lookups, e.g. `kol_whitelist.json`, `blacklist-tokens.json`). Constructed via `KnowledgePack.from_dir(path)`. Bot authors the files; framework reads them. Use `MemoryStore` for mutable runtime state — the pack is for facts stable across a run.

### Trading domain (`trading/schemas.py`)

Shared contract: `TradingContext`, `Decision`, `DataProvider` protocol, market/holder/contract/social data shapes, `ScannerConfig`, `SniperConfig`, `KOLContext`, `KOLProfile`, `KOLAnalystVerdict`. v0.12.0 added graduation shapes: `GraduationEvent`, `GraduationConfig`, `GraduationContext`, `GraduationVerdict`. v0.13.0 added position lifecycle shapes: `PartialExit`, `PositionState`, `LifecycleConfig`, `PositionContext`, `LifecycleVerdict`; also extended `Decision.action` with `"hold"`, `"take_profit"`, `"scale_out"`, `"exit_full"`. This is the *shape agreement* between the bot and the framework.

### Strategies (`strategies/`)

- `strategies/providers.py` — `MockDataProvider` and sample fixtures for offline tests/demos.
- `strategies/kol_registry.py` — `KOLRegistry`: read-only typed view of `kol_whitelist.json` from a `KnowledgePack`. `KOLRegistry.from_pack(pack)` deserialises per-wallet `KOLProfile` entries plus global thresholds. Bot computes scores/hit-rates offline and ships the JSON; framework only reads.
- `strategies/nodes/` — `filters.py` (safety/market/social rule nodes), `decide.py` (aggregate → `Decision`), `prompts.py` (narrative LLM prompts), `sniper_nodes.py`, `kol_nodes.py` (KOL fast_safety / kol_quality / fast_market / sizing / kol_analyst_prompt / kol_audit_dispatch rule nodes), `analyst.py` (scanner/sniper analyst LLM prompt builders), `graduation_nodes.py` (v0.12.0: graduation_gate, market_gate, rule_size_and_buy, graduation_prompt, graduation_guardrail, make_audit_dispatch), `lifecycle_nodes.py` (v0.13.0: emergency_exit, hard_stop_loss, time_stop, trailing_stop, tp_ladder, rule_hold; two emit patterns: `_hard_emit` short-circuits to audit/END, `_soft_emit` falls through for chaining).
- `strategies/agents/scanner.py` — `build_scanner(llm)` returns a compiled `Graph`.
- `strategies/agents/sniper.py` — `build_sniper(llm)` returns a compiled `Graph`.
- `strategies/agents/kol_copytrade.py` — `build_kol_copytrade(knowledge_pack|registry, *, mode, llm_client, decision_log, ...)` returns a compiled `Graph`. Three modes selectable at build time:
  - `"rule"` (default) — pure rule path, no LLM, target latency <1ms.
  - `"confirmed"` — rules gate first, then `kol_analyst` LLMNode approves/vetoes and sets `size_multiplier ∈ [0, 1.5]`. When `decision_log` is provided, `ReflectiveNode("reflect")` runs before the analyst (K7 reflective loop).
  - `"audit"` — rule sizing decides instantly (bot gets `Decision` immediately); `kol_audit_dispatch` fires an async LLM audit task the bot reads later for offline tuning.
- `strategies/agents/graduation.py` — `build_graduation(llm_client, *, model, knowledge_pack, decision_log, ...)` returns a compiled `Graph`. Four decision modes: `rule` / `llm` / `hybrid` / `hybrid_audit`. Graph: `fast_safety → graduation_gate → market_gate → [reflect] → grad_decide | rule_buy → [audit_dispatch] → END`.
- `strategies/agents/lifecycle.py` — `build_lifecycle(llm_client, *, model, knowledge_pack, decision_log, ...)` returns a compiled `Graph` for position management (PL1). Gates run in order: `emergency_exit → hard_stop_loss → time_stop → trailing_stop → tp_ladder → rule_hold`. Hard exits (emergency/SL/time) short-circuit via `_hard_emit`; soft exits (trailing/TP) fall through via `_soft_emit` enabling audit chaining.

## Key patterns

**Adding a new node:** write a plain function `(state: State) -> Command | None`, wrap in `RuleNode("name", fn)`, register with `graph.add_node(...)` and connect with `graph.add_edge(...)`.

**Structured LLM output:** define a Pydantic model for the schema, pass it to `LLMNode`. The node enforces JSON mode, validates, and retries automatically.

**Prompts as assets:** prompts live in `strategies/nodes/prompts.py`, not hardcoded in node logic.

**Graceful degradation:** LLM failures → `llm_failed` flag in scratch + neutral score. Tool errors → empty result + error flag. Graph never crashes on transient external failures.

**Testing without credentials:** use `InMemoryStore`, `MockDataProvider` (in `strategies/providers.py`), and a stub `LLMClient` (see `examples/walkthrough.py`). No wallet/RPC/API key needed.
