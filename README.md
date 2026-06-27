# Zetryn AI Agent Trading Framework

**AI Agent Trading Framework from Zetryn AI.**

A Python framework that turns raw Solana memecoin data into structured,
auditable trading decisions. You bring the bot, the wallet, and the RPC;
Zetryn provides the **decision engine** — eight reference agents built from
a graph of LLM analysts and hard-rule guardrails, plus a declarative
graph-spec layer if you'd rather configure than code.

```
BOT (yours)                   ZETRYN AI AGENT TRADING (this framework)
─────────────                 ─────────────────────────────────────────
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

**Zetryn decides; the bot executes.** The framework never holds your private
key and never touches the chain.

---

> [!NOTE]
> **v1.0.0 — API stable.** Public APIs are frozen across minor releases;
> behaviour changes only at major versions. The Zetryn platform (subscription
> auth, hosted **Hardes** / **Medifus** / **Easfus** models) is **not yet
> live** — today the framework runs on public LLM providers (Groq / Gemini /
> OpenRouter / Cerebras / Mistral / SambaNova / NVIDIA NIM) with your own
> keys.
>
> Paper-test first. No warranty, no fiduciary — this is a decision engine,
> not investment advice. See [LICENSE](LICENSE).

---

## Quickstart — no API key needed

```bash
git clone https://github.com/zetryn/zetryn-trading
cd zetryn-trading
pip install -e ".[dev]"
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
spending a token. With a real provider key, the reasoning is dramatically
richer.

---

## Install for real use

```bash
pip install zetryn-trading
cp .env.example .env
# fill GROQ_API_KEY_1=... (free at https://console.groq.com)
```

A single free Groq key is enough to drive every agent end-to-end. For
production, configure 2+ providers via `LLMRouter` — see
[`docs/GUIDE.md §2`](docs/GUIDE.md#2-key-rotation--multi-provider-router).

---

## Why Zetryn?

Three properties this framework refuses to compromise on:

- **Boundary clean.** Framework decides, bot executes. Zetryn never fetches
  data, holds keys, signs transactions, or tracks positions across calls —
  ever. Your bot owns I/O; the framework owns the decision graph. That
  separation is enforced in code, documented in tests, and is the reason
  the same agent runs unchanged in unit test, backtest, and live trading.

- **Graceful by design.** LLM failure → conservative fallback verdict, never
  a crash. Tool error → empty result + flag, never a crash. Rate-limited
  provider → `LLMRouter` fails over to the next entry transparently. The
  graph keeps running so the bot keeps making decisions; the loud failure
  modes that bite live trading bots are designed out.

- **Audit-first.** Every node execution produces a `StepTrace` —
  `scratch` before, duration, error if any, what came next. Every LLM
  call is structured (Pydantic-validated) and stored. Every Decision is
  loggable to `DecisionLog` and replayable through `Backtester`. The
  postmortem question "*why did the agent buy that one?*" always has a
  concrete answer.

---

## What's in the box

| Layer | What it does | Learn more |
|---|---|---|
| **Core engine** | `State`, `Node`, `Edge`, `Graph`, `Command`, trace, compile-time validator | [`zetryn/core/`](zetryn/core/) · [`CLAUDE.md`](CLAUDE.md) |
| **LLM router** | 7 providers (Groq, Gemini, OpenRouter, Cerebras, Mistral, SambaNova, NVIDIA NIM), key rotation on 429, per-model RPM/RPD/TPM/TPD throttle, three tier presets | [`docs/GUIDE.md §1–2`](docs/GUIDE.md#1-llm-providers) |
| **Knowledge** | Markdown rules + JSON data files loaded once into the system prompt — facts the LLM *reads* | [`docs/GUIDE.md §3`](docs/GUIDE.md#3-knowledge--static-context-the-llm-reads) |
| **Skills** | `Tool` + `ToolRegistry` + LLM-driven tool-use loop — functions the LLM *invokes* mid-decision | [`docs/GUIDE.md §4`](docs/GUIDE.md#4-skills--callable-tools-the-llm-invokes) |
| **Memory** | `Blacklist`, `DecisionLog`, `ReflectiveNode` (loss-pattern extractor), JSON or in-memory stores | [`docs/GUIDE.md §6`](docs/GUIDE.md#6-memory--reflective-loop) |
| **8 reference agents** | Scanner · Sniper · KOL Copy-Trade · Graduation · Lifecycle · Confluence · Dip-Buy · Organic Growth | [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) · [`docs/STRATEGIES.md`](docs/STRATEGIES.md) |
| **YAML loader** | Declarative graph specs — no Python wiring required for simple strategies | See section below |
| **Backtest** | `Backtester.run(items)` over a list of `(id, context)` pairs, same compiled graph as live | [`docs/GUIDE.md §8`](docs/GUIDE.md#8-backtesting) |
| **Observability** | Structured per-node JSON logging, `Hooks` protocol, `trace_to_dicts` serializer | [`zetryn/observability/`](zetryn/observability/) |

---

## YAML loader — declarative graphs (v0.17.0)

For strategies that don't need bespoke Python wiring, build the graph from
a YAML file. The same `Graph` object falls out — runnable, traceable,
testable, identical to a hand-built one.

```yaml
# scanner.yaml
name: yaml_scanner
entry: safety_gate

nodes:
  - {name: safety_gate, type: rule, fn: strategies.nodes.filters:fast_safety}
  - {name: analyst,     type: llm,
     client: ${llm.tier_speed},
     schema: trading.schemas:ScannerVerdict,
     prompt_fn: strategies.nodes.analyst:scanner_prompt}
  - {name: decide,      type: rule, fn: strategies.nodes.decide:aggregate}

edges:
  - {from: safety_gate, to: analyst, when: "scratch.safety_ok"}
  - {from: safety_gate, to: END,     when: "not scratch.safety_ok"}
  - {from: analyst,     to: decide}
  - {from: decide,      to: END}
```

```python
from zetryn.config import load_graph

graph = load_graph("scanner.yaml", registry={"llm.tier_speed": my_router})
state = await graph.run(State(context=ctx))
```

Validation is eager (`module:attr` references must import; `${name}`
placeholders must be in the registry; every edge target must exist; the
`when:` DSL is AST-whitelisted — **no `eval()` at runtime**). Failures
raise `ConfigError` pointing at the offending line.

CLI: `python -m zetryn.config <file.yaml>` — exit 0 if valid, 1 with
detailed message if not.

Full design rationale + DSL grammar + supported node types →
[`docs/plans/2026-06-27-yaml-loader-m13.md`](docs/plans/2026-06-27-yaml-loader-m13.md).

---

## Eight reference agents

All eight share the same contract: the bot fills an input context, the
framework returns a `Decision`. All accept `decision_log` + `reflect_*`
parameters to enable the reflective learning loop (LLM sees recent
losses before deciding).

| # | Agent | Strategy | Modes | Builder |
|---|---|---|---|---|
| A | **Scanner** | AI-first token discovery | `analyst` | `build_scanner` |
| B | **Sniper** | Sub-ms launch entry | `rule` / `llm` / `hybrid` / `hybrid_audit` | `build_sniper` |
| C | **KOL Copy-Trade** | Copy pre-vetted KOL wallets | `rule` / `confirmed` / `audit` | `build_kol_copytrade` |
| D | **Graduation Snipe** | Pump.fun → Raydium migration entry | `rule` / `llm` / `hybrid` / `hybrid_audit` | `build_graduation` |
| E | **Position Lifecycle** | Hold / TP / scale-out / emergency exit | `rule` / `llm` / `hybrid` / `hybrid_audit` | `build_lifecycle` |
| F | **Smart Money Confluence** | ≥N pre-vetted wallets accumulate same token | `rule` / `llm` / `hybrid` / `hybrid_audit` | `build_confluence` |
| G | **Early-Stage Dip Buy** | Post-dump recovery entry | `rule` / `llm` / `hybrid` / `hybrid_audit` | `build_dip_buy` |
| H | **Organic Growth Detector** | Post-launch chart-pattern triage filter | `rule` / `llm` / `hybrid` / `hybrid_audit` | `build_organic_detector` |

Per-agent specs, signatures, decision shapes, and config knobs →
[`docs/GUIDE.md §7`](docs/GUIDE.md#7-agent-reference). Strategy catalog
(shipped / considered / rejected, with tier rationale) →
[`docs/STRATEGIES.md`](docs/STRATEGIES.md).

### Decision modes (shared shape across most agents)

| Mode | Latency | LLM in hot path? | When to use |
|---|---|---|---|
| `rule` (default) | < 1 ms | No | Production, latency-critical paths |
| `llm` | 200–500 ms | Yes (decides) | Richer reasoning, older tokens |
| `hybrid` | 200–500 ms | Yes + rule guardrail | LLM decides, rules veto rug / cap size |
| `hybrid_audit` | **< 1 ms + async AI verify** | Async (non-blocking) | **Best of both worlds** |

`hybrid_audit` is the speed–intelligence bridge: the rule path returns a
`Decision` instantly, then a background coroutine runs the LLM to
second-opinion it. Result lands in `state.scratch["audit_task"]` for the
bot to `await` and log. Full pattern walkthrough →
[`docs/GUIDE.md §5`](docs/GUIDE.md#5-decision-modes).

---

## Boundary — what Zetryn owns vs what the bot owns

| Zetryn (framework) | Bot (caller) |
|---|---|
| Graph orchestration | RPC, wallet, signing |
| LLM calls (advisor / analyst / decider) | Hot loop, mempool watching |
| Scoring, decision aggregation | Trade execution, slippage, MEV |
| Memory (blacklist, decision log) | Position tracking, PnL |
| Observability (trace, hooks) | Pre-filter, fetch budgeting |
| Backtest harness | Live market data feeds |

The line is non-negotiable: **Zetryn decides, bot executes.** Never the
reverse. New schema field? Probably yes. New async fetcher inside
`zetryn/`? **No** — it belongs in your bot.

Integration patterns (push vs pull, pre-filter funnel, when to bring your
own schemas) → [`docs/GUIDE.md §9`](docs/GUIDE.md#9-bot-integration).

---

## Architecture

```
zetryn-trading/
├── zetryn/              ← the library (only this ships in the wheel)
│   ├── core/            ← graph engine
│   ├── llm/             ← clients, router, key pool, structured output, tool-use
│   ├── knowledge/       ← KnowledgePack
│   ├── tools/           ← Tool + ToolRegistry
│   ├── memory/          ← Blacklist, DecisionLog, ReflectiveNode
│   ├── observability/   ← logging, hooks, trace serialization
│   ├── auth/            ← SubscriptionAuth seam (platform-pending)
│   ├── backtest/        ← Backtester
│   └── config/          ← YAML graph loader
├── trading/             ← shared contract (TokenInput, Decision, ...)
└── strategies/          ← reference agents (move to your bot repo for production)
```

**Dependency rule (strict, enforced):** `zetryn/` imports nothing from
`trading/` or `strategies/`; `trading/` imports nothing; `strategies/`
imports both. You can `import zetryn` in your own bot and bring your own
`trading`-shaped schemas if your domain isn't Solana memecoins.

Deeper architecture (per-module conventions, design ADRs, runtime flow) →
[`CLAUDE.md`](CLAUDE.md) + [`docs/plans/`](docs/plans/).

---

## Status

**v1.0.0** — public API stable. Breaking changes will bump to v2.0.0.

Roadmap, per-feature status, and milestone history live in
[`docs/CAPABILITIES.md`](docs/CAPABILITIES.md). What's shipped vs what's
planned is updated there on every release; the README does not duplicate
that table.

**Known limits**

- The **Zetryn platform** (hosted Hardes / Medifus / Easfus models,
  subscription auth) is **not yet live**. The seam is stubbed in
  `zetryn/auth/`; production today uses public providers with your own
  keys.
- Single-provider free tier can spike p95 latency past targets.
  **Recommended production pattern: `LLMRouter` with ≥ 2 providers**
  (e.g. Groq + Gemini Flash). Working example:
  [`examples/run_with_router.py`](examples/run_with_router.py).

---

## Tests

```bash
pytest                            # all
pytest tests/test_scanner.py      # one suite
pytest tests/test_sniper.py -v    # one suite, verbose
```

No API key required. Tests use offline stubs + `MockDataProvider`.

---

## Documentation

| Doc | Purpose |
|---|---|
| [**GUIDE.md**](docs/GUIDE.md) | **Developer guide** — providers, key rotation, knowledge, skills, decision modes, memory & reflective loop, per-agent reference, backtesting, bot integration |
| [CAPABILITIES.md](docs/CAPABILITIES.md) | **Source of truth** — capability matrix, roadmap, milestone status |
| [STRATEGIES.md](docs/STRATEGIES.md) | Strategy catalog — shipped, considered, rejected (tier rationale) |
| [CHANGELOG.md](CHANGELOG.md) | Version-by-version notes |
| [CLAUDE.md](CLAUDE.md) | Architecture conventions for contributors |
| [plans/](docs/plans/) | Design docs (one per roadmap feature) |

If anything in `plans/` disagrees with `CAPABILITIES.md`,
**`CAPABILITIES.md` wins** — the plans are frozen snapshots of decisions,
not live tracking.

---

## License

MIT. Use it, fork it, build something better with it.

Zetryn's own **models** (Hardes / Medifus / Easfus) and **hosted serving**
will live behind a subscription at [zetryn.com](https://zetryn.com) when
the platform goes live. Public providers (Groq / Gemini / OpenRouter /
Cerebras / Mistral / SambaNova / NVIDIA NIM) work today, free of charge to
Zetryn, with your own keys.
