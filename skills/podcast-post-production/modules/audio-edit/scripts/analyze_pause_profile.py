#!/usr/bin/env python3
"""Compare aggregate pause profiles without emitting transcript text or source identifiers."""

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args


import argparse
import json
import math
import re
import subprocess
import sys
import unicodedata
from array import array
from difflib import SequenceMatcher
from pathlib import Path


FRAME_SECONDS = 0.02
SAMPLE_RATE = 8000
MIN_GAP_SECONDS = 0.08
MAX_GAP_SECONDS = 30.0


def load_events(path):
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raise ValueError("could not read transcript input") from None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("transcript input is not valid JSON") from None
    chunks = data.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("StepAudio transcript must contain a chunks list")
    events = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise ValueError("transcript chunk must be an object")
        try:
            offset = float(chunk.get("offset_ms", 0)) / 1000.0
        except (TypeError, ValueError):
            raise ValueError("transcript chunk has invalid timing") from None
        for event in chunk.get("events", []):
            if not isinstance(event, dict):
                raise ValueError("transcript event must be an object")
            if event.get("type") != "transcript.text.delta":
                continue
            try:
                start = offset + float(event["start_time"]) / 1000.0
                end = offset + float(event["end_time"]) / 1000.0
            except (KeyError, TypeError, ValueError):
                raise ValueError("transcript event has invalid timing") from None
            if end < start:
                raise ValueError("Transcript event end_time precedes start_time")
            events.append((start, end, str(event.get("delta", ""))))
    events.sort(key=lambda item: (item[0], item[1]))
    return events


def normalized_text(events):
    text = unicodedata.normalize("NFKC", "".join(item[2] for item in events)).lower()
    return "".join(
        char for char in text if re.match(r"[\u3400-\u9fffA-Za-z0-9]", char)
    )


def role_for(text):
    if re.search(r"[\u3002\uff01\uff1f?!]$", text):
        return "sentence"
    if re.search(r"[\uff0c\u3001\uff1b;\uff1a:]$", text):
        return "clause"
    return "intra-clause"


def percentile(values, value):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * value / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def summarize(values):
    return {
        "count": len(values),
        "total_seconds": round(sum(values), 3),
        "p25_seconds": round(percentile(values, 25), 3) if values else None,
        "median_seconds": round(percentile(values, 50), 3) if values else None,
        "p75_seconds": round(percentile(values, 75), 3) if values else None,
        "p90_seconds": round(percentile(values, 90), 3) if values else None,
        "above_1_second": sum(value > 1.0 for value in values),
        "above_2_seconds": sum(value > 2.0 for value in values),
    }


def gap_profile(events):
    roles = {"all": [], "intra-clause": [], "clause": [], "sentence": []}
    for previous, current in zip(events, events[1:]):
        gap = current[0] - previous[1]
        if gap < MIN_GAP_SECONDS or gap > MAX_GAP_SECONDS:
            continue
        role = role_for(previous[2])
        roles["all"].append(gap)
        roles[role].append(gap)
    return {role: summarize(values) for role, values in roles.items()}


def decode_audio(path):
    command = [
        "ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le",
        "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-",
    ]
    try:
        result = subprocess.run(command, capture_output=True)
    except OSError:
        raise ValueError("audio decoder is unavailable") from None
    if result.returncode != 0:
        raise ValueError("audio decoding failed")
    samples = array("h")
    samples.frombytes(result.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def frame_levels(samples):
    frame_size = int(SAMPLE_RATE * FRAME_SECONDS)
    levels = []
    usable = len(samples) - len(samples) % frame_size
    for start in range(0, usable, frame_size):
        frame = samples[start:start + frame_size]
        mean_square = sum(sample * sample for sample in frame) / frame_size
        levels.append(20.0 * math.log10(max(math.sqrt(mean_square) / 32768.0, 1e-12)))
    return levels


def energy_profile(base_path, reference_path, thresholds):
    base_samples = decode_audio(base_path)
    reference_samples = decode_audio(reference_path)
    base_levels = frame_levels(base_samples)
    reference_levels = frame_levels(reference_samples)
    if not base_levels or not reference_levels:
        raise ValueError("Audio contains no complete analysis frames")
    level_shift = percentile(base_levels, 90) - percentile(reference_levels, 90)
    normalized_reference = [value + level_shift for value in reference_levels]
    measurements = []
    for threshold in thresholds:
        base_seconds = sum(value < threshold for value in base_levels) * FRAME_SECONDS
        reference_seconds = sum(value < threshold for value in normalized_reference) * FRAME_SECONDS
        measurements.append({
            "threshold_dbfs": threshold,
            "base_low_energy_seconds": round(base_seconds, 3),
            "reference_low_energy_seconds": round(reference_seconds, 3),
            "difference_seconds": round(base_seconds - reference_seconds, 3),
        })
    return {
        "analysis_sample_rate": SAMPLE_RATE,
        "frame_seconds": FRAME_SECONDS,
        "reference_level_shift_db": round(level_shift, 3),
        "base_duration_seconds": round(len(base_samples) / SAMPLE_RATE, 3),
        "reference_duration_seconds": round(len(reference_samples) / SAMPLE_RATE, 3),
        "threshold_measurements": measurements,
    }


def parse_thresholds(value):
    try:
        thresholds = [float(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("thresholds must be comma-separated numbers") from exc
    if not thresholds:
        raise argparse.ArgumentTypeError("at least one threshold is required")
    return thresholds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_transcript", type=Path)
    parser.add_argument("reference_transcript", type=Path)
    parser.add_argument("--base-audio", type=Path)
    parser.add_argument("--reference-audio", type=Path)
    parser.add_argument("--energy-thresholds", type=parse_thresholds, default=[-45.0, -40.0, -38.0])
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    protect_output_args(args)
    if (args.base_audio is None) != (args.reference_audio is None):
        parser.error("--base-audio and --reference-audio must be supplied together")

    base_events = load_events(args.base_transcript)
    reference_events = load_events(args.reference_transcript)
    base_text = normalized_text(base_events)
    reference_text = normalized_text(reference_events)
    matcher = SequenceMatcher(None, base_text, reference_text, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    report = {
        "schema_version": 1,
        "privacy": {
            "aggregate_only": True,
            "contains_transcript_text": False,
            "contains_source_identifiers": False,
        },
        "transcript": {
            "base_characters": len(base_text),
            "reference_characters": len(reference_text),
            "matched_characters": matched,
            "retained_text_rate": round(matched / len(base_text), 6) if base_text else None,
            "sequence_similarity": round(matcher.ratio(), 6),
        },
        "pause_profiles": {
            "base": gap_profile(base_events),
            "reference": gap_profile(reference_events),
        },
    }
    if args.base_audio:
        report["audio_energy"] = energy_profile(
            args.base_audio, args.reference_audio, args.energy_thresholds
        )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json_out:
        try:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(rendered, encoding="utf-8")
        except OSError:
            raise ValueError("could not write aggregate report") from None
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        raise SystemExit(f"pause profile analysis failed: {exc}") from exc
