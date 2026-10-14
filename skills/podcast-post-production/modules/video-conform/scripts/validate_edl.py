#!/usr/bin/env python3
"""Validate conform EDL ordering, duration, and an optional rendered output."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args


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
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

from calibrate_fast_seek import ncc


def probe(path):
    return probe_json(path, entries='format=duration:stream=codec_type,codec_name,pix_fmt,width,height,r_frame_rate,nb_frames,sample_rate,channels')




def content_points(segments: list[dict], target: float) -> list[tuple[float, float, str]]:
    points: dict[tuple[int, int], tuple[float, float, str]] = {}
    for segment in segments:
        ref_in, ref_out = float(segment["reference_in_seconds"]), float(segment["reference_out_seconds"])
        source_in = float(segment["source_media_in_seconds"])
        duration = ref_out - ref_in
        margin = min(1.5, duration / 4)
        for position, label in ((ref_in + margin, "segment-start"),
                                ((ref_in + ref_out) / 2, "segment-middle"),
                                (ref_out - margin, "segment-end")):
            if duration >= 0.5:
                source_position = source_in + position - ref_in
                points[(round(position * 100), int(segment["index"]))] = (position, source_position, label)
    for position in np.arange(0.5, min(30.0, target - 0.5) + 0.001, 5.0):
        segment = next((item for item in segments if float(item["reference_in_seconds"]) <= position <
                        float(item["reference_out_seconds"])), None)
        if segment:
            source_position = float(segment["source_media_in_seconds"]) + position - float(segment["reference_in_seconds"])
            points[(round(position * 100), int(segment["index"]))] = (position, source_position, "opening-30s")
    return sorted(points.values())


def compare_content(source_pcm: np.ndarray, reference_pcm: np.ndarray, source_media_second: float,
                    reference_second: float, source_audio_start: float, sample_rate: int,
                    window: float = 1.0, radius: float = 0.20) -> tuple[float, float]:
    query_start = round(reference_second * sample_rate)
    query = np.asarray(reference_pcm[query_start:query_start + round(window * sample_rate)])
    expected_source = source_media_second - source_audio_start
    search_start_second = max(0.0, expected_source - radius)
    search_start = round(search_start_second * sample_rate)
    search_stop = round((expected_source + window + radius) * sample_rate)
    haystack = np.asarray(source_pcm[search_start:search_stop])
    if len(query) < round(window * sample_rate * 0.9) or len(haystack) < len(query):
        return -1.0, 999.0
    scores = ncc(haystack, query)
    best = int(np.argmax(scores))
    actual_source = search_start_second + best / sample_rate
    return float(scores[best]), actual_source - expected_source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--delivery-copy", type=Path)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--content-check", action="store_true")
    parser.add_argument("--source-pcm", type=Path)
    parser.add_argument("--reference-pcm", type=Path)
    parser.add_argument("--minimum-content-correlation", type=float, default=0.20)
    parser.add_argument("--maximum-content-lag", type=float, default=0.12)
    parser.add_argument("--full-decode", action="store_true")
    args = parser.parse_args()
    protect_output_args(args)
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    segments = payload.get("segments", [])
    errors, warnings = [], []
    if not segments:
        errors.append("manifest has no segments")
    previous_ref, previous_source, total = 0.0, -1.0, 0.0
    for expected, segment in enumerate(segments, 1):
        index = int(segment.get("index", -1))
        ref_in, ref_out = float(segment["reference_in_seconds"]), float(segment["reference_out_seconds"])
        source_in, source_out = float(segment["source_media_in_seconds"]), float(segment["source_media_out_seconds"])
        duration = float(segment["reference_duration"])
        if index != expected:
            errors.append(f"segment {expected}: index is {index}")
        if abs(ref_in - previous_ref) > 0.001:
            errors.append(f"segment {expected}: reference gap/overlap {ref_in - previous_ref:+.6f}s")
        if ref_out <= ref_in or source_out <= source_in or duration <= 0:
            errors.append(f"segment {expected}: non-positive interval")
        if previous_source >= 0 and source_in < previous_source - 0.001:
            errors.append(f"segment {expected}: source overlap or backward mapping")
        if abs((ref_out - ref_in) - duration) > 0.001:
            errors.append(f"segment {expected}: duration field mismatch")
        if duration * args.fps <= 3:
            warnings.append(f"segment {expected}: shorter than default three-frame join handle")
        previous_ref, previous_source, total = ref_out, source_out, total + duration
    target = float(payload.get("reference_duration_seconds", 0))
    if abs(previous_ref - target) > 0.001 or abs(total - target) > 0.001:
        errors.append(f"EDL/reference duration mismatch: end={previous_ref:.6f}, sum={total:.6f}, target={target:.6f}")
    content_report = None
    if args.content_check and segments:
        cache = payload.get("analysis_cache", {})
        source_pcm_path = args.source_pcm or Path(cache.get("source_pcm", ""))
        reference_pcm_path = args.reference_pcm or Path(cache.get("reference_pcm", ""))
        if not source_pcm_path.is_file() or not reference_pcm_path.is_file():
            errors.append("content check requires source and reference PCM caches recorded in analysis_cache")
        else:
            sample_rate = int(cache.get("sample_rate", 8000))
            source_pcm = np.memmap(source_pcm_path, dtype="<i2", mode="r")
            reference_pcm = np.memmap(reference_pcm_path, dtype="<i2", mode="r")
            checks, unsafe, low_confidence = [], [], []
            for reference_second, source_second, label in content_points(segments, target):
                correlation, lag = compare_content(
                    source_pcm, reference_pcm, source_second, reference_second,
                    float(payload.get("source_audio_start_seconds", 0.0)), sample_rate,
                )
                row = {"reference_second": round(reference_second, 3),
                       "source_media_second": round(source_second, 3), "label": label,
                       "correlation": round(correlation, 6), "lag_seconds": round(lag, 6)}
                checks.append(row)
                if correlation >= max(0.50, args.minimum_content_correlation) and abs(lag) > args.maximum_content_lag:
                    unsafe.append(row)
                elif correlation < args.minimum_content_correlation or abs(lag) > 0.04:
                    low_confidence.append(row)
            if unsafe:
                errors.append(
                    f"content-aware alignment found {len(unsafe)} high-confidence timing mismatches "
                    f"across {len(checks)} checkpoints"
                )
            opening_first_ten = [item for item in checks if item["label"] == "opening-30s" and
                                 item["reference_second"] <= 10.5]
            opening_reliable = [item for item in opening_first_ten if
                                item["correlation"] >= args.minimum_content_correlation and
                                abs(item["lag_seconds"]) <= args.maximum_content_lag]
            if len(opening_first_ten) >= 3 and len(opening_reliable) < 2:
                errors.append(
                    "opening content check failed: fewer than two of the first three 5-second checkpoints "
                    "support the mapped source time"
                )
            if low_confidence:
                warnings.append(
                    f"content-aware alignment marked {len(low_confidence)} of {len(checks)} checkpoints "
                    "low confidence; review the worst-ranked ranges and all manifest low-confidence joins"
                )
            content_report = {
                "checkpoint_count": len(checks), "unsafe_count": len(unsafe),
                "low_confidence_count": len(low_confidence),
                "minimum_correlation": min((item["correlation"] for item in checks), default=None),
                "maximum_absolute_lag_seconds": max((abs(item["lag_seconds"]) for item in checks), default=None),
                "opening_first_ten_reliable_count": len(opening_reliable),
                "unsafe": unsafe, "low_confidence": low_confidence, "checks": checks,
            }

    output_probe = None
    if args.output:
        output_probe = probe(args.output)
        rendered = float(output_probe["format"]["duration"])
        if abs(rendered - target) > 1 / args.fps:
            errors.append(f"render duration differs by {rendered - target:+.6f}s (>1 frame)")
        types = [stream.get("codec_type") for stream in output_probe.get("streams", [])]
        if "video" not in types or "audio" not in types:
            errors.append("render must contain video and audio")
        spec = payload.get("output_spec", {})
        video = next((stream for stream in output_probe.get("streams", []) if stream.get("codec_type") == "video"), {})
        audio = next((stream for stream in output_probe.get("streams", []) if stream.get("codec_type") == "audio"), {})
        expected_frames = round(target * float(spec.get("fps", args.fps)))
        if int(video.get("nb_frames", -1)) != expected_frames:
            errors.append(f"render frame count is {video.get('nb_frames')}, expected {expected_frames}")
        if video.get("codec_name") != "h264" or video.get("pix_fmt") != "yuv420p":
            errors.append(f"render video format is {video.get('codec_name')}/{video.get('pix_fmt')}, expected h264/yuv420p")
        if audio.get("sample_rate") != str(spec.get("audio_sample_rate", 48000)) or int(audio.get("channels", 0)) != int(spec.get("audio_channels", 2)):
            errors.append("render audio must be 48 kHz stereo")
        if args.full_decode:
            decode = subprocess.run([
                "ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-i", str(args.output),
                "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-",
            ], capture_output=True, text=True)
            if decode.returncode:
                errors.append(f"full decode failed: {decode.stderr[-500:]}")
    delivery_hashes = None
    if args.delivery_copy:
        if not args.output:
            errors.append("--delivery-copy requires --output")
        elif not args.delivery_copy.is_file():
            errors.append(f"delivery copy is missing: {args.delivery_copy}")
        else:
            version_hash, delivery_hash = sha256(args.output), sha256(args.delivery_copy)
            delivery_hashes = {"version": version_hash, "delivery": delivery_hash,
                               "identical": version_hash == delivery_hash}
            if version_hash != delivery_hash:
                errors.append("version and delivery hashes differ")
    report = {"ok": not errors, "segments": len(segments), "target_duration_seconds": target,
              "errors": errors, "warnings": warnings, "content_check": content_report,
              "output_probe": output_probe, "delivery_hashes": delivery_hashes}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
