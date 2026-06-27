# PL1 — Position Lifecycle Helpers (v0.13.0)

**Date:** 2026-06-27
**Status:** Shipped (v0.13.0). All 4 open questions resolved at approval: stop_loss = reason on exit_full (opt 2), trailing arms at +20%, default TP ladder confirmed, PartialExit tracking in PositionState confirmed.
**Version target:** v0.13.0
**Roadmap:** [CAPABILITIES.md §6 — PL1](../CAPABILITIES.md#6-roadmap)

---

## 0. Context

Four entry agents ship today (scanner, sniper, KOL copy-trade, graduation
snipe). All four decide *whether to open*. **Nothing in the framework
helps with the open position.** Users have to bolt on their own TP / SL /
scale-out logic outside the framework.

PL1 is the first **position-management agent**. It is NOT an entry strategy
(see [STRATEGIES.md §Notes](../STRATEGIES.md#notes)) — it's a universal risk
primitive every trader applies. Implementing it inside the framework
unblocks every future entry agent (S5, S6, ...) to ship with built-in exit
recommendations.

---

## 1. What this solves

Standard memecoin exit playbook (validated by mainstream 2026 sources):

| Action | When | Source |
|---|---|---|
| `take_profit` (partial) | PnL crosses ladder rung (e.g. +50% → sell 50% to recoup initials) | CoinLedger 2026 Playbook |
| `scale_out` (partial) | PnL crosses subsequent rungs (+100%, +300%) | DEXTools "profit-taking & position management" |
| `exit_full` (hard SL) | PnL ≤ stop_loss_pct | Universal pro practice |
| `exit_full` (trailing) | Drawdown from peak ≥ trailing_drawdown_pct (after first profit hit) | DEXTools |
| `exit_full` (time stop) | holding_seconds ≥ max_hold_seconds | Memecoin half-life reality |
| `exit_full` (emergency) | Contract goes dangerous, LP rug, etc. after entry | Universal pro practice |
| `hold` | None of the above | Default |

Framework defines + decides; bot pushes a fresh `PositionContext` per tick
and executes whatever the framework returns.

---

## 2. Framework Boundary

| The framework does | The bot does |
|---|---|
| Define `PositionContext / State / Config / Verdict` schemas | Track the open position, persist across ticks |
| Run decision graph (gates → optional LLM → `Decision`) | Stream live price / token snapshot, fill `PositionState` |
| Read `DecisionLog` for `ReflectiveNode` | Subscribe to LP / contract changes (rug post-entry) |
| Return `Decision(action, size)` to bot | Execute sell, manage slippage, MEV |
| | Write outcome to `DecisionLog` after the sell settles |

**Hard constraint:** framework holds NO position state across calls. Bot
pushes a complete `PositionState` snapshot every tick. This keeps PL1
boundary-identical to entry agents.

---

## 3. Schemas (`trading/schemas.py`)

### 3.1 `PositionState`

```python
class PartialExit(BaseModel):
    sold_at_pnl_pct: float       # PnL % at time of partial sell
    sold_size: float             # absolute size sold
    sold_at_ts: float            # unix ts

class PositionState(BaseModel):
    entry_price: float
    entry_size: float            # original position size at entry
    entry_ts: float              # unix ts of entry

    current_price: float
    current_size: float          # what's left after partial exits
    pnl_pct: float               # (current - entry) / entry  — signed
    holding_seconds: float

    peak_pnl_pct: float          # high-water mark since entry (≥ 0 on profit, ≥ entry_pnl on loss-only)
    drawdown_from_peak_pct: float  # 0..1, how far down from peak

    partial_exits: list[PartialExit] = []  # ladder rungs already hit
```

### 3.2 `LifecycleConfig`

```python
class LifecycleConfig(BaseModel):
    decision_mode: Literal["rule", "llm", "hybrid", "hybrid_audit"] = "rule"

    # Hard exits (deterministic, ALWAYS evaluated even in llm/hybrid)
    stop_loss_pct: float = -0.30         # exit if pnl ≤ this
    max_hold_seconds: float = 3600       # exit if held too long
    trailing_drawdown_pct: float = 0.50  # exit on N% drawdown from peak (only after first profit hit)
    trailing_arms_at_pnl_pct: float = 0.20  # trailing SL doesn't arm until +20%

    # TP ladder — list of (pnl_threshold, fraction_of_remaining_to_sell)
    # Defaults: at +50% sell half (recoup initials), at +100% sell another half,
    # at +300% sell remainder.
    tp_ladder: list[tuple[float, float]] = [(0.5, 0.5), (1.0, 0.5), (3.0, 1.0)]

    # Sizing safety
    min_sell_size: float = 0.0           # never emit a sell smaller than this
```

### 3.3 `PositionContext`

```python
@dataclass
class PositionContext:
    token: TokenInput        # current live snapshot (market, contract, etc.)
    position: PositionState
    config: LifecycleConfig = field(default_factory=LifecycleConfig)
```

### 3.4 `LifecycleVerdict` (LLM structured output for llm/hybrid)

```python
class LifecycleVerdict(BaseModel):
    action: Literal["hold", "take_profit", "scale_out", "exit_full"]
    size_pct: float = Field(ge=0, le=1)  # fraction of CURRENT position to sell
    confidence: float = Field(ge=0, le=1)
    reasoning: str = ""
    concerns: list[str] = Field(default_factory=list)
```

Note: LLM cannot emit `stop_loss` — that's a deterministic-only action
fired by the hard SL gate, never by LLM judgement. This prevents the LLM
from hallucinating a "stop loss" when the rule layer didn't actually
trigger.

### 3.5 `Decision` (extend existing)

Add to `Decision.action` Literal union: `"hold"`, `"take_profit"`,
`"scale_out"`, `"exit_full"`. (`"stop_loss"` is conceptually a subtype of
`exit_full` distinguished by `reasons[0]` containing "stop_loss"; we don't
add it as a separate action to keep the Decision schema small.)

All five new types re-exported from `trading/__init__.py`.

---

## 4. Graph architecture

### 4.1 Nodes

All in `strategies/nodes/lifecycle_nodes.py`.

| Node | Type | Purpose |
|---|---|---|
| `emergency_exit` | Rule | Force `exit_full` if contract turns dangerous post-entry (rug, mint authority re-enabled, LP unburned) |
| `hard_stop_loss` | Rule | If `pnl_pct ≤ stop_loss_pct` → `exit_full` |
| `time_stop` | Rule | If `holding_seconds ≥ max_hold_seconds` → `exit_full` |
| `trailing_stop` | Rule | If `peak_pnl_pct ≥ trailing_arms_at_pnl_pct` AND `drawdown_from_peak_pct ≥ trailing_drawdown_pct` → `exit_full` |
| `tp_ladder` | Rule | Find lowest un-hit rung; if `pnl_pct ≥ threshold` → `take_profit` or `scale_out` (size = fraction × current_size) |
| `rule_hold` | Rule | Fall-through: emit `hold` Decision |
| `lifecycle_prompt` | Prompt builder | Build LLM messages; inject `lessons_text` if present |
| `lifecycle_guardrail` | Rule | Hybrid mode: force `exit_full` on emergency / hard SL / time stop; hard-cap sell size; LLM never overrides deterministic exit gates |
| `audit_dispatch` | Rule | Fire async LLM audit task (hybrid_audit) |

### 4.2 Gate order (rule mode)

```
emergency_exit  → exit_full if contract.is_dangerous
hard_stop_loss  → exit_full if pnl ≤ stop_loss_pct
time_stop       → exit_full if holding > max_hold_seconds
trailing_stop   → exit_full if armed + drawdown threshold hit
tp_ladder       → take_profit / scale_out on next un-hit rung
rule_hold       → hold (default)
```

Each gate, on firing, writes `state.output = Decision(...)` and returns
`Command(goto="__end__")`. `rule_hold` is the only node that always
falls through.

### 4.3 Mode wiring

```
rule:
  emergency_exit → hard_stop_loss → time_stop → trailing_stop →
    tp_ladder → rule_hold → END

llm / hybrid:
  emergency_exit → hard_stop_loss → time_stop → [reflect?] →
    lifecycle_decide → END
  (trailing_stop + tp_ladder folded into the LLM — but guardrail enforces
   the hard exits)

hybrid_audit:
  emergency_exit → hard_stop_loss → time_stop → trailing_stop →
    tp_ladder → rule_hold → audit_dispatch → END
  (reflect intentionally skipped — sub-ms rule path must not block on a
   memory read; bot reflects offline)
```

**Design choice — deterministic gates ALWAYS run first, even in llm
mode.** Unlike entry agents (where LLM can fully decide), here we keep
emergency / hard SL / time stop as rule-only. Reason: the cost of being
wrong on an open position is much higher than on an entry. We never let
the LLM hold past a hard SL or a known rug.

### 4.4 Reflective loop

Identical to scanner / sniper / KOL / graduation pattern:

- `ReflectiveNode("reflect", decision_log, window, ...)` inserted between
  `time_stop` and `lifecycle_decide` in `llm` / `hybrid` modes when
  `decision_log is not None`.
- `lifecycle_prompt` reads `state.scratch["lessons_text"]` and injects a
  `LESSONS from recent position-lifecycle outcomes` system block.
- `hybrid_audit` skips reflect (sub-ms rule path).

### 4.5 LLM prompt sketch

System message names the role + lays out the action space + emphasises
that emergency / hard SL gates have ALREADY been checked (LLM is deciding
inside the safe envelope). User message includes:

- Current PnL, peak PnL, drawdown from peak, holding seconds
- TP ladder state (which rungs hit, which next)
- Current token snapshot (liquidity, holder distribution drift, volume)
- Live wallet intel (have smart wallets started selling?)

LLM picks `hold` / `take_profit` / `scale_out` / `exit_full` with
`size_pct`.

---

## 5. Factory

```python
# strategies/agents/lifecycle.py
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
```

Signature is intentionally identical to `build_sniper` / `build_graduation`
/ `build_kol_copytrade` for API consistency. Re-exported from
`strategies/__init__.py` as `build_lifecycle`.

---

## 6. Files Changed

### New
```
trading/schemas.py                        ← +5 types (PositionState, PartialExit,
                                            LifecycleConfig, PositionContext,
                                            LifecycleVerdict) + extend Decision.action
trading/__init__.py                       ← re-export new types
strategies/nodes/lifecycle_nodes.py       ← all nodes + prompt builder
strategies/agents/lifecycle.py            ← build_lifecycle() factory
strategies/__init__.py                    ← re-export build_lifecycle
examples/run_lifecycle.py                 ← offline stub + ZETRYN_LIFECYCLE_USE_GROQ=1
tests/test_lifecycle_nodes.py             ← gate trigger cases
tests/test_lifecycle_agent.py             ← mode wiring tests
tests/test_lifecycle_reflective.py        ← reflective loop tests
docs/plans/2026-06-27-position-lifecycle-helpers.md  ← this file
```

### Updated
```
docs/CAPABILITIES.md   ← PL1 row: planned → done
docs/plans/README.md   ← add PL1 row
CHANGELOG.md           ← v0.13.0 entry
zetryn/__init__.py     ← version 0.12.0 → 0.13.0
pyproject.toml         ← version 0.12.0 → 0.13.0
```

---

## 7. Test Plan

**`test_lifecycle_nodes.py`** (~14 cases):
- `emergency_exit` fires on contract turning dangerous post-entry
- `hard_stop_loss` fires at exactly `pnl == stop_loss_pct`
- `hard_stop_loss` does NOT fire just above SL threshold
- `time_stop` fires at `holding_seconds == max_hold_seconds`
- `trailing_stop` does NOT fire before `trailing_arms_at_pnl_pct`
- `trailing_stop` fires when armed + drawdown threshold hit
- `tp_ladder` fires first rung when threshold crossed
- `tp_ladder` skips already-hit rungs (reads `partial_exits`)
- `tp_ladder` final rung emits `exit_full` (sells 100% remaining)
- `tp_ladder` size = fraction × `current_size`, not original
- `rule_hold` is the default when no gate fires
- gate ordering: emergency wins over SL wins over time wins over trailing wins over TP
- `min_sell_size` is respected — sells below threshold demoted to hold
- size never exceeds `current_size`

**`test_lifecycle_agent.py`** (~10 cases):
- `rule` mode: no LLM in graph
- `llm` mode without log: `lifecycle_decide` in graph, no reflect
- `llm` mode with log: reflect inserted before lifecycle_decide
- `hybrid` mode: guardrail wired (LLM cannot override hard SL)
- `hybrid_audit` mode: `audit_dispatch` in graph, no reflect
- `hybrid_audit` returns rule decision instantly + dispatches task
- `llm_client=None` + `decision_log` → pure rule, no reflect
- LLM decision `hold` honored when no gate fires
- LLM decision `scale_out 50%` honored, size = 0.5 × current_size
- LLM failure → graceful skip via guardrail (default to rule decision)

**`test_lifecycle_reflective.py`** (~6 cases):
- Seeded losing exits → `lessons_text` reaches LLM prompt
- Empty log → reflect runs, no lessons block
- `reflect_window` parameter threading
- `hybrid_audit` skips reflect
- `rule` mode skips reflect even with log provided
- `llm_client=None` + log → no reflect

**Target:** all tests passing, ruff clean → tag v0.13.0.

---

## 8. Non-goals (v0.13.0)

- **Position persistence inside the framework** — bot owns this. The
  framework receives a complete `PositionState` per tick; it never
  remembers state between calls.
- **Dynamic TP ladder learning** — TP ladder is config-driven (static per
  position). A future `LifecycleConfig.adaptive_ladder` flag could read
  from `DecisionLog`, but not v0.13.
- **Multi-position portfolio logic** — one `PositionContext` = one
  position. Cross-position concerns (correlated exits, portfolio-level
  drawdown) are bot-level.
- **MEV-aware slippage modeling** — execution layer; out of framework
  scope.
- **Re-entry recommendations after exit** — if the bot wants to re-enter,
  it pushes the token back into an entry agent. PL1 only handles the
  current open position.

---

## 9. Open questions for review

1. **Action vocabulary.** Should `stop_loss` be a separate `Decision.action`
   value, or is it sufficient to use `exit_full` with `reasons=[
   "hard_stop_loss"]`? Current draft uses the second approach (smaller
   schema). Confirm OK or split.

2. **Trailing arming threshold.** Default `trailing_arms_at_pnl_pct = 0.20`
   (only trail after +20%). Reasonable, or should default be 0 (trail from
   entry)?

3. **TP ladder defaults.** `[(0.5, 0.5), (1.0, 0.5), (3.0, 1.0)]` = sell
   half at +50%, half of remainder at +100%, all at +300%. Standard memecoin
   playbook — confirm or override.

4. **`PartialExit` tracking inside `PositionState`** — required so the bot
   can replay "which ladder rungs already hit". Bot fills this; framework
   reads. OK with the shape?
