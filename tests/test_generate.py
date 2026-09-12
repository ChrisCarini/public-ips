from __future__ import annotations

import json
import shutil
from pathlib import Path

from public_ips.cli import run_generation

FIXED_TS = "2026-01-02T14:35:22+00:00"


def _copy_repo_tree(src: Path, dst: Path) -> None:
    for item in src.iterdir():
        if item.name in {".git", ".pytest_cache", "__pycache__"}:
            continue
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def test_generate_from_fixtures(tmp_path: Path) -> None:
    src_root = Path(__file__).resolve().parents[1]
    root = tmp_path / "repo"
    root.mkdir()
    _copy_repo_tree(src_root, root)

    assert run_generation(root, fixtures=root / "tests" / "fixtures", timestamp=FIXED_TS) == 0

    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["schema_version"] == "v1"
    providers = manifest["providers"]
    assert {
        "amazonaws.com",
        "anthropic.com",
        "apple.com",
        "azure.microsoft.com",
        "bing.com",
        "cloud.google.com",
        "cloudflare.com",
        "facebook.com",
        "github.com",
        "googlebot.com",
        "openai.com",
        "oracle.com",
        "perplexity.com",
        "pingdom.com",
    } <= providers.keys()
    assert providers["amazonaws.com"]["categories"]["amazon"]["counts"] == {
        "ipv4": 1,
        "ipv6": 1,
    }
    assert providers["azure.microsoft.com"]["categories"]["azurecloud"]["counts"] == {
        "ipv4": 1,
        "ipv6": 1,
    }
    assert providers["cloud.google.com"]["categories"]["google_cloud"]["counts"] == {
        "ipv4": 1,
        "ipv6": 1,
    }
    github_categories = providers["github.com"]["categories"]
    assert {
        "actions_macos",
        "codespaces",
        "copilot",
        "github_enterprise_importer",
    } <= github_categories.keys()
    assert github_categories["actions_macos"]["counts"] == {"ipv4": 8, "ipv6": 0}
    assert github_categories["codespaces"]["counts"] == {"ipv4": 191, "ipv6": 0}
    assert github_categories["copilot"]["counts"] == {"ipv4": 15, "ipv6": 2}

    gh_all = (root / "github.com" / "all.txt").read_text().splitlines()
    gh_v4 = (root / "github.com" / "ipv4.txt").read_text().splitlines()
    gh_v6 = (root / "github.com" / "ipv6.txt").read_text().splitlines()
    assert gh_all == gh_v4 + gh_v6

    cf_children = [p.name for p in (root / "cloudflare.com").iterdir() if p.is_dir()]
    assert cf_children == []


def test_generate_preserves_changelog_history_when_no_new_events(tmp_path: Path) -> None:
    src_root = Path(__file__).resolve().parents[1]
    root = tmp_path / "repo"
    root.mkdir()
    _copy_repo_tree(src_root, root)

    assert run_generation(root, fixtures=root / "tests" / "fixtures", timestamp=FIXED_TS) == 0
    first_changes = (root / "changes.jsonl").read_text()
    first_root_changelog = (root / "CHANGELOG.md").read_text()
    first_provider_changelog = (root / "github.com" / "CHANGELOG.md").read_text()
    assert first_changes.strip()
    assert "## " in first_root_changelog
    assert "## " in first_provider_changelog

    assert run_generation(root, fixtures=root / "tests" / "fixtures", timestamp=FIXED_TS) == 0

    assert (root / "changes.jsonl").read_text() == first_changes
    assert (root / "CHANGELOG.md").read_text() == first_root_changelog
    assert (root / "github.com" / "CHANGELOG.md").read_text() == first_provider_changelog
