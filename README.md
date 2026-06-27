# Zetryn Trading

**AI Agent Trading from Zetryn AI.**

> [!WARNING]
> **🚧 Alpha — work in progress.** Zetryn Trading is in active development.
> Public APIs may change between minor versions, the AI analyst prompts are
> still being tuned with real outcome data, and the Zetryn platform
> (subscription auth, hosted Hardes / Medifus / Easfus models) is **not yet
> live**. Today the library runs on public LLM providers (Groq / Gemini /
> OpenRouter / OpenAI / Anthropic) with your own keys.
>
> **Recommended use right now:** development, research, paper trading,
> backtests, dogfooding inside your own bot. **Not yet recommended for
> unattended live trading with real funds.** No warranty — see [LICENSE](LICENSE).

A Python library that turns raw Solana memecoin data into structured,
auditable trading decisions. You bring the bot, the wallet, and the RPC;
Zetryn Trading provides the **agent** — a graph of LLM analysts and hard-rule
guardrails.

```
BOT (yours)                   ZETRYN TRADING (this library)
─────────────                 ─────────────────────────────────────
gather token data  ──push──>  safety_gate → intel_gate → market_gate
                                                  │
                                         ┌────────┘
                                         ▼
                              ai analyst (LLM): safety / market /
                                         wallets / social verdict
                                                  │
                                         guardrail (sanity check)
                                                  │
                                                  ▼
                                       Decision { action, confidence,
                                                  analysis, reasons }
                                                  │
execute (or not) <───────────────────────────────┘
```

Zetryn Trading **decides**; the bot **executes**. The library never holds your
private key and never touches the chain.

---

## Why AI-first?

Most "trading bots" are spreadsheets with extra steps: thresholds, weighted
formulas, hardcoded heuristics. They work — until rug techniques evolve, or a
qualitative signal (Twitter mention velocity, KOL pattern, bonding curve regime)
matters more than your formula captured.

Zetryn's reference agents put an **LLM as the primary analyst**:

- **Hard gates** instantly reject obvious junk (honeypot, mint authority active,
  dev rug history, bundle attacks, dead liquidity). Sub-millisecond. No LLM call
  burned on rugs.
- **AI analyst** (one rich LLM call) evaluates survivors across four dimensions —
  safety, market, wallets, social — returning a structured `FullAnalysis` with
  per-aspect verdict + reasoning + final recommendation.
- **Guardrail** rules sanity-check the LLM's output. They can demote a verdict
  but never promote — hard reality (liquidity floor, sniper density) always wins
  over a hallucinated bullish call.

Result: decisions you can **audit**, **debug**, and **explain** — not just a
score from nowhere.

---

## Knowledge vs Skills

Two ways to extend the agent without forking the framework. They solve
different problems — use both if you need both.

|   | **Knowledge** | **Skills** |
|---|---|---|
| What it is | Passive context the LLM **reads** | Callable functions the LLM **invokes** |
| Form | Markdown rules + JSON data files | Python functions with input schemas |
| When evaluated | Once, prepended to the system prompt | On demand, mid-analysis |
| API | [`KnowledgePack`](zetryn/knowledge/pack.py) | [`Tool`, `ToolRegistry`](zetryn/tools/) |
| Examples | House rules, KOL whitelist, blacklist tokens, lessons | `check_rug(mint)`, `fetch_holders(mint)`, `get_kol_buys(mint)` |
| Cost | Free (just tokens in the prompt) | Each call is a real API / RPC hit |

**Rule of thumb:** if the LLM should *know* something up front, it's
**knowledge**. If the LLM should *do* something to get an answer, it's a
**skill**.

```python
from zetryn.knowledge import KnowledgePack
from zetryn.tools import Tool, ToolRegistry
from strategies import build_scanner

# 1. KNOWLEDGE — facts and rules the analyst reads in every run
pack = KnowledgePack.from_dir("./my-bot/knowledge")
#   ./my-bot/knowledge/system/01-house-rules.md
#   ./my-bot/knowledge/data/kol-whitelist.json

# 2. SKILLS — capabilities the analyst can invoke when it needs more data
async def check_rug(mint: str) -> dict:
    return await rugcheck_api.score(mint)

tools = ToolRegistry()
tools.register(Tool("check_rug", "On-chain rug verification", check_rug))

# 3. Wire both into the agent
scanner = build_scanner(llm, knowledge_pack=pack)
# (tool-use loop wiring lands in a follow-up release — see CAPABILITIES.md)
```

**Status:** `KnowledgePack` injection is fully wired into the scanner and
sniper as of 0.2.0. `Tool` / `ToolRegistry` exists and can be called from
rule nodes today; an LLM-driven tool-use loop (so the analyst can invoke
tools mid-decision on its own) is on the roadmap.

---

## Two agents, four sniper modes

### Agent A — Scanner

Slow path for "should we buy this?" Takes 1–3s, fully LLM-driven analysis.
Returns `Decision` with the full per-aspect `FullAnalysis` attached.

```python
from strategies import build_scanner
from trading import ScannerConfig, TradingContext
from zetryn.core import State
from zetryn.llm import OpenAICompatibleClient, ProviderConfig, GROQ_BASE_URL

# 1. Pick an LLM provider (free tier: Groq / Gemini / OpenRouter)
provider = ProviderConfig(
    name="groq",
    base_url=GROQ_BASE_URL,
    model="llama-3.3-70b-versatile",
    key_envs=["GROQ_API_KEY_1", "GROQ_API_KEY_2", "GROQ_API_KEY_3"],
)
llm = OpenAICompatibleClient(provider)

# 2. Build the agent
scanner = build_scanner(llm, model="llama-3.3-70b-versatile")

# 3. Run it — bot pushes a fully-formed TokenInput
state = await scanner.run(State(context=TradingContext(token=token_input)))
decision = state.output

print(decision.action)        # "alert" | "watch" | "skip"
print(decision.confidence)    # 0..1
print(decision.analysis)      # FullAnalysis with per-aspect verdicts
```

### Agent B — Sniper

Fast path for "BUY NOW or skip." Four modes, picked via `SniperConfig.decision_mode`:

| Mode | Latency | LLM in hot path? | When to use |
|---|---|---|---|
| `rule` (default) | < 1 ms | No | Production sniper, ultra-fresh launches |
| `llm` | 200-500 ms | Yes (decides) | Tokens older than 1 minute, LLM-driven entry |
| `hybrid` | 200-500 ms | Yes + rule guardrail | LLM decides, rules veto rug / cap size |
| `hybrid_audit` | **< 1 ms decision + async AI verify** | Async (non-blocking) | **Best of both worlds** |

**`hybrid_audit`** is the AI-meets-speed bridge: the rule path decides instantly,
then a background coroutine runs the LLM to second-opinion that decision. Result
is stored in `state.scratch["audit_task"]`, ready to be written to `DecisionLog`
for offline analysis (where do rule and AI disagree? what does that mean for
tuning?). The bot trades immediately on the rule decision — no LLM in the hot
path.

```python
from strategies import build_sniper
sniper = build_sniper(llm)  # llm only used for audit / llm / hybrid modes

state = await sniper.run(State(context=TradingContext(
    token=token, config=SniperConfig(decision_mode="hybrid_audit"),
)))

# Decision returned in <1 ms — trade now.
bot.execute(state.output)

# Then await the audit verdict (no rush).
verdict = await state.scratch["audit_task"]
await decision_log.log(state.run_id, {
    **state.output.model_dump(),
    "audit": verdict.model_dump(),
})
```

**Reflective sniper (v0.11.0):** pass a `DecisionLog` at build time and the
sniper's LLM path becomes loss-aware — a `ReflectiveNode` runs between
`fast_market` and the LLM decider, compiling a `LESSONS from recent snipe
outcomes` block from the last N decisions. The LLM conditions on real
historical losses, not just the static prompt.

```python
from zetryn.memory import DecisionLog, JSONFileStore

log = DecisionLog(JSONFileStore("./sniper-decisions.json"))

# Reflective loop active in llm / hybrid modes only.
# hybrid_audit intentionally skips reflect — the sub-ms rule path must not
# block on a memory read; the bot can reflect offline in that mode.
sniper = build_sniper(
    llm,
    decision_log=log,
    reflect_window=20,      # how many past decisions to look at
    reflect_top_k=5,        # top-k loser patterns to surface
)
```

---

## Install

```bash
pip install zetryn-trading
```

Or from source:

```bash
git clone https://github.com/zetryn/zetryn-trading
cd zetryn-trading
pip install -e ".[dev]"
```

Then copy the example env file and add at least one provider key (free):

```bash
cp .env.example .env
# fill GROQ_API_KEY_1=... (free at https://console.groq.com)
```

---

## See it work, no API key needed

```bash
cd examples
python walkthrough.py
```

Runs the scanner on 16 dummy memecoin scenarios — gem, rug, bundle attack,
smart-money entry, pumpfun near-graduation, sell pressure — and prints, for
each:

1. **INPUT** — the signals the bot pushed in
2. **PROCESSING** — which gate stopped it, or the full analyst pipeline
3. **ANALYSIS** — per-aspect AI verdict with signals + reasoning
4. **OUTPUT** — the `Decision` returned to the bot

Uses a heuristic stub LLM so you can see the shape of the output without
spending a token. With a real Groq key, the reasoning is dramatically richer.

---

## Three-phase LLM evolution

The same agents, different providers, different cost / quality / speed.

### Phase 1 — Free (today)

- Groq `llama-3.3-70b-versatile` (primary), Gemini Flash, OpenRouter `:free`,
  plus Cerebras / Mistral / SambaNova / NVIDIA NIM (v0.8.0)
- Single rich `analyst` LLM call per scanner decision
- `KeyPool` rotates keys within an entry; `LLMRouter` fails over across
  entries (each entry = one `provider + model` combo) with per-model
  RPM/RPD/TPM/TPD throttle. Rotation order is **entry-by-entry, then
  key-by-key inside each entry** — see
  [docs/CAPABILITIES.md §5 "Rotation order"](docs/CAPABILITIES.md) for the
  full walk-through and why the class is named `LLMRouter` (generic) rather
  than `ZetrynRouter` (brand-tied).
- $0/month, suitable for development and early production

### Phase 2 — Paid

- OpenAI (GPT-4o, OpenAI-compatible), Anthropic Claude (native adapter, soon)
- Optionally split `analyst` into parallel specialist nodes (safety / market /
  wallets / social) for richer reasoning
- $0.001–$0.02 per decision, scales to thousands/min

### Phase 3 — Zetryn models

When the Zetryn platform goes live (workstream P1–P4):

| Node | Model | Why |
|---|---|---|
| `safety_analyst` | **Easfus** | Fast pattern matching on contracts |
| `market_analyst` | **Easfus** | Numeric reasoning, low latency |
| `wallets_analyst` | **Medifus** | Wallet behavior context, balanced |
| `social_analyst` | **Medifus** | NLP sentiment + KOL quality |
| `synthesizer` | **Hardes** | Deep cross-aspect reasoning |

Zetryn models are fine-tuned for memecoin trading specifically and bundled into
the subscription (Free / Basic / Pro / Max). No per-token billing for users.

**Code structure does not change across phases.** Only `ProviderConfig` does.

---

## Architecture

```
zetryn-trading/
├── zetryn/              ← the agent library (installable; only this ships in wheel)
│   ├── core/            ← graph engine: State, Node, Edge, Graph, Command
│   ├── llm/             ← LLMClient, OpenAICompatibleClient, KeyPool, LLMNode,
│   │                       LLMRouter (multi-provider failover + throttle)
│   ├── knowledge/       ← KnowledgePack (markdown + JSON playbook loader)
│   ├── tools/           ← Tool, ToolRegistry
│   ├── memory/          ← MemoryStore, Blacklist, DecisionLog, ReflectiveNode
│   ├── observability/   ← structured logging, hooks, trace serialization
│   ├── auth/            ← SubscriptionAuth, License (Zetryn platform seam)
│   └── backtest/        ← generic Backtester
├── trading/             ← shared contract (TokenInput, Decision, FullAnalysis,
│                           GrowthSnapshot, DipBuySnapshot, ConfluenceEvent, ...)
└── strategies/          ← reference agents (move to your bot repo for production)
    ├── nodes/           ← filters.py, analyst.py, decide.py, sniper_nodes.py,
    │                       kol_nodes.py, graduation_nodes.py, lifecycle_nodes.py,
    │                       confluence_nodes.py, dip_buy_nodes.py, growth_nodes.py
    └── agents/          ← scanner.py, sniper.py, kol_copytrade.py,
                            graduation.py, lifecycle.py, confluence.py,
                            dip_buy.py, growth_detector.py
```

**Dependency rule (strict):**
- `zetryn/` imports nothing from `trading/` or `strategies/`
- `trading/` imports nothing
- `strategies/` imports both

So you can `import zetryn` in your own bot and bring your own `trading`-shaped
schemas if your domain isn't Solana memecoins.

---

## Push vs pull

Zetryn Trading supports both data-ingress patterns:

- **Push** (recommended for production): bot fetches data, builds `TokenInput`,
  calls `agent.run(State(context=TradingContext(token=token_input)))`. Latency
  predictable, no surprise external calls.
- **Pull**: implement the `DataProvider` protocol, agent calls `provider.fetch(mint)`.
  Useful for backtests with `HistoricalDataProvider`.

Test, backtest, and live are the same graph — only the provider changes.

---

## Pre-filter at the bot

Zetryn Trading is cheap to run, but **filling `TokenInput` is not** — Helius,
GMGN, Twitter, DexScreener all cost API quota. Pre-filter at the bot:

```python
def worth_fetching(ws_event) -> bool:
    return (
        ws_event.liquidity_usd >= 3_000
        and 30 <= ws_event.age_seconds <= 3600
        and ws_event.mint not in blacklist
        and ws_event.creator not in known_ruggers
    )
```

10,000 tokens/min from a pumpfun WS → ~50 candidates/min after pre-filter → fully
enriched and pushed to the agent. The agent's job is the **last mile**, not
discovery.

---

## What Zetryn Trading owns vs what the bot owns

| Zetryn Trading | Bot |
|---|---|
| Graph orchestration | RPC, wallet, signing |
| LLM calls (advisor / analyst / decider) | Hot loop, mempool watching |
| Scoring, decision aggregation | Trade execution, slippage, MEV |
| Memory (blacklist, decision log) | Position tracking, PnL |
| Observability (trace, hooks) | Pre-filter, fetch budgeting |
| Backtest harness | Live market data feeds |

Boundary is non-negotiable: **Zetryn Trading decides, bot executes.** Never the
reverse.

---

## Status

**Maturity:** Alpha (v0.16.0) — actively developed, breaking changes possible
between 0.x releases until the API stabilises.

**Single source of truth for roadmap & milestone status:**
[`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) §6. The summary below is just
a snapshot — the table over there is what gets updated on every release.

What's built (v0.16.0):

- Core engine, LLM layer, tools, memory, observability, auth seam, backtest
- **Nine reference strategy agents — all sharing a consistent four-mode shape:**

  | Agent | Strategy | Modes | Builder |
  |---|---|---|---|
  | Scanner | AI-first discovery | `analyst` (single LLM call) | `build_scanner` |
  | Sniper | Sub-ms launch entry | `rule` / `llm` / `hybrid` / `hybrid_audit` | `build_sniper` |
  | KOL Copy-Trade | Copy pre-vetted KOL wallets | `rule` / `confirmed` / `audit` | `build_kol_copytrade` |
  | Graduation Snipe | Pump.fun → Raydium migration entry | `rule` / `llm` / `hybrid` / `hybrid_audit` | `build_graduation` |
  | **Position Lifecycle** | Hold / TP / scale-out / emergency exit | `rule` / `llm` / `hybrid` / `hybrid_audit` | `build_lifecycle` |
  | **Smart Money Confluence** | ≥N pre-vetted wallets accumulate same token | `rule` / `llm` / `hybrid` / `hybrid_audit` | `build_confluence` |
  | **Early-Stage Dip Buy** | Post-dump recovery entry (launch or graduation) | `rule` / `llm` / `hybrid` / `hybrid_audit` | `build_dip_buy` |
  | **Organic Growth Detector** | Post-launch chart-pattern triage filter | `rule` / `llm` / `hybrid` / `hybrid_audit` | `build_organic_detector` |

  All agents expose the same `decision_log` + `reflect_window` +
  `reflect_feature_keys` + `reflect_top_k` parameters. Passing a `DecisionLog`
  inserts a `ReflectiveNode` before the LLM call — the analyst sees a
  `LESSONS from recent outcomes` block compiled from real historical losses.

- Pre-P1 foundations: `KnowledgePack`, `LLMRouter` (multi-provider failover
  + per-model throttle), `ReflectiveNode`
- **7 LLM providers** wired with per-model free-tier presets:
  Groq, Gemini, OpenRouter, **Cerebras, Mistral, SambaNova, NVIDIA NIM** (v0.8.0).
  Plus three opinionated router tier presets (`TIER_SPEED` /
  `TIER_QUALITY` / `TIER_VOLUME`) via `build_tier_entries()`. Example:
  [`examples/run_kol_tier_router.py`](examples/run_kol_tier_router.py).
- LLM tool-use loop: `tool_use_loop` + `ToolUseNode` let the analyst invoke
  registered tools mid-decision. Example:
  [`examples/run_with_tools.py`](examples/run_with_tools.py).
- Latency bench at [`examples/bench_scanner_latency.py`](examples/bench_scanner_latency.py)
  (supports `ZETRYN_BENCH_PROVIDER=router` for multi-provider comparison)

Known limits:

- Single-provider free tier can spike p95 past the M8 5s target.
  **Recommended production pattern: `LLMRouter` with ≥2 providers**
  (Groq + Gemini Flash). Working example:
  [`examples/run_with_router.py`](examples/run_with_router.py). See
  CAPABILITIES.md §5 "Reliability pattern".
- Zetryn platform (hosted models, subscription auth) is **not yet live** —
  the seam is stubbed; production uses public providers with your own keys.

---

## Tests

```bash
pytest                            # all
pytest tests/test_scanner.py      # scanner
pytest tests/test_sniper.py -v    # sniper, verbose
```

No API key required. Tests use offline stubs + `MockDataProvider`.

---

## Documentation

| Doc | Purpose | Update cadence |
|---|---|---|
| [CAPABILITIES.md](docs/CAPABILITIES.md) | **Source of truth** — capability matrix, roadmap, M8 closeout evidence | Every release |
| [CHANGELOG.md](CHANGELOG.md) | Version-by-version notes | Every release |
| [plans/2026-06-23-…](docs/plans/2026-06-23-zetryn-agent-framework-design.md) | Architecture Decision Record — original framework design | Frozen (historical) |
| [plans/2026-06-24-…](docs/plans/2026-06-24-ai-first-pivot.md) | Architecture Decision Record — AI-first pivot rationale | Frozen (historical) |

If a roadmap line in any of the plan docs disagrees with CAPABILITIES.md,
**CAPABILITIES.md is correct** — the plans are kept as snapshots of the
decisions, not as live tracking.

---

## License

MIT. Use it, fork it, build something better with it.

Zetryn's own **models** (Hardes / Medifus / Easfus) and **hosted serving** are
behind a subscription at [zetryn.com](https://zetryn.com). Public providers
(Groq, Gemini, OpenRouter, OpenAI, Anthropic) work today, free of charge to
Zetryn, with your own keys.