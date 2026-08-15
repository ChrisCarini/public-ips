from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network, collapse_addresses

from public_ips.models import FamilyNetworks


def sort_ipv4(networks: set[IPv4Network]) -> list[IPv4Network]:
    return sorted(networks, key=lambda n: (int(n.network_address), n.prefixlen))


def sort_ipv6(networks: set[IPv6Network]) -> list[IPv6Network]:
    return sorted(networks, key=lambda n: (int(n.network_address), n.prefixlen))


def collapse_family(family: FamilyNetworks) -> FamilyNetworks:
    return FamilyNetworks(
        ipv4=set(collapse_addresses(sort_ipv4(family.ipv4))),
        ipv6=set(collapse_addresses(sort_ipv6(family.ipv6))),
    )


def format_family_lines(family: FamilyNetworks) -> tuple[list[str], list[str], list[str]]:
    v4 = [str(n) for n in sort_ipv4(family.ipv4)]
    v6 = [str(n) for n in sort_ipv6(family.ipv6)]
    return v4 + v6, v4, v6
