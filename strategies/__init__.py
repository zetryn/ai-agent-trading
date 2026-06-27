"""Reference strategies built on the zetryn framework.

This is the proving ground: concrete memecoin agents (scanner, later sniper) and
sample data. In production these typically live in the bot repo; here they
demonstrate and test the framework against the ``trading`` contract.
"""

from .agents.graduation import build_graduation
from .agents.kol_copytrade import build_kol_copytrade
from .agents.lifecycle import build_lifecycle
from .agents.scanner import build_scanner
from .agents.sniper import build_sniper
from .kol_registry import KOLRegistry
from .providers import SAMPLE_TOKENS, SampleProvider

__all__ = [
    "KOLRegistry",
    "SAMPLE_TOKENS",
    "SampleProvider",
    "build_graduation",
    "build_kol_copytrade",
    "build_lifecycle",
    "build_scanner",
    "build_sniper",
]
