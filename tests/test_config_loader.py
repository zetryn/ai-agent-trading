"""Tests for the YAML graph loader."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from zetryn.config import ConfigError, load_graph
from zetryn.core.state import END, Command, State


# --- Test fixtures (referenced from YAML) -----------------------------------


def safety_gate(state: State) -> None:
    state.scratch["safety_ok"] = state.context.get("token") != "BAD"


def decide_buy(state: State) -> Command:
    state.output = {"action": "buy", "size": 1.0}
    return Command(goto=END)


def decide_skip(state: State) -> Command:
    state.output = {"action": "skip"}
    return Command(goto=END)


class DummyVerdict(BaseModel):
    score: float = 0.5


def dummy_prompt(state: State):
    return []


def dummy_result_fn(verdict: DummyVerdict, state: State):
    return {"action": "buy" if verdict.score > 0.5 else "skip"}


# --- Helpers ----------------------------------------------------------------


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "spec.yaml"
    p.write_text(text, encoding="utf-8")
    return p


# --- Happy paths ------------------------------------------------------------


def test_rule_only_graph_compiles_and_runs(tmp_path):
    yaml = """
name: simple
entry: gate
nodes:
  - {name: gate, type: rule, fn: tests.test_config_loader:safety_gate}
  - {name: buy,  type: rule, fn: tests.test_config_loader:decide_buy}
  - {name: skip, type: rule, fn: tests.test_config_loader:decide_skip}
edges:
  - {from: gate, to: buy,  when: "scratch.safety_ok"}
  - {from: gate, to: skip, when: "not scratch.safety_ok"}
  - {from: buy,  to: END}
  - {from: skip, to: END}
"""
    g = load_graph(_write(tmp_path, yaml))
    assert g.name == "simple"
    assert len(g._nodes) == 3
    assert len(g._edges) == 4


@pytest.mark.asyncio
async def test_rule_graph_executes_end_to_end(tmp_path):
    yaml = """
name: simple
entry: gate
nodes:
  - {name: gate, type: rule, fn: tests.test_config_loader:safety_gate}
  - {name: buy,  type: rule, fn: tests.test_config_loader:decide_buy}
  - {name: skip, type: rule, fn: tests.test_config_loader:decide_skip}
edges:
  - {from: gate, to: buy,  when: "scratch.safety_ok"}
  - {from: gate, to: skip, when: "not scratch.safety_ok"}
"""
    g = load_graph(_write(tmp_path, yaml))

    good = await g.run(State(context={"token": "GOOD"}))
    assert good.output == {"action": "buy", "size": 1.0}

    bad = await g.run(State(context={"token": "BAD"}))
    assert bad.output == {"action": "skip"}


def test_llm_node_builds_with_registry(tmp_path):
    class StubClient:
        async def complete(self, *a, **kw):  # pragma: no cover - not invoked
            raise NotImplementedError

    yaml = """
name: with_llm
entry: analyst
nodes:
  - name: analyst
    type: llm
    client: ${llm.stub}
    schema: tests.test_config_loader:DummyVerdict
    prompt_fn: tests.test_config_loader:dummy_prompt
edges:
  - {from: analyst, to: END}
"""
    g = load_graph(_write(tmp_path, yaml), registry={"llm.stub": StubClient()})
    assert "analyst" in g._nodes


def test_llm_decision_node_builds(tmp_path):
    class StubClient:
        pass

    yaml = """
name: with_decision
entry: decide
nodes:
  - name: decide
    type: llm_decision
    client: ${llm.stub}
    schema: tests.test_config_loader:DummyVerdict
    prompt_fn: tests.test_config_loader:dummy_prompt
    result_fn: tests.test_config_loader:dummy_result_fn
edges: []
"""
    g = load_graph(_write(tmp_path, yaml), registry={"llm.stub": StubClient()})
    assert "decide" in g._nodes


def test_end_sentinel_in_when_condition(tmp_path):
    yaml = """
name: short
entry: gate
nodes:
  - {name: gate, type: rule, fn: tests.test_config_loader:decide_buy}
edges:
  - {from: gate, to: END}
"""
    g = load_graph(_write(tmp_path, yaml))
    assert g._edges[0].target == END


# --- Schema errors ----------------------------------------------------------


def test_missing_name_field(tmp_path):
    yaml = "entry: foo\nnodes: []\nedges: []\n"
    with pytest.raises(ConfigError, match="missing required field 'name'"):
        load_graph(_write(tmp_path, yaml))


def test_missing_entry_field(tmp_path):
    yaml = "name: x\nnodes: []\nedges: []\n"
    with pytest.raises(ConfigError, match="missing required field 'entry'"):
        load_graph(_write(tmp_path, yaml))


def test_empty_nodes_list(tmp_path):
    yaml = "name: x\nentry: foo\nnodes: []\nedges: []\n"
    with pytest.raises(ConfigError, match="'nodes' must be a non-empty list"):
        load_graph(_write(tmp_path, yaml))


def test_unsupported_node_type(tmp_path):
    yaml = """
name: x
entry: foo
nodes:
  - {name: foo, type: bogus, fn: tests.test_config_loader:decide_buy}
edges: []
"""
    with pytest.raises(ConfigError, match="unsupported node type 'bogus'"):
        load_graph(_write(tmp_path, yaml))


def test_duplicate_node_name(tmp_path):
    yaml = """
name: x
entry: foo
nodes:
  - {name: foo, type: rule, fn: tests.test_config_loader:decide_buy}
  - {name: foo, type: rule, fn: tests.test_config_loader:decide_skip}
edges: []
"""
    with pytest.raises(ConfigError, match="duplicate node name 'foo'"):
        load_graph(_write(tmp_path, yaml))


def test_entry_not_in_nodes(tmp_path):
    yaml = """
name: x
entry: missing
nodes:
  - {name: foo, type: rule, fn: tests.test_config_loader:decide_buy}
edges: []
"""
    with pytest.raises(ConfigError, match="entry 'missing' not in registered"):
        load_graph(_write(tmp_path, yaml))


def test_edge_to_unknown_node(tmp_path):
    yaml = """
name: x
entry: foo
nodes:
  - {name: foo, type: rule, fn: tests.test_config_loader:decide_buy}
edges:
  - {from: foo, to: ghost}
"""
    with pytest.raises(ConfigError, match="edge.to 'ghost' not in registered"):
        load_graph(_write(tmp_path, yaml))


# --- Reference resolution errors --------------------------------------------


def test_function_reference_missing_colon(tmp_path):
    yaml = """
name: x
entry: foo
nodes:
  - {name: foo, type: rule, fn: tests.test_config_loader.decide_buy}
edges: []
"""
    with pytest.raises(ConfigError, match="missing ':'"):
        load_graph(_write(tmp_path, yaml))


def test_function_module_not_importable(tmp_path):
    yaml = """
name: x
entry: foo
nodes:
  - {name: foo, type: rule, fn: nonexistent.module:fn}
edges: []
"""
    with pytest.raises(ConfigError, match="not importable"):
        load_graph(_write(tmp_path, yaml))


def test_function_attribute_missing(tmp_path):
    yaml = """
name: x
entry: foo
nodes:
  - {name: foo, type: rule, fn: tests.test_config_loader:does_not_exist}
edges: []
"""
    with pytest.raises(ConfigError, match="has no attribute 'does_not_exist'"):
        load_graph(_write(tmp_path, yaml))


# --- Registry placeholder errors --------------------------------------------


def test_placeholder_not_in_registry(tmp_path):
    yaml = """
name: x
entry: a
nodes:
  - name: a
    type: llm
    client: ${llm.missing}
    schema: tests.test_config_loader:DummyVerdict
    prompt_fn: tests.test_config_loader:dummy_prompt
edges: []
"""
    with pytest.raises(ConfigError, match=r"\$\{llm.missing\} not in registry"):
        load_graph(_write(tmp_path, yaml), registry={"llm.other": object()})


def test_placeholder_wrong_format(tmp_path):
    yaml = """
name: x
entry: a
nodes:
  - name: a
    type: llm
    client: "just_a_string"
    schema: tests.test_config_loader:DummyVerdict
    prompt_fn: tests.test_config_loader:dummy_prompt
edges: []
"""
    with pytest.raises(ConfigError, match="must be a registry placeholder"):
        load_graph(_write(tmp_path, yaml), registry={})


# --- DSL integration --------------------------------------------------------


def test_invalid_when_expression(tmp_path):
    yaml = """
name: x
entry: foo
nodes:
  - {name: foo, type: rule, fn: tests.test_config_loader:decide_buy}
edges:
  - {from: foo, to: END, when: "len(scratch.items) > 0"}
"""
    with pytest.raises(ConfigError, match="when:"):
        load_graph(_write(tmp_path, yaml))


# --- YAML errors ------------------------------------------------------------


def test_invalid_yaml_syntax(tmp_path):
    yaml = "name: x\n  entry: foo\nnodes:\n -bad\n"
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_graph(_write(tmp_path, yaml))


def test_top_level_not_mapping(tmp_path):
    yaml = "- a\n- b\n"
    with pytest.raises(ConfigError, match="top-level YAML must be a mapping"):
        load_graph(_write(tmp_path, yaml))


def test_file_not_found(tmp_path):
    with pytest.raises(ConfigError, match="cannot read file"):
        load_graph(tmp_path / "does_not_exist.yaml")


# --- Error formatting -------------------------------------------------------


def test_error_includes_path_and_location(tmp_path):
    yaml = """
name: x
entry: foo
nodes:
  - {name: foo, type: rule, fn: tests.test_config_loader:does_not_exist}
edges: []
"""
    p = _write(tmp_path, yaml)
    with pytest.raises(ConfigError) as exc:
        load_graph(p)
    msg = str(exc.value)
    assert str(p) in msg
    assert "nodes[0]" in msg
    assert "'foo'" in msg
