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

- Groq `llama-3.3-70b-versatile` (primary), Gemini Flash, OpenRouter `:free`
- Single rich `analyst` LLM call per scanner decision
- `KeyPool` rotates keys within a provider; `LLMRouter` fails over across
  providers with per-model RPM/RPD/TPM/TPD throttle (free-tier presets included)
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
├── trading/             ← shared contract (TokenInput, Decision, FullAnalysis, ...)
└── strategies/          ← reference agents (move to your bot repo for production)
    ├── nodes/           ← analyst.py, decide.py, filters.py, sniper_nodes.py
    └── agents/          ← scanner.py, sniper.py
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

**Maturity:** Alpha — actively developed, breaking changes possible between
0.x releases until the API stabilises.

What's built:

- ✅ Core engine, LLM layer, tools, memory, observability, auth seam, backtest
- ✅ Scanner v2 (AI-first, M8)
- ✅ Sniper with `rule` / `llm` / `hybrid` / `hybrid_audit` modes (M9)
- ✅ Schema enrichment for memecoin signals (M7)
- ✅ Packaging + docs (M10)
- ✅ Pre-P1 foundations: `KnowledgePack` (playbook loader), `LLMRouter`
  (multi-provider failover + per-model throttle), `ReflectiveNode`
  (loss-pattern extractor from `DecisionLog`) — see
  [docs/CAPABILITIES.md](docs/CAPABILITIES.md)

What's in progress / not yet ready:

- 🚧 Real outcome data → analyst prompt tuning (need live runs to calibrate)
- 🚧 Zetryn platform: `RemoteSubscriptionAuth`, hosted vLLM serving
  Hardes / Medifus / Easfus models, billing
- 🚧 Anthropic native adapter (prompt caching, extended thinking)

Planned later (not blocking 0.1.x):

- 📅 YAML strategy loader (once 3+ strategies in code reveal repeating patterns)
- 📅 Multi-agent panel via `AgentNode` (specialist analyst subgraphs)
- 📅 Vector / semantic memory for cross-token reasoning
- 📅 Copy-trade strategy reference agent

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

- [Capabilities & Gap Analysis](docs/CAPABILITIES.md) —
  matrix of what works today, links to source modules, F1–F3 status
- [Design (2026-06-23)](docs/plans/2026-06-23-zetryn-agent-framework-design.md) —
  original architecture
- [AI-First Pivot (2026-06-24)](docs/plans/2026-06-24-ai-first-pivot.md) —
  current architecture, 3-phase LLM evolution, sniper `hybrid_audit`
- [CHANGELOG](CHANGELOG.md)

---

## License

MIT. Use it, fork it, build something better with it.

Zetryn's own **models** (Hardes / Medifus / Easfus) and **hosted serving** are
behind a subscription at [zetryn.com](https://zetryn.com). Public providers
(Groq, Gemini, OpenRouter, OpenAI, Anthropic) work today, free of charge to
Zetryn, with your own keys.
