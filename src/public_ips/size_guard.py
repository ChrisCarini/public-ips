from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

# GitHub rejects any pushed blob larger than 100 MB and warns above 50 MB.
GITHUB_LIMIT_BYTES = 100 * 1024 * 1024
GITHUB_WARNING_BYTES = 50 * 1024 * 1024


def committable_files(root: Path) -> list[Path]:
    """Return repository-relative paths Git would include in a commit from ``root``."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=True,
        text=True,
    )
    return [Path(name) for name in result.stdout.split("\0") if name]


def oversized_files(root: Path, *, limit: int = GITHUB_LIMIT_BYTES) -> list[tuple[Path, int]]:
    """Return ``(path, size)`` pairs for committable files of at least ``limit`` bytes."""
    found: list[tuple[Path, int]] = []
    for relative in committable_files(root):
        path = root / relative
        if not path.is_file() or path.is_symlink():
            continue
        size = path.stat().st_size
        if size >= limit:
            found.append((relative, size))
    return sorted(found)


def _megabytes(size: int) -> str:
    return f"{size / (1024 * 1024):.2f} MB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when files that would be committed are too large for GitHub"
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--limit-bytes", type=int, default=GITHUB_LIMIT_BYTES)
    parser.add_argument("--warn-bytes", type=int, default=GITHUB_WARNING_BYTES)
    args = parser.parse_args(argv)

    try:
        # One scan of the working tree covers both thresholds.
        large = oversized_files(args.root, limit=min(args.limit_bytes, args.warn_bytes))
    except (OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Size check failed: {error}\n")

    blocking = [item for item in large if item[1] >= args.limit_bytes]
    warning = [item for item in large if item[1] < args.limit_bytes]

    for path, size in warning:
        print(
            f"warning: {path} is {_megabytes(size)}, above GitHub's "
            f"{_megabytes(args.warn_bytes)} recommended maximum"
        )
    if not blocking:
        return 0

    lines = [
        f"error: {path} is {_megabytes(size)}, above GitHub's {_megabytes(args.limit_bytes)} "
        "file size limit"
        for path, size in blocking
    ]
    lines.append(
        "Pushing these files will be rejected. Publish bulky generated data with the "
        "Pages build (see 'Data outputs' in README.md) or shard it instead of committing it."
    )
    parser.exit(1, "\n".join(lines) + "\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
