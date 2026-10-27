#!/usr/bin/env python3
"""Validate a locked-video revision against its versioned JSON manifest."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args, distinct_output


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
import re
import subprocess
from pathlib import Path


def resolved(base: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def seconds(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).replace(",", ".").split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    raise ValueError(f"invalid timestamp: {value}")




def probe(path: Path, ffprobe: str) -> dict:
    try:
        payload = probe_json(path, ffprobe=ffprobe, full=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(exc.stderr.strip() or f"cannot probe {path}") from exc
    streams = payload.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError(f"no video stream: {path}")
    audio = [item for item in streams if item.get("codec_type") == "audio"]
    return {
        "duration": float(payload.get("format", {}).get("duration") or video.get("duration") or 0),
        "width": int(video.get("width") or 0), "height": int(video.get("height") or 0),
        "frame_rate": video.get("avg_frame_rate"), "pixel_format": video.get("pix_fmt"),
        "audio_tracks": len(audio),
        "audio_layout": [
            {
                "sample_rate": item.get("sample_rate"), "channels": item.get("channels"),
                "channel_layout": item.get("channel_layout"),
                "default": item.get("disposition", {}).get("default", 0),
            } for item in audio
        ],
    }


def validate_metadata(manifest: dict, source: dict, output: dict) -> list[str]:
    errors = []
    deletions = [(seconds(item["start"]), seconds(item["end"])) for item in manifest.get("deletions", [])]
    deleted = sum(end - start for start, end in deletions)
    expected = float(manifest.get("expected_output_duration", source["duration"] - deleted))
    tolerance = float(manifest.get("duration_tolerance", 0.08))
    if abs(output["duration"] - expected) > tolerance:
        errors.append(f"output duration {output['duration']:.3f}s does not match expected {expected:.3f}s")
    locked = manifest.get("locked", {})
    if locked.get("geometry", True) and (source["width"], source["height"]) != (output["width"], output["height"]):
        errors.append("locked geometry changed")
    if locked.get("frame_rate", True) and source["frame_rate"] != output["frame_rate"]:
        errors.append("locked frame rate changed")
    if locked.get("audio_layout", True) and source["audio_layout"] != output["audio_layout"]:
        errors.append("locked audio layout or disposition changed")
    return errors


def validate_srt_end(path: Path, duration: float) -> list[str]:
    errors, previous_end = [], 0.0
    pattern = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")
    for index, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if " --> " not in line:
            continue
        matches = pattern.findall(line)
        if len(matches) != 2:
            errors.append(f"invalid cue timestamp on line {index}")
            continue
        values = [int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000 for h, m, s, ms in matches]
        if values[0] < previous_end - 0.001:
            errors.append(f"subtitle overlap on line {index}")
        if values[1] <= values[0] or values[1] > duration + 0.02:
            errors.append(f"subtitle range invalid on line {index}")
        previous_end = values[1]
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()
    protect_output_args(args)
    manifest_path = args.manifest.resolve()
    base = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = []
    if manifest.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    source, output = resolved(base, manifest["source"]), resolved(base, manifest["output"])
    if source == output:
        errors.append("source and output must differ")
    for label, path in (("source", source), ("output", output)):
        if not path.is_file():
            errors.append(f"missing {label}: {path}")
    source_probe = output_probe = None
    if source.is_file() and output.is_file():
        source_hash = sha256(source)
        expected_hash = manifest.get("source_sha256")
        if expected_hash and source_hash != expected_hash:
            errors.append("source SHA-256 does not match manifest")
        source_probe, output_probe = probe(source, args.ffprobe), probe(output, args.ffprobe)
        errors.extend(validate_metadata(manifest, source_probe, output_probe))
    output_subtitle = manifest.get("output_subtitle")
    distinct_output(args.report, source, output, *([resolved(base, output_subtitle)] if output_subtitle else []))
    if output_subtitle and output_probe:
        subtitle_path = resolved(base, output_subtitle)
        if not subtitle_path.is_file():
            errors.append(f"missing output subtitle: {subtitle_path}")
        else:
            errors.extend(validate_srt_end(subtitle_path, output_probe["duration"]))
    report = {
        "id": manifest.get("id"), "ok": not errors, "errors": errors,
        "source": str(source), "source_sha256": sha256(source) if source.is_file() else None,
        "output": str(output), "output_sha256": sha256(output) if output.is_file() else None,
        "source_probe": source_probe, "output_probe": output_probe,
        "technical_qa": "pass" if not errors else "fail",
        "human_full_review": "not_recorded", "release_ready": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "errors": len(errors)}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
