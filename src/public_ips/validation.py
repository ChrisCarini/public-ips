from __future__ import annotations

from ipaddress import ip_network

from public_ips.models import FamilyNetworks


def _is_global_network(cidr: str) -> bool:
    net = ip_network(cidr, strict=True)
    return bool(net.is_global)


def parse_networks(
    cidrs: list[str], *, allow_non_global: bool, warning_prefix: str, warnings: list[str]
) -> FamilyNetworks:
    family = FamilyNetworks()
    seen: set[str] = set()
    for raw in cidrs:
        network = ip_network(raw, strict=True)
        canonical = str(network)
        if canonical in seen:
            warnings.append(f"{warning_prefix}: duplicate upstream CIDR '{canonical}'")
            continue
        seen.add(canonical)
        if not allow_non_global and not _is_global_network(canonical):
            message = (
                f"{warning_prefix}: non-global CIDR '{canonical}' blocked; "
                "set allow_non_global=true to permit"
            )
            raise ValueError(
                message
            )
        family.add(network)
    return family


def validate_path_component(value: str) -> None:
    if not value or value.startswith("/") or ".." in value or "/" in value or "\\" in value:
        raise ValueError(f"Invalid path component: {value}")
