#!/usr/bin/env python3
"""Inventory or delete recognized conform intermediates while preserving named media."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args, outside_package, distinct_output


import argparse
import json
from pathlib import Path


PROCESS_SUFFIXES = {".mp4", ".mov", ".mkv", ".mp3", ".wav", ".pcm", ".aac", ".m4a", ".npy"}
CACHE_DIRECTORY_NAMES = {"audio", "chunks", "features", "previews", "asr-raw"}


def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}TB"


def write_placeholders(root: Path, sources: list[Path], finals: list[Path]) -> None:
    def safe_placeholder(path):
        if path.is_symlink() or not inside(path, root):
            raise ValueError('Refusing linked or external placeholder path')
        outside_package(path)
        distinct_output(path, *sources, *finals)
        return path
    source_lines = ["# Protected source media", "", "These files remain until the user manually moves them:", ""]
    source_lines += [f"- `{path.name}`" for path in sources]
    source_lines += ["", "Do not delete, move, rename, overwrite, or auto-clean these files.", ""]
    safe_placeholder(root / "SOURCE_FILES_PLACEHOLDER.md").write_text("\n".join(source_lines), encoding="utf-8")
    delivery = root / "delivery"
    safe_placeholder(delivery).mkdir(parents=True, exist_ok=True)
    final_lines = ["# Protected final media", "", "These approved finals remain until the user manually moves them:", ""]
    final_lines += [f"- `{path.name}`" for path in finals]
    final_lines += ["", "Do not delete, move, rename, overwrite, or auto-clean these files.", ""]
    safe_placeholder(delivery / "PLACEHOLDER.md").write_text("\n".join(final_lines), encoding="utf-8")
    cache_directories = [root / "versions" / "videos"]
    work = root / "work"
    if work.exists():
        cache_directories.extend(
            path for path in work.rglob("*") if path.is_dir() and not path.is_symlink() and inside(path, root) and path.name in CACHE_DIRECTORY_NAMES
        )
    for directory in sorted(set(cache_directories)):
        safe_placeholder(directory).mkdir(parents=True, exist_ok=True)
        safe_placeholder(directory / "PLACEHOLDER.md").write_text(
            "# Regenerable process directory\n\nLarge process media and caches were cleared after approval. Keep this placeholder.\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--source", action="append", default=[], type=Path, required=True)
    parser.add_argument("--final", action="append", default=[], type=Path, required=True)
    parser.add_argument("--delete-extra", action="append", default=[], type=Path,
                        help="Exact user-authorized project-contained file, e.g. an older audio edition")
    parser.add_argument("--execute", action="store_true", help="Delete after reviewing the default dry-run")
    args = parser.parse_args()
    protect_output_args(args)
    root = args.project_root.resolve()
    sources = [path.resolve() for path in args.source]
    finals = [path.resolve() for path in args.final]
    protected = set(sources + finals)
    for path in protected:
        if not path.is_file() or not inside(path, root):
            raise SystemExit(f"Protected path is missing or outside project: {path}")
    candidates = set()
    for relative in ("work", "versions/videos"):
        base = root / relative
        if not base.exists() or base.is_symlink() or not inside(base, root):
            continue
        for path in base.rglob("*"):
            is_process = (path.suffix.lower() in PROCESS_SUFFIXES or
                          path.name.endswith(".filter.txt") or
                          path.name.startswith("concat-") or path.name == "concat.txt")
            if path.is_file() and not path.is_symlink() and inside(path, root) and is_process and path.resolve() not in protected:
                candidates.add(path.resolve())
        for path in base.rglob("__pycache__"):
            if path.is_dir() and not path.is_symlink() and inside(path, root):
                candidates.update(item.resolve() for item in path.rglob("*") if item.is_file() and not item.is_symlink() and inside(item, root))
    for extra in args.delete_extra:
        path = extra.resolve()
        if extra.is_symlink() or not inside(path, root) or path in protected:
            raise SystemExit(f"Refusing extra deletion outside project or protected: {path}")
        if path.is_file():
            candidates.add(path)
    ordered = sorted(candidates)
    total = sum(path.stat().st_size for path in ordered)
    report = {"mode": "execute" if args.execute else "dry-run", "project_root": str(root),
              "protected": [str(path) for path in sorted(protected)],
              "delete_count": len(ordered), "delete_bytes": total, "delete_size": human_size(total),
              "delete": [str(path) for path in ordered]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.execute:
        return
    for path in ordered:
        if path.is_symlink() or not inside(path, root) or path.resolve() in protected:
            raise RuntimeError('Cleanup target changed or became unsafe')
        path.unlink(missing_ok=True)
    write_placeholders(root, sources, finals)
    missing = [str(path) for path in protected if not path.is_file()]
    if missing:
        raise RuntimeError(f"Protected files missing after cleanup: {missing}")
    print(json.dumps({"cleanup_complete": True, "deleted_size": human_size(total)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
