"""CLI: ``python -m zetryn.config <file.yaml>``.

Validates a YAML graph spec without instantiating any registry. Placeholders
will fail validation — for full end-to-end validation with live objects,
call :func:`zetryn.config.load_graph` from Python instead.
"""

from __future__ import annotations

import argparse
import sys

from .loader import ConfigError, load_graph


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m zetryn.config",
        description="Validate a Zetryn YAML graph spec.",
    )
    parser.add_argument("file", help="Path to the YAML spec to validate.")
    args = parser.parse_args(argv)

    try:
        graph = load_graph(args.file)
    except ConfigError as exc:
        print(f"ConfigError: {exc}", file=sys.stderr)
        return 1

    n_nodes = len(graph._nodes)  # noqa: SLF001 — CLI introspection
    n_edges = len(graph._edges)  # noqa: SLF001
    n_warn = len(graph.warnings)
    print(f"OK: {graph.name} ({n_nodes} nodes, {n_edges} edges, {n_warn} warnings)")
    for w in graph.warnings:
        print(f"  warning: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
