#!/usr/bin/env python3
"""Render vertical trailer jobs from a JSON manifest using ffmpeg."""

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import outside_package, distinct_output, child_output


from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args


import argparse
import math
from shared.fonts import load_font, check_glyphs
import json
import shlex
import subprocess
import time
from pathlib import Path

from subtitle_qa import parse_srt, validate_srt


def seconds(value):
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).replace(",", ".").split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    raise ValueError(f"Invalid timestamp: {value}")


def timestamp(value):
    total_ms = round(float(value) * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_part, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d}.{milliseconds:03d}"


def audit_clips(job, defaults):
    transition = float(job.get("transition", defaults.get("transition", 0.2)))
    merge_threshold = float(job.get("merge_threshold", defaults.get("merge_threshold", 0.5)))
    parsed = []
    print(f"EDL AUDIT {job['id']}")
    print("index | source in | source out | duration")
    for index, clip in enumerate(job.get("clips", []), start=1):
        start, end = seconds(clip["in"]), seconds(clip["out"])
        duration = end - start
        parsed.append((start, end, duration))
        print(f"{index:>5} | {timestamp(start)} | {timestamp(end)} | {duration:8.3f}s")
        if duration <= transition * 2:
            print(f"WARN {job['id']} clip {index}: shorter than two transitions")
    for index in range(1, len(parsed)):
        previous_end = parsed[index - 1][1]
        current_start = parsed[index][0]
        gap = current_start - previous_end
        if 0 <= gap <= merge_threshold:
            print(
                f"WARN {job['id']} clips {index}/{index + 1}: source gap {gap:.3f}s; "
                "merge unless the gap is an intentional removal"
            )
    print(f"joins: {max(0, len(parsed) - 1)}")


def wait_for_readable_output(path, attempts=30, delay=0.25):
    for _ in range(attempts):
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            return float(probe.stdout.strip())
        time.sleep(delay)
    raise RuntimeError(f"rendered output is not readable by ffprobe: {path}")


def subtitle_font(path, size):
    return load_font(path, size)


def rgba_color(value, default):
    value = str(value or default).lstrip("#")
    if len(value) == 6:
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4)) + (255,)
    if len(value) == 8:
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4, 6))
    raise ValueError(f"invalid RGBA color {value!r}")


def render_subtitle_layers(job, width, height, media_duration):
    subtitles = job.get("subtitles")
    if not subtitles:
        return []
    if isinstance(subtitles, str):
        subtitles = {"path": subtitles}
    subtitle_path = Path(subtitles["path"])
    if not subtitle_path.exists():
        raise FileNotFoundError(subtitle_path)
    bad_terms = []
    for item in subtitles.get("bad_terms", []):
        if isinstance(item, dict):
            bad_terms.append((str(item.get("wrong", "")), str(item.get("correct", ""))))
        elif isinstance(item, str) and "=" in item:
            bad_terms.append(tuple(item.split("=", 1)))
    text = subtitle_path.read_text(encoding="utf-8-sig")
    report = validate_srt(
        text,
        max_chars=int(subtitles.get("max_chars", 16)),
        media_duration=media_duration,
        bad_terms=tuple(bad_terms),
        enforce_house_style=bool(subtitles.get("house_style", True)),
    )
    if not report["ok"]:
        raise ValueError(f"{job['id']}: subtitle QA failed: {'; '.join(report['errors'])}")
    cues, parse_errors = parse_srt(text)
    if parse_errors:
        raise ValueError(f"{job['id']}: subtitle parsing failed: {'; '.join(parse_errors)}")

    from PIL import Image, ImageDraw

    font_size = int(subtitles.get("font_size", max(24, round(width * 0.046))))
    font = subtitle_font(subtitles.get("font"), font_size)
    fill = rgba_color(subtitles.get("color"), "#FFFFFFFF")
    stroke_fill = rgba_color(subtitles.get("stroke_color"), "#000000E6")
    stroke_width = int(subtitles.get("stroke_width", max(2, round(font_size * 0.08))))
    padding = int(subtitles.get("padding", max(8, round(font_size * 0.25))))
    line_spacing = int(subtitles.get("line_spacing", max(4, round(font_size * 0.18))))
    margin_v = int(subtitles.get("margin_v", max(48, round(height * 0.08))))
    asset_dir = Path(
        subtitles.get(
            "asset_dir",
            Path(job["output"]).parent / f".{Path(job['output']).stem}-subtitle-assets",
        )
    )
    outside_package(asset_dir)
    for cue in cues: child_output(asset_dir, f"cue-{cue.number:05d}.png", *input_files(job))
    asset_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    for cue in cues:
        text_value = "\n".join(cue.lines)
        check_glyphs(font, text_value)
        scratch = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)
        box = draw.multiline_textbbox(
            (0, 0),
            text_value,
            font=font,
            spacing=line_spacing,
            align="center",
            stroke_width=stroke_width,
        )
        image_width = min(width, max(1, math.ceil(box[2] - box[0] + padding * 2)))
        image_height = max(1, math.ceil(box[3] - box[1] + padding * 2))
        image = Image.new("RGBA", (image_width, image_height), (0, 0, 0, 0))
        image_draw = ImageDraw.Draw(image)
        image_draw.multiline_text(
            (image_width / 2, padding - box[1]),
            text_value,
            font=font,
            fill=fill,
            anchor="ma",
            spacing=line_spacing,
            align="center",
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        path = asset_dir / f"cue-{cue.number:05d}.png"
        image.save(path)
        generated.append(
            {
                "type": "image",
                "path": str(path),
                "start": cue.start,
                "end": cue.end,
                "x": max(0, (width - image_width) // 2),
                "y": max(0, height - margin_v - image_height),
                "width": image_width,
                "height": image_height,
                "_subtitle": True,
            }
        )
    return generated


def timed_layers(job, generated_layers=()):
    layers = list(job.get("timed_layers", [])) + list(generated_layers)
    parsed = []
    for index, layer in enumerate(layers, start=1):
        kind = layer.get("type", "image")
        if kind not in {"image", "video"}:
            raise ValueError(f"{job['id']}: timed layer {index} has unsupported type {kind!r}")
        path = Path(layer["path"])
        if not path.exists():
            raise FileNotFoundError(path)
        start = seconds(layer.get("start", 0))
        end = seconds(layer["end"])
        if start < 0 or end <= start:
            raise ValueError(f"{job['id']}: timed layer {index} has invalid range {start}..{end}")
        width = int(layer.get("width", 0))
        height = int(layer.get("height", 0))
        if width <= 0 or height <= 0:
            raise ValueError(f"{job['id']}: timed layer {index} requires positive width and height")
        parsed.append((kind, path, start, end, width, height, layer))
    return parsed


def input_files(job):
    values = [job['source'], *job.get('_protected_inputs', [])]
    if job.get('overlay'): values.append(job['overlay'])
    values.extend(layer['path'] for layer in job.get('timed_layers', []))
    for key in ('path', 'font'):
        value = job.get('subtitles', {}).get(key)
        if value: values.append(value)
    return values


def ffmpeg_command(job, defaults, force=False):
    source = Path(job["source"])
    output = outside_package(Path(job["output"]))
    distinct_output(output, *input_files(job))
    clips = job.get("clips", [])
    if not source.exists():
        raise FileNotFoundError(source)
    if not clips:
        raise ValueError(f"{job['id']}: no clips")
    transition = float(job.get("transition", defaults.get("transition", 0.2)))
    parsed = []
    for clip in clips:
        start, end = seconds(clip["in"]), seconds(clip["out"])
        duration = end - start
        if start < 0 or duration <= max(0, transition * 2):
            raise ValueError(f"{job['id']}: invalid clip {clip}")
        parsed.append((start, end, duration))
    width = int(job.get("width", defaults.get("width", 1080)))
    height = int(job.get("height", defaults.get("height", 1920)))
    video_y = int(job.get("video_y", defaults.get("video_y", 656)))
    video_height = int(job.get("video_height", defaults.get("video_height", 608)))
    fps = float(job.get("fps", defaults.get("fps", 30)))
    outro = defaults.get("outro", {}).copy()
    outro.update(job.get("outro", {}))
    fade_to_black = max(0.0, float(outro.get("fade_to_black", 0)))
    black_hold = max(0.0, float(outro.get("black_hold", 0)))
    outro_tail = fade_to_black + black_hold
    content_duration = sum(item[2] for item in parsed) - transition * max(0, len(parsed) - 1)
    generated_subtitle_layers = render_subtitle_layers(
        job, width, height, content_duration + outro_tail
    )

    command = ["ffmpeg", "-hide_banner", "-y" if force else "-n"]
    for start, end, _ in parsed:
        command += ["-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(source)]
    input_count = len(parsed)
    overlay = job.get("overlay")
    overlay_index = None
    if overlay:
        if not Path(overlay).exists():
            raise FileNotFoundError(overlay)
        command += ["-loop", "1", "-i", str(overlay)]
        overlay_index = input_count
        input_count += 1
    layers = timed_layers(job, generated_subtitle_layers)
    layer_inputs = []
    for kind, path, start, end, layer_width, layer_height, layer in layers:
        layer_index = input_count
        if kind == "image":
            command += ["-loop", "1", "-i", str(path)]
        else:
            command += ["-i", str(path)]
        layer_inputs.append(
            (layer_index, kind, path, start, end, layer_width, layer_height, layer)
        )
        input_count += 1

    filters = []
    for index in range(len(parsed)):
        filters.append(f"[{index}:v]setpts=PTS-STARTPTS,format=yuv420p[v{index}]")
        filters.append(f"[{index}:a]asetpts=PTS-STARTPTS[a{index}]")
    video_label, audio_label = "v0", "a0"
    elapsed = parsed[0][2]
    for index in range(1, len(parsed)):
        offset = elapsed - transition
        next_video, next_audio = f"vx{index}", f"ax{index}"
        filters.append(f"[{video_label}][v{index}]xfade=transition=fade:duration={transition:.3f}:offset={offset:.3f}[{next_video}]")
        filters.append(f"[{audio_label}][a{index}]acrossfade=d={transition:.3f}:c1=tri:c2=tri[{next_audio}]")
        video_label, audio_label = next_video, next_audio
        elapsed += parsed[index][2] - transition

    background = str(job.get("background", defaults.get("background", "#F4F1EA"))).replace("#", "0x")
    filters.append(
        f"[{video_label}]fps={fps:g},scale={width}:{video_height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{video_height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"pad={width}:{height}:0:{video_y}:color={background},setsar=1[base]"
    )
    if overlay_index is not None:
        filters.append(f"[base][{overlay_index}:v]overlay=0:0:shortest=1[framed]")
    else:
        filters.append("[base]null[framed]")
    composed_label = "framed"
    mixed_audio_label = audio_label
    for layer_number, (layer_index, kind, _path, start, end, layer_width, layer_height, layer) in enumerate(
        layer_inputs, start=1
    ):
        layer_label = f"layer{layer_number}"
        next_composed = f"composed{layer_number}"
        filters.append(
            f"[{layer_index}:v]setpts=PTS-STARTPTS+{start:.3f}/TB,"
            f"scale={layer_width}:{layer_height}:force_original_aspect_ratio=decrease,"
            f"pad={layer_width}:{layer_height}:(ow-iw)/2:(oh-ih)/2:color=0x00000000,"
            f"format=rgba[{layer_label}]"
        )
        x = str(layer.get("x", 0))
        y = str(layer.get("y", 0))
        filters.append(
            f"[{composed_label}][{layer_label}]overlay=x={x}:y={y}:"
            f"enable='between(t,{start:.3f},{end:.3f})':eof_action=pass:shortest=0[{next_composed}]"
        )
        composed_label = next_composed
        if kind == "video" and layer.get("mix_audio"):
            audio_layer_label = f"layera{layer_number}"
            next_audio_label = f"mixa{layer_number}"
            duration = end - start
            delay_ms = round(start * 1000)
            gain = float(layer.get("audio_gain", 1.0))
            filters.append(
                f"[{layer_index}:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,"
                f"volume={gain:.6f},adelay={delay_ms}|{delay_ms}[{audio_layer_label}]"
            )
            filters.append(
                f"[{mixed_audio_label}][{audio_layer_label}]"
                f"amix=inputs=2:duration=first:dropout_transition=0[{next_audio_label}]"
            )
            mixed_audio_label = next_audio_label
    if outro_tail:
        chain = f"[{composed_label}]tpad=stop_mode=clone:stop_duration={outro_tail:.3f}"
        if fade_to_black:
            chain += f",fade=t=out:st={elapsed:.3f}:d={fade_to_black:.3f}"
        filters.append(chain + "[outv]")
        filters.append(
            f"[{mixed_audio_label}]loudnorm=I=-16:LRA=11:TP=-1.5,"
            f"apad=pad_dur={outro_tail:.3f}[outa]"
        )
    else:
        filters.append(f"[{composed_label}]null[outv]")
        filters.append(f"[{mixed_audio_label}]loudnorm=I=-16:LRA=11:TP=-1.5[outa]")

    output.parent.mkdir(parents=True, exist_ok=True)
    command += [
        "-filter_complex", ";".join(filters),
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", str(defaults.get("preset", "medium")),
        "-crf", str(job.get("crf", defaults.get("crf", 21))),
        "-pix_fmt", "yuv420p", "-r", f"{fps:g}",
        "-c:a", "aac", "-b:a", str(job.get("audio_bitrate", defaults.get("audio_bitrate", "192k"))),
        "-ar", str(job.get("audio_sample_rate", defaults.get("audio_sample_rate", 48000))),
        "-ac", "2", "-movflags", "+faststart", "-shortest", str(output),
    ]
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--only", action="append", default=[], help="job id; repeatable")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    protect_output_args(args)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    defaults = manifest.get("defaults", {})
    jobs = [job for job in manifest.get("jobs", []) if not args.only or job["id"] in args.only]
    if not jobs:
        raise SystemExit("No matching jobs")
    failures = []
    protected_inputs = [args.manifest, *(value for item in manifest.get('jobs', []) for value in input_files(item))]
    for job in jobs:
        job['_protected_inputs'] = protected_inputs
        output = outside_package(Path(job["output"]))
        if output.exists() and not args.force:
            print(f"SKIP {job['id']}: {output}")
            continue
        try:
            audit_clips(job, defaults)
            command = ffmpeg_command(job, defaults, args.force)
            print(f"JOB {job['id']}\n{shlex.join(command)}", flush=True)
            if not args.dry_run:
                subprocess.run(command, check=True)
                duration = wait_for_readable_output(output)
                print(f"STABLE {job['id']}: {timestamp(duration)}", flush=True)
        except Exception as exc:
            failures.append((job["id"], str(exc)))
            print(f"FAIL {job['id']}: {exc}", flush=True)
    if failures:
        raise SystemExit("; ".join(f"{job}: {reason}" for job, reason in failures))


if __name__ == "__main__":
    main()
