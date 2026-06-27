"""Tests for the ``python -m zetryn.config`` CLI."""

from __future__ import annotations

from pathlib import Path

from zetryn.config.__main__ import main


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "spec.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_cli_valid_spec_exits_zero(tmp_path, capsys):
    yaml = """
name: ok
entry: gate
nodes:
  - {name: gate, type: rule, fn: tests.test_config_loader:decide_buy}
edges:
  - {from: gate, to: END}
"""
    rc = main([str(_write(tmp_path, yaml))])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("OK: ok")


def test_cli_invalid_spec_exits_one(tmp_path, capsys):
    yaml = """
name: bad
entry: missing
nodes:
  - {name: gate, type: rule, fn: tests.test_config_loader:decide_buy}
edges: []
"""
    rc = main([str(_write(tmp_path, yaml))])
    err = capsys.readouterr().err
    assert rc == 1
    assert "ConfigError" in err
    assert "entry 'missing'" in err
