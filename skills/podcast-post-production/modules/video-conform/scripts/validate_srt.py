#!/usr/bin/env python3
"""Validate a locked-final SRT against structure, timing, media, and term rules."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args
from shared.media import duration_seconds
from shared.subtitles import Cue, parse_srt as shared_parse_srt

import argparse
import json
import re
import subprocess
import sys
import math
import unicodedata
from dataclasses import dataclass
from pathlib import Path


TIMECODE_RE = re.compile(
    r"^(?P<sh>\d{2}):(?P<sm>\d{2}):(?P<ss>\d{2}),(?P<sms>\d{3})"
    r"\s+-->\s+"
    r"(?P<eh>\d{2}):(?P<em>\d{2}):(?P<es>\d{2}),(?P<ems>\d{3})$"
)
HOUSE_PUNCTUATION_RE = re.compile(r"[，。！？；：“”《》（）、,.!?;:\"'()]")




def parse_duration(value: str) -> float:
    parts = str(value).replace(",", ".").split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    raise ValueError(f"invalid duration: {value}")


def video_duration(path: Path) -> float:
    return duration_seconds(path)


def match_seconds(match: re.Match[str], prefix: str) -> float:
    return (
        int(match.group(f"{prefix}h")) * 3600
        + int(match.group(f"{prefix}m")) * 60
        + int(match.group(f"{prefix}s"))
        + int(match.group(f"{prefix}ms")) / 1000
    )


def parse_srt(text: str) -> tuple[list[Cue], list[str]]:
    return shared_parse_srt(text, strict_components=True)


def validate_srt(
    text: str,
    *,
    media_duration: float,
    max_chars: int | None = None,
    bad_terms: tuple[tuple[str, str], ...] = (),
    enforce_house_style: bool = True,
    profile: str | None = None,
    max_lines: int | None = None,
    max_screen_chars: int | None = None,
) -> dict:
    if profile not in (None, 'compact-clean'):
        raise ValueError('unknown subtitle profile')
    compact_style = profile == 'compact-clean'
    max_chars = 16 if max_chars is None else max_chars
    max_lines = (2 if compact_style else None) if max_lines is None else max_lines
    max_screen_chars = (28 if compact_style else None) if max_screen_chars is None else max_screen_chars
    if not math.isfinite(media_duration) or media_duration <= 0:
        raise ValueError('media duration must be positive and finite')
    if any(v is not None and v <= 0 for v in (max_chars, max_lines, max_screen_chars)):
        raise ValueError('subtitle length limits must be positive')
    cues, errors = parse_srt(text)
    previous_end = 0.0
    for expected, cue in enumerate(cues, start=1):
        if cue.number != expected:
            errors.append(f"cue order: expected {expected}, found {cue.number}")
        if cue.end <= cue.start:
            errors.append(f"cue {cue.number}: non-positive duration")
        if cue.start < previous_end - 0.0005:
            errors.append(f"cue {cue.number}: overlaps previous cue by {previous_end - cue.start:.3f}s")
        if cue.end > media_duration + 0.001:
            errors.append(
                f"cue {cue.number}: ends at {cue.end:.3f}s beyond locked final {media_duration:.3f}s"
            )
        previous_end = max(previous_end, cue.end)
        if max_lines is not None and len(cue.lines) > max_lines:
            errors.append(f'cue {cue.number}: line count exceeds {max_lines}')
        sizes = [len(line) if compact_style else len(re.sub(r'\s+', '', line)) for line in cue.lines]
        if max_screen_chars is not None and sum(sizes) > max_screen_chars:
            errors.append(f'cue {cue.number}: screen length exceeds {max_screen_chars}')
        dual = compact_style and any(line.startswith('-') for line in cue.lines)
        if dual and (len(cue.lines) != 2 or not all(line.startswith('-') and len(line) > 1 for line in cue.lines)):
            errors.append(f'cue {cue.number}: invalid dual dialogue prefix')
        for line_number, line in enumerate(cue.lines, start=1):
            compact = line if compact_style else re.sub(r"\s+", "", line)
            if len(compact) > max_chars:
                errors.append(
                    f"cue {cue.number} line {line_number}: {len(compact)} chars exceeds {max_chars}"
                )
            residue = any(
                unicodedata.category(ch)[0] in ('P', 'S', 'C') and not (dual and j == 0 and ch == '-')
                for j, ch in enumerate(line)
            ) if compact_style else bool(HOUSE_PUNCTUATION_RE.search(line))
            if enforce_house_style and residue:
                errors.append(f"cue {cue.number} line {line_number}: punctuation residue")
            for wrong, correct in bad_terms:
                if wrong and wrong in line:
                    errors.append(
                        f"cue {cue.number} line {line_number}: bad term {wrong!r}; expected {correct!r}"
                    )
    return {
        "ok": not errors,
        "cue_count": len(cues),
        "media_duration_seconds": media_duration,
        "last_end_seconds": cues[-1].end if cues else None,
        "errors": errors,
        "profile": profile,
        "limits": {"max_chars": max_chars, "max_lines": max_lines, "max_screen_chars": max_screen_chars},
    }


def parse_bad_terms(items: list[str]) -> tuple[tuple[str, str], ...]:
    pairs = []
    for item in items:
        if "=" not in item:
            raise ValueError(f"--bad-term must be WRONG=CORRECT, got {item!r}")
        wrong, correct = item.split("=", 1)
        if not wrong.strip() or not correct.strip():
            raise ValueError(f"--bad-term must contain non-empty values, got {item!r}")
        pairs.append((wrong.strip(), correct.strip()))
    return tuple(pairs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("srt", type=Path)
    duration_group = parser.add_mutually_exclusive_group(required=True)
    duration_group.add_argument("--video", type=Path, help="Locked final video")
    duration_group.add_argument("--media-duration", help="Seconds or HH:MM:SS.mmm")
    parser.add_argument("--max-chars", type=int)
    parser.add_argument("--profile", choices=['compact-clean'])
    parser.add_argument("--max-lines", type=int)
    parser.add_argument("--max-screen-chars", type=int)
    parser.add_argument("--bad-term", action="append", default=[], help="WRONG=CORRECT")
    parser.add_argument("--allow-punctuation", action="store_true")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    protect_output_args(args)
    try:
        duration = video_duration(args.video) if args.video else parse_duration(args.media_duration)
        report = validate_srt(
            args.srt.read_text(encoding="utf-8-sig"),
            media_duration=duration,
            max_chars=args.max_chars,
            bad_terms=parse_bad_terms(args.bad_term),
            enforce_house_style=not args.allow_punctuation,
            profile=args.profile,
            max_lines=args.max_lines,
            max_screen_chars=args.max_screen_chars,
        )
    except (OSError, UnicodeError, ValueError, subprocess.CalledProcessError) as exc:
        report = {
            "ok": False,
            "cue_count": 0,
            "media_duration_seconds": None,
            "last_end_seconds": None,
            "errors": [str(exc)],
        }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
