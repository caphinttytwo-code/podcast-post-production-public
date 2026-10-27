#!/usr/bin/env python3
"""Verify source and backup inventories using hashes from current file reads."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args


import argparse
import json
from pathlib import Path


def unique_by_relative(payload: dict) -> dict:
    result = {}
    for item in payload.get("records", []):
        key = item["relative_path"]
        if key in result:
            raise ValueError(f"duplicate relative path across roots: {key}")
        result[key] = item
    return result


def verify(source: dict, backup: dict) -> dict:
    source_index, backup_index = unique_by_relative(source), unique_by_relative(backup)
    records = []
    for relative, item in sorted(source_index.items()):
        candidate = backup_index.get(relative)
        status = "missing"
        if candidate:
            if item.get("hash_current_read") and candidate.get("hash_current_read") and item.get("sha256") and item.get("sha256") == candidate.get("sha256"):
                status = "hash_verified"
            elif item.get("size") == candidate.get("size"):
                status = "metadata_only"
            else:
                status = "mismatch"
        records.append({"relative_path": relative, "status": status})
    counts = {status: sum(item["status"] == status for item in records) for status in ("hash_verified", "metadata_only", "mismatch", "missing")}
    return {"schema_version": 1, "records": records, "counts": counts, "all_hash_verified": counts["hash_verified"] == len(records)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    protect_output_args(args)
    report = verify(
        json.loads(args.source.read_text(encoding="utf-8")),
        json.loads(args.backup.read_text(encoding="utf-8")),
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False))
    return 0 if report["all_hash_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
