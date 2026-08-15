from __future__ import annotations

import pytest

from public_ips.validation import parse_networks


def test_parse_networks_rejects_host_bits() -> None:
    with pytest.raises(ValueError):
        parse_networks(["192.0.2.1/24"], allow_non_global=True, warning_prefix="t", warnings=[])


def test_parse_networks_warns_duplicates() -> None:
    warnings: list[str] = []
    family = parse_networks(
        ["203.0.113.0/24", "203.0.113.0/24"],
        allow_non_global=True,
        warning_prefix="t",
        warnings=warnings,
    )
    assert len(family.ipv4) == 1
    assert warnings and "duplicate" in warnings[0]
