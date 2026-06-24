# Zetryn — Capabilities & Gap Analysis

Status snapshot of the framework **before** the P1–P4 work begins.
Use this as a single source of truth for "what works today vs. what we still need to build".

> Legend: ✅ implemented · ⚠️ partial · ❌ not yet

---

## 1. Capability Matrix

| # | Capability | Status | Where it lives | Notes |
|---|------------|--------|----------------|-------|
| 1 | Knowledge injection at startup (static context + data lookups) | ✅ | [`zetryn/knowledge/pack.py`](../zetryn/knowledge/pack.py) (`KnowledgePack`) | `KnowledgePack.from_dir(path)` loads markdown → `system_blocks()` and JSON → `lookup(ns, key)`. **Knowledge ≠ Skills** — knowledge is passive context the LLM *reads*; for callable skills (functions the LLM can *invoke*), see [`zetryn/tools/`](../zetryn/tools/) (`Tool` + `ToolRegistry`). Both can be mixed in the same agent. |
| 2 | API key pool rotation | ✅ | [`zetryn/llm/keypool.py`](../zetryn/llm/keypool.py), [`zetryn/llm/openai_compat.py`](../zetryn/llm/openai_compat.py) | On HTTP 429 the offending key is penalised and another is acquired. Driven by `ProviderConfig.key_envs`. |
| 3 | Prompt-engineered reading of failed trade history (e.g. `PF26 -26%`, `ILY -21%`) | ✅ | [`zetryn/memory/reflective.py`](../zetryn/memory/reflective.py) (`ReflectiveNode`) | Node reads `DecisionLog`, lists recent losers by id + avg pnl, writes summary to `scratch["lessons_text"]` for prompt injection. |
| 4 | Reflective analysis of past decision blunders | ✅ | [`zetryn/memory/reflective.py`](../zetryn/memory/reflective.py) (`reflect()`, `ReflectionResult`) | Deterministic post-mortem extractor groups losers by feature buckets and ranks them by `loss_count`. |
| 5 | Loss-pattern recognition from recorded outcomes | ✅ | [`zetryn/memory/reflective.py`](../zetryn/memory/reflective.py) (`Pattern`) | Numeric features bucketed by quartile, categorical features grouped by value. Emits patterns like `top10_pct = > 0.30: 3/4 losses (rate 75%, avg pnl -22%)`. |
| 6 | Per-model throttle + auto-fallback across keys / providers | ✅ | [`zetryn/llm/router.py`](../zetryn/llm/router.py) (`LLMRouter`, `RouterEntry`, `get_free_tier_limit`) | Multi-provider failover wraps any number of `LLMClient`s and implements the same protocol. Per-entry `RateLimit` enforces RPM/RPD/TPM/TPD via sliding windows. Free-tier presets per-model for Groq, Gemini, and OpenRouter `:free` shared bucket. |
| 7 | Persisting new knowledge learned at runtime | ✅ | [`zetryn/memory/store.py`](../zetryn/memory/store.py), [`zetryn/knowledge/pack.py`](../zetryn/knowledge/pack.py), [`zetryn/memory/reflective.py`](../zetryn/memory/reflective.py) | Static playbook via `KnowledgePack`; mutable per-run state via `MemoryStore`; outcomes auto-summarised back into the next run by `ReflectiveNode`. The learning loop is now closed. |
| 8 | LLM-driven tool/skill invocation (function calling) | ⚠️ | [`zetryn/tools/`](../zetryn/tools/) (`Tool`, `ToolRegistry`) | `Tool` schema + safe-call (timeout, no-crash, OpenAI function-spec) exists. Rule nodes can already call tools directly. Missing: an LLM tool-use loop so the analyst can invoke tools mid-decision via the provider's native function-calling API. Tracked as a follow-up to F1–F3. |

---

## 2. Gap Analysis (before P1–P4)

Three structural gaps block every later milestone:

### ~~G1. No knowledge ingestion path~~ — **Closed by F1 (2026-06-24)**
- Resolved by `KnowledgePack.from_dir(path)`: markdown under `system/` becomes
  system-prompt blocks; JSON under `data/` is read via `lookup(ns, key)`.
- Deployments can now ship a playbook (rules, KOL whitelist, lessons) without
  editing Python.

### ~~G2. No reflective / self-learning loop~~ — **Closed by F2 (2026-06-24)**
- Resolved by `ReflectiveNode` + the pure `reflect()` extractor.
- The node reads the last N records from `DecisionLog`, buckets losers by
  feature, and writes both a structured `ReflectionResult` and a
  prompt-ready `lessons_text` into `state.scratch`.
- Downstream prompts can prepend `state.scratch["lessons_text"]` to the
  system message to make the agent loss-aware.

### ~~G3. No multi-provider routing~~ — **Closed by F3 (2026-06-24)**
- Resolved by `LLMRouter` / `RouterEntry` / `get_free_tier_limit`.
- Per-entry `RateLimit(rpm, rpd, tpm, tpd)` enforced locally with sliding windows;
  free-tier presets shipped for Groq, Gemini, and OpenRouter (`:free` shared bucket).
- `LLMNode` is unchanged — `LLMRouter` satisfies the `LLMClient` protocol.

---

## 3. Foundation Work to Do Before P1

These three components unblock the rest of the roadmap. Build them first, in this order:

### ~~F1. `KnowledgePack` loader~~ — **Done (2026-06-24)**
- Shipped: `KnowledgePack` dataclass + `KnowledgePackError` in
  [`zetryn/knowledge/`](../zetryn/knowledge/).
- Surface: `from_dir(path)`, `system_blocks()`, `as_system_message()`,
  `lookup(ns, key, default)`, `namespaces()`.
- Layout: `pack/system/*.md` (sorted by filename) + `pack/data/*.json`.
- Tests: [`tests/test_knowledge_pack.py`](../tests/test_knowledge_pack.py)
  (11 cases — load, ordering, JSON parse, error path, lookup, round-trip).

### ~~F2. `ReflectiveNode`~~ — **Done (2026-06-24)**
- Shipped: `ReflectiveNode`, pure `reflect()`, `ReflectionResult`, `Pattern`
  in [`zetryn/memory/reflective.py`](../zetryn/memory/reflective.py).
- Rule-based (no LLM): cheap and deterministic — safe for live loops.
  Numeric features bucketed by quartile, categorical features by value.
  Patterns sorted by `loss_count` then `avg_pnl`.
- Surface: `ReflectiveNode(name, decision_log, *, window=20, output_key="lessons",
  feature_keys=None, loss_threshold=0.0, top_k=5)`.
- Writes `scratch["lessons"]` (`ReflectionResult`) and `scratch["lessons_text"]`
  (string) — prompts read the latter directly.
- Tests: [`tests/test_reflective_node.py`](../tests/test_reflective_node.py)
  (15 cases — bucketing, sorting, top-k, window, custom output key, empty log).

### ~~F3. `LLMRouter` (multi-provider)~~ — **Done (2026-06-24)**
- Shipped: `LLMRouter`, `RouterEntry`, `_Throttle` (RPM/RPD/TPM/TPD sliding windows).
- Presets: `PROVIDER_FREE_TIER_LIMITS` per provider AND per model (Groq, Gemini),
  plus shared `:free` bucket for OpenRouter.
- Helper: `get_free_tier_limit(provider, model) -> RateLimit | None`.
- Tests: `tests/test_llm_router.py` (17 cases — failover, throttle, exhaustion, presets).

---

## 4. Summary

| Foundation | Unblocks |
|------------|----------|
| ~~F1 `KnowledgePack` loader~~ ✅ | #1, partly #7 |
| ~~F2 `ReflectiveNode`~~ ✅ | #3, #4, #5, partly #7 |
| ~~F3 `LLMRouter`~~ ✅ | #6 |

Once F1–F3 are in place, P1–P4 can proceed without re-touching the core engine.

**Progress:** F1 ✅ · F2 ✅ · F3 ✅ — all foundations in place. **P1 can start.**
