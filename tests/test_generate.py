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
    assert providers.get("github.com") is not None
    assert providers.get("cloudflare.com") is not None
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
