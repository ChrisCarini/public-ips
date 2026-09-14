from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from public_ips.cli import run_generation
from public_ips.config import load_provider_configs
from public_ips.site import main, publish_site


def _entry(**overrides: object) -> dict[str, object]:
    return {
        "provider": "example.com",
        "category": None,
        "ip_family": "ipv4",
        "cidr": "1.1.1.0/24",
        "path": "example.com/ipv4.txt",
        "line": 1,
        "source_url": "https://example.com/ips",
        "anchor": "unused-anchor",
        **overrides,
    }


def _source(root: Path, entries: list[dict[str, object]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "search-index.json").write_text(
        json.dumps({"schema_version": "v1", "entries": entries})
    )
    (root / "ranges.csv").write_text(
        "provider,category,ip_family,cidr,source_url,first_observed_at\n"
    )
    provider = root / "example.com"
    provider.mkdir(exist_ok=True)
    (provider / "ipv4.txt").write_bytes(b"1.1.1.0/24\r\n8.8.8.0/24\r\n")
    (provider / "all.txt").write_bytes(b"1.1.1.0/24\r\n8.8.8.0/24\r\n")


def _decode(index: dict[str, Any]) -> list[dict[str, object]]:
    assert set(index) == {"schema_version", "strings", "entries"}
    assert index["schema_version"] == "v2"
    strings = index["strings"]
    assert all(isinstance(value, str) for value in strings)
    assert len(strings) == len(set(strings))
    decoded = []
    for row in index["entries"]:
        assert len(row) == 7
        assert all(type(value) is int for value in row)
        assert row[2] in (4, 6)
        decoded.append(
            {
                "provider": strings[row[0]],
                "category": None if row[1] == -1 else strings[row[1]],
                "ip_family": f"ipv{row[2]}",
                "cidr": strings[row[3]],
                "path": strings[row[4]],
                "line": row[5],
                "source_url": strings[row[6]],
            }
        )
    return decoded


def _assert_snapshot(root: Path, output: Path) -> None:
    original = json.loads((root / "search-index.json").read_text())
    deployed = json.loads((output / "search-index.json").read_text())
    decoded = _decode(deployed)
    assert decoded == [
        {key: value for key, value in entry.items() if key != "anchor"}
        for entry in original["entries"]
    ]
    expected_lists = set()
    for entry in decoded:
        path = Path(str(entry["path"]))
        for relative in (path, path.with_name("all.txt")):
            expected_lists.add(relative)
            assert (output / relative).read_bytes() == (root / relative).read_bytes()
        assert (output / path).read_text().splitlines()[int(str(entry["line"])) - 1] == (
            entry["cidr"]
        )
    assert {path.relative_to(output) for path in output.rglob("*.txt")} == expected_lists


def test_publish_roundtrip_and_exact_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    output = root / "site" / "dist"
    entries = [
        _entry(),
        _entry(cidr="8.8.8.0/24", line=2),
        _entry(category="edge", path="example.com/edge/ipv4.txt"),
        _entry(ip_family="ipv6", cidr="2606:4700::/32", path="example.com/ipv6.txt"),
    ]
    _source(root, entries)
    category = root / "example.com" / "edge"
    category.mkdir()
    (category / "ipv4.txt").write_bytes(b"1.1.1.0/24\n")
    (category / "all.txt").write_bytes(b"1.1.1.0/24\n")
    (root / "example.com" / "ipv6.txt").write_bytes(b"2606:4700::/32\n")
    (root / "example.com" / "all.txt").write_bytes(
        b"1.1.1.0/24\r\n8.8.8.0/24\r\n2606:4700::/32\r\n"
    )
    (root / "example.com" / "unreferenced.txt").write_text("not published")
    (root / "private.json").write_text("not published")
    output.mkdir(parents=True)
    (output / "index.html").write_text("frontend")
    original_index = (root / "search-index.json").read_bytes()

    assert main(["--root", str(root), "--output", str(output)]) == 0

    _assert_snapshot(root, output)
    compact = json.loads((output / "search-index.json").read_text())
    assert compact["entries"][0][3] == compact["entries"][2][3]
    assert len({row[0] for row in compact["entries"]}) == 1
    assert len({row[6] for row in compact["entries"]}) == 1
    assert (root / "search-index.json").read_bytes() == original_index
    assert (output / "index.html").read_text() == "frontend"
    assert (output / "ranges.csv").read_bytes() == (root / "ranges.csv").read_bytes()
    assert not (output / "private.json").exists()
    assert len((output / "search-index.json").read_bytes()) < len(original_index)


def test_publish_all_configured_providers_from_fixtures(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    root = tmp_path / "repo"
    root.mkdir()
    for directory in ("providers", "schemas"):
        shutil.copytree(repo / directory, root / directory)
    assert run_generation(
        root, fixtures=repo / "tests" / "fixtures", timestamp="2026-01-02T14:35:22+00:00"
    ) == 0
    output = root / "site" / "dist"

    publish_site(root, output)

    _assert_snapshot(root, output)
    decoded = _decode(json.loads((output / "search-index.json").read_text()))
    expected = {config.provider_id for config in load_provider_configs(root)}
    assert len(expected) >= 13
    assert {entry["provider"] for entry in decoded} == expected
    assert (output / "ranges.csv").read_bytes() == (root / "ranges.csv").read_bytes()
    assert not (output / "providers").exists()
    assert not (output / "schemas").exists()
    assert not list(output.rglob("ranges.json"))


@pytest.mark.parametrize(
    "path",
    ["../outside.txt", "/outside.txt", "example.com/../outside.txt", r"..\outside.txt",
     "C:/outside.txt", "example.com//ipv4.txt", "./example.com/ipv4.txt", "private.json", ""],
)
def test_reject_unsafe_list_paths(tmp_path: Path, path: str) -> None:
    root = tmp_path / "repo"
    output = root / "site" / "dist"
    _source(root, [_entry(path=path)])
    with pytest.raises(ValueError, match="Invalid list path"):
        publish_site(root, output)
    assert not output.exists()


@pytest.mark.parametrize(
    ("side", "relative"),
    [
        ("source", "example.com/ipv4.txt"),
        ("source", "example.com/all.txt"),
        ("source", "example.com"),
        ("source", "search-index.json"),
        ("output", "example.com/ipv4.txt"),
        ("output", "example.com/all.txt"),
        ("output", "example.com"),
        ("output", "search-index.json"),
    ],
)
def test_reject_symlink_escape(tmp_path: Path, side: str, relative: str) -> None:
    root = tmp_path / "repo"
    output = root / "site" / "dist"
    _source(root, [_entry()])
    outside = tmp_path / "outside"
    outside.mkdir()
    protected = outside / "protected.txt"
    protected.write_text("unchanged")
    link = (root if side == "source" else output) / relative
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_dir():
        shutil.rmtree(link)
    else:
        link.unlink(missing_ok=True)
    link.symlink_to(outside if relative == "example.com" else protected)

    with pytest.raises(ValueError, match="Path escapes"):
        publish_site(root, output)
    assert protected.read_text() == "unchanged"
    assert list(outside.iterdir()) == [protected]


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        ("example.com/ipv4.txt", "Missing source list"),
        ("example.com/all.txt", "Missing source list"),
        ("ranges.csv", "Missing generated CSV"),
    ],
)
def test_fail_on_missing_snapshot_file(tmp_path: Path, relative: str, message: str) -> None:
    root = tmp_path / "repo"
    _source(root, [_entry()])
    (root / relative).unlink()
    output = root / "site" / "dist"
    with pytest.raises(ValueError, match=message):
        publish_site(root, output)
    assert not output.exists()


def test_reject_output_overwriting_source(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _source(root, [_entry()])
    original = (root / "search-index.json").read_bytes()
    for output in (root, root.parent):
        with pytest.raises(ValueError, match="Output must not"):
            publish_site(root, output)
    assert (root / "search-index.json").read_bytes() == original


def test_empty_index(tmp_path: Path) -> None:
    _source(tmp_path, [])
    output = tmp_path / "dist"
    publish_site(tmp_path, output)
    assert json.loads((output / "search-index.json").read_text()) == {
        "schema_version": "v2", "strings": [], "entries": [],
    }


@pytest.mark.parametrize(
    "overrides",
    [{"line": 0}, {"line": True}, {"ip_family": "ipv5"}, {"category": 42}, {"provider": None}],
)
def test_reject_invalid_entries(tmp_path: Path, overrides: dict[str, object]) -> None:
    _source(tmp_path, [_entry(**overrides)])
    with pytest.raises(ValueError):
        publish_site(tmp_path, tmp_path / "dist")


def test_cli_reports_invalid_index(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "search-index.json").write_text('{"schema_version":"v2","entries":[]}')
    with pytest.raises(SystemExit) as error:
        main(["--root", str(tmp_path), "--output", str(tmp_path / "dist")])
    assert error.value.code == 1
    assert "Site publishing failed: Expected a v1 search index" in capsys.readouterr().err
