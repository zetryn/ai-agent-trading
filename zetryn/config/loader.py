"""YAML graph spec loader.

Public entry: :func:`load_graph`. Validates the spec eagerly — every reference
must resolve, every placeholder must be in the supplied registry, every edge
must point at a known node — before the resulting :class:`Graph` is returned.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any

import yaml

from ..core.graph import Graph, GraphValidationError
from ..core.node import RuleNode
from ..core.state import END
from ..llm.node import LLMDecisionNode, LLMNode
from .dsl import DSLError, compile_condition

_PLACEHOLDER_RE = re.compile(r"^\$\{([a-zA-Z0-9_.\-]+)\}$")
_SUPPORTED_TYPES = frozenset({"rule", "llm", "llm_decision"})


class ConfigError(Exception):
    """Raised on any YAML schema or reference resolution failure.

    Carries an optional ``path`` (YAML file) and ``location`` (e.g.
    ``nodes[1] ('foo')``) so the error message can point straight at the
    offending spot.
    """

    def __init__(
        self,
        message: str,
        *,
        path: str | None = None,
        location: str | None = None,
    ) -> None:
        self.message = message
        self.path = path
        self.location = location
        super().__init__(self._format())

    def _format(self) -> str:
        prefix = self.path or "config"
        if self.location:
            prefix = f"{prefix} [{self.location}]"
        return f"{prefix}: {self.message}"


# ----- Public API -----------------------------------------------------------


def load_graph(
    path: str | Path,
    *,
    registry: dict[str, Any] | None = None,
) -> Graph:
    """Load, validate, and compile a YAML graph spec.

    Args:
        path: Path to the YAML file.
        registry: Mapping of ``${name}`` placeholders to live objects (LLM
            clients, knowledge packs, decision logs, etc.). Required if the
            spec references any placeholders.

    Returns:
        A compiled :class:`Graph` ready to run.

    Raises:
        ConfigError: on any schema, reference, or validation failure.
    """
    registry = registry or {}
    path_obj = Path(path)
    spath = str(path_obj)

    try:
        text = path_obj.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read file: {exc}", path=spath) from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML: {exc}", path=spath) from exc

    if not isinstance(data, dict):
        raise ConfigError(
            f"top-level YAML must be a mapping, got {type(data).__name__}",
            path=spath,
        )

    for field in ("name", "entry", "nodes", "edges"):
        if field not in data:
            raise ConfigError(f"missing required field {field!r}", path=spath)

    name = data["name"]
    entry = data["entry"]
    nodes_spec = data["nodes"]
    edges_spec = data["edges"]

    if not isinstance(name, str) or not name:
        raise ConfigError("'name' must be a non-empty string", path=spath)
    if not isinstance(entry, str) or not entry:
        raise ConfigError("'entry' must be a non-empty string", path=spath)
    if not isinstance(nodes_spec, list) or not nodes_spec:
        raise ConfigError("'nodes' must be a non-empty list", path=spath)
    if not isinstance(edges_spec, list):
        raise ConfigError("'edges' must be a list", path=spath)

    graph = Graph(name=name)
    seen: set[str] = set()

    for i, ns in enumerate(nodes_spec):
        node = _build_node(ns, registry, path=spath, index=i)
        if node.name in seen:
            raise ConfigError(
                f"duplicate node name {node.name!r}",
                path=spath,
                location=f"nodes[{i}]",
            )
        seen.add(node.name)
        graph.add_node(node)

    if entry not in seen:
        raise ConfigError(
            f"entry {entry!r} not in registered nodes (found: {sorted(seen)})",
            path=spath,
        )
    graph.set_entry(entry)

    for i, es in enumerate(edges_spec):
        _add_edge(graph, es, seen, path=spath, index=i)

    try:
        graph.compile()
    except GraphValidationError as exc:
        raise ConfigError(f"graph validation failed: {exc}", path=spath) from exc

    return graph


# ----- Reference resolution -------------------------------------------------


def _resolve_reference(ref: Any, kind: str) -> Any:
    """Resolve a 'module.path:attr' string into the imported attribute."""
    if not isinstance(ref, str):
        raise ConfigError(
            f"{kind} must be a 'module:attr' string, got {type(ref).__name__}"
        )
    if ":" not in ref:
        raise ConfigError(
            f"invalid {kind} reference {ref!r}: expected 'module.path:name' "
            f"(missing ':')"
        )
    module_path, _, attr = ref.partition(":")
    module_path, attr = module_path.strip(), attr.strip()
    if not module_path or not attr:
        raise ConfigError(
            f"invalid {kind} reference {ref!r}: both module path and "
            f"attribute name are required"
        )
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ConfigError(
            f"{kind} module {module_path!r} not importable: {exc}"
        ) from exc
    if not hasattr(module, attr):
        raise ConfigError(
            f"{kind} module {module_path!r} has no attribute {attr!r}"
        )
    return getattr(module, attr)


def _resolve_placeholder(value: Any, registry: dict[str, Any], kind: str) -> Any:
    """Resolve a ``${name}`` placeholder string against the registry."""
    if not isinstance(value, str):
        raise ConfigError(
            f"{kind} must be a ${{name}} placeholder, got {type(value).__name__}"
        )
    m = _PLACEHOLDER_RE.match(value)
    if not m:
        raise ConfigError(
            f"{kind} must be a registry placeholder of form ${{name}}, "
            f"got {value!r}"
        )
    key = m.group(1)
    if key not in registry:
        provided = sorted(registry.keys())
        raise ConfigError(
            f"{kind} ${{{key}}} not in registry. Provided keys: {provided}"
        )
    return registry[key]


# ----- Node builders --------------------------------------------------------


def _build_node(
    spec: Any,
    registry: dict[str, Any],
    *,
    path: str,
    index: int,
) -> Any:
    if not isinstance(spec, dict):
        raise ConfigError(
            "node entry must be a mapping",
            path=path,
            location=f"nodes[{index}]",
        )

    name = spec.get("name")
    ntype = spec.get("type")
    if not isinstance(name, str) or not name:
        raise ConfigError(
            "node missing required 'name'",
            path=path,
            location=f"nodes[{index}]",
        )
    if ntype not in _SUPPORTED_TYPES:
        raise ConfigError(
            f"unsupported node type {ntype!r} "
            f"(supported: {sorted(_SUPPORTED_TYPES)})",
            path=path,
            location=f"nodes[{index}] ({name!r})",
        )

    loc = f"nodes[{index}] ({name!r})"

    if ntype == "rule":
        return _build_rule_node(spec, path=path, loc=loc, name=name)

    if ntype == "llm":
        return _build_llm_node(spec, registry, path=path, loc=loc, name=name)

    # llm_decision
    return _build_llm_decision_node(spec, registry, path=path, loc=loc, name=name)


def _build_rule_node(spec: dict, *, path: str, loc: str, name: str) -> RuleNode:
    fn_ref = spec.get("fn")
    if not fn_ref:
        raise ConfigError("rule node missing required 'fn'", path=path, location=loc)
    fn = _wrap(lambda: _resolve_reference(fn_ref, "fn"), path=path, loc=loc)
    if not callable(fn):
        raise ConfigError(
            f"fn {fn_ref!r} is not callable",
            path=path,
            location=loc,
        )
    return RuleNode(name, fn)


def _build_llm_node(
    spec: dict,
    registry: dict[str, Any],
    *,
    path: str,
    loc: str,
    name: str,
) -> LLMNode:
    for f in ("client", "schema", "prompt_fn"):
        if f not in spec:
            raise ConfigError(
                f"llm node missing required {f!r}", path=path, location=loc
            )

    client = _wrap(
        lambda: _resolve_placeholder(spec["client"], registry, "client"),
        path=path, loc=loc,
    )
    schema = _wrap(
        lambda: _resolve_reference(spec["schema"], "schema"),
        path=path, loc=loc,
    )
    prompt_fn = _wrap(
        lambda: _resolve_reference(spec["prompt_fn"], "prompt_fn"),
        path=path, loc=loc,
    )

    fallback_fn = None
    if "fallback_fn" in spec:
        fallback_fn = _wrap(
            lambda: _resolve_reference(spec["fallback_fn"], "fallback_fn"),
            path=path, loc=loc,
        )

    return LLMNode(
        name=name,
        client=client,
        schema=schema,
        prompt_fn=prompt_fn,
        output_key=spec.get("output_key"),
        fallback_fn=fallback_fn,
        model=spec.get("model"),
        max_attempts=int(spec.get("max_attempts", 3)),
    )


def _build_llm_decision_node(
    spec: dict,
    registry: dict[str, Any],
    *,
    path: str,
    loc: str,
    name: str,
) -> LLMDecisionNode:
    for f in ("client", "schema", "prompt_fn", "result_fn"):
        if f not in spec:
            raise ConfigError(
                f"llm_decision node missing required {f!r}", path=path, location=loc
            )

    client = _wrap(
        lambda: _resolve_placeholder(spec["client"], registry, "client"),
        path=path, loc=loc,
    )
    schema = _wrap(
        lambda: _resolve_reference(spec["schema"], "schema"),
        path=path, loc=loc,
    )
    prompt_fn = _wrap(
        lambda: _resolve_reference(spec["prompt_fn"], "prompt_fn"),
        path=path, loc=loc,
    )
    result_fn = _wrap(
        lambda: _resolve_reference(spec["result_fn"], "result_fn"),
        path=path, loc=loc,
    )

    guardrail_fn = None
    if "guardrail_fn" in spec:
        guardrail_fn = _wrap(
            lambda: _resolve_reference(spec["guardrail_fn"], "guardrail_fn"),
            path=path, loc=loc,
        )

    fallback_fn = None
    if "fallback_fn" in spec:
        fallback_fn = _wrap(
            lambda: _resolve_reference(spec["fallback_fn"], "fallback_fn"),
            path=path, loc=loc,
        )

    goto = spec.get("goto", END)
    if goto == "END":
        goto = END

    return LLMDecisionNode(
        name=name,
        client=client,
        schema=schema,
        prompt_fn=prompt_fn,
        result_fn=result_fn,
        guardrail_fn=guardrail_fn,
        fallback_fn=fallback_fn,
        model=spec.get("model"),
        max_attempts=int(spec.get("max_attempts", 3)),
        goto=goto,
    )


# ----- Edge builder ---------------------------------------------------------


def _add_edge(
    graph: Graph,
    spec: Any,
    node_names: set[str],
    *,
    path: str,
    index: int,
) -> None:
    loc = f"edges[{index}]"
    if not isinstance(spec, dict):
        raise ConfigError("edge entry must be a mapping", path=path, location=loc)
    src = spec.get("from")
    dst = spec.get("to")
    when = spec.get("when")

    if not isinstance(src, str) or not src:
        raise ConfigError("edge missing required 'from'", path=path, location=loc)
    if not isinstance(dst, str) or not dst:
        raise ConfigError("edge missing required 'to'", path=path, location=loc)
    if src not in node_names:
        raise ConfigError(
            f"edge.from {src!r} not in registered nodes",
            path=path, location=loc,
        )

    # Accept literal "END" and the END sentinel itself.
    if dst == "END":
        dst = END
    if dst != END and dst not in node_names:
        raise ConfigError(
            f"edge.to {dst!r} not in registered nodes "
            f"(use 'END' for terminal edges)",
            path=path, location=loc,
        )

    condition = None
    if when is not None:
        if not isinstance(when, str):
            raise ConfigError(
                f"'when' must be a string expression, got {type(when).__name__}",
                path=path, location=loc,
            )
        try:
            condition = compile_condition(when)
        except DSLError as exc:
            raise ConfigError(
                f"when: {exc}", path=path, location=loc
            ) from exc

    graph.add_edge(src, dst, when=condition)


# ----- Helpers --------------------------------------------------------------


def _wrap(thunk, *, path: str, loc: str):
    """Run a resolver, re-tagging any ConfigError with path + location."""
    try:
        return thunk()
    except ConfigError as exc:
        # Preserve the original message but attach the surrounding context.
        raise ConfigError(exc.message, path=path, location=loc) from exc
