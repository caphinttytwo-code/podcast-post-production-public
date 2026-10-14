#!/usr/bin/env python3
"""Align a podcast candidate with a human reference edit.

The default report omits transcript text and source identifiers. Use
--include-text only with --json-out pointing into the episode workspace.
Findings are non-executable and start with review_status=pending.
"""

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
from shared.files import package_root


import argparse
import json
import math
import re
import subprocess
import sys
import unicodedata
from array import array
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


SKILL_ROOT = package_root(Path(__file__))
TOKEN_RE = re.compile(r"[\u3400-\u9fffA-Za-z0-9]")
AUDIO_SAMPLE_RATE = 2000
FRAME_SECONDS = 0.02

SENSITIVE_PATTERNS = {
    "number": re.compile(r"\d|第[一二三四五六七八九十百千万亿两]|[一二三四五六七八九两]+[十百千万亿]"),
    "negation": re.compile(r"不能|不等于|并不|未必|不一定|不是|没有|不会|不可|无需|无须|非|别"),
    "qualification": re.compile(r"也许|可能|大概|大约|几乎|通常|往往|有时|部分|某些|至少|至多|仅仅|只是|只要"),
    "causality": re.compile(r"因为|所以|因此|由于|导致|意味着|取决于|如果|那么|才能|才会"),
    "transition": re.compile(r"但是|可是|然而|不过|相反|同时|另外|首先|其次|最后"),
    "reference": re.compile(r"作者|老师|研究|数据|报告|论文|书中|这本书"),
    "conclusion": re.compile(r"结论|总之|这说明|可以看出|所以|因此|意味着"),
    "persona": re.compile(r"我想|我觉得|我认为|我是|欢迎|谢谢|听到这里"),
    "section_navigation": re.compile(r"这一期|本期|下一期|下期|接下来|说到这里|首先|第二|第三|最后"),
}


@dataclass
class Token:
    char: str
    start: float
    end: float


def read_json(path: Path, label: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise ValueError(f"could not read {label}") from None
    except json.JSONDecodeError:
        raise ValueError(f"{label} is not valid JSON") from None
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data


def normalize_chars(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return "".join(char for char in normalized if TOKEN_RE.fullmatch(char))


def transcript_tokens(path: Path) -> tuple[str | None, list[Token]]:
    data = read_json(path, "StepAudio transcript")
    chunks = data.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("StepAudio transcript must contain a chunks list")
    tokens = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise ValueError("transcript chunk must be an object")
        try:
            offset = float(chunk.get("offset_ms", 0)) / 1000.0
        except (TypeError, ValueError):
            raise ValueError("transcript chunk has invalid offset") from None
        for event in chunk.get("events", []):
            if not isinstance(event, dict) or event.get("type") != "transcript.text.delta":
                continue
            try:
                start = offset + float(event["start_time"]) / 1000.0
                end = offset + float(event["end_time"]) / 1000.0
            except (KeyError, TypeError, ValueError):
                raise ValueError("transcript event has invalid timing") from None
            if end < start:
                raise ValueError("transcript event end precedes start")
            for char in normalize_chars(str(event.get("delta", ""))):
                tokens.append(Token(char, start, end))
    if not tokens:
        raise ValueError("transcript contains no timed text tokens")
    return data.get("model"), tokens


def seconds_from_audio(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError("could not probe comparison audio")
    try:
        return float(result.stdout.strip())
    except ValueError:
        raise ValueError("comparison audio has invalid duration") from None


def decode_audio(path: Path) -> array:
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le",
            "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(AUDIO_SAMPLE_RATE), "-",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise ValueError("could not decode comparison audio")
    samples = array("h")
    samples.frombytes(result.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        raise ValueError("comparison audio is empty")
    return samples


def audio_features(samples: array) -> list[tuple[float, float]]:
    frame_size = int(AUDIO_SAMPLE_RATE * FRAME_SECONDS)
    features = []
    usable = len(samples) - len(samples) % frame_size
    for start in range(0, usable, frame_size):
        frame = samples[start:start + frame_size]
        rms = math.sqrt(sum(value * value for value in frame) / frame_size)
        crossings = sum((left < 0) != (right < 0) for left, right in zip(frame, frame[1:]))
        features.append((math.log1p(rms), crossings / max(1, frame_size - 1)))
    return features


def feature_correlation(left: list[tuple[float, float]], right: list[tuple[float, float]]) -> float:
    if len(left) != len(right) or len(left) < 4:
        return 0.0
    score = 0.0
    used = 0
    for dimension in (0, 1):
        a = [item[dimension] for item in left]
        b = [item[dimension] for item in right]
        mean_a = sum(a) / len(a)
        mean_b = sum(b) / len(b)
        centered_a = [value - mean_a for value in a]
        centered_b = [value - mean_b for value in b]
        norm_a = math.sqrt(sum(value * value for value in centered_a))
        norm_b = math.sqrt(sum(value * value for value in centered_b))
        if norm_a <= 1e-9 or norm_b <= 1e-9:
            continue
        score += sum(x * y for x, y in zip(centered_a, centered_b)) / (norm_a * norm_b)
        used += 1
    return max(0.0, score / used) if used else 0.0


def best_feature_match(
    reference: list[tuple[float, float]],
    candidate: list[tuple[float, float]],
    reference_time: float,
    candidate_time: float,
) -> float:
    frame_count = 18
    radius = 45
    reference_index = round(reference_time / FRAME_SECONDS)
    candidate_index = round(candidate_time / FRAME_SECONDS)
    if reference_index < 0 or reference_index + frame_count > len(reference):
        return 0.0
    window = reference[reference_index:reference_index + frame_count]
    best = 0.0
    for position in range(max(0, candidate_index - radius), min(len(candidate) - frame_count, candidate_index + radius) + 1):
        best = max(best, feature_correlation(window, candidate[position:position + frame_count]))
    return best


def acoustic_evidence(
    base_features: list[tuple[float, float]] | None,
    reference_features: list[tuple[float, float]] | None,
    base_before: float,
    base_after: float,
    reference_before: float,
    reference_after: float,
) -> dict | None:
    if base_features is None or reference_features is None:
        return None

    def side(base_point: float, reference_point: float, offsets: tuple[float, ...]) -> float:
        return max(
            (
                best_feature_match(
                    base_features, reference_features, base_point + offset, reference_point + offset
                )
                for offset in offsets
                if base_point + offset >= 0 and reference_point + offset >= 0
            ),
            default=0.0,
        )

    before = side(base_before, reference_before, (-1.4, -1.0, -0.6, -0.3))
    after = side(base_after, reference_after, (0.18, 0.5, 0.9, 1.3))
    return {"before_correlation": round(before, 3), "after_correlation": round(after, 3)}


def sensitive_flags(text: str) -> list[str]:
    return [name for name, pattern in SENSITIVE_PATTERNS.items() if pattern.search(text)]


def confidence(anchor_before: int, anchor_after: int, acoustic: dict | None) -> str:
    stable_text = min(anchor_before, anchor_after)
    if acoustic is None:
        return "medium" if stable_text >= 8 else "uncertain"
    before = acoustic["before_correlation"]
    after = acoustic["after_correlation"]
    if stable_text >= 6 and min(before, after) >= 0.75:
        return "high"
    if stable_text >= 4 and (min(before, after) >= 0.55 or max(before, after) >= 0.75):
        return "medium"
    return "uncertain"


def source_mapper(edl_path: Path, source_duration: float):
    data = read_json(edl_path, "baseline EDL")
    cuts = sorted(
        ({"start": float(item["start"]), "end": float(item["end"])} for item in data.get("cuts", [])),
        key=lambda item: item["start"],
    )
    merged = []
    for item in cuts:
        if item["start"] < 0 or item["end"] <= item["start"] or item["end"] > source_duration + 0.001:
            raise ValueError("baseline EDL contains an invalid cut")
        if merged and item["start"] <= merged[-1]["end"] + 0.1:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
        else:
            merged.append(dict(item))
    keep = []
    cursor = 0.0
    for item in merged:
        if item["start"] > cursor:
            keep.append((cursor, item["start"]))
        cursor = max(cursor, item["end"])
    if cursor < source_duration:
        keep.append((cursor, source_duration))
    fade = float(data.get("crossfade_seconds", 0.02))
    timeline = []
    edit_cursor = 0.0
    for index, (source_start, source_end) in enumerate(keep):
        if index:
            edit_cursor -= fade
        edit_end = edit_cursor + source_end - source_start
        timeline.append((edit_cursor, edit_end, source_start))
        edit_cursor = edit_end

    def mapping(edit_time: float) -> dict | None:
        matches = [item for item in timeline if item[0] <= edit_time <= item[1]]
        if not matches:
            return None
        selected = matches[-1]
        return {
            "seconds": round(selected[2] + edit_time - selected[0], 6),
            "ambiguous_crossfade": len(matches) > 1,
        }

    return mapping


def text_slice(tokens: list[Token], start: int, end: int) -> str:
    return "".join(token.char for token in tokens[max(0, start):min(len(tokens), end)])


def build_report(args) -> dict:
    base_model, base = transcript_tokens(args.baseline_transcript)
    reference_model, reference = transcript_tokens(args.reference_transcript)
    if base_model and reference_model and base_model != reference_model:
        raise ValueError("compared transcripts must use the same ASR model")
    base_text = "".join(token.char for token in base)
    reference_text = "".join(token.char for token in reference)
    matcher = SequenceMatcher(None, base_text, reference_text, autojunk=False)
    opcodes = matcher.get_opcodes()

    base_features = reference_features = None
    baseline_duration = args.baseline_duration
    reference_duration = args.reference_duration
    if args.baseline_audio:
        base_samples = decode_audio(args.baseline_audio)
        reference_samples = decode_audio(args.reference_audio)
        base_features = audio_features(base_samples)
        reference_features = audio_features(reference_samples)
        baseline_duration = seconds_from_audio(args.baseline_audio)
        reference_duration = seconds_from_audio(args.reference_audio)

    mapping = None
    if args.baseline_edl:
        mapping = source_mapper(args.baseline_edl, args.source_duration)

    content_events = []
    for opcode_index, (tag, a0, a1, b0, b1) in enumerate(opcodes):
        removed_chars = (a1 - a0) - (b1 - b0)
        if tag == "equal" or removed_chars < 2 or min(a0, b0) == 0:
            continue
        if a1 >= len(base) or b1 >= len(reference):
            continue
        base_before, base_after = base[a0 - 1].end, base[a1].start
        reference_before, reference_after = reference[b0 - 1].end, reference[b1].start
        removed_seconds = (base_after - base_before) - (reference_after - reference_before)
        if removed_seconds < args.minimum_removed_seconds:
            continue
        deleted = text_slice(base, a0, a1)
        retained_context = text_slice(reference, b0 - args.context_chars, b1 + args.context_chars)
        flags = sensitive_flags(deleted)
        similarity = SequenceMatcher(None, deleted, retained_context, autojunk=False).ratio()
        proposed = (
            "sensitive-review"
            if flags
            else "mechanical-omission-candidate"
            if similarity >= 0.45
            else "semantic-or-structural-review"
        )
        previous_equal = opcodes[opcode_index - 1] if opcode_index else None
        next_equal = opcodes[opcode_index + 1] if opcode_index + 1 < len(opcodes) else None
        anchor_before = previous_equal[2] - previous_equal[1] if previous_equal and previous_equal[0] == "equal" else 0
        anchor_after = next_equal[2] - next_equal[1] if next_equal and next_equal[0] == "equal" else 0
        acoustic = acoustic_evidence(
            base_features, reference_features, base_before, base_after, reference_before, reference_after
        )
        event = {
            "id": f"C{len(content_events) + 1:03d}",
            "kind": "content",
            "baseline_start": round(base_before, 6),
            "baseline_end": round(base_after, 6),
            "reference_join_start": round(reference_before, 6),
            "reference_join_end": round(reference_after, 6),
            "estimated_removed_seconds": round(removed_seconds, 6),
            "removed_characters": removed_chars,
            "retained_context_similarity": round(similarity, 6),
            "sensitive_flags": flags,
            "proposed_classification": proposed,
            "confidence": confidence(anchor_before, anchor_after, acoustic),
            "review_status": "pending",
        }
        if mapping:
            event["source_start"] = mapping(base_before)
            event["source_end"] = mapping(base_after)
        if acoustic:
            event["acoustic"] = acoustic
        if args.include_text:
            event["deleted_text"] = deleted
            event["baseline_context"] = text_slice(base, a0 - args.context_chars, a1 + args.context_chars)
            event["reference_context"] = retained_context
        content_events.append(event)

    pause_events = []
    for tag, a0, a1, b0, b1 in opcodes:
        if tag != "equal" or a1 - a0 < 2:
            continue
        for offset in range(1, a1 - a0):
            ai0, ai1 = a0 + offset - 1, a0 + offset
            bi0, bi1 = b0 + offset - 1, b0 + offset
            base_gap = base[ai1].start - base[ai0].end
            reference_gap = reference[bi1].start - reference[bi0].end
            removed_seconds = base_gap - reference_gap
            if base_gap < args.minimum_baseline_gap or removed_seconds < args.minimum_removed_seconds:
                continue
            base_before, base_after = base[ai0].end, base[ai1].start
            reference_before, reference_after = reference[bi0].end, reference[bi1].start
            context = text_slice(base, ai0 - 8, ai1 + 9)
            flags = sensitive_flags(context)
            acoustic = acoustic_evidence(
                base_features, reference_features, base_before, base_after, reference_before, reference_after
            )
            event = {
                "id": f"P{len(pause_events) + 1:03d}",
                "kind": "pause",
                "baseline_start": round(base_before, 6),
                "baseline_end": round(base_after, 6),
                "reference_start": round(reference_before, 6),
                "reference_end": round(reference_after, 6),
                "baseline_gap_seconds": round(base_gap, 6),
                "reference_gap_seconds": round(reference_gap, 6),
                "estimated_removed_seconds": round(removed_seconds, 6),
                "sensitive_flags": flags,
                "proposed_classification": "sensitive-review" if flags else "pause-adjustment",
                "confidence": confidence(16, 16, acoustic),
                "review_status": "pending",
            }
            if mapping:
                event["source_start"] = mapping(base_before)
                event["source_end"] = mapping(base_after)
            if acoustic:
                event["acoustic"] = acoustic
            if args.include_text:
                event["context"] = context
            pause_events.append(event)

    content_seconds = sum(event["estimated_removed_seconds"] for event in content_events)
    pause_seconds = sum(event["estimated_removed_seconds"] for event in pause_events)
    summary = {
        "content_event_count": len(content_events),
        "pause_event_count": len(pause_events),
        "pending_event_count": len(content_events) + len(pause_events),
        "sensitive_event_count": sum(bool(event["sensitive_flags"]) for event in content_events + pause_events),
        "content_estimated_seconds": round(content_seconds, 6),
        "pause_estimated_seconds": round(pause_seconds, 6),
        "accounted_seconds": round(content_seconds + pause_seconds, 6),
    }
    durations = None
    if baseline_duration is not None and reference_duration is not None:
        shorter = baseline_duration - reference_duration
        durations = {
            "baseline_seconds": round(baseline_duration, 6),
            "reference_seconds": round(reference_duration, 6),
            "reference_shorter_seconds": round(shorter, 6),
            "unresolved_residual_seconds": round(shorter - content_seconds - pause_seconds, 6),
        }
    return {
        "schema_version": 1,
        "analysis_type": "human-reference-edit-comparison",
        "asr_model": base_model or reference_model,
        "privacy": {
            "contains_transcript_text": bool(args.include_text),
            "contains_source_identifiers": False,
            "skill_repository_output_forbidden": True,
        },
        "method": {
            "sequence_similarity": round(matcher.ratio(), 6),
            "baseline_characters": len(base),
            "reference_characters": len(reference),
            "acoustic_validation": bool(base_features),
            "source_timeline_mapping": bool(mapping),
        },
        "durations": durations,
        "summary": summary,
        "content_events": content_events,
        "pause_events": pause_events,
    }


def output_is_inside_skill(path: Path) -> bool:
    try:
        path.resolve().relative_to(SKILL_ROOT.resolve())
        return True
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_transcript", type=Path)
    parser.add_argument("reference_transcript", type=Path)
    parser.add_argument("--baseline-audio", type=Path)
    parser.add_argument("--reference-audio", type=Path)
    parser.add_argument("--baseline-duration", type=float)
    parser.add_argument("--reference-duration", type=float)
    parser.add_argument("--baseline-edl", type=Path)
    parser.add_argument("--source-duration", type=float)
    parser.add_argument("--minimum-removed-seconds", type=float, default=0.28)
    parser.add_argument("--minimum-baseline-gap", type=float, default=0.36)
    parser.add_argument("--context-chars", type=int, default=48)
    parser.add_argument("--include-text", action="store_true")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    protect_output_args(args)
    if (args.baseline_audio is None) != (args.reference_audio is None):
        parser.error("--baseline-audio and --reference-audio must be supplied together")
    if (args.baseline_edl is None) != (args.source_duration is None):
        parser.error("--baseline-edl and --source-duration must be supplied together")
    if args.include_text and args.json_out is None:
        parser.error("--include-text requires --json-out")
    if args.json_out and output_is_inside_skill(args.json_out):
        parser.error("comparison output must stay in the episode workspace, not the Skill repository")
    if args.minimum_removed_seconds < 0 or args.minimum_baseline_gap < 0 or args.context_chars < 1:
        parser.error("thresholds must be non-negative and context-chars must be positive")
    report = build_report(args)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        raise SystemExit(f"reference comparison failed: {exc}") from exc
