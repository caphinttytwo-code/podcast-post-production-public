#!/usr/bin/env python3
"""Dry-run or render a B conform: selected source picture plus continuous reference audio."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args, distinct_output, child_output


from pathlib import Path as _PackagePath
import sys as _package_sys
_PACKAGE_ROOT = _PackagePath(__file__).resolve().parents[3]
if str(_PACKAGE_ROOT) not in _package_sys.path:
    _package_sys.path.insert(0, str(_PACKAGE_ROOT))
from shared.files import sha256 as digest


import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from build_acoustic_edl import probe_media, timing_risk


def seconds(value: str | float | int) -> float:
    if isinstance(value, (float, int)):
        return float(value)
    hour, minute, remainder = value.split(":")
    return int(hour) * 3600 + int(minute) * 60 + float(remainder)




def filter_graph(segments: list[dict], fps: int, soft_frames: int, target_duration: float,
                 audio_index: int) -> tuple[str, int]:
    soft_duration = soft_frames / fps
    lines, counts = [], []
    last = len(segments) - 1
    if not segments:
        raise ValueError("Manifest has no segments")
    for index, segment in enumerate(segments):
        reference_in = segment.get("reference_in_seconds", seconds(segment["reference_in"]))
        reference_out = segment.get("reference_out_seconds", seconds(segment["reference_out"]))
        count = round(reference_out * fps) - round(reference_in * fps)
        if count <= soft_frames:
            raise ValueError(f"Segment {index + 1} is too short for {soft_frames} soft frames")
        counts.append(count)
        split = (f"null[body{index}]" if len(segments) == 1 else
                 f"split=2[body{index}src][hold{index}src]" if index == 0 else
                 f"split=2[first{index}src][body{index}src]" if index == last else
                 f"split=3[first{index}src][body{index}src][hold{index}src]")
        lines.append(f"[{index}:v]fps={fps},tpad=stop_mode=clone:stop_duration=0.2,"
                     f"trim=start_frame=0:end_frame={count},setpts=N/({fps}*TB),format=yuv420p,{split}")
    for index, count in enumerate(counts):
        if len(segments) == 1:
            continue
        body_start = 0 if index == 0 else soft_frames
        lines.append(f"[body{index}src]trim=start_frame={body_start}:end_frame={count},"
                     f"setpts=N/({fps}*TB)[body{index}]")
        if index < last:
            lines.append(f"[hold{index}src]trim=start_frame={count - 1}:end_frame={count},setpts=PTS-STARTPTS,"
                         f"tpad=stop_mode=clone:stop_duration={soft_duration:.6f},"
                         f"trim=start_frame=0:end_frame={soft_frames},setpts=N/({fps}*TB)[hold{index}]")
        if index > 0:
            lines.append(f"[first{index}src]trim=start_frame=0:end_frame={soft_frames},"
                         f"setpts=N/({fps}*TB),format=yuva420p,"
                         f"fade=t=in:st=0:d={soft_duration:.6f}:alpha=1[first{index}]")
            lines.append(f"[hold{index - 1}][first{index}]overlay=0:0:shortest=1,"
                         f"format=yuv420p[transition{index - 1}]")
    inputs = []
    for index in range(len(segments)):
        if index:
            inputs.append(f"[transition{index - 1}]")
        inputs.append(f"[body{index}]")
    target_frames = round(target_duration * fps)
    lines.append("".join(inputs) + f"concat=n={len(inputs)}:v=1:a=0,"
                 f"trim=start_frame=0:end_frame={target_frames},setpts=N/({fps}*TB)[vout]")
    lines.append(f"[{audio_index}:a]aresample=48000,atrim=start=0:end={target_duration:.6f},"
                 "asetpts=PTS-STARTPTS[aout]")
    if sum(counts) != target_frames:
        raise ValueError(f"Frame audit failed: segment sum {sum(counts)} != target {target_frames}")
    return ";\n".join(lines), target_frames


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--seek-calibration", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fps", type=int)
    parser.add_argument("--soft-frames", type=int, choices=range(1, 6))
    parser.add_argument("--crf", type=int)
    parser.add_argument("--preset", default="medium")
    parser.add_argument("--execute", action="store_true", help="Render after the default dry-run")
    args = parser.parse_args()
    protect_output_args(args)

    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    if payload.get("audio_strategy") != "reference-audio-continuous":
        raise SystemExit("Manifest is not locked to B/reference-audio-continuous")
    source = Path(payload["source_video"])
    reference = Path(payload["reference_audio"])
    for path in (source, reference):
        if not path.is_file():
            raise SystemExit(f"Missing input: {path}")
    spec = payload.get("output_spec", {})
    fps = args.fps or int(spec.get("fps", 30))
    soft_frames = args.soft_frames or int(spec.get("soft_frames", 3))
    crf = args.crf if args.crf is not None else int(spec.get("crf", 21))
    risk = payload.get("source_timing") or timing_risk(probe_media(source))
    if risk.get("requires_seek_calibration") and not args.seek_calibration:
        raise SystemExit(
            "Source timing is marked risky; run calibrate_manifest_seeks.py and pass --seek-calibration"
        )
    calibration = None
    calibrated_rows: dict[int, dict] = {}
    if args.seek_calibration:
        calibration = json.loads(args.seek_calibration.read_text(encoding="utf-8"))
        if calibration.get("job_id") != payload.get("job_id"):
            raise SystemExit("Seek calibration job_id does not match the EDL manifest")
        if calibration.get("manifest_sha256") != digest(args.manifest):
            raise SystemExit("Seek calibration was created for a different manifest revision")
        if int(calibration.get("unsafe_count", -1)) != 0:
            raise SystemExit("Seek calibration contains unsafe segments")
        calibrated_rows = {int(row["segment_index"]): row for row in calibration.get("rows", [])}
        expected_indices = {int(segment["index"]) for segment in payload["segments"]}
        if set(calibrated_rows) != expected_indices:
            raise SystemExit("Seek calibration must cover every segment exactly once")
        thresholds = calibration.get("thresholds", {})
        minimum_correlation = float(thresholds.get("minimum_correlation", 0.80))
        maximum_residual = float(thresholds.get("maximum_residual_seconds", 0.005))
        for segment in payload["segments"]:
            row = calibrated_rows[int(segment["index"])]
            if abs(float(row["desired_source_second"]) - float(segment["source_media_in_seconds"])) > 0.001:
                raise SystemExit(f"Seek calibration desired time mismatch at segment {segment['index']}")
            if (float(row["verified_correlation"]) < minimum_correlation or
                    abs(float(row["residual_error_seconds"])) > maximum_residual):
                raise SystemExit(f"Unsafe seek calibration at segment {segment['index']}")
    output = args.output.resolve()
    distinct_output(output, source, reference)
    protected = [source, reference, args.manifest] + ([args.seek_calibration] if args.seek_calibration else [])
    partial = child_output(output.parent, f".{output.stem}.encoding{output.suffix}", *protected)
    filter_path = child_output(output.parent, output.with_suffix(".filter.txt").name, *protected)
    if output.exists() or partial.exists():
        raise SystemExit(f"Refusing to overwrite output or partial: {output}")
    segments = payload["segments"]
    target_duration = float(payload["reference_duration_seconds"])
    graph, target_frames = filter_graph(segments, fps, soft_frames, target_duration, len(segments))
    command = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error"]
    for segment in segments:
        row = calibrated_rows.get(int(segment["index"]))
        media_in = float(row["corrected_seek_second"] if row else segment["source_media_in_seconds"])
        duration = float(segment["reference_duration"])
        command += ["-ss", f"{media_in:.6f}", "-t", f"{duration + 0.25:.6f}", "-i", str(source)]
    command += ["-i", str(reference), "-/filter_complex", str(filter_path),
                "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-preset", args.preset,
                "-crf", str(crf), "-pix_fmt", "yuv420p", "-r", str(fps),
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                "-map_metadata", "-1", "-movflags", "+faststart", "-progress", "pipe:1", str(partial)]
    summary = {"mode": "execute" if args.execute else "dry-run", "segments": len(segments),
               "joins": max(0, len(segments) - 1), "fps": fps, "soft_frames": soft_frames,
               "target_frames": target_frames, "target_duration_seconds": target_duration,
               "seek_calibrated": bool(calibration),
               "maximum_seek_residual_seconds": (calibration or {}).get("maximum_residual_error_seconds"),
               "output": str(output)}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.execute:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    filter_path.write_text(graph + "\n", encoding="utf-8")
    process = subprocess.Popen(command, text=True, stdout=subprocess.PIPE)
    last_report = -300.0
    assert process.stdout is not None
    for line in process.stdout:
        if not line.startswith("out_time_us="):
            continue
        value = line.split("=", 1)[1].strip()
        if not value.isdigit():
            continue
        encoded_seconds = int(value) / 1_000_000
        if encoded_seconds - last_report >= 300:
            print(json.dumps({"encoded_seconds": round(encoded_seconds, 1),
                              "percent": round(encoded_seconds / target_duration * 100, 1)}), flush=True)
            last_report = encoded_seconds
    exit_code = process.wait()
    if exit_code:
        raise subprocess.CalledProcessError(exit_code, command)
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,codec_name,pix_fmt,r_frame_rate,nb_frames,sample_rate,channels",
         "-of", "json", str(partial)],
        check=True, text=True, capture_output=True,
    )
    probe = json.loads(result.stdout)
    rendered_duration = float(probe["format"]["duration"])
    stream_types = {stream.get("codec_type") for stream in probe.get("streams", [])}
    if abs(rendered_duration - target_duration) > 1 / fps:
        raise RuntimeError(f"Partial duration mismatch: {rendered_duration:.6f} vs {target_duration:.6f}")
    if not {"video", "audio"}.issubset(stream_types):
        raise RuntimeError(f"Partial render lacks video or audio: {stream_types}")
    video = next(stream for stream in probe["streams"] if stream.get("codec_type") == "video")
    if int(video.get("nb_frames", -1)) != target_frames:
        raise RuntimeError(f"Partial frame count mismatch: {video.get('nb_frames')} vs {target_frames}")
    partial.replace(output)
    print(json.dumps({"render_complete": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
