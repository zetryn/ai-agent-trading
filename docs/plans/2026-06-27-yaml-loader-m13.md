# M13 — YAML Loader

**Date:** 2026-06-27
**Status:** Shipped (v0.17.0)

Deklarative graph spec: muat strategi tanpa kode Python. Boundary tetap utuh
(framework tidak punya I/O, tidak instantiate LLM clients sendiri).

## 1. Tujuan

1. Sebuah strategi sederhana bisa dimuat dari satu file YAML, tanpa builder
   Python kustom.
2. Validasi struktur dilakukan **sebelum** graph berjalan (eager) supaya bot
   gagal cepat saat startup, bukan di tengah trading.
3. Existing Python builder (`build_scanner`, `build_sniper`, dst.) tetap
   bekerja apa adanya — YAML loader bersifat **additive**, bukan replacement.

## 2. Keputusan desain (final)

Lima keputusan kunci sudah dikunci lewat brainstorming:

| # | Topik | Pilihan | Alasan singkat |
|---|---|---|---|
| 1 | Condition DSL | Mini-DSL boolean lewat AST-whitelist | Ekspresif tanpa risiko eval; logic kompleks didorong ke `RuleNode` (design pressure sehat) |
| 2 | Injection objek live (LLM client, dll.) | Named registry `${name}` | Eksplisit, validator deteksi unresolved sebelum compile, mendukung multi-client per graph |
| 3 | Format referensi fungsi | Colon separator `module.path:attr` | Unambiguous, convention standar (setuptools, uvicorn, pytest) |
| 4 | Timing validasi | One-shot validate-on-load | Bot startup gagal cepat & actionable; kritikal untuk konteks trading |
| 5 | Scope v1 | RuleNode + LLMNode (+ LLMDecisionNode) + Edge + END | Ships 1–2 hari; ReflectiveNode/AgentNode/tool-use defer ke M13.1 saat ada use case riil |

## 3. Schema YAML

```yaml
name: scanner                              # str, required — graph name
entry: fast_safety                         # str, required — name of entry node

nodes:                                     # list[dict], required, non-empty
  - name: fast_safety                      # str, required, unique
    type: rule                             # "rule" | "llm" | "llm_decision"
    fn: strategies.nodes.filters:fast_safety   # module:attr

  - name: scanner_analyst
    type: llm
    client: ${llm.tier_speed}              # placeholder, resolved from registry
    schema: trading.schemas:ScannerVerdict # module:attr — must be pydantic BaseModel
    prompt_fn: strategies.nodes.analyst:scanner_prompt
    # Optional:
    output_key: scanner_verdict            # str, default = node name
    model: "groq/llama-3.3-70b"            # str
    max_attempts: 3                        # int, default 3
    fallback_fn: strategies.nodes.fallbacks:neutral   # module:attr

  - name: scanner_decide
    type: llm_decision
    client: ${llm.tier_quality}
    schema: trading.schemas:ScannerVerdict
    prompt_fn: strategies.nodes.analyst:scanner_prompt
    result_fn: strategies.nodes.decide:scanner_to_decision
    # Optional:
    guardrail_fn: strategies.nodes.decide:safety_guardrail
    fallback_fn: strategies.nodes.decide:conservative_default
    goto: END                              # str, default = END

edges:                                     # list[dict], required (can be empty)
  - from: fast_safety
    to: scanner_analyst
    when: "scratch.safety_ok"
  - from: fast_safety
    to: END                                # "END" mapped to END sentinel
    when: "not scratch.safety_ok"
  - from: scanner_analyst
    to: scanner_decide                     # unconditional edge: no when
```

### Aturan tambahan
- Nama node harus unik.
- `entry` harus mengacu ke node terdaftar.
- Edge `from` harus mengacu ke node terdaftar; `to` boleh node terdaftar atau
  literal string `"END"` (case-sensitive).
- `${name}` placeholder hanya valid sebagai nilai utuh field, bukan
  interpolasi tengah string.

## 4. Condition DSL

Subset Python yang aman, di-parse via `ast.parse(..., mode="eval")` lalu
divalidasi node-whitelist; **tidak ada `eval()` runtime**.

| Diizinkan | Contoh |
|---|---|
| Root identifiers | `scratch`, `context`, `output` |
| Attribute access | `scratch.safety_ok`, `context.token.symbol` |
| Konstanta | `True`, `False`, `None`, int, float, string (single/double quote) |
| Perbandingan | `==` `!=` `<` `>` `<=` `>=` |
| Boolean | `and` `or` `not` |
| Tanda kurung | `(`, `)` |

| Ditolak |
|---|
| Fungsi/method call (`len(x)`, `x.startswith(...)`) |
| Indexing (`x[0]`) |
| Aritmetika (`+`, `-`, `*`, `/`) |
| `is`, `in`, `lambda`, `:=`, comprehensions, f-strings |

**Pelampiasan logic kompleks**: pindah ke `RuleNode` yang menulis flag ke
`state.scratch`, lalu edge cuma test flag tersebut. Ini design pressure
yang dikehendaki — DSL sengaja sempit.

**Semantik akses**:
- `scratch` adalah `dict`; access via `getattr` jatuh ke `Mapping.get`.
- `context` opaque (dataclass / pydantic / dict); `getattr` dulu, lalu
  fall-back `.get` jika `Mapping`.
- Jika chain access menyentuh `None`, sisa rantai pendek-sirkuit ke `None`
  (tidak raise).

## 5. Public API

```python
# zetryn/config/__init__.py
from .loader import load_graph, ConfigError

__all__ = ["load_graph", "ConfigError"]
```

```python
def load_graph(
    path: str | Path,
    *,
    registry: dict[str, Any] | None = None,
) -> Graph:
    """Parse, validate, dan compile satu YAML spec menjadi Graph siap-run.

    Raises ConfigError dengan path + lokasi YAML pada setiap kegagalan validasi.
    """
```

### CLI

```bash
python -m zetryn.config <file.yaml>
```

Output: `OK: <name> (N nodes, M edges, K warnings)` atau `ConfigError: ...`
dengan exit code 1.

CLI **tidak** terima `registry` flag — placeholder akan ditolak dengan
`ConfigError`. Untuk lulus validasi end-to-end yang melibatkan placeholder,
caller harus invoke `load_graph()` dari Python.

CLI cuma cek YAML syntax + schema + reference resolvability — gunakan
sebagai pre-commit hook atau CI gate.

## 6. Error format

Semua kegagalan memunculkan `ConfigError(message, path=..., location=...)`
dengan `__str__` berformat:

```
<path> [<location>]: <message>
```

Contoh:
```
scanner.yaml [nodes[1] ('scanner_analyst')]: client ${llm.tier_speed} not in
registry. Provided keys: ['llm.quality', 'memory.log']
```

```
scanner.yaml [edges[2]]: when: invalid condition syntax in
"scratch.safety_ok && scratch.score > 0.7": invalid syntax (use 'and' not '&&')
```

## 7. Out of scope (defer)

- `ReflectiveNode` (butuh wiring `decision_log` + `feature_keys` — wujud
  schema-nya belum jelas)
- `AgentNode` (sub-graph nesting)
- Tool-use loop di LLMNode
- `extends:` / YAML import / inheritance
- Hot reload / file watcher
- `dump_graph(graph) -> yaml` (round-trip)

Semua di atas tetap bisa dipakai dari kode Python — YAML loader **tidak
menggantikan** pola builder existing. User bebas menulis:

```python
g = load_graph("kol_base.yaml", registry={...})
g.add_node(ReflectiveNode("reflect", decision_log=log))
g.add_edge("reflect", "kol_analyst")
```

## 8. Rencana test

- `test_config_dsl.py` — parser DSL: tiap operator, akses dotted, konstanta,
  reject untuk fungsi/aritmetika/indexing, akses `None` short-circuit.
- `test_config_loader.py` — happy path (rule + llm + llm_decision), missing
  field, bad reference (module tidak importable, attr tidak ada), bad
  placeholder, duplicate node, edge ke node tidak terdaftar, entry tidak
  terdaftar.
- `test_config_cli.py` — minimal: validasi file valid → exit 0; file invalid
  → exit 1 dengan pesan.

## 9. Dependensi

Tambah `pyyaml>=6.0` ke `[project.dependencies]`. Stdlib `ast` cukup untuk
DSL — tidak ada parser library tambahan.

## 10. Release

- Versi bump: 0.16.0 → **0.17.0**
- CHANGELOG entry baru.
- Update `docs/plans/README.md` dengan row "Shipped (v0.17.0)".
- `docs/CAPABILITIES.md` — tandai M13 ✅.
