#!/usr/bin/env python3
"""Align proofread subtitle cue text to character-level ASR timestamp evidence."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args


import argparse
import difflib
import json
from pathlib import Path


PUNCTUATION = set("，。！？；：、,.!?;:（）()《》〈〉“”‘’…—-· \t\r\n|")


def is_content_char(char: str) -> bool:
    return char not in PUNCTUATION


def load_records(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        for key in ("segments", "events", "records", "result"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        raise ValueError("timestamp JSON must be a list or contain segments/events/records")
    records = []
    for index, record in enumerate(payload, 1):
        if not isinstance(record, dict) or not str(record.get("text", "")).strip():
            continue
        try:
            start = float(record["start_ms"])
            end = float(record["end_ms"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"timestamp record {index} requires numeric start_ms/end_ms") from exc
        records.append({"text": str(record["text"]), "start_ms": start, "end_ms": end})
    if not records:
        raise ValueError("timestamp JSON contains no usable speech records")
    return records


def explode_source(records: list[dict]) -> list[dict]:
    chars = []
    for record in records:
        text = record["text"]
        start = record["start_ms"]
        end = max(start, record["end_ms"])
        width = max(end - start, 1.0)
        for index, char in enumerate(text):
            if is_content_char(char):
                chars.append({
                    "char": char,
                    "start": start + width * index / len(text),
                    "end": start + width * (index + 1) / len(text),
                })
    if not chars:
        raise ValueError("timestamp records contain no content characters")
    return chars


def load_cues(path: Path, max_chars: int = 16) -> list[dict]:
    cues = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        visual_lines = line.split("|")
        if len(visual_lines) > 2:
            raise ValueError(f"cue line {line_number} has more than two visual lines")
        if any(len(item) > max_chars for item in visual_lines):
            raise ValueError(f"cue line {line_number} exceeds {max_chars} characters")
        flat = "".join(visual_lines)
        if not any(is_content_char(char) for char in flat):
            raise ValueError(f"cue line {line_number} has no content")
        cues.append({"display": "\n".join(visual_lines), "flat": flat})
    if not cues:
        raise ValueError("cue file contains no usable cues")
    return cues


def align_times(source: list[dict], target_chars: list[str]):
    source_text = "".join(item["char"] for item in source)
    target_text = "".join(target_chars)
    matcher = difflib.SequenceMatcher(None, source_text, target_text, autojunk=False)
    times = [None] * len(target_chars)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(j2 - j1):
                item = source[i1 + offset]
                times[j1 + offset] = (item["start"], item["end"])
            continue
        if tag == "delete":
            continue
        if i2 > i1:
            span_start, span_end = source[i1]["start"], source[i2 - 1]["end"]
        else:
            previous = source[i1 - 1]["end"] if i1 else 0.0
            following = source[i1]["start"] if i1 < len(source) else previous + 80.0 * max(1, j2 - j1)
            span_start, span_end = previous, max(previous, following)
        count = max(1, j2 - j1)
        width = max(span_end - span_start, 1.0)
        for offset in range(j2 - j1):
            times[j1 + offset] = (
                span_start + width * offset / count,
                span_start + width * (offset + 1) / count,
            )
    last_end = 0.0
    for index, value in enumerate(times):
        if value is None:
            value = (last_end, last_end + 40.0)
            times[index] = value
        last_end = max(last_end, value[1])
    return times, matcher.ratio(), matcher.get_opcodes()


def srt_clock(milliseconds: float) -> str:
    total = max(0, int(round(milliseconds)))
    hours, remainder = divmod(total, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def build(records: list[dict], cues: list[dict], duration_ms: float):
    if duration_ms <= 40:
        raise ValueError("video duration must be greater than 40 ms")
    source = explode_source(records)
    target_chars: list[str] = []
    cue_ranges = []
    for cue in cues:
        content = [char for char in cue["flat"] if is_content_char(char)]
        begin = len(target_chars)
        target_chars.extend(content)
        cue_ranges.append((begin, len(target_chars)))
    times, ratio, opcodes = align_times(source, target_chars)
    timed = []
    for cue, (begin, end) in zip(cues, cue_ranges):
        timed.append({
            "start": max(0.0, times[begin][0] - 40.0),
            "end": min(duration_ms - 20.0, times[end - 1][1] + 80.0),
            "display": cue["display"],
        })
    for index in range(len(timed) - 1):
        timed[index]["end"] = min(timed[index]["end"], timed[index + 1]["start"] - 20.0)
    for index, cue in enumerate(timed):
        if cue["end"] <= cue["start"]:
            limit = timed[index + 1]["start"] if index + 1 < len(timed) else duration_ms - 20.0
            cue["end"] = min(limit - 20.0, cue["start"] + 400.0)
        if cue["end"] <= cue["start"]:
            raise ValueError(f"cue {index + 1} cannot be assigned a positive duration")
    blocks = [
        f"{index}\n{srt_clock(cue['start'])} --> {srt_clock(cue['end'])}\n{cue['display']}"
        for index, cue in enumerate(timed, 1)
    ]
    report = {
        "source_content_characters": len(source),
        "target_content_characters": len(target_chars),
        "alignment_ratio": ratio,
        "cue_count": len(timed),
        "first_cue_ms": timed[0]["start"],
        "last_cue_end_ms": timed[-1]["end"],
        "non_equal_alignment_blocks": [
            {"tag": tag, "source": [i1, i2], "target": [j1, j2]}
            for tag, i1, i2, j1, j2 in opcodes if tag != "equal"
        ],
        "requires_human_review": True,
    }
    return "\n\n".join(blocks) + "\n", report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timestamps", required=True, type=Path)
    parser.add_argument("--cues", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--video-duration-ms", type=float, required=True)
    parser.add_argument("--max-chars", type=int, default=16)
    args = parser.parse_args()
    protect_output_args(args)
    srt, report = build(
        load_records(args.timestamps),
        load_cues(args.cues, args.max_chars),
        args.video_duration_ms,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(srt, encoding="utf-8")
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
