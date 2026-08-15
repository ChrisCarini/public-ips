from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from public_ips.models import ChangeEvent, FamilyNetworks, ProviderSnapshot
from public_ips.normalization import collapse_family, format_family_lines


def _write_text_file(path: Path, lines: list[str]) -> None:
    body = "\n".join(lines)
    if lines:
        body = f"{body}\n"
    path.write_text(body)


def _family_count(family: FamilyNetworks) -> dict[str, int]:
    return {"ipv4": len(family.ipv4), "ipv6": len(family.ipv6)}


def provider_union(snapshot: ProviderSnapshot) -> FamilyNetworks:
    merged = FamilyNetworks()
    merged.union(snapshot.uncategorized)
    for ranges in snapshot.categories.values():
        merged.union(ranges)
    return merged


def canonical_payload(snapshot: ProviderSnapshot) -> dict[str, Any]:
    provider = provider_union(snapshot)
    categories = {
        category: {
            "ipv4": [
                str(c)
                for c in sorted(family.ipv4, key=lambda n: (int(n.network_address), n.prefixlen))
            ],
            "ipv6": [
                str(c)
                for c in sorted(family.ipv6, key=lambda n: (int(n.network_address), n.prefixlen))
            ],
        }
        for category, family in sorted(snapshot.categories.items())
    }
    return {
        "provider": snapshot.provider_id,
        "uncategorized": {
            "ipv4": [
                str(c)
                for c in sorted(
                    snapshot.uncategorized.ipv4, key=lambda n: (int(n.network_address), n.prefixlen)
                )
            ],
            "ipv6": [
                str(c)
                for c in sorted(
                    snapshot.uncategorized.ipv6, key=lambda n: (int(n.network_address), n.prefixlen)
                )
            ],
        },
        "categories": categories,
        "provider_union": {
            "ipv4": [
                str(c)
                for c in sorted(provider.ipv4, key=lambda n: (int(n.network_address), n.prefixlen))
            ],
            "ipv6": [
                str(c)
                for c in sorted(provider.ipv6, key=lambda n: (int(n.network_address), n.prefixlen))
            ],
        },
    }


def canonical_hash(snapshot: ProviderSnapshot) -> str:
    payload = canonical_payload(snapshot)
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _paths_for(prefix: str = "") -> dict[str, str]:
    return {
        "all": f"{prefix}all.txt",
        "ipv4": f"{prefix}ipv4.txt",
        "ipv6": f"{prefix}ipv6.txt",
        "collapsed_all": f"{prefix}collapsed-all.txt",
        "collapsed_ipv4": f"{prefix}collapsed-ipv4.txt",
        "collapsed_ipv6": f"{prefix}collapsed-ipv6.txt",
    }


def write_provider_outputs(
    root: Path,
    snapshot: ProviderSnapshot,
    first_observed_at: str,
    generated_at: str,
) -> tuple[dict[str, Any], list[dict[str, str | int | None]], list[dict[str, Any]]]:
    provider_dir = root / snapshot.output_dir
    provider_dir.mkdir(parents=True, exist_ok=True)

    provider_family = provider_union(snapshot)
    collapsed_provider = collapse_family(provider_family)
    all_lines, ipv4_lines, ipv6_lines = format_family_lines(provider_family)
    collapsed_all_lines, collapsed_ipv4_lines, collapsed_ipv6_lines = format_family_lines(
        collapsed_provider
    )

    _write_text_file(provider_dir / "all.txt", all_lines)
    _write_text_file(provider_dir / "ipv4.txt", ipv4_lines)
    _write_text_file(provider_dir / "ipv6.txt", ipv6_lines)
    _write_text_file(provider_dir / "collapsed-all.txt", collapsed_all_lines)
    _write_text_file(provider_dir / "collapsed-ipv4.txt", collapsed_ipv4_lines)
    _write_text_file(provider_dir / "collapsed-ipv6.txt", collapsed_ipv6_lines)

    category_json: dict[str, Any] = {}
    csv_rows: list[dict[str, str | int | None]] = []
    search_entries: list[dict[str, Any]] = []

    def add_rows(category: str | None, family: FamilyNetworks, base: Path) -> None:
        family_lines, f4, f6 = format_family_lines(family)
        c_family = collapse_family(family)
        c_all, c4, c6 = format_family_lines(c_family)
        _write_text_file(base / "all.txt", family_lines)
        _write_text_file(base / "ipv4.txt", f4)
        _write_text_file(base / "ipv6.txt", f6)
        _write_text_file(base / "collapsed-all.txt", c_all)
        _write_text_file(base / "collapsed-ipv4.txt", c4)
        _write_text_file(base / "collapsed-ipv6.txt", c6)

        for family_name, lines, rel in (
            ("ipv4", f4, "ipv4.txt"),
            ("ipv6", f6, "ipv6.txt"),
        ):
            for index, cidr in enumerate(lines, start=1):
                row: dict[str, str | int | None] = {
                    "provider": snapshot.provider_id,
                    "category": category,
                    "ip_family": family_name,
                    "cidr": cidr,
                    "source_url": snapshot.source_urls[0],
                    "first_observed_at": first_observed_at,
                }
                csv_rows.append(row)
                search_entries.append(
                    {
                        "provider": snapshot.provider_id,
                        "category": category,
                        "ip_family": family_name,
                        "cidr": cidr,
                        "path": str((base / rel).relative_to(root)),
                        "line": index,
                        "anchor": (
                            f"{snapshot.provider_id}-{(category or 'root')}-{family_name}-{index}"
                        ),
                        "source_url": snapshot.source_urls[0],
                    }
                )

    add_rows(None, provider_family, provider_dir)
    for category, family in sorted(snapshot.categories.items()):
        category_dir = provider_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)
        add_rows(category, family, category_dir)
        category_json[category] = {
            "paths": _paths_for(f"{category}/"),
            "counts": _family_count(family),
            "ipv4": [
                str(c)
                for c in sorted(family.ipv4, key=lambda n: (int(n.network_address), n.prefixlen))
            ],
            "ipv6": [
                str(c)
                for c in sorted(family.ipv6, key=lambda n: (int(n.network_address), n.prefixlen))
            ],
        }

    normalized_hash = canonical_hash(snapshot)
    ranges_json = {
        "schema_version": "v1",
        "provider_id": snapshot.provider_id,
        "display_name": snapshot.display_name,
        "source_urls": snapshot.source_urls,
        "documentation_url": snapshot.documentation_url,
        "attribution": snapshot.attribution,
        "terms_url": snapshot.terms_url,
        "normalized_data_sha256": normalized_hash,
        "source_body_sha256": snapshot.source_body_hash,
        "first_observed_at": first_observed_at,
        "generated_at": generated_at,
        "provider": {
            "paths": _paths_for(),
            "counts": _family_count(provider_family),
            "ipv4": [
                str(c)
                for c in sorted(
                    provider_family.ipv4, key=lambda n: (int(n.network_address), n.prefixlen)
                )
            ],
            "ipv6": [
                str(c)
                for c in sorted(
                    provider_family.ipv6, key=lambda n: (int(n.network_address), n.prefixlen)
                )
            ],
        },
        "categories": category_json,
    }
    (provider_dir / "ranges.json").write_text(
        json.dumps(ranges_json, indent=2, sort_keys=True) + "\n"
    )

    with (provider_dir / "ranges.csv").open("w", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "provider",
                "category",
                "ip_family",
                "cidr",
                "source_url",
                "first_observed_at",
            ],
        )
        writer.writeheader()
        writer.writerows(csv_rows)

    changelog_path = provider_dir / "CHANGELOG.md"
    if not changelog_path.exists():
        changelog_path.write_text(f"# Changelog - {snapshot.provider_id}\n\n")

    return ranges_json, csv_rows, search_entries


def write_root_files(
    root: Path,
    provider_rows: dict[str, dict[str, Any]],
    all_csv_rows: list[dict[str, str | int | None]],
    search_entries: list[dict[str, Any]],
    events: list[ChangeEvent],
    generated_at: str,
) -> None:
    manifest = {
        "schema_version": "v1",
        "generated_at": generated_at,
        "providers": provider_rows,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with (root / "ranges.csv").open("w", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "provider",
                "category",
                "ip_family",
                "cidr",
                "source_url",
                "first_observed_at",
            ],
        )
        writer.writeheader()
        writer.writerows(all_csv_rows)

    (root / "search-index.json").write_text(
        json.dumps({"schema_version": "v1", "entries": search_entries}, indent=2, sort_keys=True)
        + "\n"
    )

    changes_path = root / "changes.jsonl"
    if events:
        with changes_path.open("a") as f:
            for event in events:
                f.write(json.dumps(asdict(event), sort_keys=True) + "\n")
    elif not changes_path.exists():
        changes_path.write_text("")
