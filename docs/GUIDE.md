# Zetryn Trading — Developer Guide

Reference for everything that doesn't belong in the README overview. Start
here when you want to configure providers, wire up knowledge, add tools, or
understand how an agent makes decisions.

---

## Contents

1. [LLM Providers](#1-llm-providers)
2. [Key Rotation & Multi-Provider Router](#2-key-rotation--multi-provider-router)
3. [Knowledge — static context the LLM reads](#3-knowledge--static-context-the-llm-reads)
4. [Skills — callable tools the LLM invokes](#4-skills--callable-tools-the-llm-invokes)
5. [Decision Modes](#5-decision-modes)
6. [Memory & Reflective Loop](#6-memory--reflective-loop)
7. [Agent Reference](#7-agent-reference)
8. [Backtesting](#8-backtesting)
9. [Bot Integration](#9-bot-integration)

---

## 1. LLM Providers

All providers are wired via `OpenAICompatibleClient` + `ProviderConfig`. Base
URLs are exported from `zetryn.llm` for convenience.

```python
from zetryn.llm import OpenAICompatibleClient, ProviderConfig
from zetryn.llm import (
    GROQ_BASE_URL,
    GEMINI_BASE_URL,
    OPENROUTER_BASE_URL,
    CEREBRAS_BASE_URL,
    MISTRAL_BASE_URL,
    SAMBANOVA_BASE_URL,
    NVIDIA_NIM_BASE_URL,
)
```

### Provider & Model Reference

| Provider | `base_url` constant | Free-tier key env example | Recommended model |
|---|---|---|---|
| **Groq** | `GROQ_BASE_URL` | `GROQ_API_KEY_1` | `llama-3.3-70b-versatile` |
| **Gemini** | `GEMINI_BASE_URL` | `GEMINI_API_KEY` | `gemini-2.5-flash` |
| **OpenRouter** | `OPENROUTER_BASE_URL` | `OPENROUTER_API_KEY` | any `model:free` |
| **Cerebras** | `CEREBRAS_BASE_URL` | `CEREBRAS_API_KEY` | `llama-3.3-70b` |
| **Mistral** | `MISTRAL_BASE_URL` | `MISTRAL_API_KEY` | `mistral-small-latest` |
| **SambaNova** | `SAMBANOVA_BASE_URL` | `SAMBANOVA_API_KEY` | `Meta-Llama-3.3-70B-Instruct` |
| **NVIDIA NIM** | `NVIDIA_NIM_BASE_URL` | `NVIDIA_API_KEY` | `meta/llama-3.3-70b-instruct` |

### Per-Provider Free-Tier Models

**Groq**
```
llama-3.1-8b-instant          rpm=30  rpd=14400  tpm=6000   tpd=500000
llama-3.3-70b-versatile       rpm=30  rpd=1000   tpm=12000  tpd=100000
meta-llama/llama-4-scout-...  rpm=30  rpd=1000   tpm=30000  tpd=500000
openai/gpt-oss-120b           rpm=30  rpd=1000   tpm=8000   tpd=200000
openai/gpt-oss-20b            rpm=30  rpd=1000   tpm=8000   tpd=200000
qwen/qwen3-32b                rpm=60  rpd=1000   tpm=6000   tpd=500000
groq/compound                 rpm=30  rpd=250    tpm=70000
groq/compound-mini            rpm=30  rpd=250    tpm=70000
```

**Gemini**
```
gemini-2.5-flash              rpm=5   rpd=20     tpm=250000
gemini-2.5-flash-lite         rpm=10  rpd=20     tpm=250000
gemini-3.1-flash-lite         rpm=15  rpd=500    tpm=250000
gemini-3-flash                rpm=5   rpd=20     tpm=250000
gemini-3.5-flash              rpm=5   rpd=20     tpm=250000
```

**Cerebras** (wafer-scale, ~2600 tok/s output)
```
llama-4-scout-17b-16e-instruct    rpm=30  tpm=60000   tpd=1000000
llama-3.3-70b                     rpm=30  tpm=60000   tpd=1000000
qwen-3-32b                        rpm=30  tpm=60000   tpd=1000000
qwen-3-235b-a22b-instruct-2507    rpm=5   tpm=30000   tpd=1000000
gpt-oss-120b                      rpm=30  tpm=60000   tpd=1000000
glm-4.5-air                       rpm=5   tpm=30000   tpd=1000000
```

**SambaNova** (RDU hardware)
```
Meta-Llama-3.1-8B-Instruct    rpm=30  rpd=20  tpd=200000
Meta-Llama-3.1-70B-Instruct   rpm=20  rpd=20  tpd=200000
Meta-Llama-3.1-405B-Instruct  rpm=10  rpd=20  tpd=200000
Meta-Llama-3.3-70B-Instruct   rpm=20  rpd=20  tpd=200000
Qwen2.5-72B-Instruct          rpm=20  rpd=20  tpd=200000
```

**NVIDIA NIM** (phone-verified, free for prototyping)
```
deepseek-ai/deepseek-r1              rpm=40
deepseek-ai/deepseek-v3              rpm=40
meta/llama-3.3-70b-instruct          rpm=40
meta/llama-3.1-405b-instruct         rpm=40
nvidia/nemotron-4-340b-instruct      rpm=40
qwen/qwen2.5-coder-32b-instruct      rpm=40
```

**Mistral** (tight RPM — best for low-volume, high-quality calls)
```
mistral-large-latest    rpm=2  tpm=500000
mistral-small-latest    rpm=2  tpm=500000
codestral-latest        rpm=2  tpm=500000
pixtral-12b-2409        rpm=2  tpm=500000
```

**OpenRouter** (`:free` suffix = shared global limit)
```
<any-model>:free        rpm=20  rpd=50   (rpd=200 with ≥$10 credits on account)
```

### Minimal single-provider setup

```python
from zetryn.llm import OpenAICompatibleClient, ProviderConfig, GROQ_BASE_URL

llm = OpenAICompatibleClient(ProviderConfig(
    name="groq",
    base_url=GROQ_BASE_URL,
    model="llama-3.3-70b-versatile",
    key_envs=["GROQ_API_KEY_1", "GROQ_API_KEY_2"],  # rotated on 429
))
```

---

## 2. Key Rotation & Multi-Provider Router

### How KeyPool works

`ProviderConfig.key_envs` lists environment variable *names* (not values).
`OpenAICompatibleClient` resolves them at startup into a `KeyPool`. On each
request the pool picks the least-recently-used active key. On HTTP 429 that
key is penalised (60 s cooldown) and the next available key is tried
automatically — no code change needed.

```python
# 3 keys → 3× the free-tier quota for that provider
ProviderConfig(key_envs=["GROQ_API_KEY_1", "GROQ_API_KEY_2", "GROQ_API_KEY_3"])
```

Keys missing from the environment are silently skipped. At least one must
be present or the client raises `NoKeysAvailableError` at startup.

### LLMRouter — multi-provider failover

`LLMRouter` satisfies the same `LLMClient` protocol as
`OpenAICompatibleClient` — it's a drop-in replacement wherever a client is
accepted.

```python
from zetryn.llm import (
    LLMRouter, RouterEntry, OpenAICompatibleClient,
    ProviderConfig, get_free_tier_limit,
    GROQ_BASE_URL, GEMINI_BASE_URL,
)

groq = OpenAICompatibleClient(ProviderConfig(
    name="groq", base_url=GROQ_BASE_URL,
    model="llama-3.3-70b-versatile",
    key_envs=["GROQ_API_KEY_1", "GROQ_API_KEY_2"],
))
gemini = OpenAICompatibleClient(ProviderConfig(
    name="gemini", base_url=GEMINI_BASE_URL,
    model="gemini-2.5-flash",
    key_envs=["GEMINI_API_KEY"],
))

router = LLMRouter([
    RouterEntry(
        client=groq,
        name="groq:llama-3.3-70b",
        limit=get_free_tier_limit("groq", "llama-3.3-70b-versatile"),
    ),
    RouterEntry(
        client=gemini,
        name="gemini:2.5-flash",
        limit=get_free_tier_limit("gemini", "gemini-2.5-flash"),
    ),
])

scanner = build_scanner(router)   # router is an LLMClient — drop-in
```

**Rotation order:** entry-by-entry (outer), then key-by-key within each
entry's `KeyPool` (inner). A 429 on one entry's every key triggers a 30 s
entry cooldown and the router moves to the next entry. All entries exhausted
→ `NoKeysAvailableError` → `LLMNode` applies its fallback, graph never
crashes.

### Tier presets

Three opinionated preset orderings. Import and call `build_tier_entries()`:

```python
from zetryn.llm import (
    TIER_SPEED, TIER_QUALITY, TIER_VOLUME,
    build_tier_entries, LLMRouter,
    GROQ_BASE_URL, CEREBRAS_BASE_URL, GEMINI_BASE_URL,
    OpenAICompatibleClient, ProviderConfig,
)

clients = {
    "groq": OpenAICompatibleClient(ProviderConfig(
        name="groq", base_url=GROQ_BASE_URL,
        key_envs=["GROQ_API_KEY_1"],
    )),
    "cerebras": OpenAICompatibleClient(ProviderConfig(
        name="cerebras", base_url=CEREBRAS_BASE_URL,
        key_envs=["CEREBRAS_API_KEY"],
    )),
    "gemini": OpenAICompatibleClient(ProviderConfig(
        name="gemini", base_url=GEMINI_BASE_URL,
        key_envs=["GEMINI_API_KEY"],
    )),
}

# Pick one tier:
router = LLMRouter(build_tier_entries(TIER_SPEED,   clients))  # Cerebras → Groq
router = LLMRouter(build_tier_entries(TIER_QUALITY, clients))  # SambaNova 405B → Gemini → Groq
router = LLMRouter(build_tier_entries(TIER_VOLUME,  clients))  # OpenRouter :free → Gemini → Groq
```

Providers absent from the `clients` dict are silently skipped. Working
example: [`examples/run_kol_tier_router.py`](../examples/run_kol_tier_router.py).

---

## 3. Knowledge — static context the LLM reads

`KnowledgePack` bundles static facts and is read once at startup. The LLM
sees these facts in every run via the system prompt.

### Directory layout

```
my-bot/knowledge/
├── system/
│   ├── 01-house-rules.md      ← sorted alphabetically → injected in order
│   ├── 02-rug-patterns.md
│   └── 03-kol-whitelist.md
└── data/
    ├── kol_whitelist.json     ← namespace = "kol_whitelist"
    └── blacklist-tokens.json  ← namespace = "blacklist-tokens"
```

### Loading

```python
from zetryn.knowledge import KnowledgePack

pack = KnowledgePack.from_dir("./my-bot/knowledge")
```

Files under `system/` are loaded in filename order. Each becomes a
`system`-role message prepended to the LLM prompt before any per-run data.
Files under `data/` are loaded as JSON and accessible via `lookup()`.

### Using in an agent

```python
scanner = build_scanner(llm, knowledge_pack=pack)
# or
sniper  = build_sniper(llm,   knowledge_pack=pack)
# or any other agent builder
```

The agent's prompt builder calls `pack.system_blocks()` automatically. No
other wiring needed.

### Programmatic lookups in rule nodes

```python
# In a rule node (state: State):
pack = state.context.config.knowledge_pack   # if you pass it via context
whitelist = pack.lookup("kol_whitelist")     # returns the parsed JSON object
entry = pack.lookup("kol_whitelist", "wallet_address_here", default=None)
```

### `KOLRegistry` — typed view over a JSON data file

```python
from strategies.kol_registry import KOLRegistry

registry = KOLRegistry.from_pack(pack)  # reads data/kol_whitelist.json
profile = registry.get("wallet_address")
# profile: KOLProfile | None
```

`SmartWalletRegistry` follows the same pattern for the confluence strategy.

---

## 4. Skills — callable tools the LLM invokes

Tools are capabilities the LLM can decide to call mid-analysis. Unlike
knowledge (passive, always present), a tool is only invoked when the LLM
decides it needs the information.

### Defining a tool

```python
from pydantic import BaseModel
from zetryn.tools import Tool

class HolderCheckInput(BaseModel):
    mint: str
    top_n: int = 10

async def check_holders(inp: HolderCheckInput) -> dict:
    # Your data fetcher — RPC, API, cache, whatever
    data = await my_rpc_client.get_token_accounts(inp.mint, limit=inp.top_n)
    return {"count": data.total, "top10_pct": data.top10_pct}

tool = Tool(
    name="check_holders",
    description="Fetch on-chain holder distribution for a token.",
    fn=check_holders,
    input_schema=HolderCheckInput,
)
```

### Registering tools

```python
from zetryn.tools import ToolRegistry

registry = ToolRegistry()
registry.register(tool)
```

### Using in an agent

```python
from zetryn.llm.tool_use import ToolUseNode

# ToolUseNode drives the LLM ↔ tool loop
node = ToolUseNode(
    "analyst",
    llm_client=llm,
    registry=registry,
    prompt_fn=my_prompt_builder,
    result_fn=my_result_parser,
    max_iterations=5,
)
```

The `tool_use_loop` function can also be called standalone inside a
`RuleNode` for custom wiring. Working example:
[`examples/run_with_tools.py`](../examples/run_with_tools.py).

### Rule of thumb

Use knowledge when the LLM just needs to *know* something upfront (static
rules, whitelists, lessons). Use a tool when the LLM needs to *fetch* data
to answer a question that changes per run.

---

## 5. Decision Modes

All strategy agents (except Scanner, which is AI-first only) support four
modes via `config.decision_mode`.

| Mode | Latency | LLM in hot path | When to use |
|---|---|---|---|
| `rule` | < 1 ms | No | Production hot path; maximum speed |
| `llm` | 200–500 ms | Yes (decides) | LLM drives the decision fully |
| `hybrid` | 200–500 ms | Yes + guardrail | LLM decides; rule guardrail can only demote, never promote |
| `hybrid_audit` | **< 1 ms decision** + async AI | Async, non-blocking | Best of both: bot acts immediately on rule decision, LLM second-opinions in background |

### `hybrid_audit` pattern

```python
state = await agent.run(State(context=ctx))

# Decision is available immediately — act on it now.
bot.execute(state.output)

# Later, await the background audit (no rush):
if "audit_task" in state.scratch:
    verdict = await state.scratch["audit_task"]
    # verdict: AuditVerdict(agrees, confidence, concerns, reasoning)
    await decision_log.log(state.run_id, {
        **state.output.model_dump(),
        "audit": verdict.model_dump(),
    })
```

### Setting the mode

```python
from trading import SniperConfig, TradingContext

ctx = TradingContext(
    token=token_input,
    config=SniperConfig(decision_mode="hybrid_audit"),
)
```

Each agent has its own `Config` class (e.g. `SniperConfig`, `GrowthConfig`,
`DipBuyConfig`). All expose `decision_mode` with the same four options.

---

## 6. Memory & Reflective Loop

### Stores

```python
from zetryn.memory import InMemoryStore, JSONFileStore

# For tests and ephemeral runs — zero setup:
store = InMemoryStore()

# For cross-run persistence:
store = JSONFileStore("./decisions.json")
```

### DecisionLog

Records every decision + outcome. The bot calls `record_outcome()` after
the trade result is known.

```python
from zetryn.memory import DecisionLog

log = DecisionLog(JSONFileStore("./decisions.json"))

# After agent.run():
await log.log(state.run_id, state.output.model_dump())

# After trade closes (bot side):
await log.record_outcome(state.run_id, pnl_pct=-0.12, outcome="loss")
```

### ReflectiveNode — loss-aware LLM

Pass `decision_log` to any agent builder that supports it. The node runs
**before** the LLM call, reads the last `reflect_window` decisions from the
log, buckets losers by feature quartile, and writes a `LESSONS from recent
outcomes` block to `state.scratch["lessons_text"]`. The LLM's prompt
builder picks this up automatically.

```python
sniper = build_sniper(
    llm,
    decision_log=log,
    reflect_window=20,    # how many past decisions to look at
    reflect_top_k=5,      # top-k loser patterns to surface in the prompt
    reflect_feature_keys=["top10_pct", "whale_pct", "source"],  # optional focus
)
```

**When the node runs:**
- `llm` / `hybrid` modes → `ReflectiveNode` runs before the LLM call
- `rule` / `hybrid_audit` modes → skipped (rule path must not block on I/O)

**No `decision_log` passed →** behaviour is identical to prior releases
(backwards-compatible). The `ReflectiveNode` is simply not added to the
graph.

### Blacklist

```python
from zetryn.memory import Blacklist

bl = Blacklist(store)
await bl.add_mint("SCAM_MINT_123")
await bl.add_dev("RUGGED_DEV_WALLET")

# Inside fast_safety node — checked automatically when using strategies.nodes.sniper_nodes.fast_safety
```

---

## 7. Agent Reference

All agents return a `Decision`:

```python
Decision(
    action:     str,          # see per-agent table
    confidence: float,        # 0..1
    size:       float | None, # position size multiplier or pct
    scores:     dict[str, float],
    reasons:    list[str],    # human-readable audit trail
    flags:      dict[str, Any],  # rug_risk, llm_failed, classification, ...
    meta:       dict[str, Any],  # run_id, latency_ms
)
```

---

### Scanner — `build_scanner`

AI-first discovery. Single rich LLM call across safety / market / wallets /
social. Slow path (~1–3 s).

```python
from strategies import build_scanner
from trading import ScannerConfig, TradingContext
from zetryn.core import State

scanner = build_scanner(llm, knowledge_pack=pack, decision_log=log)
state = await scanner.run(State(context=TradingContext(token=token_input)))
```

| `action` | Meaning |
|---|---|
| `"alert"` | Strong buy signal |
| `"watch"` | Monitor, not yet ready |
| `"skip"` | Reject |

---

### Sniper — `build_sniper`

Sub-millisecond launch entry. Four modes.

```python
from strategies import build_sniper
from trading import SniperConfig, TradingContext

sniper = build_sniper(llm, knowledge_pack=pack, decision_log=log)
state = await sniper.run(State(context=TradingContext(
    token=token_input,
    config=SniperConfig(decision_mode="hybrid_audit", max_size=2.0),
)))
```

| `action` | Meaning |
|---|---|
| `"buy"` | Enter now |
| `"skip"` | Pass |
| `"abort"` | Rug/manipulation detected |

Graph: `fast_safety → fast_market → [reflect →] snipe_decide / rule_buy → [audit] → END`

---

### KOL Copy-Trade — `build_kol_copytrade`

Copy pre-vetted KOL wallet buys. Three modes (`rule` / `confirmed` / `audit`).
Requires a `KnowledgePack` with `data/kol_whitelist.json` or a pre-built
`KOLRegistry`.

```python
from strategies import build_kol_copytrade, KOLRegistry

registry = KOLRegistry.from_pack(pack)  # or pass pack= directly

agent = build_kol_copytrade(
    llm_client=llm,
    registry=registry,
    decision_mode="confirmed",
    decision_log=log,
)
from trading import KOLContext, KOLBuyEvent
state = await agent.run(State(context=KOLContext(token=token_input, event=buy_event)))
```

---

### Graduation Snipe — `build_graduation`

Entry in the 5–30 s window after a Pump.fun token graduates to Raydium. Gates
on bonding-curve fill speed, unique buyers, LP burned, premium %.

```python
from strategies import build_graduation
from trading import GraduationContext, GraduationEvent, GraduationConfig

agent = build_graduation(llm, knowledge_pack=pack, decision_log=log)
state = await agent.run(State(context=GraduationContext(
    token=token_input,
    event=GraduationEvent(
        mint="...", graduated_at_ts=..., bonding_curve_fill_pct=0.98,
        unique_buyers_pre_grad=320, lp_burned=True, lp_locked=False,
        graduation_premium_pct=0.15,
    ),
    config=GraduationConfig(decision_mode="hybrid_audit"),
)))
```

---

### Position Lifecycle — `build_lifecycle`

Position management: hold / take-profit / scale-out / emergency exit.
Hard exits (emergency / SL / time stop) are always rule-deterministic even
in `llm` / `hybrid` modes.

```python
from strategies import build_lifecycle
from trading import PositionContext, PositionState, LifecycleConfig

agent = build_lifecycle(llm, decision_log=log)
state = await agent.run(State(context=PositionContext(
    token=token_input,
    position=PositionState(
        entry_price=0.00100, current_price=0.00135,
        entry_ts=..., size_sol=1.5,
        peak_price=0.00140, stop_loss_pct=0.20,
    ),
    config=LifecycleConfig(decision_mode="rule"),
)))
# action ∈ {"hold", "take_profit", "scale_out", "exit_full"}
```

---

### Smart Money Confluence — `build_confluence`

Fires when ≥ N pre-vetted smart wallets have accumulated the same token
within a rolling window. Requires a `SmartWalletRegistry`.

```python
from strategies import build_confluence, SmartWalletRegistry
from trading import ConfluenceContext, ConfluenceEvent, ConfluenceConfig

registry = SmartWalletRegistry.from_pack(pack)  # data/smart_wallet_whitelist.json

agent = build_confluence(llm, registry=registry, decision_log=log)
state = await agent.run(State(context=ConfluenceContext(
    token=token_input,
    event=ConfluenceEvent(
        mint="...", detected_at_ts=...,
        accumulations=[...],  # list[SmartWalletAccumulation]
    ),
    config=ConfluenceConfig(decision_mode="hybrid_audit", min_wallet_count=3),
)))
```

---

### Early-Stage Dip Buy — `build_dip_buy`

Post-dump recovery entry. One agent, two events: `launch` (sniper/bundler
dump clears, token still in bonding curve) or `graduation` (early-BC-buyer
TP wave after Raydium migration).

```python
from strategies import build_dip_buy
from trading import DipBuyContext, DipBuySnapshot, DipBuyConfig

agent = build_dip_buy(llm, decision_log=log)
state = await agent.run(State(context=DipBuyContext(
    token=token_input,
    snapshot=DipBuySnapshot(
        event_type="launch",          # or "graduation"
        mint="...",
        detected_at_ts=...,
        time_since_event_seconds=180.0,
        price_vs_ath_pct=-0.30,       # 30% below ATH
        sell_pressure_score=0.20,
        buy_ratio_5m=0.60,
        holder_retention_pct=0.75,
        unique_buyers_trend=0.30,
        price_stable_seconds=60.0,
    ),
    config=DipBuyConfig(
        event_type="launch",
        decision_mode="hybrid_audit",
    ),
)))
```

Gates: `timing_gate → dip_gate → recovery_gate → market_gate → decision`

---

### Organic Growth Detector — `build_organic_detector`

Triage filter that classifies post-launch time-series as organic, suspicious,
or manipulated. Use it to promote scanner candidates with confirmed organic
chart patterns.

```python
from strategies import build_organic_detector
from trading import GrowthContext, GrowthSnapshot, GrowthConfig

agent = build_organic_detector(llm, decision_log=log)
state = await agent.run(State(context=GrowthContext(
    token=token_input,
    snapshot=GrowthSnapshot(
        mint="...",
        detected_at_ts=...,
        observation_seconds=300.0,    # how long you've been watching
        candle_count=10,
        price_trajectory="steady_climb",  # steady_climb | volatile | vertical_pump | flat | declining
        sell_presence_pct=0.30,       # 0=no sells, 1=every candle has sells
        unique_buyer_trend=0.40,      # >0 = rising, <0 = declining
        holder_growth_rate=3.0,       # new holders/min
        has_healthy_pullback=True,
        max_drawdown_pct=0.12,
        whale_volume_pct=0.25,
        volume_acceleration=1.8,
    ),
    config=GrowthConfig(decision_mode="rule"),
)))

d = state.output
# d.action          → "buy" (organic) | "skip" (suspicious) | "abort" (manipulated)
# d.flags["classification"]      → "organic" | "suspicious" | "manipulated"
# d.scores["organic_score"]      → 0.0 – 1.0  (5 dims × 0.2 each)
```

Hard-abort patterns caught before scoring:
- `vertical_pump` + `sell_presence < 0.03` → coordinated pump, instant abort
- `whale_volume_pct > 0.85` → extreme whale dominance, instant abort

---

## 8. Backtesting

```python
from zetryn.backtest import Backtester
from trading import TradingContext

items = [
    ("id-001", TradingContext(token=token_a)),
    ("id-002", TradingContext(token=token_b)),
    # ...
]

bt = Backtester(agent)
result = await bt.run(items)

print(result.total)           # total runs
print(result.by_action)       # {"buy": 12, "skip": 38, "abort": 5}
print(result.avg_confidence)  # mean confidence across all decisions
```

Test, backtest, and live use the same compiled graph. Swap the
`DataProvider` or `TokenInput` source — the agent is unchanged.

---

## 9. Bot Integration

How your bot feeds data to the agent, and how to keep the framework fast
when the surrounding pipeline isn't.

### Push vs pull

Zetryn supports both data-ingress patterns:

- **Push** (recommended for production): the bot fetches data, builds
  `TokenInput`, and calls
  `agent.run(State(context=TradingContext(token=token_input)))`. Latency
  is predictable because the agent never reaches out — every external
  call happened in your code, on your terms.
- **Pull**: the bot implements the `DataProvider` protocol and the agent
  calls `provider.fetch(mint)`. Useful for backtests with
  `HistoricalDataProvider`, or for testing with `MockDataProvider`.

Test, backtest, and live use the **same compiled graph** — only the
provider (or where the `TokenInput` came from) changes.

### Pre-filter at the bot

Zetryn is cheap to run, but **filling `TokenInput` is not** — Helius,
GMGN, Twitter, DexScreener, BirdEye all cost API quota and latency.
Pre-filter at the bot so the agent only sees candidates worth a deep
look.

```python
def worth_fetching(ws_event) -> bool:
    return (
        ws_event.liquidity_usd >= 3_000
        and 30 <= ws_event.age_seconds <= 3600
        and ws_event.mint not in blacklist
        and ws_event.creator not in known_ruggers
    )
```

Typical funnel: 10,000 tokens/min from a Pump.fun WebSocket → ~50
candidates/min after pre-filter → fully enriched and pushed to the
agent. The agent's job is the **last mile** (decision), not discovery.

If the bot can answer "is this even plausibly tradable?" in under 1 ms
with rules, do it there. The agent should only see candidates the bot
already believes warrant the LLM call.

### What Zetryn owns vs what the bot owns

The boundary is non-negotiable. Mixing these up is the #1 source of
confusion when integrating Zetryn for the first time.

| Zetryn (framework) | Bot (caller) |
|---|---|
| Graph orchestration | RPC, wallet, signing |
| LLM calls (advisor / analyst / decider) | Hot loop, mempool watching |
| Scoring, decision aggregation | Trade execution, slippage, MEV |
| Memory (blacklist, decision log) | Position tracking, PnL |
| Observability (trace, hooks) | Pre-filter, fetch budgeting |
| Backtest harness | Live market data feeds |

**Zetryn decides, the bot executes.** Never the reverse. If you find
yourself adding a fetcher inside `zetryn/`, stop — it belongs in your
bot.
