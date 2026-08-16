from __future__ import annotations

import argparse
import difflib
import filecmp
import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from jsonschema import validate

from public_ips.adapters import CloudflareAdapter, GitHubAdapter
from public_ips.changelog import render_changelogs
from public_ips.config import load_provider_configs
from public_ips.diffing import diff_family
from public_ips.http_client import RetryingHttpClient
from public_ips.models import ChangeEvent, FamilyNetworks, ProviderConfig, ProviderSnapshot
from public_ips.rendering import (
    canonical_hash,
    provider_union,
    write_provider_outputs,
    write_root_files,
)


@dataclass
class FileHttpClient:
    fixtures_root: Path

    def get(self, url: str) -> tuple[int, bytes, str | None, str | None, str | None]:
        slug = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
        path = self.fixtures_root / f"{slug}.json"
        if not path.exists():
            raise FileNotFoundError(f"Fixture for URL not found: {url} -> {path.name}")
        payload = json.loads(path.read_text())
        body = json.dumps(payload["body"], separators=(",", ":"), sort_keys=True).encode("utf-8")
        return int(payload["status_code"]), body, str(payload.get("content_type")), None, None


def _adapter_for(config: ProviderConfig) -> GitHubAdapter | CloudflareAdapter:
    if config.adapter == "github_meta":
        return GitHubAdapter(config)
    if config.adapter == "cloudflare_ips":
        return CloudflareAdapter(config)
    raise ValueError(f"Unknown adapter: {config.adapter}")


def _load_existing_ranges(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return cast(dict[str, Any], json.loads(path.read_text()))


def _family_from_json(payload: dict[str, Any]) -> FamilyNetworks:
    from ipaddress import ip_network

    family = FamilyNetworks()
    for cidr in payload.get("ipv4", []):
        family.add(ip_network(str(cidr), strict=True))
    for cidr in payload.get("ipv6", []):
        family.add(ip_network(str(cidr), strict=True))
    return family


def _event_id(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _make_events(
    provider: str,
    when: str,
    old_ranges: dict[str, Any] | None,
    new_snapshot: ProviderSnapshot,
    normalized_hash: str,
) -> list[ChangeEvent]:
    events: list[ChangeEvent] = []
    if old_ranges is None:
        union = provider_union(new_snapshot)
        events.append(
            ChangeEvent(
                schema_version="v1",
                event_id=_event_id(provider, when, "initial_import"),
                event_type="initial_import",
                timestamp_utc=when,
                provider=provider,
                normalized_hash=normalized_hash,
                source_body_hash=new_snapshot.source_body_hash,
                counts={
                    "ipv4": len(union.ipv4),
                    "ipv6": len(union.ipv6),
                    "categories": len(new_snapshot.categories),
                },
            )
        )
        return events

    old_categories = dict(old_ranges.get("categories", {}))
    for category, ranges in sorted(new_snapshot.categories.items()):
        old_family = _family_from_json(old_categories.get(category, {}))
        delta = diff_family(old_family, ranges)
        for cidr in delta["added_ipv4"]:
            events.append(
                ChangeEvent(
                    schema_version="v1",
                    event_id=_event_id(provider, when, category, "ipv4", "added", cidr),
                    event_type="range_change",
                    timestamp_utc=when,
                    provider=provider,
                    normalized_hash=normalized_hash,
                    source_body_hash=new_snapshot.source_body_hash,
                    category=category,
                    ip_family="IPv4",
                    operation="added",
                    cidr=cidr,
                )
            )
        for cidr in delta["removed_ipv4"]:
            events.append(
                ChangeEvent(
                    schema_version="v1",
                    event_id=_event_id(provider, when, category, "ipv4", "removed", cidr),
                    event_type="range_change",
                    timestamp_utc=when,
                    provider=provider,
                    normalized_hash=normalized_hash,
                    source_body_hash=new_snapshot.source_body_hash,
                    category=category,
                    ip_family="IPv4",
                    operation="removed",
                    cidr=cidr,
                )
            )
        for cidr in delta["added_ipv6"]:
            events.append(
                ChangeEvent(
                    schema_version="v1",
                    event_id=_event_id(provider, when, category, "ipv6", "added", cidr),
                    event_type="range_change",
                    timestamp_utc=when,
                    provider=provider,
                    normalized_hash=normalized_hash,
                    source_body_hash=new_snapshot.source_body_hash,
                    category=category,
                    ip_family="IPv6",
                    operation="added",
                    cidr=cidr,
                )
            )
        for cidr in delta["removed_ipv6"]:
            events.append(
                ChangeEvent(
                    schema_version="v1",
                    event_id=_event_id(provider, when, category, "ipv6", "removed", cidr),
                    event_type="range_change",
                    timestamp_utc=when,
                    provider=provider,
                    normalized_hash=normalized_hash,
                    source_body_hash=new_snapshot.source_body_hash,
                    category=category,
                    ip_family="IPv6",
                    operation="removed",
                    cidr=cidr,
                )
            )

    old_provider = _family_from_json(old_ranges.get("provider", {}))
    new_provider = provider_union(new_snapshot)
    delta = diff_family(old_provider, new_provider)
    for cidr in delta["added_ipv4"]:
        events.append(
            ChangeEvent(
                schema_version="v1",
                event_id=_event_id(provider, when, "root", "ipv4", "added", cidr),
                event_type="range_change",
                timestamp_utc=when,
                provider=provider,
                normalized_hash=normalized_hash,
                source_body_hash=new_snapshot.source_body_hash,
                ip_family="IPv4",
                operation="added",
                cidr=cidr,
            )
        )
    for cidr in delta["removed_ipv4"]:
        events.append(
            ChangeEvent(
                schema_version="v1",
                event_id=_event_id(provider, when, "root", "ipv4", "removed", cidr),
                event_type="range_change",
                timestamp_utc=when,
                provider=provider,
                normalized_hash=normalized_hash,
                source_body_hash=new_snapshot.source_body_hash,
                ip_family="IPv4",
                operation="removed",
                cidr=cidr,
            )
        )
    for cidr in delta["added_ipv6"]:
        events.append(
            ChangeEvent(
                schema_version="v1",
                event_id=_event_id(provider, when, "root", "ipv6", "added", cidr),
                event_type="range_change",
                timestamp_utc=when,
                provider=provider,
                normalized_hash=normalized_hash,
                source_body_hash=new_snapshot.source_body_hash,
                ip_family="IPv6",
                operation="added",
                cidr=cidr,
            )
        )
    for cidr in delta["removed_ipv6"]:
        events.append(
            ChangeEvent(
                schema_version="v1",
                event_id=_event_id(provider, when, "root", "ipv6", "removed", cidr),
                event_type="range_change",
                timestamp_utc=when,
                provider=provider,
                normalized_hash=normalized_hash,
                source_body_hash=new_snapshot.source_body_hash,
                ip_family="IPv6",
                operation="removed",
                cidr=cidr,
            )
        )

    return events


def _validate_json_against_schema(schema_path: Path, payload_path: Path) -> None:
    if not schema_path.exists() or not payload_path.exists():
        return
    schema = json.loads(schema_path.read_text())
    payload = json.loads(payload_path.read_text())
    validate(instance=payload, schema=schema)


def run_generation(
    root: Path, *, fixtures: Path | None = None, timestamp: str | None = None
) -> int:
    configs = load_provider_configs(root)
    if not configs:
        raise ValueError("No provider configs found")

    client = FileHttpClient(fixtures) if fixtures else RetryingHttpClient()
    now = timestamp or datetime.now(UTC).replace(microsecond=0).isoformat()
    existing_manifest = _load_existing_ranges(root / "manifest.json")

    tmp_dir = Path(tempfile.mkdtemp(prefix="public-ips-"))
    provider_rows: dict[str, dict[str, Any]] = {}
    all_csv_rows: list[dict[str, str | int | None]] = []
    all_search_entries: list[dict[str, Any]] = []
    all_events: list[ChangeEvent] = []

    try:
        for config in configs:
            adapter = _adapter_for(config)
            raw = adapter.fetch(client)
            snapshot = adapter.extract(raw)
            normalized = canonical_hash(snapshot)
            existing_path = root / config.output_dir / "ranges.json"
            existing = _load_existing_ranges(existing_path)
            previous_hash = existing.get("normalized_data_sha256") if existing else None
            first_observed = (
                str(existing.get("first_observed_at", now))
                if existing and previous_hash == normalized
                else now
            )
            generated_at = (
                str(existing.get("generated_at", now))
                if existing and previous_hash == normalized
                else now
            )
            if existing and previous_hash == normalized:
                snapshot.source_body_hash = str(
                    existing.get("source_body_sha256", snapshot.source_body_hash)
                )

            (tmp_dir / config.output_dir).mkdir(parents=True, exist_ok=True)
            data, rows, search_entries = write_provider_outputs(
                tmp_dir, snapshot, first_observed, generated_at
            )
            provider_rows[config.provider_id] = data
            all_csv_rows.extend(rows)
            all_search_entries.extend(search_entries)

            if previous_hash != normalized:
                all_events.extend(
                    _make_events(config.provider_id, now, existing, snapshot, normalized)
                )

        root_generated_at = (
            str(existing_manifest.get("generated_at", now))
            if existing_manifest and not all_events
            else now
        )
        write_root_files(
            tmp_dir,
            provider_rows,
            all_csv_rows,
            all_search_entries,
            all_events,
            root_generated_at,
        )
        render_changelogs(tmp_dir)

        _validate_json_against_schema(
            root / "schemas" / "manifest.v1.json", tmp_dir / "manifest.json"
        )
        for ranges_json in tmp_dir.glob("*/ranges.json"):
            _validate_json_against_schema(root / "schemas" / "ranges.v1.json", ranges_json)

        for generated in tmp_dir.iterdir():
            target = root / generated.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            if generated.is_dir():
                shutil.copytree(generated, target)
            else:
                shutil.copy2(generated, target)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return 0


def _collect_diffs(cmp_obj: Any, rel_path: str = "") -> list[tuple[str, str]]:
    """Recursively collect (status, relative_path) pairs describing dircmp differences."""
    diffs: list[tuple[str, str]] = []
    for name in sorted(cmp_obj.left_only):
        diffs.append(("removed", f"{rel_path}{name}"))
    for name in sorted(cmp_obj.right_only):
        diffs.append(("added", f"{rel_path}{name}"))
    for name in sorted(cmp_obj.diff_files):
        diffs.append(("changed", f"{rel_path}{name}"))
    for name, sub_cmp in sorted(cmp_obj.subdirs.items()):
        diffs.extend(_collect_diffs(sub_cmp, f"{rel_path}{name}/"))
    return diffs


def _print_file_diff(committed_path: Path, generated_path: Path, rel_path: str) -> None:
    try:
        old_lines = committed_path.read_text().splitlines(keepends=True)
        new_lines = generated_path.read_text().splitlines(keepends=True)
    except (UnicodeDecodeError, OSError):
        print(f"    (binary or unreadable file, unable to show diff for {rel_path})")
        return
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"committed/{rel_path}",
        tofile=f"generated/{rel_path}",
    )
    diff_text = "".join(diff)
    if diff_text:
        print(diff_text)
    else:
        print(f"    (no textual diff found for {rel_path})")


def _check_mode(root: Path, fixtures: Path | None, timestamp: str | None) -> int:
    def has_diff(cmp_obj: Any) -> bool:
        if cmp_obj.left_only or cmp_obj.right_only or cmp_obj.diff_files:
            return True
        return any(has_diff(sub) for sub in cmp_obj.subdirs.values())

    with tempfile.TemporaryDirectory(prefix="public-ips-check-") as tmp:
        tmp_root = Path(tmp)
        for item in root.iterdir():
            if item.name == ".git":
                continue
            target = tmp_root / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        run_generation(tmp_root, fixtures=fixtures, timestamp=timestamp)
        left = filecmp.dircmp(root, tmp_root, ignore=[".git", ".pytest_cache", "__pycache__"])
        if has_diff(left):
            print("Generated files are stale. Run generation and commit changes.")
            diffs = _collect_diffs(left)
            for status, rel_path in diffs:
                print(f"  {status}: {rel_path}")
            print()
            for status, rel_path in diffs:
                if status != "changed":
                    continue
                print(f"--- diff for {rel_path} ---")
                _print_file_diff(root / rel_path, tmp_root / rel_path, rel_path)
            return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="public-ips")
    parser.add_argument("command", choices=["generate", "check"])
    parser.add_argument("--fixtures", type=str, default=None)
    parser.add_argument("--timestamp", type=str, default=None)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    fixtures = Path(args.fixtures) if args.fixtures else None

    if args.command == "generate":
        raise SystemExit(run_generation(root, fixtures=fixtures, timestamp=args.timestamp))
    raise SystemExit(_check_mode(root, fixtures=fixtures, timestamp=args.timestamp))


if __name__ == "__main__":
    main()
