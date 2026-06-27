# Strategy #4 — Pump.fun Graduation Snipe (v0.12.0)

**Date:** 2026-06-27
**Status:** Approved — ready for implementation
**Version target:** v0.12.0

---

## 0. Context

Three reference strategies already ship in `strategies/agents/`:

| Strategy | Context | Modes |
|---|---|---|
| Scanner | `TradingContext` | AI-first single LLM call |
| Sniper | `TradingContext` + `SniperConfig` | rule / llm / hybrid / hybrid_audit |
| KOL Copy-Trade | `KOLContext` | rule / confirmed / audit |

All three now share an identical reflective learning loop (`ReflectiveNode` + `DecisionLog`). Strategy #4 joins this family with the same shape.

---

## 1. What This Solves

When a Pump.fun token graduates from the bonding curve to Raydium, a short entry window opens (typically 5–30 seconds). The entry quality is highly predictable from bonding curve behavior — fill speed, unique buyers, and LP setup signal genuine demand vs. coordinated launches. No existing strategy captures this signal.

---

## 2. Framework Boundary

| The framework does | The bot does |
|---|---|
| Define `GraduationEvent/Config/Context/Verdict` schemas | Subscribe to Pump.fun WS for graduation events |
| Run decision graph (gates → optional LLM → `Decision`) | Enrich `TokenInput` from Raydium / Helius |
| Read `DecisionLog` for `ReflectiveNode` | Fill `GraduationEvent` (bonding curve + pair data) |
| Return `Decision` to bot | Execute trade, manage slippage, MEV |
| | Write outcome to `DecisionLog` via `record_outcome` |

---

## 3. Schema (`trading/schemas.py`)

### 3.1 `GraduationEvent`

Data the bot provides per graduation event:

```python
class GraduationEvent(BaseModel):
    mint: str
    pair_address: str                    # Raydium pair address
    detected_at_ts: float                # unix timestamp when bot detected event

    pair_age_seconds: float              # seconds since pair was created (latency indicator)

    # Bonding curve signals
    bonding_curve_fill_seconds: float    # how long to fill BC (lower = higher demand)
    bonding_curve_unique_buyers: int     # unique wallets that bought during BC phase
    bonding_curve_sol_raised: float      # total SOL raised in BC
    bonding_curve_premium_pct: float     # price % above last BC price at graduation

    # Raydium pair signals
    initial_liquidity_sol: float         # SOL added to LP at graduation
    initial_liquidity_token_pct: float   # % of total supply in LP
    lp_burned: bool                      # whether LP tokens were burned at launch
```

Schema is extensible — additional fields can be added in future versions without breaking existing bots.

### 3.2 `GraduationConfig`

Tunables the bot sets at build time or per-run:

```python
class GraduationConfig(BaseModel):
    decision_mode: str = "rule"           # rule | llm | hybrid | hybrid_audit

    # Gate thresholds (hard rules)
    max_fill_seconds: float = 300.0       # reject if BC took too long to fill
    min_unique_buyers: int = 50           # minimum unique BC buyers
    min_initial_liquidity_sol: float = 30.0
    require_lp_burned: bool = True        # hard gate: LP must be burned
    max_pair_age_seconds: float = 10.0    # reject if bot detected too late
    max_premium_pct: float = 20.0         # reject if already pumped > N% above BC price

    # Sizing
    base_size: float = 0.5
    max_size: float = 2.0
```

### 3.3 `GraduationContext`

What the bot hands the framework per event:

```python
@dataclass
class GraduationContext:
    token: TokenInput          # standard enrichment (market, holders, contract, social)
    event: GraduationEvent     # bonding curve + Raydium pair signals
    config: GraduationConfig
```

### 3.4 `GraduationVerdict`

Structured LLM output schema:

```python
class GraduationVerdict(BaseModel):
    action: str              # buy | skip | abort
    confidence: float        # 0..1
    size_pct: float          # fraction of max_size to deploy
    reasoning: str
    concerns: list[str]
```

All four types re-exported from `trading/__init__.py`.

---

## 4. Graph Architecture

### 4.1 Nodes

All nodes live in `strategies/nodes/graduation_nodes.py` except `fast_safety`, which is imported directly from `sniper_nodes` (contract check is identical).

| Node | Type | Purpose |
|---|---|---|
| `fast_safety` | Rule (import from sniper_nodes) | Abort instantly on dangerous contract |
| `graduation_gate` | Rule | 6 bonding curve / pair checks (see §4.2) |
| `market_gate` | Rule | Standard token checks: liquidity, top10 %, bundler/sniper density |
| `rule_size_and_buy` | Rule | Deterministic sizing → `Decision(buy)` |
| `graduation_prompt` | Prompt builder | Builds LLM messages; injects `lessons_text` when present |
| `graduation_guardrail` | Rule | Hybrid mode: force abort on rug, hard cap size |
| `audit_dispatch` | Rule | Fires async LLM audit task (hybrid_audit mode) |

### 4.2 `graduation_gate` checks (in order)

1. `lp_burned` — if `config.require_lp_burned` and `event.lp_burned is False` → abort
2. `pair_age_seconds ≤ config.max_pair_age_seconds` — too slow to detect → skip
3. `bonding_curve_fill_seconds ≤ config.max_fill_seconds` — demand too weak → skip
4. `bonding_curve_unique_buyers ≥ config.min_unique_buyers` — not enough organic buyers → skip
5. `initial_liquidity_sol ≥ config.min_initial_liquidity_sol` — LP too thin → skip
6. `bonding_curve_premium_pct ≤ config.max_premium_pct` — already pumped → skip

Each rejection writes a precise `Decision(action="skip", reasons=[...])` so the bot can log which gate fired.

### 4.3 Mode wiring

```
rule:
  fast_safety → graduation_gate → market_gate → rule_size_and_buy → END

llm / hybrid:
  fast_safety → graduation_gate → market_gate → [reflect] → grad_decide → END
                                                  ↑ only when decision_log provided

hybrid_audit:
  fast_safety → graduation_gate → market_gate → rule_size_and_buy → audit_dispatch → END
  (reflect intentionally skipped — sub-ms sync path must not block on memory read)
```

`grad_decide` is an `LLMDecisionNode` using `GraduationVerdict` as schema, `graduation_prompt` as the prompt builder, and `graduation_guardrail` as the guardrail (hybrid mode only).

### 4.4 Reflective loop

Identical to scanner / sniper / KOL pattern:

- `ReflectiveNode("reflect", decision_log, window=reflect_window, ...)` inserted between `market_gate` and `grad_decide` in `llm` / `hybrid` modes when `decision_log is not None`
- `graduation_prompt` reads `state.scratch["lessons_text"]` and injects a `LESSONS from recent graduation snipe outcomes` system block between the analyst persona and the per-token fact sheet
- `hybrid_audit` skips reflect — rule path must stay sub-ms; bot reflects offline

---

## 5. Factory

```python
# strategies/agents/graduation.py
def build_graduation(
    llm_client: LLMClient | None = None,
    *,
    model: str | None = None,
    knowledge_pack: KnowledgePack | None = None,
    decision_log: DecisionLog | None = None,
    reflect_window: int = 20,
    reflect_feature_keys: list[str] | None = None,
    reflect_top_k: int = 5,
) -> Graph:
```

Signature is intentionally identical to `build_sniper` and `build_kol_copytrade` for API consistency.

Re-exported from `strategies/__init__.py` as `build_graduation`.

---

## 6. Files Changed

### New
```
trading/schemas.py                              ← 4 new types
trading/__init__.py                             ← re-export new types
strategies/nodes/graduation_nodes.py            ← all nodes + prompt builder
strategies/agents/graduation.py                 ← build_graduation() factory
strategies/__init__.py                          ← re-export build_graduation
examples/run_graduation.py                      ← offline stub + ZETRYN_GRAD_USE_GROQ=1
tests/test_graduation_nodes.py                  ← gate rejection cases
tests/test_graduation_agent.py                  ← mode wiring tests
tests/test_graduation_reflective.py             ← reflective loop tests
docs/superpowers/specs/2026-06-27-graduation-snipe-strategy-design.md  ← this file
```

### Updated
```
docs/CAPABILITIES.md    ← add Graduation Snipe row to roadmap table
CHANGELOG.md            ← v0.12.0 entry
zetryn/__init__.py      ← version 0.11.0 → 0.12.0
pyproject.toml          ← version 0.11.0 → 0.12.0
```

---

## 7. Test Plan

**`test_graduation_nodes.py`** (~12 cases):
- Each `graduation_gate` rejection (lp not burned, too late, fill too slow, too few buyers, thin liquidity, already pumped)
- `market_gate` rejection (low liquidity, high top10)
- `fast_safety` abort on dangerous contract
- All gates pass → `rule_size_and_buy` emits buy Decision

**`test_graduation_agent.py`** (~10 cases):
- `rule` mode: no LLM node in graph
- `llm` mode without log: `grad_decide` in graph, no `reflect`
- `llm` mode with log: `reflect` inserted before `grad_decide`
- `hybrid` mode: guardrail wired
- `hybrid_audit` mode: `audit_dispatch` in graph, no `reflect`
- `llm_client=None` + `decision_log` → pure rule, no reflect
- Backwards-compat: existing `build_graduation(llm)` call works without log

**`test_graduation_reflective.py`** (~8 cases):
- Seeded losers → `lessons_text` reaches LLM prompt
- Empty log → reflect runs, no lessons block
- `reflect_window` parameter threading
- `hybrid_audit` skips reflect

**Target:** all tests passing, ruff clean → tag `v0.12.0`.

---

## 8. Non-goals (v0.12.0)

- YAML config loader (M13 — deferred)
- Anthropic native adapter (deferred)
- Multi-agent panel / parallel specialist nodes (M11 — needs paid provider)
- Any fetcher, WS subscriber, or RPC call inside the framework
