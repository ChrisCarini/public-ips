from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from public_ips.rendering import ROOT_CSV_NAME, ROOT_INDEX_NAME


def _within(base: Path, relative: Path) -> Path:
    path = base / relative
    if not path.resolve().is_relative_to(base):
        raise ValueError(f"Path escapes {base}: {relative}")
    return path


def _list_path(value: object) -> Path:
    if (
        not isinstance(value, str)
        or "\\" in value
        or ":" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError(f"Invalid list path: {value!r}")
    path = Path(value)
    if path.is_absolute() or path.suffix != ".txt":
        raise ValueError(f"Invalid list path: {value!r}")
    return path


def publish_site(root: Path, output: Path) -> None:
    """Publish a compact index and its exact list snapshot, without changing source data."""
    root = root.resolve()
    output = output.resolve()
    if root.is_relative_to(output):
        raise ValueError("Output must not contain or replace the source root")
    index_path = _within(root, Path(ROOT_INDEX_NAME))
    with index_path.open(encoding="utf-8") as stream:
        index = json.load(stream)
    if (
        not isinstance(index, dict)
        or index.get("schema_version") != "v1"
        or not isinstance(index.get("entries"), list)
    ):
        raise ValueError("Expected a v1 search index with an entries array")

    strings: list[str] = []
    string_ids: dict[str, int] = {}
    entries: list[list[int]] = []
    lists: set[Path] = set()

    def intern(value: object) -> int:
        if not isinstance(value, str):
            raise ValueError(f"Expected a string, got {value!r}")
        if value not in string_ids:
            string_ids[value] = len(strings)
            strings.append(value)
        return string_ids[value]

    for entry in index["entries"]:
        if not isinstance(entry, dict):
            raise ValueError("Expected a search entry object")
        path = _list_path(entry.get("path"))
        family = entry.get("ip_family")
        line = entry.get("line")
        if family not in ("ipv4", "ipv6") or type(line) is not int or line < 1:
            raise ValueError("Expected an IPv4/IPv6 family and a positive line number")
        category = entry.get("category")
        entries.append(
            [
                intern(entry.get("provider")),
                -1 if category is None else intern(category),
                4 if family == "ipv4" else 6,
                intern(entry.get("cidr")),
                intern(entry.get("path")),
                line,
                intern(entry.get("source_url")),
            ]
        )
        lists.update((path, path.with_name("all.txt")))

    # Validate every source and destination before publishing any files.
    copies: list[tuple[Path, Path]] = []
    for relative in sorted(lists):
        source = _within(root, relative)
        destination = _within(output, relative)
        if source.resolve().is_relative_to(output):
            raise ValueError(f"Source list is inside the output: {relative}")
        if not source.is_file():
            raise ValueError(f"Missing source list: {relative}")
        copies.append((source, destination))
    # The combined CSV is a deploy-only download; it is generated, never committed.
    csv_source = _within(root, Path(ROOT_CSV_NAME))
    if not csv_source.is_file():
        raise ValueError(f"Missing generated CSV: {ROOT_CSV_NAME} (run 'public-ips generate')")
    copies.append((csv_source, _within(output, Path(ROOT_CSV_NAME))))
    destination_index = _within(output, Path(ROOT_INDEX_NAME))
    for source, destination in copies:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    output.mkdir(parents=True, exist_ok=True)
    with destination_index.open("w", encoding="utf-8") as stream:
        json.dump(
            {"schema_version": "v2", "strings": strings, "entries": entries},
            stream,
            separators=(",", ":"),
        )
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish deploy-only search data and list files")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("site/dist"))
    args = parser.parse_args(argv)
    try:
        publish_site(args.root, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Site publishing failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
