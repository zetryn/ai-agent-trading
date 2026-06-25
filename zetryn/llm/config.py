"""Provider configuration.

Config stores only the *names* of environment variables holding keys — never the
values. Keys are resolved from the environment at build time and missing keys
fail fast with a clear error.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .keypool import KeyPool
from .types import LLMError


@dataclass
class ProviderConfig:
    """Describes one OpenAI-compatible provider."""

    name: str
    base_url: str
    model: str
    key_envs: list[str] = field(default_factory=list)  # NAMES of env vars (production)
    keys: list[str] = field(default_factory=list)  # literal keys (quick local testing only)
    timeout_s: float = 30.0
    max_retries: int = 3
    cooldown_s: float = 60.0
    temperature: float = 0.2
    # Whether to request response_format=json_object for structured calls.
    supports_json_mode: bool = True

    def resolve_keys(self, *, environ: dict[str, str] | None = None) -> list[str]:
        """Resolve keys. Literal ``keys`` win (testing); else read ``key_envs`` from env."""
        if self.keys:
            return list(self.keys)
        env = environ if environ is not None else os.environ
        keys = [env[name] for name in self.key_envs if env.get(name)]
        if not keys:
            raise LLMError(
                f"provider {self.name!r}: none of {self.key_envs} are set in the "
                "environment (check your .env), and no literal keys were given"
            )
        return keys

    def build_key_pool(self, *, environ: dict[str, str] | None = None) -> KeyPool:
        return KeyPool(self.resolve_keys(environ=environ), cooldown_s=self.cooldown_s)


# Provider base_url presets. The caller supplies model + key env var names.
#
# Tier 1 — zero-cost (default for dev):
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
# Tier 1 — additional free-tier providers (no credit card required):
CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
SAMBANOVA_BASE_URL = "https://api.sambanova.ai/v1"
NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
# Tier 2 — paid (next level). OpenAI is OpenAI-compatible; Anthropic (Claude) needs
# a native adapter for prompt caching and is added separately, or reached via
# OpenRouter for the OpenAI-compatible path.
OPENAI_BASE_URL = "https://api.openai.com/v1"
# Tier 3 — Zetryn's own hosted models: see zetryn.llm.zetryn_client.ZETRYN_API_BASE.
