"""Tests for the v0.8.0 provider expansion (Cerebras / Mistral / SambaNova /
NVIDIA NIM) and the tier preset builders."""

from __future__ import annotations

import pytest

from zetryn.llm import (
    CEREBRAS_BASE_URL,
    MISTRAL_BASE_URL,
    NVIDIA_NIM_BASE_URL,
    PROVIDER_FREE_TIER_LIMITS,
    SAMBANOVA_BASE_URL,
    TIER_QUALITY,
    TIER_SPEED,
    TIER_VOLUME,
    LLMRouter,
    TierSpec,
    build_tier_entries,
    get_free_tier_limit,
)
from zetryn.llm.types import LLMResult, Message

# -- new BASE_URL constants ------------------------------------------------


def test_new_base_urls_are_strings_with_v1_path():
    """Each new provider URL ends with /v1 (or compatible)."""
    for url in (CEREBRAS_BASE_URL, MISTRAL_BASE_URL,
                SAMBANOVA_BASE_URL, NVIDIA_NIM_BASE_URL):
        assert isinstance(url, str)
        assert url.startswith("https://")
        assert "/v1" in url


# -- free-tier presets -----------------------------------------------------


def test_new_providers_have_at_least_one_model_each():
    for provider in ("cerebras", "mistral", "sambanova", "nvidia_nim"):
        assert provider in PROVIDER_FREE_TIER_LIMITS, provider
        assert len(PROVIDER_FREE_TIER_LIMITS[provider]) >= 1


@pytest.mark.parametrize("provider,model,expected_rpm", [
    ("cerebras", "llama-3.3-70b", 30),
    ("cerebras", "gpt-oss-120b", 30),
    ("mistral", "mistral-large-latest", 2),
    ("sambanova", "Meta-Llama-3.1-405B-Instruct", 10),
    ("nvidia_nim", "deepseek-ai/deepseek-r1", 40),
])
def test_get_free_tier_limit_resolves_new_providers(provider, model, expected_rpm):
    limit = get_free_tier_limit(provider, model)
    assert limit is not None, f"{provider}/{model} should have a preset"
    assert limit.rpm == expected_rpm


def test_unknown_model_returns_none_per_provider():
    assert get_free_tier_limit("cerebras", "ghost-model") is None
    assert get_free_tier_limit("mistral", "ghost-model") is None
    assert get_free_tier_limit("ghost-provider", "anything") is None


# -- tier presets ----------------------------------------------------------


def test_tier_specs_are_well_formed():
    for name, tier in (("SPEED", TIER_SPEED),
                       ("QUALITY", TIER_QUALITY),
                       ("VOLUME", TIER_VOLUME)):
        assert len(tier) >= 2, f"{name} tier should have ≥2 specs for failover"
        for spec in tier:
            assert isinstance(spec, TierSpec)
            assert spec.provider and spec.model
            assert spec.provider in PROVIDER_FREE_TIER_LIMITS, (
                f"{name}: {spec.provider} missing from PROVIDER_FREE_TIER_LIMITS"
            )


def test_speed_tier_starts_with_cerebras():
    """Speed tier should prioritise Cerebras (fastest free inference)."""
    assert TIER_SPEED[0].provider == "cerebras"


def test_quality_tier_starts_with_sambanova_405b():
    """Quality tier should prioritise the largest open model gratis."""
    assert TIER_QUALITY[0].provider == "sambanova"
    assert "405B" in TIER_QUALITY[0].model


def test_volume_tier_starts_with_openrouter_free_suffix():
    assert TIER_VOLUME[0].provider == "openrouter"
    assert TIER_VOLUME[0].model.endswith(":free")


# -- build_tier_entries() --------------------------------------------------


class _FakeClient:
    """Minimal LLMClient stand-in."""

    name = "fake"

    async def complete(self, messages: list[Message], **kw) -> LLMResult:
        return LLMResult(text="", model="fake", latency_ms=0.0)

    async def aclose(self) -> None:
        pass


def test_build_tier_entries_silently_skips_missing_providers():
    """Caller passes a dict with only one provider — others are skipped."""
    clients = {"groq": _FakeClient()}
    entries = build_tier_entries(TIER_SPEED, clients)
    # TIER_SPEED has cerebras + 2 groq entries; cerebras gets skipped
    assert all(e.client is clients["groq"] for e in entries)
    assert 1 <= len(entries) <= len(TIER_SPEED)


def test_build_tier_entries_with_all_providers_present():
    """Caller passes a dict covering every provider in the tier."""
    fakes = {p: _FakeClient() for p in {s.provider for s in TIER_SPEED}}
    entries = build_tier_entries(TIER_SPEED, fakes)
    assert len(entries) == len(TIER_SPEED)
    # Each entry has its preset limit attached
    for entry, spec in zip(entries, TIER_SPEED, strict=True):
        assert entry.name == f"{spec.provider}:{spec.model}"
        expected = get_free_tier_limit(spec.provider, spec.model)
        assert entry.limit is expected


def test_build_tier_entries_returns_empty_when_no_providers_match():
    entries = build_tier_entries(TIER_SPEED, {})
    assert entries == []


def test_built_entries_wire_cleanly_into_LLMRouter():
    """Sanity: the output of build_tier_entries is a valid input to LLMRouter."""
    fakes = {p: _FakeClient() for p in {s.provider for s in TIER_QUALITY}}
    entries = build_tier_entries(TIER_QUALITY, fakes)
    router = LLMRouter(entries)
    assert len(router.entries) == len(entries)


# -- backwards compat: existing providers still resolve --------------------


def test_existing_providers_still_work():
    """Ensure adding new providers didn't break Groq / Gemini / OpenRouter."""
    assert get_free_tier_limit("groq", "openai/gpt-oss-20b") is not None
    assert get_free_tier_limit("gemini", "gemini-2.5-flash") is not None
    assert get_free_tier_limit("openrouter", "anything:free") is not None
