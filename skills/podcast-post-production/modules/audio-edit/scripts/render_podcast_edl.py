#!/usr/bin/env python3
"""Render a removal EDL and master a podcast to MP3, WAV, or both."""

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args


import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


DEFAULTS = {
    "crossfade_seconds": 0.02,
    "pre_gain_db": -3.0,
    "highpass_hz": 65,
    "target_lufs": -19.0,
    "true_peak_dbtp": -1.2,
    "sample_rate": 48000,
    "channels": 1,
    "bitrate_kbps": 128,
    "wav_bit_depth": 24,
}

SUPPORTED_EDL_VERSIONS = {1, 2, 3}
PAUSE_CATEGORIES = {"pause-compression", "content-with-pause-trim"}
PAUSE_ROLES = {"intra-clause", "clause", "sentence", "section", "rhetorical"}
EDITORIAL_PASSES = {"mechanical", "semantic", "pause"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
REVIEW_ACTIONS = {"remove", "compress", "keep"}
REVIEW_STATUSES = {"pending", "rejected"}
RISK_FLAGS = {"meaning", "logic", "reference", "emotion", "persona", "rhythm", "boundary"}


def run(command):
    return subprocess.run(command, check=True, capture_output=True, text=True)


def duration(path):
    result = run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
    )
    return float(result.stdout.strip())


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
        raise RuntimeError("Could not parse loudnorm output")
    return json.loads(matches[-1])


def normalized_cuts(items, source_duration):
    cuts = []
    for index, item in enumerate(items):
        start = float(item["start"])
        end = float(item["end"])
        if start < 0 or end <= start or end > source_duration + 0.001:
            raise ValueError(f"Invalid cut #{index + 1}: {start}..{end}")
        cuts.append({"start": start, "end": min(end, source_duration)})
    cuts.sort(key=lambda item: item["start"])
    merged = []
    for item in cuts:
        if merged and item["start"] <= merged[-1]["end"] + 0.1:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
        else:
            merged.append(dict(item))
    return merged


def keep_segments(cuts, source_duration):
    keep = []
    cursor = 0.0
    for item in cuts:
        if item["start"] > cursor:
            keep.append((cursor, item["start"]))
        cursor = max(cursor, item["end"])
    if cursor < source_duration:
        keep.append((cursor, source_duration))
    return keep


def filtergraph(keep, config):
    fade = float(config["crossfade_seconds"])
    graph = []
    for index, (start, end) in enumerate(keep):
        graph.append(f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[s{index}]")
    current = "s0"
    for index in range(1, len(keep)):
        out = f"x{index}"
        graph.append(f"[{current}][s{index}]acrossfade=d={fade:.3f}:c1=tri:c2=tri[{out}]")
        current = out
    tail = f"[{current}]volume={float(config['pre_gain_db']):.3f}dB"
    highpass = int(config["highpass_hz"])
    if highpass > 0:
        tail += f",highpass=f={highpass}:p=2"
    graph.append(tail + "[outa]")
    return ";\n".join(graph) + "\n"


def master_filter(measured, config, correction=0.0):
    target = float(config["target_lufs"])
    peak = float(config["true_peak_dbtp"])
    value = (
        f"loudnorm=I={target}:TP={peak}:LRA=11:"
        f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true"
    )
    if abs(correction) >= 0.01:
        value += f",volume={correction:.3f}dB"
    return value


def encode_mp3(source, output, config, audio_filter=None):
    command = ["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(source)]
    if audio_filter:
        command.extend(["-af", audio_filter])
    command.extend(
        [
            "-ar", str(int(config["sample_rate"])), "-ac", str(int(config["channels"])),
            "-c:a", "libmp3lame", "-b:a", f"{int(config['bitrate_kbps'])}k",
            "-id3v2_version", "3", str(output),
        ]
    )
    run(command)


def encode_wav(source, output, config, audio_filter):
    bit_depth = int(config["wav_bit_depth"])
    if bit_depth != 24:
        raise ValueError(f"Unsupported wav_bit_depth: {bit_depth}; expected 24")
    run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(source),
            "-af", audio_filter,
            "-ar", str(int(config["sample_rate"])), "-ac", str(int(config["channels"])),
            "-c:a", "pcm_s24le", str(output),
        ]
    )


def output_format(path):
    suffix = path.suffix.lower()
    if suffix == ".mp3":
        return "mp3"
    if suffix == ".wav":
        return "wav"
    raise ValueError(f"Unsupported output suffix: {path.suffix or '<none>'}; expected .mp3 or .wav")


def validate_deliveries(data, outputs):
    if len(outputs) != len(set(outputs)):
        raise ValueError("Duplicate output path")
    formats = [output_format(path) for path in outputs]
    if len(formats) != len(set(formats)):
        raise ValueError("Duplicate delivery format")
    declared = data.get("delivery_formats")
    if declared is None:
        if formats != ["mp3"]:
            raise ValueError("Legacy EDLs without delivery_formats support one MP3 output only")
        return formats
    if not isinstance(declared, list) or not declared:
        raise ValueError("delivery_formats must be a non-empty list")
    normalized = [str(item).lower() for item in declared]
    if any(item not in {"mp3", "wav"} for item in normalized):
        raise ValueError("delivery_formats accepts only mp3 and wav")
    if len(normalized) != len(set(normalized)):
        raise ValueError("delivery_formats contains duplicates")
    if set(normalized) != set(formats):
        raise ValueError(
            f"Output suffixes {sorted(formats)} do not match delivery_formats {sorted(normalized)}"
        )
    return normalized


def validate_edl(data):
    version = data.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError("EDL version must be an integer")
    if version not in SUPPORTED_EDL_VERSIONS:
        expected = ", ".join(str(item) for item in sorted(SUPPORTED_EDL_VERSIONS))
        raise ValueError(f"Unsupported EDL version: {version}; expected one of {expected}")
    if version == 1:
        return version
    if version == 3:
        branch = data.get("branch")
        if not isinstance(branch, str) or not branch.strip():
            raise ValueError("EDL v3 requires a non-empty branch")
        basis = data.get("transcript_basis")
        if not isinstance(basis, dict):
            raise ValueError("EDL v3 requires transcript_basis")
        for field in ("source", "mechanical"):
            if not isinstance(basis.get(field), str) or not basis[field].strip():
                raise ValueError(f"EDL v3 transcript_basis.{field} must be a non-empty path")
        if basis.get("semantic_based_on") != "mechanical":
            raise ValueError("EDL v3 semantic decisions must be based on the mechanical transcript")
        cuts = data.get("cuts", [])
        if not isinstance(cuts, list):
            raise ValueError("EDL v3 cuts must be a list")
        for index, cut in enumerate(cuts, 1):
            if not isinstance(cut, dict):
                raise ValueError(f"EDL v3 cut #{index} must be an object")
            if cut.get("pass") not in EDITORIAL_PASSES:
                raise ValueError(f"EDL v3 cut #{index} has invalid pass: {cut.get('pass')!r}")
            if cut.get("decision_status") != "approved":
                raise ValueError(f"EDL v3 cut #{index} is not approved")
            if cut.get("confidence") not in CONFIDENCE_LEVELS:
                raise ValueError(
                    f"EDL v3 cut #{index} has invalid confidence: {cut.get('confidence')!r}"
                )
            for field in ("category", "reason"):
                if not isinstance(cut.get(field), str) or not cut[field].strip():
                    raise ValueError(f"EDL v3 cut #{index} requires non-empty {field}")
        candidates = data.get("review_candidates", [])
        if not isinstance(candidates, list):
            raise ValueError("EDL v3 review_candidates must be a list")
        for index, candidate in enumerate(candidates, 1):
            if not isinstance(candidate, dict):
                raise ValueError(f"Review candidate #{index} must be an object")
            try:
                start = float(candidate["start"])
                end = float(candidate["end"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Review candidate #{index} requires numeric start and end"
                ) from exc
            if start < 0 or end <= start:
                raise ValueError(f"Review candidate #{index} has an invalid interval")
            if candidate.get("pass") not in EDITORIAL_PASSES:
                raise ValueError(f"Review candidate #{index} has invalid pass")
            if candidate.get("proposed_action") not in REVIEW_ACTIONS:
                raise ValueError(f"Review candidate #{index} has invalid proposed_action")
            if candidate.get("status") not in REVIEW_STATUSES:
                raise ValueError(f"Review candidate #{index} has invalid status")
            if candidate.get("confidence") not in CONFIDENCE_LEVELS:
                raise ValueError(f"Review candidate #{index} has invalid confidence")
            for field in ("category", "reason"):
                if not isinstance(candidate.get(field), str) or not candidate[field].strip():
                    raise ValueError(f"Review candidate #{index} requires non-empty {field}")
            risks = candidate.get("risk_flags")
            if (
                not isinstance(risks, list)
                or not risks
                or any(risk not in RISK_FLAGS for risk in risks)
            ):
                raise ValueError(f"Review candidate #{index} has invalid risk_flags")
    for index, cut in enumerate(data.get("cuts", []), 1):
        if cut.get("category") not in PAUSE_CATEGORIES:
            continue
        role = cut.get("pause_role")
        if role not in PAUSE_ROLES:
            raise ValueError(f"Pause cut #{index} has invalid pause_role: {role!r}")
        try:
            original = float(cut["original_gap_seconds"])
            retained = float(cut["retained_gap_seconds"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Pause cut #{index} requires numeric original_gap_seconds and retained_gap_seconds"
            ) from exc
        if original < 0 or retained < 0 or retained > original:
            raise ValueError(
                f"Pause cut #{index} requires 0 <= retained_gap_seconds <= original_gap_seconds"
            )
        evidence = cut.get("boundary_evidence")
        required_evidence = {"asr", "waveform"}
        if version == 3:
            required_evidence.add("listening")
        if not isinstance(evidence, list) or not required_evidence.issubset(evidence):
            raise ValueError(
                f"Pause cut #{index} requires boundary_evidence containing "
                + ", ".join(sorted(required_evidence))
            )
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("edl", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--also-output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    protect_output_args(args)

    data = json.loads(args.edl.read_text(encoding="utf-8"))
    outputs = [args.output] + ([args.also_output] if args.also_output else [])
    try:
        edl_version = validate_edl(data)
        delivery_formats = validate_deliveries(data, outputs)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    existing = [path for path in outputs if path.exists()]
    if existing and not args.force and not args.dry_run:
        joined = ", ".join(str(path) for path in existing)
        raise SystemExit(f"Output exists: {joined}; version it or pass --force")
    unresolved = [
        item for item in data.get("manual_treatments", []) if item.get("status") != "applied"
    ]
    if unresolved:
        raise SystemExit(
            f"EDL has {len(unresolved)} unresolved manual treatment(s); apply or remove them before rendering"
        )
    config = {**DEFAULTS, **{key: data[key] for key in DEFAULTS if key in data}}
    if "wav" in delivery_formats and int(config["wav_bit_depth"]) != 24:
        raise SystemExit("WAV delivery currently requires wav_bit_depth=24")
    source_duration = duration(args.source)
    cuts = normalized_cuts(data.get("cuts", []), source_duration)
    keep = keep_segments(cuts, source_duration)
    if not keep:
        raise SystemExit("EDL removes the entire source")
    fade = float(config["crossfade_seconds"])
    shortest = min(end - start for start, end in keep)
    if shortest <= fade * 2:
        raise SystemExit(f"Shortest keep segment {shortest:.3f}s is not longer than twice the crossfade")
    removed = sum(item["end"] - item["start"] for item in cuts)
    expected = source_duration - removed - max(0, len(keep) - 1) * fade
    audit = {
        "edl_version": edl_version,
        "source_duration": source_duration,
        "cuts": len(cuts),
        "keep_segments": len(keep),
        "removed_seconds": round(removed, 3),
        "expected_output_seconds": round(expected, 3),
        "shortest_keep_seconds": round(shortest, 3),
        "settings": config,
        "delivery_formats": delivery_formats,
        "outputs": [str(path) for path in outputs],
        "applied_manual_treatments": len(data.get("manual_treatments", [])),
        "review_candidates_ignored": len(data.get("review_candidates", [])),
        "pending_review_candidates": sum(
            item.get("status") == "pending" for item in data.get("review_candidates", [])
        ),
    }
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0

    for output in outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="podcast-edl-") as tmp:
        tmpdir = Path(tmp)
        graph_path = tmpdir / "filtergraph.txt"
        assembly = tmpdir / "assembly.flac"
        mastered_wav = tmpdir / "mastered.wav"
        first_mp3 = tmpdir / "first.mp3"
        graph_path.write_text(filtergraph(keep, config), encoding="utf-8")
        run(
            [
                "ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(args.source),
                "-/filter_complex", str(graph_path), "-map", "[outa]",
                "-ar", str(int(config["sample_rate"])), "-ac", str(int(config["channels"])),
                "-c:a", "flac", str(assembly),
            ]
        )
        measured = loudness(assembly, config["target_lufs"], config["true_peak_dbtp"])
        base_filter = master_filter(measured, config)
        encode_wav(assembly, mastered_wav, config, base_filter)
        mastered_stats = loudness(mastered_wav, config["target_lufs"], config["true_peak_dbtp"])
        wav_correction = float(config["target_lufs"]) - float(mastered_stats["input_i"])
        if wav_correction > 0:
            peak_headroom = float(config["true_peak_dbtp"]) - float(mastered_stats["input_tp"])
            wav_correction = min(wav_correction, max(0.0, peak_headroom))
        if abs(wav_correction) > 0.15:
            encode_wav(
                assembly, mastered_wav, config, master_filter(measured, config, wav_correction)
            )

        wav_output = next((path for path in outputs if output_format(path) == "wav"), None)
        if wav_output:
            shutil.copy2(mastered_wav, wav_output)

        mp3_output = next((path for path in outputs if output_format(path) == "mp3"), None)
        if mp3_output:
            encode_mp3(mastered_wav, first_mp3, config)
            encoded = loudness(first_mp3, config["target_lufs"], config["true_peak_dbtp"])
            correction = float(config["target_lufs"]) - float(encoded["input_i"])
            if correction > 0:
                peak_headroom = float(config["true_peak_dbtp"]) - float(encoded["input_tp"])
                correction = min(correction, max(0.0, peak_headroom))
            if abs(correction) > 0.15:
                encode_mp3(mastered_wav, mp3_output, config, f"volume={correction:.3f}dB")
            else:
                shutil.move(first_mp3, mp3_output)

    deliveries = []
    for output in outputs:
        final = loudness(output, config["target_lufs"], config["true_peak_dbtp"])
        integrated = float(final["input_i"])
        true_peak = float(final["input_tp"])
        deliveries.append(
            {
                "output": str(output),
                "format": output_format(output),
                "integrated_lufs": integrated,
                "true_peak_dbtp": true_peak,
            }
        )
        if abs(integrated - float(config["target_lufs"])) > 0.5:
            raise SystemExit(f"Final integrated loudness missed tolerance: {output}")
        if true_peak > float(config["true_peak_dbtp"]) + 0.05:
            raise SystemExit(f"Final true peak exceeded limit: {output}")
    print(json.dumps({"deliveries": deliveries}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or str(exc), file=sys.stderr)
        raise
