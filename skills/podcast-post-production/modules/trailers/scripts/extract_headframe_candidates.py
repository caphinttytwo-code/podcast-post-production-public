#!/usr/bin/env python3
"""Extract configured still candidates and package previews, contact sheets, and audit."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import outside_package, child_output, distinct_output


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


from shared.fonts import load_font
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


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


def clock(value: float) -> str:
    millis = round(value * 1000)
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"




def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "-", value).strip("-.")
    return cleaned or "candidate"


def probe(path: Path, ffprobe: str) -> dict:
    try:
        payload = probe_json(path, ffprobe=ffprobe, entries='stream=width,height,avg_frame_rate:format=duration', selector='v:0')
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(exc.stderr.strip() or f"cannot probe {path}") from exc
    stream = payload.get("streams", [{}])[0]
    return {
        "duration": float(payload.get("format", {}).get("duration") or 0),
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "frame_rate": stream.get("avg_frame_rate"),
    }


def expand_candidates(job: dict) -> list[dict]:
    candidates = []
    for item in job.get("timestamps", []):
        if isinstance(item, dict):
            candidates.append({"time": seconds(item["time"]), "label": str(item.get("label", ""))})
        else:
            candidates.append({"time": seconds(item), "label": ""})
    for window_index, window in enumerate(job.get("windows", []), 1):
        start, end = seconds(window["start"]), seconds(window["end"])
        count = int(window.get("count", 3))
        if start < 0 or end <= start or count < 1:
            raise ValueError(f"invalid window {window_index} for {job['id']}")
        step = (end - start) / (count + 1)
        for index in range(count):
            candidates.append({
                "time": start + step * (index + 1),
                "label": str(window.get("label", f"window-{window_index}")),
            })
    if not candidates:
        raise ValueError(f"{job['id']} has no timestamps or windows")
    return candidates


def parse_color(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError("background must be a six-digit hex color")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def font(path: Path | None, size: int):
    return load_font(path, size)


def contain_preview(source: Path, size: tuple[int, int], background: tuple[int, int, int]) -> Image.Image:
    with Image.open(source) as opened:
        image = ImageOps.contain(opened.convert("RGB"), size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, background)
    canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def contact_sheet(entries: list[dict], output: Path, background, label_font) -> None:
    columns = min(3, max(1, len(entries)))
    rows = math.ceil(len(entries) / columns)
    cell_w, image_h, label_h = 270, 360, 48
    sheet = Image.new("RGB", (columns * cell_w, rows * (image_h + label_h)), background)
    draw = ImageDraw.Draw(sheet)
    for index, entry in enumerate(entries):
        x = (index % columns) * cell_w
        y = (index // columns) * (image_h + label_h)
        with Image.open(entry["mobile_path"]) as preview:
            sheet.paste(preview.convert("RGB"), (x, y))
        label = f"{index + 1:02d}  {entry['timecode']}"
        draw.text((x + 8, y + image_h + 10), label, font=label_font, fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=94, subsampling=0)


def extract(ffmpeg: str, video: Path, timestamp: float, output: Path) -> None:
    child_output(output.parent, output.name, video)
    temporary = child_output(output.parent, f".{output.stem}.tmp.png", video)
    if temporary.exists():
        temporary.unlink()
    result = subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{timestamp:.6f}",
        "-i", str(video), "-frames:v", "1", "-fps_mode", "passthrough", str(temporary),
    ], capture_output=True, text=True)
    if result.returncode or not temporary.is_file():
        raise RuntimeError(result.stderr.strip() or f"failed to extract {video} at {timestamp}")
    with Image.open(temporary) as image:
        image.verify()
    os.replace(temporary, output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    protect_output_args(args)
    config_path = args.config.resolve()
    base = config_path.parent
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output_dir = outside_package(resolved(base, config["output_dir"]))
    background = parse_color(str(config.get("background", "#202020")))
    label_font_path = resolved(base, config["font_file"]) if config.get("font_file") else None
    label_font = font(label_font_path, int(config.get("label_size", 20)))
    ffmpeg, ffprobe = str(config.get("ffmpeg", "ffmpeg")), str(config.get("ffprobe", "ffprobe"))
    plan = []
    for job in config.get("jobs", []):
        video = resolved(base, job["video"])
        for rank, candidate in enumerate(expand_candidates(job), 1):
            plan.append({"job": str(job["id"]), "video": video, "rank": rank, **candidate})
    if not plan:
        raise ValueError("configuration has no candidate jobs")
    protected = [args.config, *(item['video'] for item in plan)]
    if label_font_path: protected.append(label_font_path)
    manifest_path = child_output(output_dir, str(config.get("manifest_name", "candidate-manifest.json")), *protected)
    selection_path = child_output(output_dir, str(config.get("selection_name", "candidate-selection.md")), *protected)
    distinct_output(selection_path, manifest_path)
    if args.dry_run:
        print(json.dumps([
            {**item, "video": str(item["video"]), "timecode": clock(item["time"])} for item in plan
        ], ensure_ascii=False, indent=2))
        return 0

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "candidate_pending_user_confirmation",
        "release_ready": False,
        "jobs": [],
    }
    grouped: dict[str, list[dict]] = {}
    failures = []
    for item in plan:
        grouped.setdefault(item["job"], []).append(item)
    for job_id, candidates in grouped.items():
        video = candidates[0]["video"]
        job_dir = child_output(output_dir, safe_name(job_id), *protected)
        if not video.is_file():
            failures.append({"job": job_id, "error": f"missing video: {video}"})
            continue
        source_hash = sha256(video)
        source_probe = probe(video, ffprobe)
        job_entries = []
        for item in candidates:
            try:
                if item["time"] < 0 or item["time"] >= source_probe["duration"]:
                    raise ValueError(f"timestamp outside video duration: {clock(item['time'])}")
                stem = f"{safe_name(job_id)}__{item['rank']:02d}__{clock(item['time']).replace(':', '-')}"
                original = child_output(output_dir, f"{safe_name(job_id)}/original/{stem}.png", *protected)
                delivery = child_output(output_dir, f"{safe_name(job_id)}/delivery-preview/{stem}.png", *protected)
                mobile = child_output(output_dir, f"{safe_name(job_id)}/mobile-preview/{stem}.png", *protected)
                for path in (original, delivery, mobile):
                    path.parent.mkdir(parents=True, exist_ok=True)
                if original.exists() and not args.force:
                    with Image.open(original) as image:
                        image.verify()
                else:
                    extract(ffmpeg, video, item["time"], original)
                if args.force or not delivery.exists():
                    contain_preview(original, (1080, 1440), background).save(delivery)
                if args.force or not mobile.exists():
                    contain_preview(original, (270, 360), background).save(mobile)
                entry = {
                    "rank": item["rank"], "time_seconds": item["time"], "timecode": clock(item["time"]),
                    "label": item["label"], "original": str(original), "delivery_preview": str(delivery),
                    "mobile_preview": str(mobile), "original_sha256": sha256(original),
                    "delivery_sha256": sha256(delivery), "mobile_sha256": sha256(mobile),
                    "mobile_path": mobile,
                }
                job_entries.append(entry)
            except Exception as exc:
                failures.append({"job": job_id, "rank": item["rank"], "error": str(exc)})
        sheet = child_output(output_dir, f"{safe_name(job_id)}/{safe_name(job_id)}-contact-sheet.jpg", *protected)
        if job_entries:
            contact_sheet(job_entries, sheet, background, label_font)
        for entry in job_entries:
            entry.pop("mobile_path", None)
        unchanged = sha256(video) == source_hash
        manifest["jobs"].append({
            "id": job_id, "video": str(video), "source_sha256": source_hash,
            "source_probe": source_probe, "source_unchanged": unchanged,
            "contact_sheet": str(sheet), "contact_sheet_sha256": sha256(sheet) if sheet.exists() else None,
            "candidates": job_entries,
        })
    manifest["failures"] = failures
    manifest["ok"] = not failures and all(job["source_unchanged"] for job in manifest["jobs"])
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Headframe Candidate Selection", "", "- Status: `candidate_pending_user_confirmation`", "- Technical validation does not mean final selection.", ""]
    for job in manifest["jobs"]:
        lines.extend([f"## {job['id']}", ""])
        lines.extend(f"- {entry['rank']:02d} `{entry['timecode']}` {entry['label']}".rstrip() for entry in job["candidates"])
        lines.append("")
    if failures:
        lines.extend(["## Failures", ""] + [f"- {item}" for item in failures])
    selection_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"jobs": len(manifest["jobs"]), "candidates": sum(len(job["candidates"]) for job in manifest["jobs"]), "failures": len(failures)}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
