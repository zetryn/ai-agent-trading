# Changelog

All notable changes to `zetryn-trading` will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] — 2026-06-28

**Wheel now ships reference implementations.** From this release the
PyPI wheel includes `trading/` (data contracts) and `strategies/`
(reference agent factories) alongside the `zetryn/` engine. Users can
now `pip install zetryn-trading` and import everything they need to
run a Solana memecoin bot end-to-end, without porting reference code
into their own repo first.

### Added to the wheel

- **`trading/schemas.py`** — all data contracts the framework defines.
  `TokenInput`, `Decision`, `TradingContext` plus every per-strategy
  `*Context` / `*Verdict` / `*Config` schema (`KOLContext`,
  `KOLProfile`, `KOLAnalystVerdict`, `GraduationEvent`,
  `GraduationConfig`, `GraduationContext`, `GraduationVerdict`,
  `PartialExit`, `PositionState`, `LifecycleConfig`, `PositionContext`,
  `LifecycleVerdict`, `SmartWalletProfile`, `SmartWalletAccumulation`,
  `ConfluenceEvent`, `ConfluenceConfig`, `ConfluenceContext`,
  `ConfluenceVerdict`, `DipBuySnapshot`, `DipBuyConfig`,
  `DipBuyContext`, `DipBuyVerdict`, `GrowthSnapshot`, `GrowthConfig`,
  `GrowthContext`, `GrowthVerdict`, `MarketData`, `HolderData`,
  `ContractData`, `SocialData`, `ActivityData`, `WalletIntel`,
  `PumpfunData`).
- **`strategies/agents/*.py`** — 8 reference agent factories:
  `build_scanner`, `build_sniper`, `build_kol_copytrade`,
  `build_graduation`, `build_lifecycle`, `build_confluence`,
  `build_dip_buy`, `build_organic_detector`.
- **`strategies/nodes/*.py`** — every rule / analyst / decide node the
  reference agents wire up (`filters`, `analyst`, `decide`,
  `sniper_nodes`, `kol_nodes`, `graduation_nodes`, `lifecycle_nodes`,
  `confluence_nodes`, `dip_buy_nodes`, `growth_nodes`, `prompts`).
- **`strategies/providers.py`**, **`strategies/kol_registry.py`**,
  **`strategies/smart_wallet_registry.py`**, **`strategies/backtest.py`**.

### Changed

- **`[tool.hatch.build.targets.wheel] packages`** —
  `["zetryn"]` → `["zetryn", "trading", "strategies"]`. This is the
  only substantive change vs v1.0.0; the runtime code is otherwise
  identical.
- **`CLAUDE.md` §Architecture§Dependency rules** — clarified that the
  wheel scope is broader than the dependency rule. The dependency rule
  is non-negotiable (no I/O inside the framework wheel); the wheel
  scope is a packaging decision and is allowed to include domain
  reference code as long as that code holds no I/O.

### Rationale

The v1.0.0 design intent was that `strategies/` would be "ported" into
the bot repo. That kept the wheel lean and the engine domain-neutral
but created real friction: a user installing `zetryn-trading` could
import the graph engine but not the `Decision` schema they needed to
consume the framework's output. The boundary the framework cares about
(no I/O in the wheel) was never broken by bundling reference code —
schemas and node/edge factories are pure code that touches nothing
external.

Industry precedent: every domain-branded framework (Django, LangChain,
Rails, HuggingFace) ships reference implementations alongside the
engine. `zetryn-trading` follows the same pattern from v1.1.0.

### Migration from v1.0.0

None. `from zetryn.core import ...` etc. keeps working unchanged.
What was already on PyPI in v1.0.0 is still on PyPI; v1.1.0 only
adds. Users who had been porting `trading/` and `strategies/` into
their own repo can switch to `pip install zetryn-trading>=1.1.0`
and import directly — but the ported copy keeps working too if they
prefer to maintain a fork.

### Notes for downstream

- `zetryn-ai/bot` M2 design (wiring scanners into a framework agent)
  is unblocked: the bot will depend on `zetryn-trading>=1.1.0` and
  import `from trading.schemas import TokenInput` /
  `from strategies.agents.scanner import build_scanner` directly. No
  porting step needed.

## [1.0.0] — 2026-06-27

**First stable release.** Public API is now frozen across v1.x — any
breaking change will bump to v2.0.0. Functional codebase is identical to
v0.17.0; this release is the formal commitment to API stability plus a
documentation rewrite focused on first-impression clarity for new users.

### Stability commitment

- **`zetryn.core`, `zetryn.llm`, `zetryn.knowledge`, `zetryn.memory`,
  `zetryn.tools`, `zetryn.observability`, `zetryn.backtest`,
  `zetryn.config`, `zetryn.auth`** — every public symbol exported from
  these subpackages is contract. Breaking changes only at v2.0.0.
- **`trading/schemas.py`** — `Decision`, `TradingContext`, every `*Context`
  / `*Verdict` / `*Config` schema is stable. New optional fields may be
  added; required fields will not be added or removed without a major bump.
- **`strategies/`** — reference agents are shipped as examples. Their
  public `build_*(...)` signatures follow the same stability rules; their
  internal node/edge layout is implementation detail.
- Bug fixes between minor releases follow `1.0.x` patch versioning;
  additive features (e.g. M14 multi-agent panel currently on branch)
  bump to `1.x.0`; breaking changes bump to `2.0.0`.

### Recap — what's in v1.0.0

(See [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) for the live matrix.)

- **Graph engine** (M0–M10) — `State`, `Node`, `Edge`, `Graph`,
  `Command`, compile-time validator, per-node `StepTrace`.
- **LLM layer** — `OpenAICompatibleClient` for 7 providers (Groq,
  Gemini, OpenRouter, Cerebras, Mistral, SambaNova, NVIDIA NIM),
  `KeyPool` rotation on 429, `LLMRouter` multi-provider failover with
  per-model RPM/RPD/TPM/TPD throttle, three tier presets
  (`TIER_SPEED` / `TIER_QUALITY` / `TIER_VOLUME`).
- **Knowledge + Memory + Tools** — `KnowledgePack` (markdown + JSON
  playbook), `MemoryStore` / `Blacklist` / `DecisionLog`,
  `ReflectiveNode` loss-pattern extractor wired into every LLM path,
  `Tool` + `ToolRegistry` + `tool_use_loop` for LLM-driven tool calls.
- **8 reference agents** — Scanner, Sniper, KOL Copy-Trade, Graduation
  Snipe, Position Lifecycle, Smart Money Confluence, Early-Stage Dip
  Buy, Organic Growth Detector. All share `decision_log` + `reflect_*`
  parameters for the learning loop.
- **YAML loader** (M13, v0.17.0) — `zetryn.config.load_graph(path,
  registry=...)` with AST-whitelisted boolean DSL, `module:attr`
  references, `${name}` placeholders, eager validation, CLI validator.
- **Backtest harness** — `Backtester.run(items)`; test, backtest, and
  live all use the same compiled graph.

### Documentation

- **README rewritten** for v1.0.0: 47% shorter (602 → 321 lines),
  structured as summary + handoffs to GUIDE.md / CAPABILITIES.md /
  STRATEGIES.md / plans/. Quickstart-first ordering, YAML loader
  featured, M14 intentionally not mentioned.
- **`docs/GUIDE.md §9 Bot Integration`** added — push vs pull,
  pre-filter funnel at the bot, and the framework/bot boundary table
  consolidated from README.

### Out of scope (deferred)

- **M14 multi-agent panel** — development on branch
  `feat/dev/multi-agent-panel`. Targets v1.1.0 once real-source
  testing on `zetryn-ai/bot` template completes.
- **M11** (Phase 2 LLM, parallel specialists with paid providers) and
  **M12** (Phase 3, Zetryn-hosted Hardes / Medifus / Easfus) — platform
  workstream P1–P4 must ship first; see `docs/CAPABILITIES.md §6`.

### Known limits

- **Zetryn platform** (hosted models, subscription auth) is **not yet
  live**. The auth seam is stubbed in `zetryn/auth/`; production today
  uses public LLM providers with your own keys.
- Single-provider free tier can spike p95 latency past targets.
  Recommended production pattern: `LLMRouter` with ≥ 2 providers.
  Working example: [`examples/run_with_router.py`](examples/run_with_router.py).

### Migration from v0.17.0

None. v1.0.0 is the v0.17.0 codebase with a stable-API guarantee and a
documentation rewrite. No code changes required; `pip install --upgrade`
is sufficient.

## [0.17.0] — 2026-06-27

M13 ships: **YAML graph loader**. Declarative graph specs — load a strategy
from a single YAML file, no Python builder required. Existing Python
builders (`build_scanner`, `build_sniper`, etc.) are unchanged; the loader
is purely additive.

### Added
- **`zetryn.config.load_graph(path, *, registry=None) -> Graph`** —
  parses, validates, and compiles a YAML spec eagerly. Every
  `module:attr` reference must import, every `${name}` placeholder must
  be in the supplied registry, every edge must point at a known node, and
  every `when:` expression must parse. Validation failures raise
  `ConfigError` with the YAML path + offending location.
- **Mini boolean DSL** for edge `when:` conditions — subset of Python
  (dotted attribute access on `scratch`/`context`/`output`, comparisons,
  `and`/`or`/`not`, literals). Parsed via `ast.parse` with a strict
  node whitelist; **no `eval()` at runtime**. Function calls, indexing,
  arithmetic, and `is`/`in` are rejected by design — push complex logic
  into `RuleNode` instead.
- **Three node types** supported in v1: `rule`, `llm`, `llm_decision`.
  `ReflectiveNode`, `AgentNode`, and tool-use loops stay Python-only for
  now (will be added as M13.1 if real usage demands it).
- **CLI validator** — `python -m zetryn.config <file.yaml>` returns
  exit 0 on a valid spec, 1 with a detailed `ConfigError` otherwise.
- **Example**: `examples/scanner.yaml` + `examples/run_yaml_scanner.py`
  — offline demo, no provider key required.

### Dependencies
- Added `pyyaml>=6.0` to `[project.dependencies]`.

### Design
- Brainstormed decisions documented in
  [docs/plans/2026-06-27-yaml-loader-m13.md](docs/plans/2026-06-27-yaml-loader-m13.md).
- Boundary preserved: framework never instantiates LLM clients; YAML can
  only *reference* objects the caller passed in via `registry=`.

## [0.16.0] — 2026-06-27

A1 ships: **Organic Growth Detector** — first A-tier strategy. A triage
filter that classifies a token's post-launch time-series as organic,
suspicious, or manipulated. Promotes scanner candidates with confirmed
organic growth shape; hard-aborts on manipulation tells without scoring.

### Added
- **`build_organic_detector(...)`** in `strategies.agents.growth_detector`
  — compiled graph with four modes (`rule` / `llm` / `hybrid` /
  `hybrid_audit`). Reflective loop wired into `llm` / `hybrid` when
  `decision_log` is provided. Audit fires for **all** classifications
  (organic, suspicious, and manipulated) — demotions are equally worth
  auditing.
- **New schemas in `trading/schemas.py`**: `GrowthSnapshot` (12 fields:
  candle_count, price_trajectory, sell_presence_pct, unique_buyer_trend,
  holder_growth_rate, has_healthy_pullback, max_drawdown_pct,
  whale_volume_pct, volume_acceleration), `GrowthConfig` (7 thresholds),
  `GrowthContext`, `GrowthVerdict`.
- **`strategies/nodes/growth_nodes.py`** — `fast_safety` (re-export),
  `observation_gate` (min seconds + min candles), `manipulation_gate`
  (vertical pump + zero sellers hard abort; extreme whale hard abort),
  `organic_classify` (5-dim scorer: trajectory, sells, buyers, pullback,
  whale), `growth_prompt` / `make_growth_prompt` / `growth_result` /
  `growth_guardrail` (can only demote, never promote) /
  `make_audit_dispatch`.
- **`examples/run_growth_detector.py`** — offline stub demo across 9
  scenarios. Opt-in real Groq via `ZETRYN_GROWTH_USE_GROQ=1`.
- **Tests** — `test_growth_nodes.py` (12), `test_growth_agent.py` (14).
  All tests pass, ruff clean.

### Design notes
- **Three-outcome model** — unlike entry agents (buy/skip), the growth
  detector maps: `organic→buy` (promote), `suspicious→skip` (pass
  through), `manipulated→abort` (cool down). `flags["classification"]`
  carries the string label; `scores["organic_score"]` carries the raw
  0.0–1.0 value for calibration.
- **Two hard-abort layers before scoring** — `manipulation_gate` catches
  clear tells (vertical pump + zero sellers, extreme whale > 85%) before
  the 5-dim scorer runs. Borderline cases (vertical pump WITH sellers) go
  through scoring where the trajectory dimension penalizes them.
- **Guardrail in hybrid mode** — can only demote classification, never
  promote. Vertical pump + zero sellers always abort even if LLM says
  organic.

## [0.15.0] — 2026-06-27

S6 ships: **Early-Stage Dip Buy** — the sixth (and final) S-tier entry
agent. One agent, two events: fires after the initial post-launch or
post-graduation dump settles. Config `event_type ∈ {launch, graduation}`
selects the timing window; the signal mechanic (sell pressure subsiding,
holder retention, buy-ratio recovery) is identical for both.

### Added
- **`build_dip_buy(...)`** in `strategies.agents.dip_buy` — compiled
  graph with four modes (`rule` / `llm` / `hybrid` / `hybrid_audit`).
  Reflective loop wired into `llm` / `hybrid` when a `decision_log` is
  provided.
- **New schemas in `trading/schemas.py`**: `DipBuySnapshot`
  (sell_pressure_score, buy_ratio_5m, holder_retention_pct,
  unique_buyers_trend, price_stable_seconds), `DipBuyConfig`,
  `DipBuyContext`, `DipBuyVerdict`.
- **`strategies/nodes/dip_buy_nodes.py`** — `fast_safety` (re-export),
  `timing_gate` (window check: too early / too late), `dip_gate` (min
  dip from ATH + sell pressure threshold), `recovery_gate` (buy-ratio,
  holder retention, unique buyers trend, price stability), `market_gate`,
  `rule_size_and_buy` (recovery_score × dip_bonus × sell_calm formula),
  `dip_prompt` / `dip_result` / `dip_guardrail` / `make_audit_dispatch`.
- **`examples/run_dip_buy.py`** — offline stub demo across 8 scenarios
  (good launch/grad, skip cases, rug abort). Opt-in real Groq via
  `ZETRYN_DIP_USE_GROQ=1`.
- **Tests** — `test_dip_buy_nodes.py` (16), `test_dip_buy_agent.py`
  (11). All tests pass, ruff clean.

### Design notes
- **Four gates in series** (timing → dip → recovery → market) so the
  exact rejection reason is always logged — invaluable for tuning
  thresholds from real data.
- **`event_type` is config, not schema polymorphism** — same
  `DipBuySnapshot` shape for launch and graduation; the bot sets
  `event_type` and adjusts `max_time_since_event_seconds` accordingly.
  This keeps the agent truly "one agent, two events" without branching.

## [0.14.0] — 2026-06-27

S5 ships: **Smart Money Confluence** — the fifth S-tier entry agent. Fires
when ≥ N pre-vetted smart wallets have accumulated the same token within a
rolling window. Multi-wallet correlation is the primary signal; higher
precision than any single-wallet copy because independent actors must
converge on the same thesis.

### Added
- **`build_confluence(...)`** in `strategies.agents.confluence` — compiled
  graph with four modes (`rule` / `llm` / `hybrid` / `hybrid_audit`).
  Optional `registry: SmartWalletRegistry` parameter; without it, gate
  falls back to `ConfluenceConfig` per-wallet floors only (no whitelist).
  Reflective loop wired into `llm` / `hybrid` when a `decision_log` is
  provided.
- **`SmartWalletRegistry`** in `strategies.smart_wallet_registry` — mirrors
  `KOLRegistry` pattern. Loads `smart_wallet_whitelist.json` from a
  `KnowledgePack`. Exposes `get()`, `passes_global_floor()`, `from_pack()`.
- **New schemas in `trading/schemas.py`**: `SmartWalletProfile`,
  `SmartWalletAccumulation`, `ConfluenceEvent`, `ConfluenceConfig`,
  `ConfluenceContext`, `ConfluenceVerdict`.
- **`strategies/nodes/confluence_nodes.py`** — `fast_safety` (re-export),
  `make_confluence_gate(registry)` (factory: wallet dedup, quality gate,
  count gate), `market_gate`, `rule_size_and_buy` (wallet_mult ×
  quality_mult × top10_penalty formula), `confluence_prompt` /
  `confluence_result` / `confluence_guardrail` / `make_audit_dispatch`.
- **`examples/run_confluence.py`** — offline stub demo across 5 scenarios.
  Opt-in real Groq via `ZETRYN_CONFLUENCE_USE_GROQ=1`.
- **Tests** — `test_confluence_nodes.py` (13), `test_confluence_agent.py`
  (15). All tests pass, ruff clean.

### Design notes
- **Distinct from KOL copy-trade**: KOL fires on a SINGLE named wallet's
  buy; confluence fires on ≥ N ANONYMOUS wallets converging on the same
  token. Different event shape (`ConfluenceEvent` vs `KOLBuyEvent`),
  different registry (`SmartWalletRegistry` vs `KOLRegistry`), different
  primary signal (correlated accumulation vs influencer-copy).
- **`confluence_gate` is a factory** (`make_confluence_gate(registry)`)
  because the registry is optional — without it the gate degrades
  gracefully to config-floor checks only.

## [0.13.0] — 2026-06-27

PL1 ships: the first **position-management agent**. Up to v0.12 every
shipped agent decided entry; nothing helped with the open position. PL1
fills that gap with a recommendation-only TP / SL / scale-out / trailing
graph that consumes `PositionContext` and emits a sell `Decision`.

### Added
- **`build_lifecycle(...)`** in `strategies.agents.lifecycle` — compiled
  graph with four modes (`rule` / `llm` / `hybrid` / `hybrid_audit`).
  Reflective loop wired into `llm` / `hybrid` when a `decision_log` is
  provided; intentionally skipped in `hybrid_audit` to preserve the
  sub-ms sync path.
- **New schemas in `trading/schemas.py`**: `PartialExit`, `PositionState`,
  `LifecycleConfig`, `PositionContext`, `LifecycleVerdict`. `Decision.action`
  extended with `hold`, `take_profit`, `scale_out`, `exit_full`.
- **`strategies/nodes/lifecycle_nodes.py`** — 5 rule gates
  (`emergency_exit`, `hard_stop_loss`, `time_stop`, `trailing_stop`,
  `tp_ladder`) + `rule_hold` fall-through + `lifecycle_prompt` /
  `lifecycle_guardrail` / `make_audit_dispatch` for the LLM paths.
  Hard exits (emergency / SL / time) use a short-circuit Command to
  bypass the LLM in llm/hybrid mode; soft exits (trailing / TP) fall
  through so audit_dispatch can still pick them up in hybrid_audit.
- **`examples/run_lifecycle.py`** — offline stub demo across 5 position
  scenarios (FLAT / TP_RUNG_1 / MID_LADDER / HARD_SL / TRAILING).
  Opt-in real Groq via `ZETRYN_LIFECYCLE_USE_GROQ=1`.
- **Tests** — `test_lifecycle_nodes.py` (13), `test_lifecycle_agent.py`
  (10), `test_lifecycle_reflective.py` (6). All 312 tests pass, ruff
  clean.

### Design notes
- **Hard exits are rule-only, always.** Unlike entry agents, the LLM
  cannot override emergency / hard SL / time stop. Cost of being wrong
  on an open position is far higher than on entry.
- **Framework holds no position state.** Bot pushes a complete
  `PositionState` snapshot per tick (`partial_exits` tracking ladder
  rungs the bot has already executed). Boundary-identical to entry agents.
- **Position management is NOT a strategy.** Tracked in CAPABILITIES.md
  roadmap as PL1, NOT in `docs/STRATEGIES.md` (which catalogs alpha-
  generating entry strategies). See STRATEGIES.md §Notes.

## [0.12.0] — 2026-06-27

Strategy #4 ships: the Pump.fun graduation snipe agent. Same shape as the
existing three (scanner / sniper / KOL copy-trade) — pure-rule fast path,
optional LLM decide / hybrid with deterministic guardrail, optional
``hybrid_audit`` for sub-ms rule + async LLM verify, and the same
reflective loop on the LLM paths.

### Added
- **`build_graduation(...)`** in `strategies.agents.graduation` — compiled
  graph with four modes (`rule` / `llm` / `hybrid` / `hybrid_audit`).
  Reflective loop wired into `llm` / `hybrid` when a `decision_log` is
  provided; intentionally skipped in `hybrid_audit` to preserve the
  sub-ms sync path.
- **New schemas in `trading/schemas.py`**: `GraduationEvent`,
  `GraduationConfig`, `GraduationContext`, `GraduationVerdict`. All
  re-exported from `trading/__init__.py`.
- **`strategies/nodes/graduation_nodes.py`** — `graduation_gate` (6
  bonding-curve / pair checks), `market_gate`, `rule_size_and_buy`,
  `graduation_prompt` (+ `make_graduation_prompt` for `KnowledgePack`),
  `graduation_guardrail`, and `make_audit_dispatch`. `fast_safety` is
  re-used from the sniper — the contract check is identical.
- **`examples/run_graduation.py`** — offline stub demo; opt-in real Groq
  via `ZETRYN_GRAD_USE_GROQ=1`.
- **Tests** — `test_graduation_nodes.py` (11 cases), `test_graduation_agent.py`
  (8 cases), `test_graduation_reflective.py` (6 cases). All 283 tests pass,
  ruff clean.

### Notes
- Boundary held: the framework defines `GraduationEvent` shape; the bot
  subscribes to Pump.fun WS, enriches `TokenInput` from Raydium / Helius,
  and executes. No fetcher, WS subscriber, or RPC call inside the framework.

## [0.11.0] — 2026-06-27

Two changes ship together: a K7 hotfix that wires the KOL reflective loop
end-to-end (the v0.10.0 prompt change was documented but never landed),
and `build_sniper` gains the same reflective loop the scanner and KOL
copy-trade already had — closing the strategy-consistency gap.

### Fixed
- **K7 hotfix — `kol_analyst_prompt` now actually reads `lessons_text`.**
  In v0.10.0 the `ReflectiveNode` ran and populated `state.scratch`, but
  `kol_analyst_prompt` never injected the lessons block into the analyst
  prompt, so the LLM was never actually loss-pattern-aware. The K7
  release note documented the prompt change but the code change was
  missed. The block now appears as a system message between the analyst
  persona and the per-token fact sheet, titled
  `LESSONS from recent KOL copy-trade outcomes`. The existing
  `test_confirmed_with_log_injects_lessons_into_analyst_prompt` test was
  already asserting this behavior and was failing on v0.10.0 — it now
  passes.

### Added
- **`build_sniper(decision_log=..., reflect_window=..., reflect_feature_keys=...,
  reflect_top_k=...)`** — when a `DecisionLog` is provided AND
  `decision_mode` is `llm` or `hybrid`, a `ReflectiveNode` runs between
  `fast_market` and `snipe_decide`. The LLM sees a `lessons_text` block
  compiled from recent losers as a system message. The sniper's
  `snipe_prompt` now reads `state.scratch["lessons_text"]` and injects
  it between the persona and the user fact sheet (same pattern as
  scanner + KOL analyst). All three strategies now share an identical
  learning-loop shape.
- **Reflection intentionally NOT wired into `hybrid_audit` mode.** That
  mode's promise is a sub-ms sync rule path; reading `DecisionLog`
  synchronously would defeat it. The bot's offline pipeline owns
  reflection for audit mode.
- **`tests/test_sniper_reflective_loop.py`** — 8 cases covering: no-log
  backwards-compat in llm mode, reflect ordering between fast_market
  and snipe_decide, LESSONS block reaching the prompt in hybrid mode,
  empty-log graceful behavior, `reflect_window` parameter threading,
  rule mode skips reflect, hybrid_audit skips reflect (sub-ms preserved),
  and `llm_client=None` short-circuits the whole LLM branch.

### Notes
- Boundary held: framework only **reads** `DecisionLog`. Bot still
  writes outcomes via `record_outcome` after a trade settles. No new
  fetcher or executor landed inside the framework.
- Strategy consistency: scanner, KOL copy-trade, and sniper now all
  expose the same `decision_log` + `reflect_*` parameters.

## [0.10.0] — 2026-06-26

K7 shipped — KOL Copy-Trade × `ReflectiveNode` integration. With this
release the K-series is feature-complete: KOL Copy-Trade now supports
rule / confirmed / audit / reflective in four orthogonal modes.

### Added
- **`build_kol_copytrade(..., decision_log=DecisionLog, reflect_window=20,
  reflect_feature_keys=None, reflect_top_k=5)`** — when a `decision_log`
  is provided in `confirmed` mode, a `ReflectiveNode` is inserted
  between `fast_market` and `kol_analyst`. It compiles a `lessons_text`
  summary of recent losers; the analyst prompt prepends it as a system
  block titled `LESSONS from recent KOL copy-trade outcomes`. The LLM
  conditions on real outcomes, not just the static prompt.
- **`kol_analyst_prompt` change** — reads `state.scratch["lessons_text"]`
  when present and appends one extra system message between the
  analyst persona and the per-token fact sheet. Empty / missing → no
  change (backwards-compat with v0.7.0).
- **`examples/run_kol_copytrade.py` `ZETRYN_KOL_REFLECT=1` switch** —
  seeds three mock historical losers into an in-memory `DecisionLog`
  so users can see the lessons block reach the analyst with a real
  Groq run.
- **`tests/test_kol_reflective_loop.py`** — 7 cases covering: optional
  `decision_log` param in rule mode, reflect node only added in
  confirmed mode, end-to-end happy path with lessons in prompt,
  backwards-compat (confirmed without log), empty-log edge case,
  `reflect_window` parameter threading, and hard-gate short-circuit
  bypassing reflect.

### Verified end-to-end
With three mock losers seeded and `openai/gpt-oss-20b` via Groq, the
analyst materially changed verdicts on six contrasting scenarios:
- Scenario A (Perfect Storm) dropped from multiplier 1.3 to 0.6,
  citing the historical loser pattern by name.
- Scenarios B, D, F flipped from BUY-with-reduced-size to SKIP.
- The trace path on every confirmed scenario showed
  `... → fast_market → reflect → kol_analyst → sizing` instead of
  `... → fast_market → kol_analyst → sizing`.

### Notes
- Reflection only runs in `confirmed` mode. `rule` mode has no LLM to
  condition; `audit` mode emits its decision before the analyst would
  see the lessons, and runs reflection offline via the bot's own
  pipeline if desired.
- Boundary held: framework only **reads** the `DecisionLog`. The bot
  remains responsible for writing outcomes back via `record_outcome`
  after a trade settles. No new fetcher or executor landed inside the
  framework.

## [0.9.0] — 2026-06-26

K6: KOL Copy-Trade `audit` mode. The "AI Agent" claim now extends to a
strategy that can't tolerate LLM latency in its hot path — rule sizing
runs sub-ms (Decision returned to the bot immediately), then an async
LLM audit fires in the background. The bot awaits the verdict later
and writes it to DecisionLog for offline rule tuning. Mirrors the
sniper's `hybrid_audit` pattern.

### Added
- **`kol_audit_prompt(state)`** in `strategies/nodes/kol_nodes.py` —
  builds a prompt that reviews an already-emitted Decision rather than
  producing one. Forces the LLM into "agree or flag concerns" mode.
- **`_run_kol_audit(client, messages, model)`** — background coroutine
  that swallows every exception into a flagged `KOLAnalystVerdict`
  (`approve=False`, `audit_failed: <ExceptionType>` concern). It MUST
  never raise into the event loop and crash the bot.
- **`make_kol_audit_dispatch(client, *, model, knowledge_pack)`** —
  factory returning the rule node that fires the async task. Skips
  audit entirely when the decision is not "buy" (no wasted LLM call
  on skip/abort).
- **`mode="audit"`** in `build_kol_copytrade(...)` — wires the dispatch
  node AFTER `sizing` so the Decision is already in `state.output`
  when the audit task is created. Edge: `sizing -> kol_audit_dispatch -> END`.
- **`examples/run_kol_copytrade.py`** updated with
  `ZETRYN_KOL_MODE=audit` switch to demo the audit flow end-to-end.
  `_decide()` now awaits the audit task and prints the verdict
  alongside the Decision.
- **11 new tests** in `tests/test_kol_audit_mode.py` covering: rule
  decision set BEFORE audit fires, task is an awaitable, verdict
  resolves to parsed `KOLAnalystVerdict`, disagreement does not mutate
  the Decision, LLM error swallowed into flagged verdict, garbage JSON
  also swallowed, hard-gate / kol_quality rejects skip the audit
  entirely, plus backwards-compat checks for rule + confirmed modes.

### Verified end-to-end
Live Groq (gpt-oss-20b) audit run on the six-scenario test set: the
audit caught disagreement on the three problematic cases the rule
layer can't see (subtle bundler, toxic KOL pattern, hype-no-substance)
and agreed with rule sizing on the other three. Behavior matches the
confirmed-mode variance test from v0.7.0 — proving the same prompt
quality works in audit posture.

### Backwards compatibility
- 243 tests green (215 existing + 11 from audit-mode tests + 17 from
  v0.8.0 provider expansion). No breaking change.
- `mode="rule"` (default) and `mode="confirmed"` paths unchanged.

### Notes
- The "AI Agent that trades" claim is now complete for KOL copy-trade
  across all three latency profiles:
    rule       → sub-ms, no LLM, pure judgement encoded as rules
    confirmed  → 200-500ms, LLM gates size before execution
    audit      → sub-ms execute + async LLM verdict for offline learning
- No fetcher leaked into the framework. The audit prompt sees only
  what's already in `state.context` + `state.output`.

## [0.8.0] — 2026-06-25

Provider expansion: framework now ships with four additional
OpenAI-compatible providers and three opinionated router tier presets.
Triggered by a user question — "can all these providers be added?"
(referring to the free-tier landscape: Cerebras, Mistral, SambaNova,
NVIDIA NIM, etc.). Answer was yes, then proved with code.

### Added
- **4 new BASE_URL constants** in `zetryn.llm`:
  `CEREBRAS_BASE_URL`, `MISTRAL_BASE_URL`, `SAMBANOVA_BASE_URL`,
  `NVIDIA_NIM_BASE_URL`. Wired into `OpenAICompatibleClient` with
  zero adapter changes — each provider is OpenAI-compatible.
- **Per-model free-tier presets** in `PROVIDER_FREE_TIER_LIMITS`:
  - Cerebras: 6 models (llama-3.3-70b, gpt-oss-120b, qwen-3, glm-4.5, etc.)
  - Mistral: 5 models (mistral-large/small/codestral/pixtral/embed)
  - SambaNova: 5 models (Llama-3.1-8B/70B/405B, 3.3-70B, Qwen2.5-72B)
  - NVIDIA NIM: 6 models (DeepSeek R1/V3, Llama 3.3 70B, Nemotron, etc.)
- **Three router tier presets** in `zetryn.llm`:
  - `TIER_SPEED` — Cerebras (~2,600 tok/s) → Groq fallback. For
    latency-critical sniper-style work.
  - `TIER_QUALITY` — SambaNova 405B → Gemini → Groq. For deep reasoning
    when latency tolerates 1-3s.
  - `TIER_VOLUME` — OpenRouter `:free` → Gemini → Groq. For backtests
    and high-throughput pipelines.
- **`build_tier_entries(tier, clients_by_provider)`** helper — materialises
  a tier spec list into `list[RouterEntry]`. Silently skips providers
  the caller has no keys for, so tiers degrade gracefully (not error).
- **`TierSpec` dataclass** — `{provider, model}` pair used by tier presets.
- **`examples/run_kol_tier_router.py`** — end-to-end demo: build clients
  per provider, materialise a tier, hand to `LLMRouter`, run KOL
  confirmed-mode strategy. Switchable via `ZETRYN_TIER=speed|quality|volume`.
- **17 new tests** in `tests/test_provider_expansion.py` covering BASE_URLs,
  presets per provider, tier spec validity, `build_tier_entries()`
  behaviour (graceful skip, full populate, empty input, router
  integration), and backwards-compat for existing providers.

### Backwards compatibility
- All 215 existing tests still green. No breaking change to existing
  API surface. New providers are purely additive.
- Existing `get_free_tier_limit(provider, model)` continues to work for
  Groq / Gemini / OpenRouter and now also resolves the four new providers.

### Notes
- All four new providers are confirmed OpenAI-compatible at their
  `/v1/chat/completions` endpoints. No custom adapter needed.
- For Hugging Face Inference and Cloudflare Workers AI (the two
  remaining providers in the user's reference table that need
  partial-adapter work), the framework's existing primitives still
  support them via custom `LLMClient` implementations — those just
  didn't make this release's scope.

## [0.7.0] — 2026-06-25

KOL Copy-Trade gains a real AI mode. Ships K5 of the milestone breakdown.
Triggered by a user observation in the v0.6.0 walkthrough run: with the
copy-trade strategy in rule-only mode, the "AI Agent" branding was thin
because no LLM ever ran in that flow. v0.7.0 closes that gap.

### Added
- **`KOLAnalystVerdict`** in `trading/schemas.py` — structured LLM
  output: `approve` (bool veto switch), `size_multiplier` in [0, 1.5]
  (scales the rule-derived size), `confidence`, `concerns` list,
  `reasoning`. Re-exported from `trading`.
- **`kol_analyst_prompt(state)`** + **`neutral_kol_verdict(state, exc)`**
  in `strategies/nodes/kol_nodes.py` — the analyst's job is *not* to
  re-decide the buy; it's to catch qualitative red flags the rules
  cannot encode and to nudge size based on confluence. Neutral
  fallback approves at multiplier=1.0 with `llm_failed=True` so an
  LLM outage never silently kills trades.
- **`mode="confirmed"`** in `build_kol_copytrade(...)` — opt-in flag
  that inserts the LLM analyst between `fast_market` and `sizing`.
  Requires `llm_client=...` (any `LLMClient`, including `LLMRouter`).
  Default mode stays `rule` — backwards compatible.
- **`sizing` node updated** to read `state.scratch["kol_analyst"]`:
  - `approve=False` → emits `action="skip"` with `analyst_veto=True`
  - `approve=True` → final size = rule_size × `size_multiplier`,
    still clamped at `max_size`
- **`examples/run_kol_copytrade.py`** updated with `ZETRYN_KOL_USE_GROQ=1`
  switch to demo the confirmed flow with real Groq.
- **10 new tests** in `tests/test_kol_confirmed_mode.py` covering
  approve / veto / size up / size down / LLM failure / garbage output /
  rule-mode backwards-compat / hard-gate short-circuit before LLM.
- **`docs/CAPABILITIES.md`** updated — K5 row marked done; §6 "What's
  next" reset to K6 (`audit` mode), K7 (Reflective integration), and a
  fourth-strategy candidate.

### Verified end-to-end
On real Groq Llama 3.3 70b with the example pack, the analyst
downgraded a rule-approved 2.47 SOL buy to 1.21 SOL (multiplier 0.5)
citing low_liquidity / no_social_presence / bundler_detected — proving
the LLM verdict materially shapes the final `Decision` rather than
being decorative.

### Changed
- **README §Status** — bumped to v0.7.0; "three reference strategies"
  section now mentions both KOL modes and links the env-var switch.

### Notes
- Boundary held: no fetcher landed inside the framework. The analyst
  sees the same `KOLContext` the bot already pushed; the bot still
  owns event subscription, KOL whitelist authoring, cooldown tracking,
  and trade execution.

## [0.6.0] — 2026-06-25

First strategy reference agent beyond Scanner/Sniper: **KOL Copy-Trade**
(`rule` mode). Ships K1-K4 of the milestone breakdown in
`docs/plans/2026-06-25-kol-copytrade-strategy.md`. `confirmed` (tool-use)
and `audit` modes follow in v0.7.0+; integration with `ReflectiveNode`
follows in v0.8.0.

### Added
- **Schemas** in `trading/schemas.py`: `KOLProfile`, `KOLBuyEvent`,
  `KOLCopyTradeConfig`, `KOLContext`. Re-exported from `trading`.
- **`strategies.KOLRegistry`** — typed read-only view over a
  `KnowledgePack`'s `data/kol_whitelist.json`. Exposes `get(wallet)`,
  `is_known(wallet)`, `passes_global_floor(profile)`, plus the
  pack-wide `min_tier` / `min_hit_rate`. Graceful when the pack has
  no whitelist (empty registry, not a crash).
- **`strategies/nodes/kol_nodes.py`** — pure-rule nodes:
  `fast_safety` (abort on dangerous contract), `make_kol_quality`
  (factory binding a `KOLRegistry`; enforces whitelist + pack floor +
  deployment-config floor + KOL min buy size + signal staleness +
  cooldown), `fast_market` (liquidity / volume / top10 / bundler /
  sniper gates), `sizing` (formula reads all tunables from
  `KOLCopyTradeConfig`).
- **`strategies.build_kol_copytrade(pack | registry=...)`** —
  compiled graph: `fast_safety → kol_quality → fast_market → sizing →
  END`. Re-exported from `strategies`.
- **Example** `examples/run_kol_copytrade.py` — six realistic scenarios
  (trusted KOL buy, unknown wallet, stale signal, honeypot override,
  cooldown, deployment override). Stub-only; no API key needed.
- **Tests**: `tests/test_kol_schemas_registry.py` (14 cases),
  `tests/test_kol_nodes.py` (19 cases), `tests/test_kol_copytrade.py`
  (10 cases). Suite is now 205 cases, all green.
- **Design doc**: `docs/plans/2026-06-25-kol-copytrade-strategy.md`
  captures the strategy hypothesis, boundary recap, schemas, graph,
  decisions §15, and phase breakdown §16.

### Changed
- **`README` §Status** — bumped to v0.6.0; reframed as "three reference
  agents" (Scanner / Sniper / KOL Copy-Trade) with example links.
- **`docs/CAPABILITIES.md` §6 Roadmap** — adds K (v0.6.0) row plus
  reliability and tool-use rows for v0.4.0 / v0.5.0; "What's next"
  reset to K5 (confirmed mode), K7 (reflective integration), and a
  fourth-strategy candidate as the natural next thread.

### Notes
- Boundary held tight: framework defines schemas, runs the decision
  graph, returns a `Decision`. The bot subscribes to KOL events,
  enriches `TokenInput`, maintains `kol_whitelist.json`, tracks
  cooldown state (`last_copy_ts`), and executes. No external data
  fetcher landed inside the framework.

## [0.5.0] — 2026-06-25

LLM tool-use loop shipped. Capability #8 in the matrix moves from ⚠️ to ✅:
the analyst can now invoke registered `Tool`s mid-decision using native
OpenAI-compatible function calling, with the same safety guarantees the rest
of the framework already enforces (bounded iterations, graceful tool failures,
fallback contract on total LLM failure).

### Added
- **`tool_use_loop()`** (`zetryn.llm.tool_use`) — drives the call → execute →
  feed-back → repeat conversation against any `LLMClient` and `ToolRegistry`.
  Returns the final `LLMResult` plus a `ToolUseTrace` (iterations, every tool
  call, truncation flag). `max_iterations` is mandatory and defaults to 6.
- **`ToolUseNode`** — graph node wrapping the loop. Optional `schema=...`
  parses the model's final text as Pydantic; with no schema it stores the raw
  text. Same fallback contract as `LLMNode`: on LLM/schema failure, applies
  `fallback_fn` and sets `<output_key>__llm_failed = True`.
- **`LLMResult.tool_calls`** — new field carrying the OpenAI-shaped tool call
  list when the model decides to invoke tools. Empty list when none requested.
- **`examples/run_with_tools.py`** — end-to-end demo: analyst sees a token,
  invokes `check_rug` and `get_smart_money_buys` on its own, returns a
  structured `AnalystVerdict`. Stub LLM so no API key needed.
- **`tests/test_tool_use.py`** — 11 cases covering the no-tools fast path,
  the call+continue loop, tool failures fed back to the model, malformed
  argument JSON, max-iteration truncation, schema parsing, and fallback paths.

### Changed
- **`LLMClient` protocol** — `complete()` accepts an optional `tools=[...]`
  keyword. Implementations that don't support tools may ignore it. Backwards
  compatible: existing fakes using `**kw` keep working; the one fake with an
  explicit signature in tests (`test_llm_router.py`) gained the parameter.
- **`OpenAICompatibleClient`** — forwards `tools` to the chat completions API,
  parses `message.tool_calls` from the response. Mutually exclusive with
  `json_mode` at the API level (matching OpenAI's contract).
- **`LLMRouter`** — forwards `tools` transparently to the active entry, so
  tool-use works through multi-provider failover with no extra wiring.
- **`docs/CAPABILITIES.md`** — capability #8 marked ✅ with evidence links;
  §6 "What's next" updated (both threads from v0.3.0 closed, new candidates
  identified).
- **`README` §Status** — bumped to v0.5.0 snapshot, lists the tool-use loop
  as built and points at the new example.

### Notes
- LLM tool-use is opt-in: existing scanner/sniper graphs don't change. To
  use it, instantiate a `ToolUseNode` with your `ToolRegistry` and add it to
  your graph in place of (or alongside) an `LLMNode`.

## [0.4.0] — 2026-06-25

Free-tier reliability pattern shipped as a working example and integration
tests. Closes M8 acceptance criterion #6 in practice: the scanner driven
by an `LLMRouter` with two free providers keeps p95 below the 5s target,
even when one provider rate-limits.

### Added
- **`examples/run_with_router.py`** — recommended production pattern:
  build `LLMRouter([groq, gemini])` with per-model free-tier presets and
  hand it straight to `build_scanner`. Falls back to a stub LLM when no
  keys are configured, so the demo always runs.
- **`examples/bench_scanner_latency.py` router mode** — new env knob
  `ZETRYN_BENCH_PROVIDER=router` benches the scanner through a
  multi-provider router so you can compare single-provider vs. router
  p95 directly. `ZETRYN_GROQ_MODEL` / `ZETRYN_GEMINI_MODEL` choose which
  model each entry uses.
- **`tests/test_scanner_router.py`** — 5 integration cases proving the
  router is a true drop-in `LLMClient`: single-entry equivalence,
  failover on `LLMRateLimitError`, graceful neutral verdict when every
  entry fails, persistent cooldown across scans, and `KnowledgePack`
  blocks reach the analyst through the router unchanged.

### Changed
- **`docs/CAPABILITIES.md` §5** — adds a "Reliability pattern" subsection
  with the recommended router snippet and a pointer to the bench script.
  Criterion #6 status is now "single-provider ⚠️ / router ✅".
- **README §Status** — clarifies that the router is the recommended
  production pattern, with a direct link to the new example.

### Notes
- No core API changed. `LLMRouter` already satisfied `LLMClient` since
  v0.2.0; v0.4.0 is the documentation + example + test layer proving it
  end-to-end inside the scanner.

## [0.3.0] — 2026-06-25

M8 closeout: the scanner's learning loop is now wired end-to-end. Past
losing decisions become a dynamic system-prompt block on every run, so
analyst output is conditioned on real outcomes — not just static prompt
authoring.

### Added
- **`build_scanner(..., decision_log=...)`** — when a `DecisionLog` is
  provided, a `ReflectiveNode` is inserted between the market hard gate
  and the analyst LLM. It compiles a `lessons_text` summary from the last
  N decisions (configurable via `reflect_window`, `reflect_feature_keys`,
  `reflect_top_k`) and the analyst sees it as a `Lessons from recent
  decisions` system block.
- **Analyst prompt layering** in `make_analyst_prompt(pack)` now stacks
  three layers top-to-bottom: `KnowledgePack` blocks → reflection lessons
  → analyst persona + per-token fact sheet.
- **`examples/bench_scanner_latency.py`** — latency benchmark for M8
  acceptance criterion #6. Validates real-provider p95 against the 5s
  target. Skips cleanly when no provider key is configured.
- **KeyPool stress tests** — three new cases in `tests/test_llm.py`:
  3-key cascade with mid-pool recovery, full-pool exhaustion,
  mixed 429+500+200 sequence with correct rotation accounting.
- **`tests/test_scanner_reflection.py`** — 7 cases covering scanner +
  reflective loop wiring, backwards compatibility, layering with
  KnowledgePack, and the no-LLM-no-reflect default path.

### Changed
- `make_analyst_prompt(None)` no longer returns `analyst_prompt` by
  identity — it returns a wrapper so the lessons block can be injected
  dynamically at run time. Behaviour-equivalent when no pack and no
  lessons are present; only test code using `is` identity needs updating.

### Notes
- M8 acceptance criterion #6 (p95 ≤ 5s) is now measurable with the bench
  script. Free-tier Groq frequently meets the median target (~1.5s) but
  p95 can spike past 5s under rate-limit variance. The recommended
  production mitigation is `LLMRouter` with ≥2 providers.

## [0.2.0] — 2026-06-24

Pre-P1 foundations: deployments can now ship their own playbook, fan out across
multiple LLM providers with per-model throttle, and re-use past trade outcomes
to make future decisions loss-aware.

### Added
- **`KnowledgePack`** (`zetryn.knowledge`) — markdown + JSON playbook loader.
  `KnowledgePack.from_dir(path)` reads `<pack>/system/*.md` as system-prompt
  blocks (filename order) and `<pack>/data/*.json` as structured lookups via
  `lookup(ns, key, default)`. Surfaces: `system_blocks()`,
  `as_system_message()`, `namespaces()`.
- **`LLMRouter`** (`zetryn.llm.router`) — multi-provider failover satisfying the
  `LLMClient` protocol; drops into existing `LLMNode` unchanged. Per-entry
  `RateLimit` enforced via sliding-window RPM/RPD/TPM/TPD counters.
  `PROVIDER_FREE_TIER_LIMITS` ships per-model presets for Groq (8 models),
  Gemini (5 models), and OpenRouter's `:free` shared bucket.
  `get_free_tier_limit(provider, model)` helper handles lookup safely.
- **`ReflectiveNode`** (`zetryn.memory.reflective`) — rule-based loss-pattern
  extractor over `DecisionLog`. Numeric features bucketed by quartile,
  categorical by value; writes `ReflectionResult` + ready-to-inject
  `lessons_text` to `state.scratch`. Pure `reflect()` helper exposed for direct
  use outside graphs.
- **Scanner + Sniper integration** — `build_scanner(..., knowledge_pack=pack)`
  and `build_sniper(..., knowledge_pack=pack)` prepend the pack's system blocks
  to the analyst, snipe-decide, and hybrid_audit prompts. Factories
  `make_analyst_prompt(pack)` and `make_snipe_prompt(pack)` exposed for custom
  graphs.
- **Example** `examples/run_with_knowledge.py` — runs the scanner with a
  throwaway pack, confirms house rules reach the LLM prompt.
- **`docs/CAPABILITIES.md`** — capability matrix and gap analysis, tracks
  F1–F3 foundation status.

### Changed
- `RateLimit` now has a `tpd` field (tokens-per-day), populated for Groq
  presets. Existing callers are unaffected — the default is `None`.
- README: architecture tree now lists `knowledge/`, `LLMRouter`, and
  `ReflectiveNode`; Phase 1 section mentions multi-provider failover; What's
  built includes the pre-P1 foundations row.

### Notes
- All three foundations are additive and backwards-compatible. Existing code
  paths (`build_scanner(llm)` without a pack, single-provider `OpenAICompatibleClient`)
  behave exactly as in 0.1.0.

## [0.1.0] — 2026-06-24

First public release. AI-first agent framework for Solana memecoin trading.

### Added
- **Core engine** (`zetryn.core`): `State`, `Node`, `Edge`, `Graph`, `Command`,
  `END` sentinel, per-node auto-snapshot trace, compile-time validation.
- **LLM layer** (`zetryn.llm`): `LLMClient` protocol, `OpenAICompatibleClient`
  (Groq / Gemini / OpenRouter / OpenAI), `KeyPool` rotation on 429, structured
  output with retry, `LLMNode`, `LLMDecisionNode`, `ZetrynClient` (subscription-
  gated, stub until platform live).
- **Tools** (`zetryn.tools`): `Tool` + `ToolRegistry`, graceful error handling.
- **Memory** (`zetryn.memory`): `MemoryStore` protocol, `InMemoryStore`,
  `JSONFileStore`, `Blacklist`, `DecisionLog`.
- **Observability** (`zetryn.observability`): structured per-node logging,
  `Hooks` protocol, trace serialization.
- **Auth seam** (`zetryn.auth`): `SubscriptionAuth`, `LocalSubscriptionAuth`,
  `License` with TTL cache and grace period, plan tiers (free/basic/pro/max).
- **Backtest** (`zetryn.backtest`): generic `Backtester` over `(id, context)`
  items with action distribution and pluggable metrics scorer.
- **Trading contract** (`trading/schemas.py`): `TokenInput`, `Decision`,
  `DataProvider` protocol, multi-timeframe `ActivityData`, `WalletIntel`,
  `PumpfunData`, enriched `SocialData` / `TwitterData`, `ContractData` with
  `bundled_supply` and `dev_rug_history`, `TokenSource` literal.
- **AI analyst schemas**: `AspectAnalysis`, `FullAnalysis`, `AuditVerdict`.
- **Reference strategies** (`strategies/`):
  - **Scanner (Agent A)** — AI-first: 3 hard gates (safety / intel / market) →
    1 rich LLM analyst → guardrail-aware finalize. Single LLM call returning
    structured multi-aspect verdict. Free-tier feasible.
  - **Sniper (Agent B)** — speed-first with 4 decision modes:
    `rule` (sub-ms pure-rule, default), `llm`, `hybrid` (LLM + rule guardrail),
    `hybrid_audit` (rule decides instantly, async LLM verify writes to
    DecisionLog — non-blocking hot path).
- **Examples**: `examples/walkthrough.py` (offline INPUT → PROCESSING → OUTPUT
  for 16 dummy memecoin scenarios), `examples/run_scanner.py`, `run_sniper.py`,
  `run_backtest.py`, `run_with_memory.py`.
- **Tests**: 80+ tests, no API key required (offline stubs + `MockDataProvider`).
- **Documentation**:
  - [`docs/plans/2026-06-23-zetryn-agent-framework-design.md`](docs/plans/2026-06-23-zetryn-agent-framework-design.md) — original design
  - [`docs/plans/2026-06-24-ai-first-pivot.md`](docs/plans/2026-06-24-ai-first-pivot.md) — AI-first pivot, 3-phase LLM evolution, sniper hybrid_audit