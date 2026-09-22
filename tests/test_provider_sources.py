from __future__ import annotations

from pathlib import Path

import pytest

from public_ips.adapters import adapter_for
from public_ips.cli import FileHttpClient
from public_ips.config import load_provider_configs


@pytest.mark.parametrize(
    ("provider_id", "ipv4", "ipv6"),
    [
        (
            "bunny.net",
            {"89.187.188.227/32", "89.187.188.228/32"},
            {"2400:52e0:1500::714:1/128", "2400:52e0:1500::715:1/128"},
        ),
        ("linode.com", {"72.14.177.0/24"}, {"2600:3c00::/32"}),
        (
            "tailscale.com",
            {"199.38.181.104/32", "209.177.145.120/32", "192.73.240.161/32"},
            {"2607:f740:f::bc/128", "2607:f740:f::3eb/128"},
        ),
        (
            "telegram.org",
            {"91.108.4.0/22", "91.108.56.0/22", "149.154.160.0/20"},
            {"2001:b28:f23d::/48", "2a0a:f280::/32"},
        ),
        (
            "statuscake.com",
            {"34.13.166.3/32", "146.190.20.113/32", "178.62.47.83/32", "188.166.170.233/32"},
            {"2a03:b0c0:2:d0::12d1:1/128", "2a03:b0c0:1:d0::a4:6001/128"},
        ),
        (
            "vultr.com",
            {"43.224.32.0/22", "45.32.0.0/21"},
            {"2001:19f0:8000::/38", "2a05:f480:1000::/38"},
        ),
        (
            "zoom.us",
            {"3.7.35.0/25", "3.235.82.0/23", "3.235.96.0/23"},
            {"2407:30c0::/32", "2600:9000:2600::/48", "2620:123:2000::/40"},
        ),
    ],
)
def test_official_source_formats(provider_id: str, ipv4: set[str], ipv6: set[str]) -> None:
    root = Path(__file__).resolve().parents[1]
    config = next(c for c in load_provider_configs(root) if c.provider_id == provider_id)
    adapter = adapter_for(config)
    raw = adapter.fetch(FileHttpClient(root / "tests" / "fixtures"))
    snapshot = adapter.extract(raw)

    assert set(raw.documents) == set(config.source_urls)
    assert snapshot.source_urls == config.source_urls
    assert {str(network) for network in snapshot.uncategorized.ipv4} == ipv4
    assert {str(network) for network in snapshot.uncategorized.ipv6} == ipv6
    assert snapshot.categories == {}
    assert not config.allow_non_global
    if provider_id in {"bunny.net", "linode.com"}:
        assert any("duplicate upstream CIDR" in warning for warning in snapshot.warnings)
    if provider_id == "vultr.com":
        assert len(snapshot.warnings) == 7
        assert all("excluded special-purpose CIDR" in warning for warning in snapshot.warnings)
