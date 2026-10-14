#!/usr/bin/env python3
"""Compare two current inventory manifests by member set and file evidence."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args


import argparse
import json
from pathlib import Path


def index(payload: dict) -> dict:
    return {(item["root_id"], item["relative_path"]): item for item in payload.get("records", [])}


def fingerprint(item: dict):
    if item.get("sha256"):
        return ("sha256", item["sha256"], item.get("size"))
    return ("metadata", item.get("size"), item.get("mtime_ns"))


def compare(before: dict, after: dict) -> dict:
    left, right = index(before), index(after)
    added_keys = sorted(set(right) - set(left))
    removed_keys = sorted(set(left) - set(right))
    common = sorted(set(left) & set(right))
    modified_keys = [key for key in common if fingerprint(left[key]) != fingerprint(right[key])]
    unchanged_keys = [key for key in common if key not in set(modified_keys)]
    pack = lambda keys: [{"root_id": key[0], "relative_path": key[1]} for key in keys]
    return {
        "schema_version": 1, "added": pack(added_keys), "removed": pack(removed_keys),
        "modified": pack(modified_keys), "unchanged": pack(unchanged_keys),
        "counts": {"added": len(added_keys), "removed": len(removed_keys), "modified": len(modified_keys), "unchanged": len(unchanged_keys)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    protect_output_args(args)
    report = compare(
        json.loads(args.before.read_text(encoding="utf-8")),
        json.loads(args.after.read_text(encoding="utf-8")),
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
