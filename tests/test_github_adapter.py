from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from public_ips.adapters.github import GitHubAdapter
from public_ips.models import FetchDocument, ProviderConfig, RawFetch


def _config(*, mappings: dict[str, str] | None = None) -> ProviderConfig:
    return ProviderConfig(
        provider_id="github.com",
        display_name="GitHub",
        output_dir="github.com",
        adapter="github_meta",
        source_urls=["https://api.github.com/meta"],
        documentation_url="https://docs.github.com",
        attribution="GitHub",
        terms_url=None,
        mappings=mappings or {},
    )


def _raw(body: dict[str, object]) -> RawFetch:
    return RawFetch(
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


def test_github_adapter_discovers_new_cidr_categories() -> None:
    snapshot = GitHubAdapter(_config()).extract(
        _raw(
            {
                "hooks": ["140.82.112.0/20"],
                "new_service": ["185.199.108.0/22"],
            }
        )
    )

    assert set(snapshot.categories) == {"hooks", "new_service"}
    assert {str(network) for network in snapshot.categories["new_service"].ipv4} == {
        "185.199.108.0/22"
    }


def test_github_adapter_preserves_renames_and_missing_mapped_fields() -> None:
    snapshot = GitHubAdapter(
        _config(mappings={"hooks": "webhooks", "retired_service": "retired_service"})
    ).extract(_raw({"hooks": ["140.82.112.0/20"]}))

    assert set(snapshot.categories) == {"retired_service", "webhooks"}
    assert not snapshot.categories["retired_service"].ipv4
    assert not snapshot.categories["retired_service"].ipv6


def test_github_adapter_ignores_non_cidr_metadata() -> None:
    snapshot = GitHubAdapter(_config()).extract(
        _raw(
            {
                "domains": ["github.com", "*.github.com"],
                "ssh_keys": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample"],
                "ssh_key_fingerprints": {"SHA256_RSA": "example"},
                "verifiable_password_authentication": True,
            }
        )
    )

    assert snapshot.categories == {}


@pytest.mark.parametrize(
    "values",
    [
        ["140.82.112.0/20", "not-a-cidr"],
        ["140.82.112.1/20"],
    ],
)
def test_github_adapter_rejects_malformed_or_mixed_cidr_lists(values: list[str]) -> None:
    with pytest.raises(ValueError, match="malformed or mixed CIDR"):
        GitHubAdapter(_config()).extract(_raw({"bad_service": values}))


def test_github_adapter_rejects_unsafe_category_names() -> None:
    with pytest.raises(ValueError, match="Invalid path component"):
        GitHubAdapter(_config()).extract(_raw({"../escape": ["140.82.112.0/20"]}))
