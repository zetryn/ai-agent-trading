"""YAML graph loader.

Declarative graph specs: build a ``Graph`` from a YAML file without any
caller-supplied Python wiring. Live objects (LLM clients, knowledge packs,
decision logs) are injected via a named registry — the framework never
instantiates them, preserving the I/O boundary.
"""

from .loader import ConfigError, load_graph

__all__ = ["ConfigError", "load_graph"]
