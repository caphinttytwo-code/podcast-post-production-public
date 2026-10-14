#!/usr/bin/env python3
"""Render idempotent subtitle/timecode review proxies from a JSON config."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import outside_package, distinct_output, child_output


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
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def resolved(base: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def ffmpeg_escape(value: str | Path) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")


def run_json(command: list[str]) -> dict:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "command failed")
    return json.loads(result.stdout)


def probe(path: Path, ffprobe: str) -> dict:
    try:
        payload = probe_json(path, ffprobe=ffprobe, full=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(exc.stderr.strip() or f"cannot probe {path}") from exc
    streams = payload.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError(f"no video stream: {path}")
    return {
        "duration": float(payload.get("format", {}).get("duration") or video.get("duration") or 0),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "frame_rate": video.get("avg_frame_rate") or video.get("r_frame_rate"),
        "audio_tracks": sum(item.get("codec_type") == "audio" for item in streams),
    }


def filters_available(ffmpeg: str, required: set[str]) -> None:
    result = subprocess.run([ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "cannot inspect FFmpeg filters")
    missing = [name for name in sorted(required) if name not in result.stdout]
    if missing:
        raise RuntimeError(f"FFmpeg is missing required filters: {', '.join(missing)}")


def discover(config: dict, base: Path) -> list[dict]:
    root = resolved(base, config["root"])
    output_dir = outside_package(resolved(base, config["output_dir"]))
    suffix = str(config.get("suffix", " - Review"))
    excluded = set(config.get("exclude_dirs", ["Delete", "Review", ".git"]))
    excluded.add(output_dir.name)
    items = []
    if config.get("items"):
        for index, item in enumerate(config["items"], 1):
            video = resolved(base, item["video"])
            subtitle = resolved(base, item.get("srt", video.with_suffix(".srt")))
            item_id = str(item.get("id", video.stem))
            output = resolved(base, item.get("output", output_dir / f"{video.stem}{suffix}.mp4"))
            outside_package(output)
            distinct_output(output, video, subtitle)
            items.append({"id": item_id, "video": video, "srt": subtitle, "output": output})
        return items
    if not root.is_dir():
        raise NotADirectoryError(root)
    for video in sorted(root.rglob("*.mp4")):
        if any(part in excluded for part in video.relative_to(root).parts[:-1]):
            continue
        if video.stem.endswith(suffix):
            continue
        subtitle = video.with_suffix(".srt")
        if not subtitle.is_file():
            continue
        relative_parent = video.parent.relative_to(root)
        output = output_dir / relative_parent / f"{video.stem}{suffix}.mp4"
        outside_package(output)
        distinct_output(output, video, subtitle)
        items.append({"id": str(video.relative_to(root)), "video": video, "srt": subtitle, "output": output})
    return items


def filter_chain(item: dict, config: dict) -> str:
    width = int(config.get("width", 1280))
    height = int(config.get("height", 720))
    fps = float(config.get("fps", 60))
    subtitle_size = int(config.get("subtitle_size", 28))
    margin_v = int(config.get("subtitle_margin_v", 22))
    font_name = str(config.get("subtitle_font_name", "Source Han Serif SC"))
    style = (
        f"FontName={font_name},FontSize={subtitle_size},PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,Outline=2,Alignment=2,MarginV={margin_v},WrapStyle=0"
    )
    font_directory = config.get("subtitle_font_dir")
    font_option_subtitles = ""
    if font_directory:
        directory = resolved(Path(config.get('_base', '.')), font_directory)
        if not directory.is_dir():
            raise NotADirectoryError(f"Subtitle font directory does not exist: {directory}")
        font_option_subtitles = f":fontsdir='{ffmpeg_escape(directory)}'"
    chain = [
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos",
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
        f"subtitles=filename='{ffmpeg_escape(item['srt'])}'{font_option_subtitles}:force_style='{ffmpeg_escape(style)}'",
    ]
    if config.get("timecode", True):
        font_file = config.get("timecode_font_file") or config.get("font_file")
        font_option = f"fontfile='{ffmpeg_escape(resolved(Path(config['_base']), font_file))}':" if font_file else ""
        chain.append(
            "drawtext=" + font_option +
            f"timecode='00\\:00\\:00\\:00':r={fps:g}:"
            "fontsize=28:fontcolor=white@0.92:x=w-tw-28:y=24:"
            "shadowcolor=black@0.65:shadowx=1:shadowy=1:box=1:boxcolor=black@0.22:boxborderw=5"
        )
    return ",".join(chain)


def command_for(item: dict, config: dict, temporary: Path) -> list[str]:
    ffmpeg = str(config.get("ffmpeg", "ffmpeg"))
    fps = float(config.get("fps", 60))
    return [
        ffmpeg, "-hide_banner", "-y", "-i", str(item["video"]),
        "-map", "0:v:0", "-map", "0:a?", "-vf", filter_chain(item, config),
        "-r", f"{fps:g}", "-fps_mode", "cfr", "-c:v", "libx264",
        "-preset", str(config.get("preset", "medium")), "-crf", str(config.get("crf", 20)),
        "-c:a", "copy", "-movflags", "+faststart", str(temporary),
    ]


def validate_output(source: dict, output: dict, config: dict) -> list[str]:
    errors = []
    if output["width"] != int(config.get("width", 1280)) or output["height"] != int(config.get("height", 720)):
        errors.append("unexpected output dimensions")
    tolerance = float(config.get("duration_tolerance", 0.08))
    if abs(output["duration"] - source["duration"]) > tolerance:
        errors.append(f"duration differs by {abs(output['duration'] - source['duration']):.3f}s")
    if output["audio_tracks"] != source["audio_tracks"]:
        errors.append(f"audio track count changed: {source['audio_tracks']} -> {output['audio_tracks']}")
    return errors


def write_audits(config: dict, base: Path, report: dict) -> None:
    json_path = outside_package(resolved(base, config.get("audit_json", "review-proxy-audit.json")))
    md_path = outside_package(resolved(base, config.get("audit_markdown", "review-proxy-audit.md")))
    protected = [Path(config["_config_path"])] if config.get("_config_path") else []
    for status in ("success", "planned", "skipped", "failed"):
        for item in report[status]:
            protected.extend(Path(item[k]) for k in ("video", "srt", "output") if item.get(k))
    distinct_output(json_path, *protected)
    distinct_output(md_path, json_path, *protected)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Review Proxy Audit", "", f"- Dry run: `{str(report['dry_run']).lower()}`"]
    for status in ("success", "planned", "skipped", "failed"):
        values = report[status]
        lines.extend([f"- {status}: {len(values)}"])
        lines.extend(f"  - `{item['id']}`{': ' + item['error'] if item.get('error') else ''}" for item in values)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    protect_output_args(args)
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["_base"] = str(config_path.parent)
    config["_config_path"] = str(config_path)
    base = config_path.parent
    items = discover(config, base)
    protected_inputs = [config_path, *(item[key] for item in items for key in ('video', 'srt'))]
    for key in ('timecode_font_file', 'font_file'):
        if config.get(key):
            font_input = resolved(base, config[key])
            if not font_input.is_file():
                raise FileNotFoundError(f"Font file does not exist: {font_input}")
            protected_inputs.append(font_input)
    if config.get('subtitle_font_dir'):
        font_directory = resolved(base, config['subtitle_font_dir'])
        if not font_directory.is_dir():
            raise NotADirectoryError(font_directory)
        protected_inputs.extend(p for p in font_directory.rglob('*') if p.is_file())
    for item in items: distinct_output(item['output'], *protected_inputs)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "release_ready": False,
        "success": [], "planned": [], "skipped": [], "failed": [],
    }
    if not args.dry_run and items:
        required = {"subtitles"} | ({"drawtext"} if config.get("timecode", True) else set())
        try:
            filters_available(str(config.get("ffmpeg", "ffmpeg")), required)
        except Exception as exc:
            report["global_error"] = str(exc)
            report["failed"] = [
                {
                    "id": item["id"], "video": str(item["video"]), "srt": str(item["srt"]),
                    "output": str(item["output"]), "error": str(exc),
                }
                for item in items
            ]
            write_audits(config, base, report)
            print(json.dumps({"success": 0, "planned": 0, "skipped": 0, "failed": len(items), "global_error": str(exc)}, ensure_ascii=False))
            return 1
    ffprobe = str(config.get("ffprobe", "ffprobe"))
    for item in items:
        entry = {"id": item["id"], "video": str(item["video"]), "srt": str(item["srt"]), "output": str(item["output"])}
        temporary = child_output(item['output'].parent, f".{item['output'].stem}.tmp.mp4", *protected_inputs)
        try:
            if item["output"].exists() and not args.force:
                report["skipped"].append(entry)
                continue
            if not item["video"].is_file() or not item["srt"].is_file():
                raise FileNotFoundError("video/SRT pair is incomplete")
            if args.dry_run:
                entry["command"] = command_for(item, config, temporary)
                report["planned"].append(entry)
                continue
            item["output"].parent.mkdir(parents=True, exist_ok=True)
            if temporary.exists():
                temporary.unlink()
            source_probe = probe(item["video"], ffprobe)
            result = subprocess.run(command_for(item, config, temporary), capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stderr.strip()[-2000:] or "FFmpeg render failed")
            output_probe = probe(temporary, ffprobe)
            errors = validate_output(source_probe, output_probe, config)
            if errors:
                raise RuntimeError("; ".join(errors))
            os.replace(temporary, item["output"])
            entry.update({"source_probe": source_probe, "output_probe": output_probe})
            report["success"].append(entry)
        except Exception as exc:  # keep batch progress isolated per item
            if temporary.exists():
                temporary.unlink()
            entry["error"] = str(exc)
            report["failed"].append(entry)
    write_audits(config, base, report)
    print(json.dumps({key: len(report[key]) for key in ("success", "planned", "skipped", "failed")}, ensure_ascii=False))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
