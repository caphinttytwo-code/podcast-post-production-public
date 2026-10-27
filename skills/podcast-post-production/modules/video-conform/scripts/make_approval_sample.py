#!/usr/bin/env python3
"""Render representative B/reference-audio joins and a labeled approval sample."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args, child_output


import argparse
import csv
import json
import subprocess
from pathlib import Path

import numpy as np

from calibrate_fast_seek import calibrate
from build_acoustic_edl import probe_media, timing_risk


def seconds(value: str | float | int) -> float:
    if isinstance(value, (float, int)):
        return float(value)
    hour, minute, remainder = value.split(":")
    return int(hour) * 3600 + int(minute) * 60 + float(remainder)


def probe_duration(path: Path) -> float:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ], check=True, text=True, capture_output=True)
    return float(result.stdout.strip())


def automatic_selection(cuts: list[dict], maximum: int, reference_duration: float,
                        low_confidence_indices: list[int]) -> list[tuple[dict, str]]:
    if not cuts:
        return []
    candidates: list[tuple[dict, str]] = [
        (cuts[0], "opening"),
        (min(cuts, key=lambda item: abs(float(item["reference_join_seconds"]) - reference_duration / 2)), "middle"),
        (cuts[-1], "ending"),
        (max(cuts, key=lambda item: float(item["removed_duration"])), "largest-removal"),
    ]
    for index in low_confidence_indices:
        if 1 <= index <= len(cuts):
            candidates.append((cuts[index - 1], "low-confidence"))
    for fraction, label in ((0.25, "early"), (0.75, "late")):
        candidates.append((min(cuts, key=lambda item: abs(
            float(item["reference_join_seconds"]) - reference_duration * fraction)), label))
    reasons: dict[str, list[str]] = {}
    selected_ids = []
    for cut, reason in candidates:
        reasons.setdefault(cut["cut_id"], []).append(reason)
        if cut["cut_id"] not in selected_ids and len(selected_ids) < maximum:
            selected_ids.append(cut["cut_id"])
    by_id = {item["cut_id"]: item for item in cuts}
    selected = [(by_id[cut_id], "+".join(reasons[cut_id])) for cut_id in selected_ids]
    return sorted(selected, key=lambda item: float(item[0]["reference_join_seconds"]))


def render_clip(source: Path, reference: Path, cut: dict, output: Path, pre: float, post: float,
                fps: int, soft_frames: int, outgoing_seek: float, incoming_seek: float) -> None:
    before_frames, after_frames = round(pre * fps), round(post * fps)
    if before_frames <= soft_frames or after_frames <= soft_frames:
        raise ValueError("Approval handles must be longer than the softened join")
    soft_duration = soft_frames / fps
    total = pre + post
    graph = (
        f"[0:v]fps={fps},tpad=stop_mode=clone:stop_duration=0.25,"
        f"trim=start_frame=0:end_frame={before_frames},setpts=N/({fps}*TB),format=yuv420p,"
        "split=2[outbody][holdsrc];"
        f"[1:v]fps={fps},tpad=stop_mode=clone:stop_duration=0.25,"
        f"trim=start_frame=0:end_frame={after_frames},setpts=N/({fps}*TB),format=yuv420p,"
        "split=2[firstsrc][inbody_src];"
        f"[holdsrc]trim=start_frame={before_frames - 1}:end_frame={before_frames},"
        f"setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={soft_duration:.6f},"
        f"trim=start_frame=0:end_frame={soft_frames},setpts=N/({fps}*TB)[hold];"
        f"[firstsrc]trim=start_frame=0:end_frame={soft_frames},setpts=N/({fps}*TB),"
        f"format=yuva420p,fade=t=in:st=0:d={soft_duration:.6f}:alpha=1[first];"
        "[hold][first]overlay=0:0:shortest=1,format=yuv420p[transition];"
        f"[inbody_src]trim=start_frame={soft_frames}:end_frame={after_frames},"
        f"setpts=N/({fps}*TB)[inbody];"
        f"[outbody][transition][inbody]concat=n=3:v=1:a=0,"
        f"trim=start_frame=0:end_frame={before_frames + after_frames},"
        f"setpts=N/({fps}*TB)[vout];"
        f"[2:a]aresample=48000,atrim=start=0:end={total:.6f},asetpts=PTS-STARTPTS[aout]"
    )
    reference_join = float(cut["reference_join_seconds"])
    child_output(output.parent, output.name, source, reference)
    partial = child_output(output.parent, f".{output.stem}.encoding{output.suffix}", source, reference)
    command = [
        "ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error",
        "-ss", f"{outgoing_seek:.6f}", "-t", f"{pre + 0.25:.6f}", "-i", str(source),
        "-ss", f"{incoming_seek:.6f}", "-t", f"{post + 0.25:.6f}", "-i", str(source),
        "-ss", f"{reference_join - pre:.6f}", "-t", f"{total:.6f}", "-i", str(reference),
        "-filter_complex", graph, "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
        "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-map_metadata", "-1", "-movflags", "+faststart", str(partial),
    ]
    subprocess.run(command, check=True)
    actual = probe_duration(partial)
    if abs(actual - total) > 1 / fps:
        raise RuntimeError(f"Approval clip duration mismatch: {actual:.6f} vs {total:.6f}")
    partial.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--cut-id", action="append")
    parser.add_argument("--pre", type=float, default=5.0)
    parser.add_argument("--post", type=float, default=7.0)
    parser.add_argument("--max-duration", type=float, default=120.0)
    parser.add_argument("--fps", type=int)
    parser.add_argument("--soft-frames", type=int, choices=range(1, 6))
    parser.add_argument("--source-pcm", type=Path)
    parser.add_argument("--sample-id")
    args = parser.parse_args()
    protect_output_args(args)
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    if payload.get("audio_strategy") != "reference-audio-continuous":
        raise SystemExit("Approval sample requires B/reference-audio-continuous")
    source, reference = Path(payload["source_video"]), Path(payload["reference_audio"])
    spec = payload.get("output_spec", {})
    fps = args.fps or int(spec.get("fps", 30))
    soft_frames = args.soft_frames or int(spec.get("soft_frames", 3))
    sample_id = args.sample_id or payload["job_id"]
    cuts = payload.get("cuts", [])
    by_id = {cut["cut_id"]: cut for cut in cuts}
    maximum = min(10, int(args.max_duration // (args.pre + args.post)))
    if maximum < 1:
        raise SystemExit("max-duration is shorter than one approval excerpt")
    if args.cut_id:
        unknown = [cut_id for cut_id in args.cut_id if cut_id not in by_id]
        if unknown:
            raise SystemExit(f"Unknown cut ids: {', '.join(unknown)}")
        selected = [(by_id[cut_id], "manual") for cut_id in args.cut_id[:maximum]]
    else:
        selected = automatic_selection(
            cuts, maximum, float(payload["reference_duration_seconds"]),
            [int(value) for value in payload.get("alignment", {}).get("low_confidence_cut_indices", [])],
        )
    if not selected:
        raise SystemExit("Manifest contains no joins for an approval sample")

    output_dir = args.output_dir.resolve()
    for identifier in [sample_id, *(cut['cut_id'] for cut, _ in selected)]:
        if Path(str(identifier)).name != str(identifier) or str(identifier) in {'', '.', '..'}:
            raise ValueError('sample-id and cut-id must be plain filename components')
    protected = [source, reference, args.manifest]
    if args.source_pcm: protected.append(args.source_pcm)
    elif payload.get('analysis_cache', {}).get('source_pcm'): protected.append(Path(payload['analysis_cache']['source_pcm']))
    clips_dir = child_output(output_dir, "approval-clips", *protected)
    combined = child_output(output_dir, f"{sample_id}-approval-sample.mp4", *protected)
    index_csv = child_output(output_dir, f"{sample_id}-approval-sample-index.csv", *protected)
    index_json = child_output(output_dir, f"{sample_id}-approval-sample-index.json", *protected)
    concat_list = child_output(output_dir, '.approval-sample-concat.txt', *protected)
    partial = child_output(output_dir, f".{combined.stem}.encoding{combined.suffix}", *protected)
    for number, (cut, _) in enumerate(selected, 1):
        clip = child_output(output_dir, f"approval-clips/{number:02d}-{cut['cut_id']}.mp4", *protected)
        child_output(output_dir, f"approval-clips/.{clip.stem}.encoding{clip.suffix}", *protected)
    for path in (combined, index_csv, index_json):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite approval output: {path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    pcm_path = args.source_pcm or Path(payload.get("analysis_cache", {}).get("source_pcm", ""))
    source_timing = payload.get("source_timing") or timing_risk(probe_media(source))
    needs_calibration = bool(source_timing.get("requires_seek_calibration"))
    full_pcm = np.memmap(pcm_path, dtype="<i2", mode="r") if pcm_path.is_file() else None
    if needs_calibration and full_pcm is None:
        raise FileNotFoundError("Risky source timing requires the continuous source PCM cache")
    pcm_start = float(payload.get("source_audio_start_seconds", 0.0))
    rows, clip_paths = [], []
    for number, (cut, reason) in enumerate(selected, 1):
        clip = clips_dir / f"{number:02d}-{cut['cut_id']}.mp4"
        if clip.exists():
            raise FileExistsError(f"Refusing to overwrite approval clip: {clip}")
        outgoing_end = seconds(cut.get("source_remove_in_seconds", cut["source_remove_in"]))
        incoming_start = seconds(cut.get("source_remove_out_seconds", cut["source_remove_out"]))
        outgoing_desired, incoming_desired = outgoing_end - args.pre, incoming_start
        outgoing = calibrate(source, full_pcm, outgoing_desired, pcm_start) if full_pcm is not None else None
        incoming = calibrate(source, full_pcm, incoming_desired, pcm_start) if full_pcm is not None else None
        for result in (outgoing, incoming):
            if result and (result["verified_correlation"] < 0.80 or
                           abs(result["residual_error_seconds"]) > 0.005):
                raise RuntimeError(f"Unsafe approval seek calibration: {result}")
        render_clip(source, reference, cut, clip, args.pre, args.post, fps, soft_frames,
                    float((outgoing or {}).get("corrected_seek_second", outgoing_desired)),
                    float((incoming or {}).get("corrected_seek_second", incoming_desired)))
        clip_paths.append(clip)
        rows.append({
            "sample_number": number, "selection_reason": reason, "cut_id": cut["cut_id"],
            "reference_join": cut["reference_join"], "removed_duration_seconds": cut["removed_duration"],
            "join_at_clip_seconds": args.pre,
            "combined_sample_join_seconds": round((number - 1) * (args.pre + args.post) + args.pre, 3),
            "outgoing_seek_calibration": outgoing, "incoming_seek_calibration": incoming,
            "clip": str(clip),
        })

    with index_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        flat = [{**row, "outgoing_seek_calibration": json.dumps(row["outgoing_seek_calibration"], ensure_ascii=False),
                 "incoming_seek_calibration": json.dumps(row["incoming_seek_calibration"], ensure_ascii=False)}
                for row in rows]
        writer = csv.DictWriter(handle, fieldnames=list(flat[0]))
        writer.writeheader(); writer.writerows(flat)
    index_json.write_text(json.dumps({
        "audio_strategy": "reference-audio-continuous", "fps": fps, "soft_frames": soft_frames,
        "clip_duration_seconds": args.pre + args.post, "rows": rows,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    concat_list.write_text("".join(f"file '{path.resolve().as_posix()}'\n" for path in clip_paths), encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy", "-movflags", "+faststart", str(partial),
    ], check=True)
    expected = len(rows) * (args.pre + args.post)
    actual = probe_duration(partial)
    if actual > args.max_duration + 0.05 or abs(actual - expected) > 0.25:
        raise RuntimeError(f"Combined approval duration mismatch: {actual:.6f} vs {expected:.6f}")
    partial.replace(combined)
    print(json.dumps({"sample": str(combined), "duration_seconds": actual,
                      "join_count": len(rows), "index_csv": str(index_csv),
                      "index_json": str(index_json)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
