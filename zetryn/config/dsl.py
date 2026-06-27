"""Mini boolean DSL for edge ``when:`` conditions.

Parsed via :mod:`ast` with a strict node whitelist; the resulting callable
walks the AST itself — there is no ``eval()`` at runtime. The grammar covers:

- Root identifiers: ``scratch``, ``context``, ``output`` (the State fields).
- Dotted attribute access, e.g. ``scratch.safety_ok``.
- Constants: int, float, str, ``True``, ``False``, ``None``.
- Comparisons: ``== != < > <= >=``.
- Boolean ops: ``and``, ``or``, ``not``.
- Parentheses.

Function calls, indexing, arithmetic, ``is``/``in``, lambdas, comprehensions,
and f-strings are rejected at parse time.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Mapping
from typing import Any

from ..core.state import State

Condition = Callable[[State], bool]


# Only these AST node classes are permitted anywhere in the expression tree.
_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BoolOp, ast.And, ast.Or,
    ast.UnaryOp, ast.Not,
    ast.Compare,
    ast.Eq, ast.NotEq, ast.Lt, ast.Gt, ast.LtE, ast.GtE,
    ast.Constant,
    ast.Name,
    ast.Attribute,
    ast.Load,
)

_ALLOWED_ROOTS = frozenset({"scratch", "context", "output"})


class DSLError(ValueError):
    """Raised when a ``when:`` expression violates the DSL grammar."""


def compile_condition(expr: str) -> Condition:
    """Validate a ``when:`` expression and return a State -> bool predicate."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise DSLError(
            f"invalid condition syntax in {expr!r}: {exc.msg}"
        ) from exc

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise DSLError(
                f"disallowed expression in condition {expr!r}: "
                f"{type(node).__name__} not permitted "
                f"(use only attribute access, comparisons, and and/or/not)"
            )
        if isinstance(node, ast.Name) and node.id not in _ALLOWED_ROOTS:
            raise DSLError(
                f"unknown identifier {node.id!r} in condition {expr!r} "
                f"(allowed roots: scratch, context, output)"
            )

    body = tree.body

    def evaluate(state: State) -> bool:
        env = {
            "scratch": state.scratch,
            "context": state.context,
            "output": state.output,
        }
        return bool(_eval(body, env))

    return evaluate


def _eval(node: ast.AST, env: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.Attribute):
        target = _eval(node.value, env)
        if target is None:
            return None
        if isinstance(target, Mapping):
            return target.get(node.attr)
        return getattr(target, node.attr, None)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval(node.operand, env)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for v in node.values:
                if not _eval(v, env):
                    return False
            return True
        # Or
        for v in node.values:
            if _eval(v, env):
                return True
        return False
    if isinstance(node, ast.Compare):
        left = _eval(node.left, env)
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            right = _eval(comparator, env)
            if not _compare(op, left, right):
                return False
            left = right
        return True
    # Whitelist already enforced — unreachable in practice.
    raise DSLError(f"unsupported node in evaluator: {type(node).__name__}")


def _compare(op: ast.cmpop, left: Any, right: Any) -> bool:
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    # Ordering comparisons against None short-circuit to False (no TypeError).
    if left is None or right is None:
        return False
    if isinstance(op, ast.Lt):
        return left < right
    if isinstance(op, ast.Gt):
        return left > right
    if isinstance(op, ast.LtE):
        return left <= right
    if isinstance(op, ast.GtE):
        return left >= right
    return False
