from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from public_ips.rendering import DEPLOY_ONLY_ROOT_FILES
from public_ips.size_guard import main, oversized_files


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    return root


MB = 1024 * 1024


def _write(root: Path, relative: str, size: int) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"0" * size)


def test_reports_every_oversized_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path)
    _write(root, "search-index.json", 3 * MB)
    _write(root, "example.com/all.txt", 2 * MB)
    _write(root, "small.txt", 16)

    assert main(["--root", str(root), "--limit-bytes", str(2 * MB), "--warn-bytes", str(MB)]) == 1

    message = capsys.readouterr().err
    assert (
        "error: example.com/all.txt is 2.00 MB, at or above GitHub's 2.00 MB file size limit"
        in message
    )
    assert "search-index.json" in message
    assert "small.txt" not in message
    assert "Publish bulky generated data with the Pages build" in message


def test_accepts_files_below_the_limit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path)
    _write(root, "manifest.json", MB)

    assert (
        main(["--root", str(root), "--limit-bytes", str(2 * MB), "--warn-bytes", str(2 * MB)]) == 0
    )
    assert capsys.readouterr().out == ""


def test_warns_without_failing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path)
    _write(root, "manifest.json", 2 * MB)

    assert main(["--root", str(root), "--limit-bytes", str(4 * MB), "--warn-bytes", str(MB)]) == 0
    assert (
        "warning: manifest.json is 2.00 MB, at or above GitHub's 1.00 MB recommended maximum"
        in capsys.readouterr().out
    )


def test_ignores_files_git_will_not_commit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "search-index.json", 2 * MB)
    (root / ".gitignore").write_text("/search-index.json\n")

    assert oversized_files(root, limit=MB) == []


def test_repository_does_not_track_deploy_only_outputs() -> None:
    root = Path(__file__).resolve().parents[1]
    if not (root / ".git").exists():
        pytest.skip("Not a Git checkout")
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--", *DEPLOY_ONLY_ROOT_FILES],
        capture_output=True,
        check=True,
        text=True,
    )
    assert tracked.stdout == ""
