"""Tests for the boolean DSL used in YAML edge ``when:`` conditions."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from zetryn.config.dsl import DSLError, compile_condition
from zetryn.core.state import State


@dataclass
class _Ctx:
    safety_ok: bool = True
    score: float = 0.9
    nested: "_Ctx | None" = None


def _state(*, scratch=None, context=None, output=None) -> State:
    return State(scratch=scratch or {}, context=context, output=output)


# --- Happy path ------------------------------------------------------------


def test_simple_scratch_truthy():
    cond = compile_condition("scratch.safety_ok")
    assert cond(_state(scratch={"safety_ok": True})) is True
    assert cond(_state(scratch={"safety_ok": False})) is False
    assert cond(_state(scratch={})) is False  # missing → None → False


def test_not_operator():
    cond = compile_condition("not scratch.safety_ok")
    assert cond(_state(scratch={"safety_ok": False})) is True
    assert cond(_state(scratch={"safety_ok": True})) is False


def test_and_or_combo():
    cond = compile_condition("scratch.safety_ok and scratch.score > 0.7")
    assert cond(_state(scratch={"safety_ok": True, "score": 0.8})) is True
    assert cond(_state(scratch={"safety_ok": True, "score": 0.5})) is False
    assert cond(_state(scratch={"safety_ok": False, "score": 0.9})) is False


def test_comparison_operators():
    s = _state(scratch={"x": 5})
    assert compile_condition("scratch.x == 5")(s) is True
    assert compile_condition("scratch.x != 4")(s) is True
    assert compile_condition("scratch.x < 10")(s) is True
    assert compile_condition("scratch.x > 0")(s) is True
    assert compile_condition("scratch.x <= 5")(s) is True
    assert compile_condition("scratch.x >= 5")(s) is True


def test_context_dataclass_access():
    ctx = _Ctx(safety_ok=True, score=0.95)
    cond = compile_condition("context.safety_ok and context.score >= 0.9")
    assert cond(_state(context=ctx)) is True


def test_nested_attribute_chain():
    ctx = _Ctx(safety_ok=False, nested=_Ctx(safety_ok=True, score=0.5))
    cond = compile_condition("context.nested.safety_ok")
    assert cond(_state(context=ctx)) is True


def test_none_short_circuits_chain():
    # context is None — chain access should yield None, not raise.
    cond = compile_condition("context.nested.safety_ok")
    assert cond(_state(context=None)) is False


def test_constants_supported():
    s = _state()
    assert compile_condition("True")(s) is True
    assert compile_condition("False")(s) is False
    assert compile_condition("None")(s) is False


def test_string_equality():
    cond = compile_condition("scratch.mode == 'confirmed'")
    assert cond(_state(scratch={"mode": "confirmed"})) is True
    assert cond(_state(scratch={"mode": "rule"})) is False


def test_parens_precedence():
    cond = compile_condition(
        "(scratch.a or scratch.b) and not scratch.c"
    )
    assert cond(_state(scratch={"a": True, "b": False, "c": False})) is True
    assert cond(_state(scratch={"a": False, "b": True, "c": True})) is False


def test_output_root_accessible():
    cond = compile_condition("output == 'done'")
    assert cond(_state(output="done")) is True
    assert cond(_state(output="pending")) is False


# --- Rejected expressions --------------------------------------------------


@pytest.mark.parametrize(
    "expr",
    [
        "len(scratch.items)",                  # function call
        "scratch.items[0]",                    # indexing
        "scratch.x + 1 > 5",                   # arithmetic
        "scratch.mode is None",                # `is` operator
        "scratch.x in [1, 2, 3]",              # `in` operator
        "lambda s: s.x",                       # lambda
        "scratch.x.startswith('y')",           # method call (callable attr)
        "[x for x in scratch.items]",          # comprehension
    ],
)
def test_disallowed_syntax_rejected(expr):
    with pytest.raises(DSLError):
        compile_condition(expr)


def test_unknown_identifier_rejected():
    with pytest.raises(DSLError) as exc:
        compile_condition("foo.bar")
    assert "foo" in str(exc.value)


def test_invalid_syntax_reports_clearly():
    with pytest.raises(DSLError) as exc:
        compile_condition("scratch.x &&& scratch.y")
    assert "invalid" in str(exc.value).lower()


def test_ordering_compare_with_none_is_false_not_typeerror():
    cond = compile_condition("scratch.x > 5")
    # missing key → None → ordering returns False, NO TypeError
    assert cond(_state(scratch={})) is False
