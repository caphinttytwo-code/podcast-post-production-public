#!/usr/bin/env python3
"""Validate structural properties of rendered trailers and covers."""

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args


from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.media import probe_json


import argparse
import json
import subprocess
import re
from pathlib import Path

from PIL import Image
from subtitle_qa import parse_clock, validate_srt


def probe(path):
    return probe_json(path, full=True)


def rational(value):
    numerator, denominator = value.split("/")
    return float(numerator) / float(denominator) if float(denominator) else 0


def last_frame_luma(path):
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-sseof", "-0.04", "-i", str(path),
            "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
            "-frames:v", "1", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    match = re.search(r"lavfi\.signalstats\.YAVG=([0-9.]+)", proc.stderr)
    return float(match.group(1)) if match else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    protect_output_args(args)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    defaults = manifest.get("defaults", {})
    errors = []
    for job in manifest.get("jobs", []):
        path = Path(job["output"])
        if not path.exists():
            errors.append(f"{job['id']}: missing video {path}")
            continue
        data = probe(path)
        videos = [stream for stream in data["streams"] if stream["codec_type"] == "video"]
        audios = [stream for stream in data["streams"] if stream["codec_type"] == "audio"]
        expected_w = int(job.get("width", defaults.get("width", 1080)))
        expected_h = int(job.get("height", defaults.get("height", 1920)))
        expected_fps = float(job.get("fps", defaults.get("fps", 30)))
        if len(videos) != 1:
            errors.append(f"{job['id']}: expected one video stream, found {len(videos)}")
        else:
            video = videos[0]
            if (video.get("width"), video.get("height")) != (expected_w, expected_h):
                errors.append(f"{job['id']}: dimensions {video.get('width')}x{video.get('height')}")
            fps = rational(video.get("avg_frame_rate", "0/1"))
            if abs(fps - expected_fps) > 0.05:
                errors.append(f"{job['id']}: fps {fps:.3f}, expected {expected_fps:g}")
            if video.get("codec_name") != "h264":
                errors.append(f"{job['id']}: video codec {video.get('codec_name')}, expected h264")
        if len(audios) != 1:
            errors.append(f"{job['id']}: expected one audio stream, found {len(audios)}")
        else:
            audio = audios[0]
            if audio.get("codec_name") != "aac":
                errors.append(f"{job['id']}: audio codec {audio.get('codec_name')}, expected aac")
            if int(audio.get("channels", 0)) != 2:
                errors.append(f"{job['id']}: audio channels {audio.get('channels')}, expected 2")
        covers = job.get("covers", [])
        if job.get("cover"):
            covers = covers + [{"path": job["cover"], "width": expected_w, "height": expected_h}]
        for cover in covers:
            cover_path = Path(cover["path"])
            if not cover_path.exists():
                errors.append(f"{job['id']}: missing cover {cover_path}")
            else:
                with Image.open(cover_path) as image:
                    cover_w = int(cover.get("width", expected_w))
                    cover_h = int(cover.get("height", expected_h))
                    if image.size != (cover_w, cover_h):
                        errors.append(
                            f"{job['id']}: cover {cover.get('ratio', cover_path.name)} dimensions "
                            f"{image.size[0]}x{image.size[1]}, expected {cover_w}x{cover_h}"
                        )
        subtitles = job.get("subtitles")
        if subtitles:
            subtitle_path = Path(subtitles["path"] if isinstance(subtitles, dict) else subtitles)
            subtitle_cfg = subtitles if isinstance(subtitles, dict) else {}
            if not subtitle_path.exists():
                errors.append(f"{job['id']}: missing subtitles {subtitle_path}")
            else:
                bad_terms = []
                for item in subtitle_cfg.get("bad_terms", []):
                    if isinstance(item, dict):
                        bad_terms.append((str(item.get("wrong", "")), str(item.get("correct", ""))))
                    elif isinstance(item, str) and "=" in item:
                        bad_terms.append(tuple(item.split("=", 1)))
                report = validate_srt(
                    subtitle_path.read_text(encoding="utf-8-sig"),
                    max_chars=int(subtitle_cfg.get("max_chars", 16)),
                    media_duration=float(data["format"].get("duration", 0)),
                    bad_terms=tuple(bad_terms),
                    enforce_house_style=bool(subtitle_cfg.get("house_style", True)),
                )
                errors.extend(f"{job['id']}: subtitle {item}" for item in report["errors"])
        expected_duration = 0.0
        transition = float(job.get("transition", defaults.get("transition", 0.2)))
        for clip_index, clip in enumerate(job.get("clips", [])):
            expected_duration += parse_clock(clip["out"]) - parse_clock(clip["in"])
            if clip_index:
                expected_duration -= transition
        outro_duration = defaults.get("outro", {}).copy()
        outro_duration.update(job.get("outro", {}))
        expected_duration += float(outro_duration.get("fade_to_black", 0))
        expected_duration += float(outro_duration.get("black_hold", 0))
        actual_duration = float(data["format"].get("duration", 0))
        if expected_duration and abs(actual_duration - expected_duration) > max(0.1, 1 / expected_fps):
            errors.append(
                f"{job['id']}: duration {actual_duration:.3f}s, expected {expected_duration:.3f}s"
            )
        outro = defaults.get("outro", {}).copy()
        outro.update(job.get("outro", {}))
        if float(outro.get("fade_to_black", 0)) > 0:
            luma = last_frame_luma(path)
            if luma is None:
                errors.append(f"{job['id']}: could not inspect final-frame luma")
            elif luma > 32:
                errors.append(f"{job['id']}: final frame is not near black (YAVG={luma:.2f})")
        print(f"OK structural probe: {job['id']} ({data['format'].get('duration', '?')}s)")
    if errors:
        print("\n".join(f"ERROR {item}" for item in errors))
        raise SystemExit(1)
    print(f"PASS: {len(manifest.get('jobs', []))} job(s)")


if __name__ == "__main__":
    main()
