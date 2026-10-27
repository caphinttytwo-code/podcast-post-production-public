#!/usr/bin/env python3
"""Create a read-only media-project inventory from an explicit JSON config."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args


from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.media import probe_json
from shared.files import outside_package, child_output


from pathlib import Path as _PackagePath
import sys as _package_sys
_PACKAGE_ROOT = _PackagePath(__file__).resolve().parents[3]
if str(_PACKAGE_ROOT) not in _package_sys.path:
    _package_sys.path.insert(0, str(_PACKAGE_ROOT))
from shared.files import sha256 as sha256


import argparse
import csv
import fnmatch
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


MEDIA_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".m4v", ".avi", ".wav", ".mp3", ".m4a", ".aac", ".flac"
}


def resolved(base: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()




def matches(relative: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns)


def classify(relative: str, rules: dict) -> tuple[str, str | None]:
    for classification in ("retain", "pending", "quarantine"):
        for pattern in rules.get(classification, []):
            if fnmatch.fnmatchcase(relative, pattern):
                return classification, pattern
    return "pending", None


def probe_media(path: Path, ffprobe: str) -> dict:
    try:
        payload = probe_json(path, ffprobe=ffprobe, entries='format=duration,format_name:stream=index,codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels,channel_layout:stream_disposition=default')
    except subprocess.CalledProcessError as exc:
        return {'ok': False, 'error': exc.stderr.strip()[-1000:]}
    return {'ok': True, 'format': payload.get('format', {}), 'streams': payload.get('streams', [])}


def validate_roots(config: dict, base: Path) -> tuple[list[tuple[str, Path]], Path]:
    roots = []
    seen = set()
    home = Path.home().resolve()
    for index, item in enumerate(config.get("roots", []), 1):
        root_id = str(item.get("id", f"root-{index}"))
        root = resolved(base, item["path"])
        if root_id in seen:
            raise ValueError(f"duplicate root id: {root_id}")
        if root == Path(root.anchor) or root == home:
            raise ValueError(f"refusing broad root: {root}")
        if not root.is_dir():
            raise NotADirectoryError(root)
        seen.add(root_id)
        roots.append((root_id, root))
    if not roots:
        raise ValueError("configuration requires at least one explicit root")
    output_dir = outside_package(resolved(base, config["output_dir"]))
    for _, root in roots:
        if output_dir == root or root in output_dir.parents:
            raise ValueError("output_dir must be outside every scanned root")
    return roots, output_dir


def build_inventory(config: dict, base: Path) -> tuple[dict, Path]:
    roots, output_dir = validate_roots(config, base)
    mode = str(config.get("hash_mode", "all"))
    if mode not in {"all", "media", "none"}:
        raise ValueError("hash_mode must be all, media, or none")
    rules = config.get("rules", {})
    ffprobe = str(config.get("ffprobe", "ffprobe"))
    records = []
    for root_id, root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() and not path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            classification, pattern = classify(relative, rules)
            stat = path.lstat()
            is_symlink = path.is_symlink()
            is_media = path.suffix.lower() in MEDIA_EXTENSIONS and not is_symlink
            should_hash = not is_symlink and (mode == "all" or (mode == "media" and is_media))
            record = {
                "root_id": root_id, "root": str(root), "path": str(path), "relative_path": relative,
                "size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "is_symlink": is_symlink,
                "classification": classification, "matched_rule": pattern,
                "sha256": sha256(path) if should_hash else None,
                "hash_current_read": should_hash,
                "media_probe": probe_media(path, ffprobe) if is_media else None,
            }
            records.append(record)
    inventory = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "roots": [{"id": root_id, "path": str(root)} for root_id, root in roots],
        "hash_mode": mode, "records": records,
        "counts": {
            "files": len(records),
            "retain": sum(item["classification"] == "retain" for item in records),
            "quarantine": sum(item["classification"] == "quarantine" for item in records),
            "pending": sum(item["classification"] == "pending" for item in records),
        },
        "total_bytes": sum(item["size"] for item in records),
        "mutation_performed": False,
    }
    return inventory, output_dir


def write_inventory(inventory: dict, output_dir: Path, stem: str, protected_inputs=()) -> tuple[Path, Path]:
    protected = [*protected_inputs, *(Path(item['path']) for item in inventory['records'])]
    json_path = child_output(output_dir, f"{stem}.json", *protected)
    tsv_path = child_output(output_dir, f"{stem}.tsv", *protected)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with tsv_path.open("w", encoding="utf-8", newline="") as handle:
        fields = ["root_id", "relative_path", "size", "mtime_ns", "classification", "matched_rule", "sha256", "is_symlink", "media_probe_ok"]
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fields)
        writer.writeheader()
        for item in inventory["records"]:
            writer.writerow({
                **{field: item.get(field) for field in fields},
                "media_probe_ok": item["media_probe"].get("ok") if item.get("media_probe") else "",
            })
    return json_path, tsv_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--stem", default="inventory")
    args = parser.parse_args()
    protect_output_args(args)
    if Path(args.stem).name != args.stem or args.stem in {".", ".."}:
        raise ValueError('inventory stem must be a plain filename component')
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    inventory, output_dir = build_inventory(config, config_path.parent)
    json_path, tsv_path = write_inventory(inventory, output_dir, args.stem, [config_path])
    print(json.dumps({"json": str(json_path), "tsv": str(tsv_path), **inventory["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
