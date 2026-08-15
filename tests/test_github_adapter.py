from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from public_ips.adapters.github import GitHubAdapter
from public_ips.models import FetchDocument, ProviderConfig, RawFetch


def _config() -> ProviderConfig:
    return ProviderConfig(
        provider_id="github.com",
        display_name="GitHub",
        output_dir="github.com",
        adapter="github_meta",
        source_urls=["https://api.github.com/meta"],
        documentation_url="https://docs.github.com",
        attribution="GitHub",
        terms_url=None,
        mappings={"hooks": "hooks"},
    )


def test_github_adapter_fails_unknown_cidr_like_field() -> None:
    body = {
        "hooks": ["140.82.112.0/20"],
        "new_service": ["203.0.113.0/24"],
    }
    raw = RawFetch(
        provider_id="github.com",
        retrieved_at=datetime.now(UTC),
        documents={
            "https://api.github.com/meta": FetchDocument(
                url="https://api.github.com/meta",
                body=json.dumps(body).encode(),
                content_type="application/json",
                status_code=200,
            )
        },
    )
    adapter = GitHubAdapter(_config())
    with pytest.raises(ValueError, match="appears CIDR-like"):
        adapter.extract(raw)
