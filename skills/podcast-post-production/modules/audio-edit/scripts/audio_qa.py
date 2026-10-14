#!/usr/bin/env python3
"""Measure an MP3 or WAV podcast delivery and enforce spoken-word QA targets."""

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args


from pathlib import Path as _PackagePath
import sys as _package_sys
_PACKAGE_ROOT = _PackagePath(__file__).resolve().parents[3]
if str(_PACKAGE_ROOT) not in _package_sys.path:
    _package_sys.path.insert(0, str(_PACKAGE_ROOT))
from shared.media import probe_json


import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def run(command):
    return subprocess.run(command, check=True, capture_output=True, text=True)




def probe(path):
    return probe_json(path, entries='format=duration,size,bit_rate,format_name:stream=codec_name,sample_rate,channels,channel_layout,bit_rate,bits_per_sample,bits_per_raw_sample,sample_fmt')


def loudness(path, target, peak):
    result = run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
            "-af", f"loudnorm=I={target}:TP={peak}:LRA=11:print_format=json",
            "-f", "null", "-",
        ]
    )
    matches = re.findall(r"\{\s*\"input_i\".*?\}", result.stderr, re.S)
    if not matches:
        raise RuntimeError("Could not parse loudnorm analysis")
    return json.loads(matches[-1])


def silence_count(path, threshold, duration):
    result = run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
            "-af", f"silencedetect=noise={threshold}dB:d={duration}",
            "-f", "null", "-",
        ]
    )
    return len(re.findall(r"silence_duration:", result.stderr))


def decode(path):
    run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--target-lufs", type=float, default=-19.0)
    parser.add_argument("--lufs-tolerance", type=float, default=0.5)
    parser.add_argument("--max-true-peak", type=float, default=-1.0)
    parser.add_argument("--expected-bitrate-kbps", type=int, default=128)
    parser.add_argument("--bitrate-tolerance-kbps", type=int, default=2)
    parser.add_argument("--expected-bit-depth", type=int, default=24)
    parser.add_argument("--silence-threshold", type=float, default=-45.0)
    parser.add_argument("--silence-duration", type=float, default=2.0)
    parser.add_argument("--allowed-long-silences", type=int, default=0)
    parser.add_argument("--human-reviewer")
    parser.add_argument("--human-reviewed-at")
    parser.add_argument("--human-approved", action="store_true")
    parser.add_argument("--require-release-ready", action="store_true")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    protect_output_args(args)

    decode(args.audio)
    media = probe(args.audio)
    stats = loudness(args.audio, args.target_lufs, args.max_true_peak)
    long_silences = silence_count(args.audio, args.silence_threshold, args.silence_duration)
    stream = media.get("streams", [{}])[0]
    integrated = float(stats["input_i"])
    true_peak = float(stats["input_tp"])
    bitrate = int(stream.get("bit_rate") or media.get("format", {}).get("bit_rate") or 0)
    expected_bitrate = args.expected_bitrate_kbps * 1000
    bitrate_tolerance = args.bitrate_tolerance_kbps * 1000
    if args.human_approved and (not args.human_reviewer or not args.human_reviewed_at):
        parser.error("--human-approved requires --human-reviewer and --human-reviewed-at")
    codec = str(stream.get("codec_name") or "").lower()
    format_names = {
        item.strip().lower()
        for item in str(media.get("format", {}).get("format_name") or "").split(",")
    }
    if codec == "mp3":
        delivery_format = "mp3"
    elif "wav" in format_names and codec.startswith("pcm_"):
        delivery_format = "wav"
    else:
        delivery_format = "unsupported"
    checks = {
        "complete_decode": True,
        "mono": int(stream.get("channels", 0)) == 1,
        "sample_rate_48000": int(stream.get("sample_rate", 0)) == 48000,
        "integrated_loudness": abs(integrated - args.target_lufs) <= args.lufs_tolerance,
        "true_peak": true_peak <= args.max_true_peak,
        "long_silence_within_allowance": long_silences <= args.allowed_long_silences,
    }
    if delivery_format == "mp3":
        checks["expected_bitrate"] = abs(bitrate - expected_bitrate) <= bitrate_tolerance
    elif delivery_format == "wav":
        reported_depth = int(
            stream.get("bits_per_sample")
            or stream.get("bits_per_raw_sample")
            or 0
        )
        checks["wav_pcm_s24le"] = codec == "pcm_s24le"
        checks["expected_wav_bit_depth"] = reported_depth == args.expected_bit_depth
    else:
        checks["supported_delivery_format"] = False
    technical_passed = all(checks.values())
    human_review = {
        "status": "approved" if args.human_approved else "required",
        "reviewer": args.human_reviewer,
        "reviewed_at": args.human_reviewed_at,
    }
    report = {
        "file": str(args.audio),
        "delivery_format": delivery_format,
        "format": media.get("format", {}),
        "stream": stream,
        "integrated_lufs": integrated,
        "true_peak_dbtp": true_peak,
        "loudness_range_lu": float(stats["input_lra"]),
        "silences_over_limit": long_silences,
        "checks": checks,
        "technical_passed": technical_passed,
        "human_full_length_listen": human_review,
        "release_ready": technical_passed and args.human_approved,
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(output + "\n", encoding="utf-8")
    failed = not technical_passed
    if args.require_release_ready and not report["release_ready"]:
        failed = True
    if failed and not args.report_only:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
