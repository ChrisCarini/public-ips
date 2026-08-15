from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def render_changelogs(root: Path) -> None:
    events = _load_events(root / "changes.jsonl")
    by_provider: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_provider[str(event["provider"])].append(event)

    root_lines = ["# Changelog", ""]
    for provider, provider_events in sorted(by_provider.items()):
        _render_provider(root, provider, provider_events)

    grouped = _group(events)
    for day in sorted(grouped.keys(), reverse=True):
        root_lines.append(f"## {day}")
        root_lines.append("")
        for timestamp, bucket in sorted(grouped[day].items(), reverse=True):
            root_lines.append(f"### {timestamp}")
            root_lines.append("")
            for event in bucket:
                root_lines.append(f"- {_render_line(event, link_provider=True)}")
            root_lines.append("")

    (root / "CHANGELOG.md").write_text("\n".join(root_lines).rstrip() + "\n")


def _render_provider(root: Path, provider: str, events: list[dict[str, Any]]) -> None:
    lines = [f"# Changelog - {provider}", ""]
    grouped = _group(events)
    for day in sorted(grouped.keys(), reverse=True):
        lines.append(f"## {day}")
        lines.append("")
        for timestamp, bucket in sorted(grouped[day].items(), reverse=True):
            lines.append(f"### {timestamp}")
            lines.append("")
            for event in bucket:
                lines.append(f"- {_render_line(event)}")
            lines.append("")
    (root / provider / "CHANGELOG.md").write_text("\n".join(lines).rstrip() + "\n")


def _group(events: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for event in events:
        ts = str(event["timestamp_utc"])
        day, time = ts.split("T", 1)
        grouped[day][time.replace("+00:00", "Z")].append(event)
    return grouped


def _render_line(event: dict[str, Any], *, link_provider: bool = False) -> str:
    provider = str(event["provider"])
    prefix = f"[{provider}](./{provider}/CHANGELOG.md): " if link_provider else ""
    if event["event_type"] == "initial_import":
        counts = event.get("counts", {})
        return (
            f"{prefix}Initial import with {counts.get('ipv4', 0)} IPv4 ranges, "
            f"{counts.get('ipv6', 0)} IPv6 ranges, and {counts.get('categories', 0)} categories."
        )
    op = "Added" if event.get("operation") == "added" else "Removed"
    cidr = f"`{event.get('cidr')}`"
    fam = event.get("ip_family")
    category = event.get("category")
    if category:
        return (
            f"{prefix}{op} {cidr} to `{category}` ({fam})."
            if op == "Added"
            else f"{prefix}{op} {cidr} from `{category}` ({fam})."
        )
    return f"{prefix}{op} {cidr} ({fam})."
