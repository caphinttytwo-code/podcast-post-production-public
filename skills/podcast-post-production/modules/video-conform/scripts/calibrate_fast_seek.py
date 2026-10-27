#!/usr/bin/env python3
"""Calibrate ffmpeg input-seek timestamps against continuously decoded source PCM."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args


import argparse
import json
import subprocess
from pathlib import Path

import numpy as np


SAMPLE_RATE = 8_000


def ncc(source: np.ndarray, query: np.ndarray) -> np.ndarray:
    source = source.astype(np.float64)
    query = query.astype(np.float64)
    query -= query.mean()
    length = len(query)
    if len(source) < length or length < 2:
        raise ValueError("Correlation window is shorter than the query")
    fft_size = 1 << (len(source) + length - 2).bit_length()
    numerator = np.fft.irfft(
        np.fft.rfft(source, fft_size) * np.fft.rfft(query[::-1], fft_size), fft_size
    )[length - 1:len(source)]
    cumulative = np.r_[0.0, np.cumsum(source)]
    cumulative_sq = np.r_[0.0, np.cumsum(source * source)]
    local_sum = cumulative[length:] - cumulative[:-length]
    local_sq = cumulative_sq[length:] - cumulative_sq[:-length]
    local_energy = np.maximum(local_sq - local_sum * local_sum / length, 1e-8)
    query_energy = max(float(query @ query), 1e-8)
    return numerator / np.sqrt(local_energy * query_energy)


def fast_seek_audio(source_media: Path, seek_second: float, duration: float = 8.0) -> np.ndarray:
    result = subprocess.run([
        "ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error",
        "-ss", f"{seek_second:.6f}", "-t", f"{duration:.6f}", "-i", str(source_media),
        "-map", "0:a:0", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "pipe:1",
    ], check=True, capture_output=True)
    clip = np.frombuffer(result.stdout, dtype="<i2")
    if len(clip) < SAMPLE_RATE * 3:
        raise RuntimeError(f"Fast-seek probe is too short at {seek_second:.6f}s")
    return clip


def locate(full_pcm: np.ndarray, clip: np.ndarray, expected_pcm_second: float,
           radius: float = 3.0) -> tuple[float, float]:
    query_length = round(2.5 * SAMPLE_RATE)
    offsets = list(range(0, len(clip) - query_length + 1, SAMPLE_RATE))
    if not offsets:
        raise RuntimeError("Fast-seek probe does not contain a complete correlation query")
    query_offset = max(offsets, key=lambda value: float(np.mean(
        clip[value:value + query_length].astype(np.float64) ** 2
    )))
    query = clip[query_offset:query_offset + query_length]
    offset_seconds = query_offset / SAMPLE_RATE
    search_start = max(0.0, expected_pcm_second + offset_seconds - radius)
    search_end = min(
        len(full_pcm) / SAMPLE_RATE,
        expected_pcm_second + offset_seconds + radius + len(query) / SAMPLE_RATE,
    )
    haystack = full_pcm[round(search_start * SAMPLE_RATE):round(search_end * SAMPLE_RATE)]
    scores = ncc(haystack, query)
    best = int(np.argmax(scores))
    return search_start + best / SAMPLE_RATE - offset_seconds, float(scores[best])


def calibrate(source_media: Path, full_pcm: np.ndarray, desired_media_second: float,
              pcm_start_second: float = 0.0) -> dict:
    expected_pcm_second = desired_media_second - pcm_start_second
    if expected_pcm_second < 0:
        raise ValueError("Desired media time precedes the decoded audio stream")
    first_clip = fast_seek_audio(source_media, desired_media_second)
    first_actual_pcm, first_score = locate(full_pcm, first_clip, expected_pcm_second)
    first_actual_media = first_actual_pcm + pcm_start_second
    first_error = first_actual_media - desired_media_second
    corrected_seek = max(0.0, desired_media_second - first_error)
    iterations = []
    verify_actual_media = first_actual_media
    verify_score = first_score
    residual = first_error
    for _ in range(4):
        verify_clip = fast_seek_audio(source_media, corrected_seek)
        verify_actual_pcm, verify_score = locate(full_pcm, verify_clip, expected_pcm_second)
        verify_actual_media = verify_actual_pcm + pcm_start_second
        residual = verify_actual_media - desired_media_second
        iterations.append({
            "seek_second": round(corrected_seek, 6),
            "actual_media_second": round(verify_actual_media, 6),
            "residual_error_seconds": round(residual, 6),
            "correlation": round(verify_score, 6),
        })
        if abs(residual) <= 0.001:
            break
        corrected_seek = max(0.0, corrected_seek - residual)
    return {
        "desired_source_second": round(desired_media_second, 6),
        "uncorrected_actual_second": round(first_actual_media, 6),
        "uncorrected_error_seconds": round(first_error, 6),
        "uncorrected_correlation": round(first_score, 6),
        "corrected_seek_second": round(corrected_seek, 6),
        "verified_actual_second": round(verify_actual_media, 6),
        "residual_error_seconds": round(residual, 6),
        "verified_correlation": round(verify_score, 6),
        "iterations": iterations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_media", type=Path)
    parser.add_argument("source_pcm", type=Path)
    parser.add_argument("--time", type=float, action="append", required=True)
    parser.add_argument("--pcm-start", type=float, default=0.0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    protect_output_args(args)
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite seek calibration: {args.output}")
    full_pcm = np.memmap(args.source_pcm, dtype="<i2", mode="r")
    rows = [calibrate(args.source_media, full_pcm, value, args.pcm_start) for value in args.time]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "rows": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
