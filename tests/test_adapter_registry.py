from __future__ import annotations

from pathlib import Path

import pytest

from public_ips.adapters import adapter_for
from public_ips.adapters.github import GitHubAdapter
from public_ips.config import load_provider_configs
from public_ips.models import ProviderConfig


def _config(adapter: str) -> ProviderConfig:
    return ProviderConfig(
        provider_id="example.test",
        display_name="Example",
        output_dir="example.test",
        adapter=adapter,
        source_urls=["https://example.test/ranges.json"],
        documentation_url="https://example.test/docs",
        attribution="Example",
        terms_url=None,
    )


def test_adapter_registry_creates_registered_adapter() -> None:
    assert isinstance(adapter_for(_config("github_meta")), GitHubAdapter)


def test_adapter_registry_rejects_unknown_adapter() -> None:
    with pytest.raises(ValueError, match="Unknown adapter: missing"):
        adapter_for(_config("missing"))


def test_all_provider_configs_have_registered_adapters() -> None:
    root = Path(__file__).resolve().parents[1]

    for config in load_provider_configs(root):
        adapter_for(config)
