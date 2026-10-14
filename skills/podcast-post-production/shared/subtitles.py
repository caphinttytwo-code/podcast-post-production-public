"""Common SRT syntax only; module-specific validation stays in its module."""

from __future__ import annotations

import re

from dataclasses import dataclass

TIMECODE_RE = re.compile(
    r"^(?P<sh>\d{2}):(?P<sm>\d{2}):(?P<ss>\d{2}),(?P<sms>\d{3})"
    r"\s+-->\s+"
    r"(?P<eh>\d{2}):(?P<em>\d{2}):(?P<es>\d{2}),(?P<ems>\d{3})$"
)

@dataclass(frozen=True)
class Cue:
    number: int
    start: float
    end: float
    lines: tuple[str, ...]

def match_seconds(match: re.Match[str], prefix: str) -> float:
    return (
        int(match.group(f"{prefix}h")) * 3600
        + int(match.group(f"{prefix}m")) * 60
        + int(match.group(f"{prefix}s"))
        + int(match.group(f"{prefix}ms")) / 1000
    )

def parse_srt(text: str, *, strict_components: bool = False) -> tuple[list[Cue], list[str]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return [], ["subtitle file is empty"]
    cues: list[Cue] = []
    errors: list[str] = []
    for block_index, block in enumerate(re.split(r"\n[ \t]*\n", normalized), start=1):
        lines = [line.strip() for line in block.splitlines()]
        if len(lines) < 3:
            errors.append(f"block {block_index}: expected number, timecode, and text")
            continue
        try:
            number = int(lines[0])
        except ValueError:
            errors.append(f"block {block_index}: invalid cue number {lines[0]!r}")
            continue
        match = TIMECODE_RE.match(lines[1])
        if not match:
            errors.append(f"cue {number}: invalid timecode {lines[1]!r}")
            continue
        if strict_components and any(int(match.group(p + field)) >= 60 for p in ('s', 'e') for field in ('m', 's')):
            errors.append(f"cue {number}: invalid minute or second component")
            continue
        text_lines = tuple(line for line in lines[2:] if line)
        if not text_lines:
            errors.append(f"cue {number}: empty subtitle text")
            continue
        cues.append(Cue(number, match_seconds(match, "s"), match_seconds(match, "e"), text_lines))
    return cues, errors
