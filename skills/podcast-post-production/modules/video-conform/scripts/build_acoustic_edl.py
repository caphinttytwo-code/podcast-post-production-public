#!/usr/bin/env python3
"""Build a monotonic source-video to edited-reference acoustic EDL."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args, child_output


from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.media import probe_json


from pathlib import Path as _PackagePath
import sys as _package_sys
_PACKAGE_ROOT = _PackagePath(__file__).resolve().parents[3]
if str(_PACKAGE_ROOT) not in _package_sys.path:
    _package_sys.path.insert(0, str(_PACKAGE_ROOT))
from shared.files import sha256 as sha256


import argparse
import csv
import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np


SAMPLE_RATE = 8_000
COARSE_FRAME = 400
FINE_FRAME = 160
FINE_HOP = 80


def run(command: list[str]) -> str:
    return subprocess.run(command, check=True, text=True, capture_output=True).stdout


def probe(path: Path, selector: str, field: str) -> float:
    command = ["ffprobe", "-v", "error"]
    if selector:
        command += ["-select_streams", selector, "-show_entries", f"stream={field}"]
    else:
        command += ["-show_entries", f"format={field}"]
    command += ["-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    value = run(command).strip().splitlines()[0]
    return float(value if value not in {"N/A", ""} else 0)


def probe_media(path):
    return probe_json(path, entries='format=duration,start_time:stream=index,codec_type,start_time,duration,r_frame_rate,avg_frame_rate,time_base')


def ratio(value: str | None) -> float:
    if not value or value in {"0/0", "N/A"}:
        return 0.0
    numerator, denominator = value.split("/", 1)
    return float(numerator) / float(denominator) if float(denominator) else 0.0


def timing_risk(probe_payload: dict) -> dict:
    warnings = []
    video = next((item for item in probe_payload.get("streams", []) if item.get("codec_type") == "video"), {})
    audio = next((item for item in probe_payload.get("streams", []) if item.get("codec_type") == "audio"), {})
    nominal = ratio(video.get("r_frame_rate"))
    average = ratio(video.get("avg_frame_rate"))
    if nominal and average and abs(nominal - average) > max(0.01, nominal * 0.001):
        warnings.append("variable_or_irregular_frame_rate")
    video_start = float(video.get("start_time", 0) or 0)
    audio_start = float(audio.get("start_time", 0) or 0)
    if abs(video_start - audio_start) > 0.02:
        warnings.append("audio_video_stream_start_mismatch")
    if video_start < -0.001 or audio_start < -0.001:
        warnings.append("negative_stream_start_time")
    return {
        "nominal_frame_rate": nominal,
        "average_frame_rate": average,
        "video_start_seconds": video_start,
        "audio_start_seconds": audio_start,
        "warnings": warnings,
        "requires_seek_calibration": bool(warnings),
    }




def clock(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    total, milli = divmod(milliseconds, 1000)
    hour, rem = divmod(total, 3600)
    minute, second = divmod(rem, 60)
    return f"{hour:02d}:{minute:02d}:{second:02d}.{milli:03d}"


def extract_pcm(media: Path, destination: Path) -> None:
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(media), "-map", "0:a:0",
            "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", str(destination),
        ],
        check=True,
    )


def spectral_features(path: Path, frame: int, hop: int) -> np.ndarray:
    samples = np.fromfile(path, dtype="<i2").astype(np.float32)
    if len(samples) < frame:
        raise ValueError(f"PCM is too short: {path}")
    windows = np.lib.stride_tricks.sliding_window_view(samples, frame)[::hop]
    window = np.hanning(frame).astype(np.float32)
    edges_hz = np.array([0, 100, 200, 400, 700, 1100, 1700, 2500, 4000])
    edges = np.minimum((edges_hz / (SAMPLE_RATE / frame)).astype(int), frame // 2)
    output = np.empty((len(windows), 10), dtype=np.float32)
    for start in range(0, len(windows), 20_000):
        stop = min(len(windows), start + 20_000)
        chunk = np.asarray(windows[start:stop])
        spectrum = np.abs(np.fft.rfft(chunk * window, axis=1)) ** 2 + 1.0
        bands = []
        for left, right in zip(edges[:-1], edges[1:]):
            bands.append(np.log1p(spectrum[:, left:max(left + 1, right)].mean(axis=1)))
        matrix = np.stack(bands, axis=1)
        output[start:stop, 0] = np.log1p(np.sqrt(np.mean(chunk * chunk, axis=1)))
        output[start:stop, 1:9] = matrix - matrix.mean(axis=1, keepdims=True)
        output[start:stop, 9] = np.mean((chunk[:, 1:] >= 0) != (chunk[:, :-1] >= 0), axis=1)
    return output


def correlation_scores(source: np.ndarray, query: np.ndarray) -> np.ndarray:
    dimensions = []
    length = len(query)
    for dimension in range(source.shape[1]):
        needle = query[:, dimension].astype(np.float64)
        needle -= needle.mean()
        needle_energy = float(needle @ needle)
        if needle_energy < 1e-10:
            continue
        haystack = source[:, dimension].astype(np.float64)
        numerator = np.correlate(haystack, needle, mode="valid")
        cumulative = np.r_[0.0, np.cumsum(haystack)]
        cumulative_sq = np.r_[0.0, np.cumsum(haystack * haystack)]
        local_sum = cumulative[length:] - cumulative[:-length]
        local_sq = cumulative_sq[length:] - cumulative_sq[:-length]
        local_energy = np.maximum(local_sq - local_sum * local_sum / length, 1e-8)
        dimensions.append(numerator / np.sqrt(local_energy * needle_energy))
    return np.mean(dimensions, axis=0) if dimensions else np.full(len(source) - length + 1, -1.0)


def best_match(source: np.ndarray, query: np.ndarray, low: int, high: int) -> tuple[int, float]:
    low = max(0, int(low))
    high = min(len(source) - len(query), int(high))
    if high <= low:
        return low, -1.0
    scores = correlation_scores(source[low:high + len(query)], query)
    index = int(np.argmax(scores))
    return low + index, float(scores[index])


@dataclass
class Run:
    start_second: int
    end_second: int
    offset_seconds: float
    count: int
    median_score: float
    anchors: list[tuple[int, int, float]]


def establish_initial_anchor(source: np.ndarray, reference: np.ndarray) -> tuple[int, float, dict]:
    """Require several overlapping opening anchors to agree before tracking."""
    candidates = []
    for start_second in (0.0, 0.5, 1.0):
        start = round(start_second * 20)
        for duration_second in (4.0, 5.0, 6.0):
            stop = start + round(duration_second * 20)
            if stop > len(reference):
                continue
            query = reference[start:stop]
            scores = correlation_scores(source, query)
            best = int(np.argmax(scores))
            exclusion = 40
            alternate = scores.copy()
            alternate[max(0, best - exclusion):best + exclusion + 1] = -1.0
            second = float(np.max(alternate)) if len(alternate) else -1.0
            candidates.append({
                "reference_start_seconds": start_second,
                "duration_seconds": duration_second,
                "source_start_frame": best,
                "offset_frames": best - start,
                "score": float(scores[best]),
                "second_best_score": second,
                "score_margin": float(scores[best]) - second,
            })
    clusters: list[list[dict]] = []
    for candidate in sorted(candidates, key=lambda item: item["offset_frames"]):
        if clusters and abs(candidate["offset_frames"] - float(np.median(
                [item["offset_frames"] for item in clusters[-1]]))) <= 5:
            clusters[-1].append(candidate)
        else:
            clusters.append([candidate])
    clusters.sort(key=lambda group: (
        len({item["reference_start_seconds"] for item in group}),
        len({item["duration_seconds"] for item in group}),
        sum(item["score"] + max(item["score_margin"], 0) for item in group),
    ), reverse=True)
    if not clusters:
        raise RuntimeError("No opening acoustic anchor candidates were produced")
    best = clusters[0]
    offsets = [item["offset_frames"] for item in best]
    median_score = float(np.median([item["score"] for item in best]))
    median_margin = float(np.median([item["score_margin"] for item in best]))
    distinct_starts = len({item["reference_start_seconds"] for item in best})
    distinct_lengths = len({item["duration_seconds"] for item in best})
    if (len(best) < 3 or distinct_starts < 2 or distinct_lengths < 2 or
            max(offsets) - min(offsets) > 5 or median_score < 0.50 or median_margin < 0.01):
        raise RuntimeError(
            "Opening anchors are ambiguous; stop instead of emitting a structurally valid but unsafe EDL"
        )
    offset = round(float(np.median(offsets)))
    diagnostics = {
        "method": "multi_length_multi_position_opening_consensus",
        "offset_seconds": round(offset / 20, 3),
        "support_count": len(best),
        "distinct_reference_starts": distinct_starts,
        "distinct_query_lengths": distinct_lengths,
        "offset_spread_seconds": round((max(offsets) - min(offsets)) / 20, 3),
        "median_score": round(median_score, 6),
        "median_score_margin": round(median_margin, 6),
        "candidates": [{**item, "score": round(item["score"], 6),
                         "second_best_score": round(item["second_best_score"], 6),
                         "score_margin": round(item["score_margin"], 6)} for item in candidates],
    }
    return offset, median_score, diagnostics


def track_anchors(source: np.ndarray, reference: np.ndarray) -> tuple[list[tuple[int, int | None, float]], dict]:
    last_source, seed_score, seed = establish_initial_anchor(source, reference)
    last_reference = 0
    anchors: list[tuple[int, int | None, float]] = [(0, last_source, seed_score)]
    pending: list[tuple[int, int, float, int]] = []
    for second in range(1, int(len(reference) / 20) - 3):
        reference_frame = second * 20
        query = reference[reference_frame:reference_frame + 50]
        predicted = last_source + reference_frame - last_reference
        position, score = best_match(source, query, predicted - 100, predicted + 240)
        local_threshold = 0.40 if second <= 5 else 0.58
        if score >= local_threshold:
            last_source, last_reference = position, reference_frame
            anchors.append((second, position, score))
            pending = []
            continue
        anchors.append((second, None, score))
        expanded, expanded_score = best_match(source, query, predicted - 100, predicted + 4_000)
        candidate = (second, expanded, expanded_score, reference_frame)
        candidate_offset = expanded - reference_frame
        if expanded_score < 0.58 or candidate_offset < (last_source - last_reference) - 3:
            pending = []
            continue
        if pending:
            previous_offset = pending[-1][1] - pending[-1][3]
            if second == pending[-1][0] + 1 and abs(candidate_offset - previous_offset) <= 5:
                pending.append(candidate)
            else:
                pending = [candidate]
        else:
            pending = [candidate]
        if len(pending) >= 2:
            for pending_second, pending_position, pending_score, _ in pending:
                anchors[pending_second] = (pending_second, pending_position, pending_score)
            last_source, last_reference = expanded, reference_frame
            pending = []
    return anchors, seed


def build_runs(anchors: list[tuple[int, int | None, float]], seed: dict | None = None) -> list[Run]:
    high = []
    for second, position, score in anchors:
        if position is not None and score >= 0.64:
            high.append((second, position, round((position - second * 20) / 20, 2), score))
    raw, current = [], []
    for anchor in high:
        median = float(np.median([item[2] for item in current])) if current else anchor[2]
        if not current or abs(anchor[2] - median) <= 0.15:
            current.append(anchor)
        else:
            if len(current) >= 2:
                raw.append(current)
            current = [anchor]
    if len(current) >= 2:
        raw.append(current)
    runs = [
        Run(items[0][0], items[-1][0], round(float(np.median([x[2] for x in items])), 3),
            len(items), round(float(np.median([x[3] for x in items])), 6),
            [(x[0], x[1], x[3]) for x in items])
        for items in raw
    ]
    changed = True
    while changed:
        changed = False
        for index in range(len(runs) - 1):
            if runs[index].offset_seconds <= runs[index + 1].offset_seconds + 0.15:
                continue
            left = runs[index].count * max(runs[index].median_score - 0.60, 0.01)
            right = runs[index + 1].count * max(runs[index + 1].median_score - 0.60, 0.01)
            del runs[index if left < right else index + 1]
            changed = True
            break
    merged = []
    for item in runs:
        if merged and abs(item.offset_seconds - merged[-1].offset_seconds) <= 0.15:
            previous = merged.pop()
            joined = previous.anchors + item.anchors
            offsets = [(position - second * 20) / 20 for second, position, _ in joined]
            merged.append(Run(previous.start_second, item.end_second, round(float(np.median(offsets)), 3),
                              previous.count + item.count,
                              round(float(np.median([score for _, _, score in joined])), 6), joined))
        else:
            merged.append(item)
    if seed:
        seed_offset = float(seed["offset_seconds"])
        seed_anchors = []
        for second, position, score in anchors:
            if position is not None and abs((position - second * 20) / 20 - seed_offset) <= 0.25:
                seed_anchors.append((second, position, score))
            elif second > 0 and position is not None:
                break
        if seed_anchors and (not merged or abs(merged[0].offset_seconds - seed_offset) > 0.25):
            seed_run = Run(
                0, seed_anchors[-1][0], round(seed_offset, 3),
                max(len(seed_anchors), int(seed.get("support_count", 1))),
                round(float(np.median([item[2] for item in seed_anchors])), 6), seed_anchors,
            )
            merged.insert(0, seed_run)
    return merged


def refine_offsets(source: np.ndarray, reference: np.ndarray, runs: list[Run]) -> list[float]:
    offsets = []
    for item in runs:
        if len(item.anchors) <= 9:
            chosen = item.anchors
        else:
            indices = np.linspace(0, len(item.anchors) - 1, 9).round().astype(int)
            chosen = [item.anchors[index] for index in sorted(set(indices))]
        candidates = []
        for second, _, _ in chosen:
            reference_start = second * 100
            query = reference[reference_start:reference_start + 250]
            if len(query) < 250:
                continue
            estimated = reference_start + round(item.offset_seconds * 100)
            position, score = best_match(source, query, estimated - 15, estimated + 15)
            candidates.append(((position - reference_start) / 100, score))
        if not candidates:
            offsets.append(item.offset_seconds)
            continue
        best_score = max(score for _, score in candidates)
        reliable = [offset for offset, score in candidates if score >= max(0.40, best_score - 0.15)]
        offsets.append(round(float(np.median(reliable or [offset for offset, _ in candidates])), 3))
    for index in range(1, len(offsets)):
        offsets[index] = max(offsets[index], offsets[index - 1])
    return offsets


def normalized(features: np.ndarray) -> np.ndarray:
    return (features - features.mean(axis=0, keepdims=True)) / np.maximum(features.std(axis=0, keepdims=True), 1e-6)


def boundary_error(source: np.ndarray, reference: np.ndarray, boundary: int,
                   old_offset: int, new_offset: int, radius: int) -> float:
    if boundary - radius < 0 or boundary + radius >= len(reference):
        return math.inf
    old_source, new_source = boundary + old_offset, boundary + new_offset
    if old_source - radius < 0 or new_source + radius >= len(source):
        return math.inf
    left = reference[boundary - radius:boundary] - source[old_source - radius:old_source]
    right = reference[boundary:boundary + radius] - source[new_source:new_source + radius]
    return float(np.mean(left * left) + np.mean(right * right))


def find_boundaries(source_coarse: np.ndarray, reference_coarse: np.ndarray,
                    source_fine: np.ndarray, reference_fine: np.ndarray,
                    runs: list[Run], offsets: list[float]) -> tuple[list[float], list[dict]]:
    source_coarse, reference_coarse = normalized(source_coarse), normalized(reference_coarse)
    source_fine, reference_fine = normalized(source_fine), normalized(reference_fine)
    boundaries, diagnostics = [], []
    for index in range(len(runs) - 1):
        old_offset, new_offset = round(offsets[index] * 20), round(offsets[index + 1] * 20)
        low = max(20, runs[index].end_second * 20)
        high = min(len(reference_coarse) - 20, runs[index + 1].start_second * 20)
        high = max(high, low + 1)
        coarse = min(range(low, high + 1), key=lambda value: boundary_error(
            source_coarse, reference_coarse, value, old_offset, new_offset, 20))
        old_fine, new_fine = round(offsets[index] * 100), round(offsets[index + 1] * 100)
        switch_low = max(100, runs[index].end_second * 100)
        switch_high = min(len(reference_fine) - 170, runs[index + 1].start_second * 100)
        window = 150
        advantages = []
        for candidate in range(switch_low, max(switch_low, switch_high) + 1):
            old_start, new_start = candidate + old_fine, candidate + new_fine
            if old_start < 0 or new_start < 0 or max(old_start, new_start) + window >= len(source_fine):
                continue
            reference_window = reference_fine[candidate:candidate + window]
            old_error = float(np.mean((reference_window - source_fine[old_start:old_start + window]) ** 2))
            new_error = float(np.mean((reference_window - source_fine[new_start:new_start + window]) ** 2))
            advantages.append((candidate, old_error - new_error))
        center = coarse * 5
        candidates = range(max(100, center - 120), min(len(reference_fine) - 100, center + 121))
        fine = min(candidates, key=lambda value: boundary_error(
            source_fine, reference_fine, value, old_fine, new_fine, 100))
        method = "minimum_two_sided_error"
        confidence = ("low" if runs[index].count < 3 or runs[index + 1].count < 3 or
                      min(runs[index].median_score, runs[index + 1].median_score) < 0.68 else "high")
        boundaries.append(round(fine / 100, 3))
        diagnostics.append({
            "cut_index": index + 1, "boundary_seconds": round(fine / 100, 3),
            "method": method, "confidence": confidence,
            "old_offset_seconds": offsets[index], "new_offset_seconds": offsets[index + 1],
            "maximum_state_advantage": round(max((value for _, value in advantages), default=-1.0), 6),
        })
    return boundaries, diagnostics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-video", required=True, type=Path)
    parser.add_argument("--reference-audio", required=True, type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--job-id", default="reference-conform-v01")
    parser.add_argument("--source-audio-start", type=float)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--soft-frames", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--skip-hashes", action="store_true")
    parser.add_argument("--force", action="store_true", help="Replace EDL metadata and feature caches, never source media")
    args = parser.parse_args()
    protect_output_args(args)

    source, reference, root = args.source_video.resolve(), args.reference_audio.resolve(), args.project_root.resolve()
    if Path(args.job_id).name != args.job_id or args.job_id in {"", ".", ".."}:
        raise SystemExit("job-id must be one safe path component")
    for path in (source, reference):
        if not path.is_file():
            raise SystemExit(f"Missing input: {path}")
    work = child_output(root, f"work/{args.job_id}", source, reference)
    manifests = child_output(root, "manifests", source, reference)
    manifest_path = child_output(root, f"manifests/{args.job_id}.json", source, reference)
    csv_path = child_output(root, f"manifests/{args.job_id}-edl.csv", source, reference)
    if not args.force and (manifest_path.exists() or csv_path.exists()):
        raise SystemExit("Refusing to overwrite existing EDL outputs; choose a new job id")
    audio_dir, feature_dir, qa_dir = work / "audio", work / "features", work / "qa"
    for directory in (audio_dir, feature_dir, qa_dir):
        child_output(root, directory.relative_to(root), source, reference)
    planned_names = [f"work/{args.job_id}/audio/{args.job_id}-{role}-8k-mono.pcm" for role in ('source', 'reference')]
    planned_names += [f"work/{args.job_id}/features/{args.job_id}-{role}-{grid}.npy" for role in ('source', 'reference') for grid in ('coarse-50ms', 'fine-10ms')]
    for name in planned_names: child_output(root, name, source, reference)
    for directory in (manifests, audio_dir, feature_dir, qa_dir):
        directory.mkdir(parents=True, exist_ok=True)
    source_pcm = audio_dir / f"{args.job_id}-source-8k-mono.pcm"
    reference_pcm = audio_dir / f"{args.job_id}-reference-8k-mono.pcm"
    if args.force:
        source_pcm.unlink(missing_ok=True)
        reference_pcm.unlink(missing_ok=True)
    extract_pcm(source, source_pcm)
    extract_pcm(reference, reference_pcm)

    source_coarse = spectral_features(source_pcm, COARSE_FRAME, COARSE_FRAME)
    reference_coarse = spectral_features(reference_pcm, COARSE_FRAME, COARSE_FRAME)
    source_fine = spectral_features(source_pcm, FINE_FRAME, FINE_HOP)
    reference_fine = spectral_features(reference_pcm, FINE_FRAME, FINE_HOP)
    np.save(feature_dir / f"{args.job_id}-source-coarse-50ms.npy", source_coarse)
    np.save(feature_dir / f"{args.job_id}-reference-coarse-50ms.npy", reference_coarse)
    np.save(feature_dir / f"{args.job_id}-source-fine-10ms.npy", source_fine)
    np.save(feature_dir / f"{args.job_id}-reference-fine-10ms.npy", reference_fine)

    anchors, seed = track_anchors(source_coarse, reference_coarse)
    runs = build_runs(anchors, seed)
    if len(runs) < 1:
        raise RuntimeError("No stable monotonic acoustic mapping was found")
    offsets = refine_offsets(source_fine, reference_fine, runs)
    boundaries, boundary_diagnostics = find_boundaries(
        source_coarse, reference_coarse, source_fine, reference_fine, runs, offsets)
    reference_duration = probe(reference, "", "duration")
    source_duration = probe(source, "", "duration")
    source_probe = probe_media(source)
    source_timing = timing_risk(source_probe)
    source_audio_start = args.source_audio_start
    if source_audio_start is None:
        source_audio_start = probe(source, "a:0", "start_time")
    reference_starts, reference_ends = [0.0] + boundaries, boundaries + [reference_duration]
    segments, cuts = [], []
    for index, (reference_in, reference_out, offset) in enumerate(zip(reference_starts, reference_ends, offsets), 1):
        media_in, media_out = reference_in + offset + source_audio_start, reference_out + offset + source_audio_start
        if media_in < -0.001 or media_out <= media_in:
            raise RuntimeError(f"Invalid mapped segment {index}: {media_in}..{media_out}")
        if media_out > source_duration + 0.05:
            raise RuntimeError(f"Mapped segment {index} exceeds source duration: {media_out} > {source_duration}")
        segment = {
            "index": index,
            "reference_in": clock(reference_in), "reference_out": clock(reference_out),
            "reference_in_seconds": round(reference_in, 6), "reference_out_seconds": round(reference_out, 6),
            "reference_duration": round(reference_out - reference_in, 6),
            "source_media_in": clock(media_in), "source_media_out": clock(media_out),
            "source_media_in_seconds": round(media_in, 6), "source_media_out_seconds": round(media_out, 6),
            "offset_seconds": offset,
        }
        segments.append(segment)
        if index < len(offsets):
            cuts.append({
                "cut_id": f"DIRECT-CUT-{index:03d}", "reference_join": clock(reference_out),
                "reference_join_seconds": round(reference_out, 6),
                "source_remove_in": clock(media_out),
                "source_remove_out": clock(reference_out + offsets[index] + source_audio_start),
                "source_remove_in_seconds": round(media_out, 6),
                "source_remove_out_seconds": round(reference_out + offsets[index] + source_audio_start, 6),
                "removed_duration": round(offsets[index] - offset, 6),
            })
    retained = sum(item["reference_duration"] for item in segments)
    payload = {
        "schema_version": "1.1", "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "job_id": args.job_id, "source_video": str(source), "reference_audio": str(reference),
        "input_sha256": None if args.skip_hashes else {
            "source_video": sha256(source), "reference_audio": sha256(reference),
        },
        "audio_strategy": "reference-audio-continuous", "source_audio_start_seconds": source_audio_start,
        "source_duration_seconds": round(source_duration, 6),
        "reference_duration_seconds": round(reference_duration, 6),
        "source_timing": source_timing,
        "analysis_cache": {"source_pcm": str(source_pcm), "reference_pcm": str(reference_pcm),
                           "sample_rate": SAMPLE_RATE},
        "output_spec": {"fps": args.fps, "soft_frames": args.soft_frames, "video_codec": "h264",
                        "crf": 21, "pixel_format": "yuv420p", "audio_sample_rate": 48000,
                        "audio_channels": 2, "audio_bitrate": "192k", "faststart": True},
        "alignment": {
            "coarse_grid_ms": 50, "fine_grid_ms": 10, "stable_state_count": len(runs),
            "opening_seed": seed,
            "boundary_diagnostics": boundary_diagnostics,
            "low_confidence_cut_indices": [item["cut_index"] for item in boundary_diagnostics
                                           if item["confidence"] != "high"],
            "join_count": len(cuts), "initial_trim_seconds": offsets[0],
            "internal_removed_seconds": round(sum(item["removed_duration"] for item in cuts), 6),
            "retained_duration_seconds": round(retained, 6),
            "duration_error_seconds": round(retained - reference_duration, 6),
        },
        "segments": segments, "cuts": cuts,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(segments[0]))
        writer.writeheader(); writer.writerows(segments)
    print(json.dumps({"manifest": str(manifest_path), **payload["alignment"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
