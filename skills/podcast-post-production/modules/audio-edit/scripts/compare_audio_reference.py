#!/usr/bin/env python3
"""Map rendered candidate/reference edits back to one immutable audio source.

Use this local fallback when complete compared-version transcripts are unavailable.
The result is non-executable and does not replace same-model post-edit ASR.
"""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args, package_root
from shared.guards import guard_path, guard_directory


import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None


SKILL_ROOT = package_root()
SAMPLE_RATE = 8000
HOP = 400
FPS = SAMPLE_RATE // HOP
FRAME_SAMPLES = 800
WINDOW_FRAMES = 40
ANCHOR_STEP = 5
MIN_DIFFERENCE_SECONDS = 0.1
MICRO_EDIT_SECONDS = 0.3
BANDS = [(5, 15), (15, 30), (30, 50), (50, 80), (80, 120), (120, 180), (180, 260), (260, 390)]
SENSITIVE = {
    "number": re.compile(r"\d|第[一二三四五六七八九十百千万亿两]"),
    "negation": re.compile(r"不能|不等于|并不|未必|不一定|不是|没有|不会|不可|非"),
    "qualification": re.compile(r"也许|可能|大概|通常|往往|部分|某些|至少|只是|未必|不一定"),
    "causality": re.compile(r"因为|所以|因此|由于|意味着|如果|那么|才会"),
    "transition": re.compile(r"但是|可是|然而|不过|相反|同时|另外|最后"),
    "reference": re.compile(r"老师|研究|数据|报告|论文|书中|这本书"),
    "conclusion": re.compile(r"结论|总之|这说明|所以|因此|意味着"),
    "persona": re.compile(r"我想|我觉得|我认为|我是|欢迎|听到这里"),
    "section_navigation": re.compile(r"这一期|下一期|接下来|首先|第二|第三|最后"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Locally compare rendered podcast edits by mapping both to one source."
    )
    parser.add_argument("source_audio", type=Path)
    parser.add_argument("baseline_audio", type=Path)
    parser.add_argument("reference_audio", type=Path)
    parser.add_argument("source_transcript", type=Path)
    parser.add_argument(
        "--reference-role",
        choices=("human_reference", "chatcut_reference", "agent_reference"),
        default="chatcut_reference",
    )
    parser.add_argument(
        "--direct-baseline",
        action="store_true",
        help=(
            "align the rendered reference directly to the baseline candidate, then map "
            "findings back to the immutable source with --baseline-edl"
        ),
    )
    parser.add_argument(
        "--baseline-edl",
        type=Path,
        help="EDL v3 used to render the baseline candidate; required with --direct-baseline",
    )
    parser.add_argument(
        "--baseline-transcript",
        type=Path,
        help="timed transcript of the baseline candidate; required with --direct-baseline",
    )
    parser.add_argument(
        "--minimum-difference-seconds",
        type=float,
        default=MIN_DIFFERENCE_SECONDS,
        help="retain aligned differences at or above this duration (default: 0.1)",
    )
    parser.add_argument("--include-text", action="store_true")
    parser.add_argument("--baseline-transcript-out", type=Path)
    parser.add_argument("--reference-transcript-out", type=Path)
    parser.add_argument("--json-out", type=Path, required=True)
    return parser.parse_args()


def require_project_output(path: Path) -> None:
    resolved = path.resolve()
    try:
        resolved.relative_to(SKILL_ROOT.resolve())
    except ValueError:
        return
    raise ValueError("comparison evidence must be written to the episode workspace, not the Skill directory")


def duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError("could not probe comparison audio")
    return float(result.stdout.strip())


def decode(path: Path, output: Path) -> None:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
            "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", str(output),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError("could not decode comparison audio")


def feature_windows(path: Path) -> tuple[np.ndarray, np.ndarray]:
    samples = np.fromfile(path, dtype="<i2").astype(np.float32) / 32768.0
    frame_count = 1 + (len(samples) - FRAME_SAMPLES) // HOP
    frames = np.lib.stride_tricks.as_strided(
        samples,
        shape=(frame_count, FRAME_SAMPLES),
        strides=(samples.strides[0] * HOP, samples.strides[0]),
    ).copy()
    frames *= np.hanning(FRAME_SAMPLES).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(frames, axis=1))
    features = np.stack(
        [np.log1p(spectrum[:, start:end].mean(axis=1) * 20) for start, end in BANDS], axis=1
    ).astype(np.float32)
    windows = np.lib.stride_tricks.sliding_window_view(
        features, WINDOW_FRAMES, axis=0
    ).transpose(0, 2, 1).copy()
    windows -= windows.mean(axis=1, keepdims=True)
    windows /= windows.std(axis=1, keepdims=True) + 1e-4
    windows = windows.reshape(len(windows), -1)
    windows /= np.linalg.norm(windows, axis=1, keepdims=True) + 1e-8
    return samples, windows


def merge(intervals: list[dict], gap: float = 0.12) -> list[dict]:
    output = []
    for item in sorted(intervals, key=lambda value: value["start"]):
        if item["end"] <= item["start"]:
            continue
        if output and item["start"] <= output[-1]["end"] + gap:
            output[-1]["end"] = max(output[-1]["end"], item["end"])
            output[-1]["kind"] = "merged"
        else:
            output.append(dict(item))
    return output


def align(source: np.ndarray, target: np.ndarray, source_seconds: float, target_seconds: float) -> dict:
    initial_scores = source[: 180 * FPS] @ target[0]
    initial_frame = int(np.argmax(initial_scores))
    offset = initial_frame
    last_good = 0.0
    updates = []
    matches = searches = ambiguous = 0
    source_exhausted = False

    for reference_frame in range(ANCHOR_STEP, len(target), ANCHOR_STEP):
        expected = reference_frame + offset
        local_start = max(0, expected - 2)
        local_end = min(len(source), expected + 3)
        if local_start >= local_end:
            source_exhausted = True
            break
        local = source[local_start:local_end] @ target[reference_frame]
        local_index = int(np.argmax(local))
        local_score = float(local[local_index])
        if local_score >= 0.64:
            matches += 1
            last_good = reference_frame / FPS
            continue

        searches += 1
        search_start = max(0, expected - 2)
        search_end = min(len(source), expected + 120 * FPS)
        if search_start >= search_end:
            source_exhausted = True
            break
        scores = source[search_start:search_end] @ target[reference_frame]
        order = np.argsort(scores)[-8:][::-1]
        best_relative = int(order[0])
        best_frame = search_start + best_relative
        best_score = float(scores[best_relative])
        second_score = max(
            (float(scores[index]) for index in order[1:] if abs(int(index) - best_relative) > 10),
            default=-1.0,
        )
        proposed = best_frame - reference_frame
        if best_score >= 0.72 and best_score - second_score >= 0.06 and proposed - offset >= 3:
            future = [
                float(source[best_frame + delta] @ target[reference_frame + delta])
                for delta in (40, 60, 80)
                if reference_frame + delta < len(target) and best_frame + delta < len(source)
            ]
            if future and max(future) >= 0.62:
                reference_time = reference_frame / FPS
                boundary = (min(reference_time, last_good + WINDOW_FRAMES / FPS) + reference_time) / 2
                updates.append(
                    {
                        "boundary_reference_time": round(boundary, 3),
                        "old_offset": round(offset / FPS, 3),
                        "new_offset": round(proposed / FPS, 3),
                        "effective_removed": round((proposed - offset) / FPS, 3),
                        "alignment_score": round(best_score, 3),
                    }
                )
                offset = proposed
                matches += 1
                last_good = reference_time
                continue
        ambiguous += 1

    cuts = [{"start": 0.0, "end": round(initial_frame / FPS, 3), "kind": "initial-trim"}]
    for update in updates:
        boundary = update["boundary_reference_time"]
        cuts.append(
            {
                "start": round(boundary + update["old_offset"], 3),
                "end": round(boundary + update["new_offset"], 3),
                "kind": "internal-edit",
                "alignment_score": update["alignment_score"],
            }
        )
    final_offset = offset / FPS
    cuts.append(
        {
            "start": round(min(source_seconds, target_seconds + final_offset), 3),
            "end": round(source_seconds, 3),
            "kind": "tail-trim",
        }
    )
    cuts = merge(cuts)
    return {
        "initial_offset": round(initial_frame / FPS, 3),
        "initial_score": round(float(initial_scores[initial_frame]), 3),
        "final_offset": round(final_offset, 3),
        "cuts": cuts,
        "diagnostics": {
            "matches": matches,
            "forward_searches": searches,
            "ambiguous_anchors": ambiguous,
            "source_exhausted_before_target_end": source_exhausted,
            "window_seconds": WINDOW_FRAMES / FPS,
            "anchor_step_seconds": ANCHOR_STEP / FPS,
        },
    }


def subtract(
    left: list[dict], right: list[dict], minimum: float = MIN_DIFFERENCE_SECONDS
) -> list[dict]:
    result = []
    for item in left:
        pieces = [(item["start"], item["end"])]
        for other in right:
            revised = []
            for start, end in pieces:
                if other["end"] <= start or other["start"] >= end:
                    revised.append((start, end))
                else:
                    if other["start"] > start:
                        revised.append((start, other["start"]))
                    if other["end"] < end:
                        revised.append((other["end"], end))
            pieces = revised
        result.extend(
            {"start": round(start, 3), "end": round(end, 3)}
            for start, end in pieces
            if end - start >= minimum
        )
    return merge(result, 0.25)


def read_source_events(
    path: Path,
    *,
    prefer_edit_timeline: bool = False,
) -> tuple[str | None, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    events = []
    for chunk in data.get("chunks", []):
        offset = int(chunk.get("offset_ms", 0))
        for event in chunk.get("events", []):
            if event.get("type") != "transcript.text.delta":
                continue
            events.append(
                {
                    "text": str(event.get("delta", "")),
                    "source_start_ms": offset + int(event["start_time"]),
                    "source_end_ms": offset + int(event["end_time"]),
                }
            )
    if not events and prefer_edit_timeline:
        for event in data.get("events", []):
            start = event.get("edit_start_ms")
            end = event.get("edit_end_ms")
            if start is None or end is None:
                continue
            events.append(
                {
                    "text": str(event.get("text", "")),
                    "source_start_ms": int(start),
                    "source_end_ms": int(end),
                }
            )
    if not events:
        raise ValueError("source transcript contains no timed StepAudio events")
    return data.get("model"), events


def annotate(
    intervals: list[dict],
    events: list[dict],
    include_text: bool,
    transcript_timeline: str = "source",
) -> list[dict]:
    output = []
    for number, item in enumerate(intervals, 1):
        text = "".join(
            event["text"]
            for event in events
            if item["start"] <= (event["source_start_ms"] + event["source_end_ms"]) / 2000 < item["end"]
        )
        normalized = "".join(re.findall(r"[\u3400-\u9fffA-Za-z0-9]", text))
        duration_seconds = round(item["end"] - item["start"], 3)
        is_micro_edit = duration_seconds < MICRO_EDIT_SECONDS
        finding = {
            "id": f"A{number:04d}",
            **item,
            "duration": duration_seconds,
            "difference_type": (
                "micro-edit"
                if is_micro_edit
                else "content-bearing"
                if len(normalized) >= 2
                else "pause-or-boundary"
            ),
            "micro_edit": is_micro_edit,
            "confidence": "uncertain" if is_micro_edit else "provisional",
            "transcript_timeline": transcript_timeline,
            "sensitive_flags": [name for name, pattern in SENSITIVE.items() if pattern.search(text)],
            "review_status": "pending",
        }
        if include_text:
            finding[f"{transcript_timeline}_transcript_excerpt"] = text[:180]
        output.append(finding)
    return output


def source_mapper(edl_path: Path, source_duration: float):
    try:
        data = json.loads(edl_path.read_text(encoding="utf-8"))
    except OSError:
        raise ValueError("could not read baseline EDL") from None
    except json.JSONDecodeError:
        raise ValueError("baseline EDL is not valid JSON") from None
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
        timeline.append((edit_cursor, edit_end, source_start, index))
        edit_cursor = edit_end

    def mapping(edit_time: float) -> dict | None:
        matches = [item for item in timeline if item[0] <= edit_time <= item[1]]
        if not matches:
            return None
        selected = matches[-1]
        return {
            "seconds": round(selected[2] + edit_time - selected[0], 6),
            "segment_index": selected[3],
            "ambiguous_crossfade": len(matches) > 1,
        }

    return mapping


def add_source_mapping(findings: list[dict], mapping) -> None:
    for finding in findings:
        baseline_start = finding["start"]
        baseline_end = finding["end"]
        source_start = mapping(baseline_start)
        source_end = mapping(baseline_end)
        finding["baseline_start"] = baseline_start
        finding["baseline_end"] = baseline_end
        finding["source_start"] = source_start
        finding["source_end"] = source_end
        continuous = bool(
            source_start
            and source_end
            and source_start["segment_index"] == source_end["segment_index"]
            and not source_start["ambiguous_crossfade"]
            and not source_end["ambiguous_crossfade"]
        )
        finding["source_mapping_continuous"] = continuous
        if not continuous:
            finding["confidence"] = "uncertain"


def duration_reconciliation(
    baseline_seconds: float,
    reference_seconds: float,
    reference_more: list[dict],
    baseline_more: list[dict],
) -> dict:
    observed = baseline_seconds - reference_seconds
    reference_removed = sum(item["duration"] for item in reference_more)
    baseline_removed = sum(item["duration"] for item in baseline_more)
    projected_net = reference_removed - baseline_removed
    residual = observed - projected_net
    tolerance = max(0.25, abs(observed) * 0.002)
    return {
        "observed_reference_shorter_seconds": round(observed, 3),
        "projected_reference_removes_more_seconds": round(reference_removed, 3),
        "projected_baseline_removes_more_seconds": round(baseline_removed, 3),
        "projected_net_shortening_seconds": round(projected_net, 3),
        "unresolved_residual_seconds": round(residual, 3),
        "tolerance_seconds": round(tolerance, 3),
        "within_tolerance": abs(residual) <= tolerance,
        "possible_residual_causes": [
            "codec delay or padding",
            "crossfade overlap",
            "alignment boundary uncertainty",
            "differences shorter than the configured minimum",
        ],
    }


def retained_segments(cuts: list[dict], source_seconds: float) -> list[tuple[float, float, float]]:
    output = []
    cursor = removed = 0.0
    for cut in cuts:
        if cut["start"] > cursor:
            output.append((cursor, cut["start"], removed))
        removed += cut["end"] - cut["start"]
        cursor = max(cursor, cut["end"])
    if cursor < source_seconds:
        output.append((cursor, source_seconds, removed))
    return output


def write_projected_transcript(
    path: Path, cuts: list[dict], events: list[dict], source_seconds: float, model: str | None, role: str
) -> None:
    require_project_output(path)
    segments = retained_segments(cuts, source_seconds)
    projected = []
    for event in events:
        center = (event["source_start_ms"] + event["source_end_ms"]) / 2000
        segment = next((item for item in segments if item[0] <= center < item[1]), None)
        if segment is None:
            continue
        source_start, source_end, removed = segment
        start = max(event["source_start_ms"] / 1000, source_start) - removed
        end = min(event["source_end_ms"] / 1000, source_end) - removed
        projected.append(
            {
                "type": "transcript.text.delta",
                "delta": event["text"],
                "start_time": round(start * 1000),
                "end_time": round(max(start, end) * 1000),
            }
        )
    payload = {
        "model": model,
        "provenance": "local-acoustic-projection from source transcript; not post-edit ASR",
        "comparison_role": role,
        "chunks": [{"chunk": f"{role}-projected", "offset_ms": 0, "events": projected}],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def low_energy(samples: np.ndarray) -> dict:
    frame = int(SAMPLE_RATE * 0.02)
    usable = len(samples) - len(samples) % frame
    values = samples[:usable].reshape(-1, frame).astype(np.float64)
    db = 20 * np.log10(np.sqrt(np.mean(values * values, axis=1)) + 1e-12)
    p95 = float(np.percentile(db, 95))
    output = {"p95_frame_rms_dbfs": round(p95, 2), "relative_thresholds": {}}
    for below in (30, 35, 40):
        threshold = p95 - below
        mask = db <= threshold
        runs = []
        start = None
        for index, value in enumerate(mask):
            if value and start is None:
                start = index
            elif not value and start is not None:
                runs.append((index - start) * 0.02)
                start = None
        if start is not None:
            runs.append((len(mask) - start) * 0.02)
        output["relative_thresholds"][f"p95_minus_{below}db"] = {
            "threshold_dbfs": round(threshold, 2),
            "low_energy_seconds": round(float(mask.sum()) * 0.02, 3),
            "runs_over_1s": sum(value >= 1 for value in runs),
            "runs_over_2s": sum(value >= 2 for value in runs),
            "longest_run_seconds": round(max(runs, default=0.0), 3),
        }
    return output


def main() -> int:
    args = parse_args()
    if np is None:
        raise ValueError("numpy is required; use the bundled workspace Python runtime when available")
    if args.minimum_difference_seconds <= 0:
        raise ValueError("--minimum-difference-seconds must be greater than zero")
    if args.direct_baseline and (not args.baseline_edl or not args.baseline_transcript):
        raise ValueError(
            "--direct-baseline requires --baseline-edl and --baseline-transcript"
        )
    require_project_output(args.json_out)
    for optional in (args.baseline_transcript_out, args.reference_transcript_out):
        if optional:
            require_project_output(optional)

    source_seconds = duration(args.source_audio)
    baseline_seconds = duration(args.baseline_audio)
    reference_seconds = duration(args.reference_audio)
    model, events = read_source_events(args.source_transcript)
    baseline_model = baseline_events = None
    if args.direct_baseline:
        baseline_model, baseline_events = read_source_events(
            args.baseline_transcript,
            prefer_edit_timeline=True,
        )
        if model and baseline_model and model != baseline_model:
            raise ValueError("source and baseline transcripts must use the same ASR model")

    with tempfile.TemporaryDirectory(prefix="podcast-audio-reference-") as temporary:
        temporary = Path(temporary)
        decoded = {name: temporary / f"{name}.s16" for name in ("source", "baseline", "reference")}
        decode(args.source_audio, decoded["source"])
        decode(args.baseline_audio, decoded["baseline"])
        decode(args.reference_audio, decoded["reference"])
        source_samples, source_windows = feature_windows(decoded["source"])
        baseline_samples, baseline_windows = feature_windows(decoded["baseline"])
        reference_samples, reference_windows = feature_windows(decoded["reference"])
        baseline_alignment = align(source_windows, baseline_windows, source_seconds, baseline_seconds)
        reference_alignment = align(source_windows, reference_windows, source_seconds, reference_seconds)
        projected_reference_more = annotate(
            subtract(
                reference_alignment["cuts"],
                baseline_alignment["cuts"],
                args.minimum_difference_seconds,
            ),
            events,
            args.include_text,
        )
        projected_baseline_more = annotate(
            subtract(
                baseline_alignment["cuts"],
                reference_alignment["cuts"],
                args.minimum_difference_seconds,
            ),
            events,
            args.include_text,
        )
        direct_reference_alignment = None
        source_projection_differences = None
        if args.direct_baseline:
            direct_reference_alignment = align(
                baseline_windows, reference_windows, baseline_seconds, reference_seconds
            )
            reference_more = annotate(
                subtract(
                    direct_reference_alignment["cuts"],
                    [],
                    args.minimum_difference_seconds,
                ),
                baseline_events,
                args.include_text,
                "baseline_candidate",
            )
            add_source_mapping(reference_more, source_mapper(args.baseline_edl, source_seconds))
            baseline_more = []
            source_projection_differences = {
                "purpose": (
                    "supplementary bidirectional review; excluded from direct-baseline "
                    "duration reconciliation"
                ),
                "reference_removes_more": projected_reference_more,
                "baseline_removes_more": projected_baseline_more,
            }
        else:
            reference_more = projected_reference_more
            baseline_more = projected_baseline_more
        if args.baseline_transcript_out:
            write_projected_transcript(
                args.baseline_transcript_out, baseline_alignment["cuts"], events,
                source_seconds, model, "baseline_candidate"
            )
        if args.reference_transcript_out:
            write_projected_transcript(
                args.reference_transcript_out, reference_alignment["cuts"], events,
                source_seconds, model, args.reference_role
            )
        report = {
            "schema_version": 1,
            "analysis_type": (
                "direct-baseline-acoustic-reference-projection"
                if args.direct_baseline
                else "local-acoustic-reference-projection"
            ),
            "reference_role": args.reference_role,
            "method": {
                "external_upload": False,
                "sample_rate": SAMPLE_RATE,
                "window_seconds": WINDOW_FRAMES / FPS,
                "anchor_step_seconds": ANCHOR_STEP / FPS,
                "text_provenance": (
                    "existing baseline-candidate transcript plus EDL source mapping; not reference ASR"
                    if args.direct_baseline
                    else "existing source transcript projection; not compared-version ASR"
                ),
                "boundary_precision": "review guide, typically about 0.25-1.0 seconds",
                "minimum_difference_seconds": args.minimum_difference_seconds,
                "micro_edit_threshold_seconds": MICRO_EDIT_SECONDS,
                "direct_baseline": args.direct_baseline,
                "finding_timeline": "baseline_candidate" if args.direct_baseline else "source",
            },
            "privacy": {
                "contains_transcript_text": args.include_text,
                "contains_source_identifiers": False,
            },
            "durations": {
                "source_seconds": round(source_seconds, 3),
                "baseline_seconds": round(baseline_seconds, 3),
                "reference_seconds": round(reference_seconds, 3),
                "reference_shorter_seconds": round(baseline_seconds - reference_seconds, 3),
            },
            "baseline_alignment": baseline_alignment,
            "reference_alignment": reference_alignment,
            "direct_reference_alignment": direct_reference_alignment,
            "source_projection_differences": source_projection_differences,
            "reference_removes_more": reference_more,
            "baseline_removes_more": baseline_more,
            "duration_reconciliation": duration_reconciliation(
                baseline_seconds, reference_seconds, reference_more, baseline_more
            ),
            "summary": {
                "reference_removes_more_count": len(reference_more),
                "reference_removes_more_seconds": round(sum(item["duration"] for item in reference_more), 3),
                "baseline_removes_more_count": len(baseline_more),
                "baseline_removes_more_seconds": round(sum(item["duration"] for item in baseline_more), 3),
                "micro_edit_pending": sum(
                    bool(item.get("micro_edit")) for item in reference_more + baseline_more
                ),
                "sensitive_pending": sum(bool(item["sensitive_flags"]) for item in reference_more + baseline_more),
                "all_findings_pending": True,
            },
            "low_energy_profiles": {
                "baseline": low_energy(baseline_samples),
                "reference": low_energy(reference_samples),
            },
            "review_status": "pending",
            "edl_mutated": False,
            "release_ready": False,
        }

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
