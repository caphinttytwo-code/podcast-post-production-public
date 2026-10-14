#!/usr/bin/env python3
"""Retime an SRT after approved deletions on the parent-video timeline."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args, child_output, distinct_output


from pathlib import Path as _PackagePath
import sys as _package_sys
_PACKAGE_ROOT = _PackagePath(__file__).resolve().parents[3]
if str(_PACKAGE_ROOT) not in _package_sys.path:
    _package_sys.path.insert(0, str(_PACKAGE_ROOT))
from shared.files import sha256 as sha256


import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path


TIME_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$")


@dataclass
class Cue:
    number: int
    start: float
    end: float
    lines: list[str]


def seconds(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).replace(",", ".").split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    raise ValueError(f"invalid timestamp: {value}")


def parse_clock(value: str) -> float:
    match = TIME_RE.match(value.strip())
    if not match:
        raise ValueError(f"invalid SRT timestamp: {value}")
    hours, minutes, secs, millis = map(int, match.groups())
    return hours * 3600 + minutes * 60 + secs + millis / 1000


def clock(value: float) -> str:
    millis = max(0, round(value * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def parse_srt(text: str) -> list[Cue]:
    cues = []
    blocks = re.split(r"\n\s*\n", text.strip()) if text.strip() else []
    for block_index, block in enumerate(blocks, 1):
        lines = block.splitlines()
        if len(lines) < 3 or " --> " not in lines[1]:
            raise ValueError(f"invalid SRT block {block_index}")
        start, end = lines[1].split(" --> ", 1)
        cue = Cue(int(lines[0]), parse_clock(start), parse_clock(end), lines[2:])
        if cue.end <= cue.start:
            raise ValueError(f"cue {cue.number} has non-positive duration")
        cues.append(cue)
    return cues


def normalize_deletions(payload) -> list[tuple[float, float, str]]:
    if isinstance(payload, dict):
        payload = payload.get("deletions", [])
    deletions = []
    for index, item in enumerate(payload, 1):
        start, end = seconds(item["start"]), seconds(item["end"])
        if start < 0 or end <= start:
            raise ValueError(f"invalid deletion {index}")
        deletions.append((start, end, str(item.get("reason", ""))))
    deletions.sort()
    for previous, current in zip(deletions, deletions[1:]):
        if current[0] < previous[1]:
            raise ValueError("deletion intervals overlap")
    return deletions


def retime(cues: list[Cue], deletions: list[tuple[float, float, str]]):
    kept, removed = [], []
    for cue in cues:
        matching = next((item for item in deletions if cue.start < item[1] and cue.end > item[0]), None)
        if matching:
            start, end, _ = matching
            if cue.start >= start and cue.end <= end:
                removed.append(cue.number)
                continue
            raise ValueError(
                f"cue {cue.number} crosses deletion boundary {clock(start)}..{clock(end)}; revise it manually"
            )
        shift = sum(end - start for start, end, _ in deletions if end <= cue.start)
        kept.append(Cue(len(kept) + 1, cue.start - shift, cue.end - shift, cue.lines))
    return kept, removed


def serialize(cues: list[Cue]) -> str:
    return "\n\n".join(
        f"{cue.number}\n{clock(cue.start)} --> {clock(cue.end)}\n" + "\n".join(cue.lines)
        for cue in cues
    ) + ("\n" if cues else "")




def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--edits", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    protect_output_args(args)
    if args.output.resolve() == args.input.resolve():
        raise ValueError("output must not overwrite input")
    if args.output.exists() or args.report.exists():
        raise FileExistsError("output/report already exists; use a new version path")
    cues = parse_srt(args.input.read_text(encoding="utf-8-sig"))
    deletions = normalize_deletions(json.loads(args.edits.read_text(encoding="utf-8")))
    result, removed = retime(cues, deletions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    distinct_output(args.report, args.output)
    temporary = child_output(args.output.parent, f".{args.output.name}.tmp", args.input, args.edits, args.report)
    temporary.write_text(serialize(result), encoding="utf-8")
    os.replace(temporary, args.output)
    report = {
        "input": str(args.input), "input_sha256": sha256(args.input),
        "output": str(args.output), "output_sha256": sha256(args.output),
        "input_cues": len(cues), "output_cues": len(result), "removed_cues": removed,
        "deleted_seconds": sum(end - start for start, end, _ in deletions),
        "requires_human_review": True, "release_ready": False,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
