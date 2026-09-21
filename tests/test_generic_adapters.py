from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from public_ips.adapters.generic import (
    AtlassianIpRangesAdapter,
    AzureServiceTagsAdapter,
    DatadogIpRangesAdapter,
    GenericCidrAdapter,
    VultrIpRangesAdapter,
)
from public_ips.models import FetchDocument, ProviderConfig, RawFetch


def _config(
    *, adapter: str = "generic_cidr", url: str = "https://example.test/ranges"
) -> ProviderConfig:
    return ProviderConfig(
        provider_id="example.test",
        display_name="Example",
        output_dir="example.test",
        adapter=adapter,
        source_urls=[url],
        documentation_url="https://example.test/docs",
        attribution="Example",
        terms_url=None,
    )


def _raw(config: ProviderConfig, body: bytes, *, status_code: int = 200) -> RawFetch:
    url = config.source_urls[0]
    return RawFetch(
        provider_id=config.provider_id,
        retrieved_at=datetime.now(UTC),
        documents={
            url: FetchDocument(
                url=url,
                body=body,
                content_type=None,
                status_code=status_code,
            )
        },
    )


def test_generic_adapter_text_fallback_normalizes_and_warns() -> None:
    config = _config()
    snapshot = GenericCidrAdapter(config).extract(
        _raw(config, b"\xff\n8.8.8.8/24\n2001:4860:4860::8888\n")
    )

    assert {str(network) for network in snapshot.uncategorized.ipv4} == {"8.8.8.0/24"}
    assert {str(network) for network in snapshot.uncategorized.ipv6} == {
        "2001:4860:4860::8888/128"
    }
    assert any(
        "normalized upstream CIDR '8.8.8.8/24' to '8.8.8.0/24'" in warning
        for warning in snapshot.warnings
    )
    assert any(
        "normalized upstream CIDR '2001:4860:4860::8888' "
        "to '2001:4860:4860::8888/128'" in warning
        for warning in snapshot.warnings
    )


@pytest.mark.parametrize(
    "body",
    [b"10.0.0.0/8\n", b"127.0.0.0/8\n", b"fc00::/7\n", b"192.0.2.0/25\n"],
)
def test_vultr_rejects_unexpected_non_global_ranges(body: bytes) -> None:
    config = _config(adapter="vultr_ip_ranges")

    with pytest.raises(ValueError, match="non-global CIDR"):
        VultrIpRangesAdapter(config).extract(_raw(config, b"45.32.0.0/21\n" + body))


@pytest.mark.parametrize("body", [b"", b"# No prefixes\n", b"192.0.2.0/24\n2001:db8::/32\n"])
def test_vultr_rejects_empty_public_list(body: bytes) -> None:
    config = _config(adapter="vultr_ip_ranges")

    with pytest.raises(ValueError, match="no public ranges found"):
        VultrIpRangesAdapter(config).extract(_raw(config, body))


@pytest.mark.parametrize("body", [b"<html>Error</html>", b"not-a-cidr", b"45.32.0.1/21"])
def test_vultr_rejects_malformed_prefixes(body: bytes) -> None:
    config = _config(adapter="vultr_ip_ranges")

    with pytest.raises(ValueError):
        VultrIpRangesAdapter(config).extract(_raw(config, body))


def test_vultr_rejects_http_failure() -> None:
    config = _config(adapter="vultr_ip_ranges")

    with pytest.raises(ValueError, match="vultr fetch failed: status=503"):
        VultrIpRangesAdapter(config).extract(_raw(config, b"Unavailable", status_code=503))


class _StubClient:
    def __init__(self, responses: dict[str, tuple[int, bytes]]) -> None:
        self.responses = responses

    def get(self, url: str) -> tuple[int, bytes, str | None, str | None, str | None]:
        status, body = self.responses[url]
        return status, body, None, None, None


def test_azure_adapter_discovers_download_url() -> None:
    landing_url = "https://www.microsoft.com/en-us/download/details.aspx?id=56519"
    download_url = "https://download.microsoft.com/download/1/2/3/ServiceTags_Public_20260101.json"
    config = _config(adapter="azure_service_tags", url=landing_url)
    raw = AzureServiceTagsAdapter(config).fetch(
        _StubClient(
            {
                landing_url: (200, f'<a href="{download_url}">Download</a>'.encode()),
                download_url: (200, b'{"values": []}'),
            }
        )
    )

    assert set(raw.documents) == {landing_url, download_url}


def test_azure_adapter_reports_landing_page_failure() -> None:
    config = _config(adapter="azure_service_tags")

    with pytest.raises(ValueError, match="azure landing page fetch failed: status=503"):
        AzureServiceTagsAdapter(config).extract(
            _raw(config, b"Service unavailable", status_code=503)
        )


def test_azure_adapter_reports_missing_download_url() -> None:
    config = _config(adapter="azure_service_tags")

    with pytest.raises(ValueError, match="could not locate ServiceTags_Public"):
        AzureServiceTagsAdapter(config).extract(_raw(config, b"<html></html>"))


def test_azure_adapter_rejects_invalid_values_shape() -> None:
    config = _config(adapter="azure_service_tags")
    download_url = "https://download.microsoft.com/download/1/2/3/ServiceTags_Public_20260101.json"

    with pytest.raises(ValueError, match="azure response field 'values' must be a list"):
        AzureServiceTagsAdapter(config).extract(
            RawFetch(
                provider_id=config.provider_id,
                retrieved_at=datetime.now(UTC),
                documents={
                    download_url: FetchDocument(
                        url=download_url,
                        body=json.dumps({"values": {}}).encode(),
                        content_type="application/json",
                        status_code=200,
                    )
                },
            )
        )


def test_atlassian_adapter_extracts_cidrs_by_product_without_network_field() -> None:
    config = _config(adapter="atlassian_ip_ranges")
    snapshot = AtlassianIpRangesAdapter(config).extract(
        _raw(
            config,
            json.dumps(
                {
                    "items": [
                        {
                            "network": "8.8.8.0",
                            "cidr": "8.8.8.0/24",
                            "product": ["jira", "confluence"],
                        },
                        {
                            "network": "2001:4860:4860::",
                            "cidr": "2001:4860:4860::/48",
                            "product": ["bitbucket"],
                        },
                    ]
                }
            ).encode(),
        )
    )

    assert {str(network) for network in snapshot.categories["jira"].ipv4} == {"8.8.8.0/24"}
    assert {str(network) for network in snapshot.categories["confluence"].ipv4} == {
        "8.8.8.0/24"
    }
    assert {str(network) for network in snapshot.categories["bitbucket"].ipv6} == {
        "2001:4860:4860::/48"
    }
    assert all(not snapshot.categories[category].ipv4 for category in ["bitbucket"])
    assert not snapshot.uncategorized.ipv4


def test_datadog_adapter_extracts_top_level_categories() -> None:
    config = _config(adapter="datadog_ip_ranges")
    snapshot = DatadogIpRangesAdapter(config).extract(
        _raw(
            config,
            json.dumps(
                {
                    "version": 1,
                    "modified": "2026-01-01T00:00:00",
                    "synthetics": {
                        "prefixes_ipv4": ["8.8.8.0/24"],
                        "prefixes_ipv6": ["2001:4860:4860::/48"],
                    },
                    "remote-configuration": {
                        "prefixes_ipv4": ["8.8.4.0/24"],
                        "prefixes_ipv6": [],
                    },
                }
            ).encode(),
        )
    )

    assert {str(network) for network in snapshot.categories["synthetics"].ipv4} == {
        "8.8.8.0/24"
    }
    assert {str(network) for network in snapshot.categories["synthetics"].ipv6} == {
        "2001:4860:4860::/48"
    }
    assert {str(network) for network in snapshot.categories["remote-configuration"].ipv4} == {
        "8.8.4.0/24"
    }
