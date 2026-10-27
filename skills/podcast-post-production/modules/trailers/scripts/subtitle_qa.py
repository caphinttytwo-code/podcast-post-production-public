#!/usr/bin/env python3
"""Validate the structure and Chinese house style of an SRT subtitle file."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args


from pathlib import Path as _PackagePath
import sys as _package_sys
_PACKAGE_ROOT = _PackagePath(__file__).resolve().parents[3]
if str(_PACKAGE_ROOT) not in _package_sys.path:
    _package_sys.path.insert(0, str(_PACKAGE_ROOT))
from shared.subtitles import Cue, match_seconds, parse_srt


import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


TIMECODE_RE = re.compile(
    r"^(?P<sh>\d{2}):(?P<sm>\d{2}):(?P<ss>\d{2}),(?P<sms>\d{3})"
    r"\s+-->\s+"
    r"(?P<eh>\d{2}):(?P<em>\d{2}):(?P<es>\d{2}),(?P<ems>\d{3})$"
)
HOUSE_PUNCTUATION_RE = re.compile(r"[，。！？；：“”《》（）、,.!?;:\"'()]")
DEFAULT_FILLERS = ("啊", "嗯", "呃", "哎呀", "那个")




def parse_clock(value: str) -> float:
    parts = str(value).replace(",", ".").split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    raise ValueError(f"invalid duration: {value}")






def standalone_filler(line: str, fillers: tuple[str, ...]) -> str | None:
    compact = re.sub(r"\s+", " ", line).strip()
    tokens = compact.split(" ")
    for filler in fillers:
        if compact == filler or filler in tokens or compact.startswith(f"{filler} "):
            return filler
    return None


def validate_srt(
    text: str,
    *,
    max_chars: int = 16,
    media_duration: float | None = None,
    bad_terms: tuple[tuple[str, str], ...] = (),
    fillers: tuple[str, ...] = DEFAULT_FILLERS,
    enforce_house_style: bool = True,
) -> dict:
    cues, errors = parse_srt(text)
    previous_end = 0.0
    for expected, cue in enumerate(cues, start=1):
        if cue.number != expected:
            errors.append(f"cue order: expected {expected}, found {cue.number}")
        if cue.end <= cue.start:
            errors.append(f"cue {cue.number}: non-positive duration")
        if cue.start < previous_end - 0.0005:
            errors.append(f"cue {cue.number}: overlaps previous cue by {previous_end - cue.start:.3f}s")
        if media_duration is not None and cue.end > media_duration + 0.001:
            errors.append(
                f"cue {cue.number}: ends at {cue.end:.3f}s beyond media duration {media_duration:.3f}s"
            )
        previous_end = max(previous_end, cue.end)
        for line_number, line in enumerate(cue.lines, start=1):
            compact = re.sub(r"\s+", "", line)
            if len(compact) > max_chars:
                errors.append(
                    f"cue {cue.number} line {line_number}: {len(compact)} chars exceeds {max_chars}"
                )
            if enforce_house_style and HOUSE_PUNCTUATION_RE.search(line):
                errors.append(f"cue {cue.number} line {line_number}: punctuation residue")
            filler = standalone_filler(line, fillers)
            if filler:
                errors.append(f"cue {cue.number} line {line_number}: standalone filler {filler!r}")
            for wrong, correct in bad_terms:
                if wrong and wrong in line:
                    errors.append(
                        f"cue {cue.number} line {line_number}: bad term {wrong!r}; expected {correct!r}"
                    )
    return {
        "ok": not errors,
        "cue_count": len(cues),
        "last_end_seconds": cues[-1].end if cues else None,
        "errors": errors,
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
    parser.add_argument("--max-chars", type=int, default=16)
    parser.add_argument("--media-duration", help="Seconds or HH:MM:SS.mmm")
    parser.add_argument("--bad-term", action="append", default=[], help="WRONG=CORRECT")
    parser.add_argument("--filler", action="append", default=[], help="Additional standalone filler")
    parser.add_argument("--allow-punctuation", action="store_true")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    protect_output_args(args)
    try:
        report = validate_srt(
            args.srt.read_text(encoding="utf-8-sig"),
            max_chars=args.max_chars,
            media_duration=parse_clock(args.media_duration) if args.media_duration else None,
            bad_terms=parse_bad_terms(args.bad_term),
            fillers=DEFAULT_FILLERS + tuple(args.filler),
            enforce_house_style=not args.allow_punctuation,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        report = {"ok": False, "cue_count": 0, "last_end_seconds": None, "errors": [str(exc)]}
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
