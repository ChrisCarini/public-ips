from __future__ import annotations

from public_ips.models import FamilyNetworks


def diff_family(old: FamilyNetworks, new: FamilyNetworks) -> dict[str, list[str]]:
    old_v4 = {str(n) for n in old.ipv4}
    old_v6 = {str(n) for n in old.ipv6}
    new_v4 = {str(n) for n in new.ipv4}
    new_v6 = {str(n) for n in new.ipv6}
    return {
        "added_ipv4": sorted(new_v4 - old_v4),
        "removed_ipv4": sorted(old_v4 - new_v4),
        "added_ipv6": sorted(new_v6 - old_v6),
        "removed_ipv6": sorted(old_v6 - new_v6),
    }
