"""Compare protected video frames and per-track audio packets on exact clocks."""
from contextlib import contextmanager
from fractions import Fraction
import json
import subprocess
import tempfile


class EvidenceUnavailable(ValueError):
    pass


def time(value):
    if type(value) not in (int, str):
        raise EvidenceUnavailable("Exact times must be integer seconds or rational/decimal strings")
    return Fraction(value)


def interval(row):
    start, end = time(row["start"]), time(row["end"])
    if start < 0 or end <= start:
        raise EvidenceUnavailable("Invalid time interval")
    return start, end


def ffjson(ffprobe, args, path, field):
    data = subprocess.check_output([ffprobe, "-v", "error", *args, "-of", "json", str(path)])
    return json.loads(data).get(field, [])


def streams(ffprobe, path, kind):
    return ffjson(ffprobe, ["-select_streams", kind, "-show_streams", "-show_data_hash", "sha256"], path, "streams")


def timestamps(ffprobe, path, scale):
    rows = ffjson(ffprobe, ["-select_streams", "v:0", "-show_frames", "-show_entries",
                            "frame=best_effort_timestamp,width,height,pix_fmt"], path, "frames")
    if not rows:
        raise EvidenceUnavailable("No decoded picture timestamps")
    pts = [int(row["best_effort_timestamp"]) * scale for row in rows]
    if pts != sorted(set(pts)):
        raise EvidenceUnavailable("Picture timestamps are missing, repeated or out of order")
    return pts, rows


def mapping(manifest):
    raw = manifest.get("time_map")
    if not isinstance(raw, list) or not raw:
        raise EvidenceUnavailable("An exact source/output time map is required")
    spans = []
    for item in raw:
        source_start, output_start, length = map(time, (item["source_start"], item["output_start"], item["duration"]))
        if min(source_start, output_start) < 0 or length <= 0:
            raise EvidenceUnavailable("Invalid time map span")
        if spans and (source_start < spans[-1][1] or output_start < spans[-1][3]):
            raise EvidenceUnavailable("Time map is not monotonic and disjoint")
        spans.append((source_start, source_start + length, output_start, output_start + length))
    return spans


def mapped(value, spans):
    for start, end, target, _ in spans:
        if start <= value < end:
            return target + value - start
    return None


def contains(value, intervals):
    return any(start <= value < end for start, end in intervals)


def approved_picture(manifest, width, height, format_name):
    entries = []
    for row in manifest.get("picture_changes", []):
        span = interval(row)
        rect = row.get("region")
        if rect is not None:
            if not isinstance(rect, list) or len(rect) != 4 or any(type(x) is not int for x in rect):
                raise EvidenceUnavailable("A picture region needs four integer coordinates")
            x, y, w, h = rect
            if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
                raise EvidenceUnavailable("Picture region is outside frame geometry")
            if format_name == "yuv420p" and any(x % 2 for x in rect):
                raise EvidenceUnavailable("YUV420 regions must align to the two-pixel chroma grid")
        entries.append((span, rect))
    entries.sort(key=lambda entry: entry[0])
    for ((_, left_end), _), ((right_start, _), _) in zip(entries, entries[1:]):
        if left_end > right_start:
            raise EvidenceUnavailable("Picture permissions overlap")
    return entries


def planes(width, height, format_name):
    if format_name == "yuv420p" and not (width % 2 or height % 2):
        return [(width, height, 1, 1), (width // 2, height // 2, 2, 1),
                (width // 2, height // 2, 2, 1)]
    if format_name == "yuv444p":
        return [(width, height, 1, 1)] * 3
    if format_name == "rgb24":
        return [(width, height, 1, 3)]
    raise EvidenceUnavailable("Native pixel comparison supports yuv420p, yuv444p and rgb24")


def same_outside(left, right, layout, rect):
    if rect is None:
        return left == right
    x, y, w, h = rect
    offset = 0
    for width, height, scale, channels in layout:
        stride = width * channels
        x1, x2, y1, y2 = x // scale * channels, (x + w) // scale * channels, y // scale, (y + h) // scale
        for row in range(height):
            start = offset + row * stride
            end = start + stride
            if y1 <= row < y2:
                if left[start:start+x1] != right[start:start+x1] or left[start+x2:end] != right[start+x2:end]:
                    return False
            elif left[start:end] != right[start:end]:
                return False
        offset += height * stride
    return True


@contextmanager
def decode(ffmpeg, path, format_name):
    with tempfile.TemporaryFile() as errors:
        child = subprocess.Popen([ffmpeg, "-nostdin", "-v", "error", "-xerror", "-noautorotate", "-i", str(path),
                                  "-map", "0:v:0", "-an", "-sn", "-dn", "-fps_mode", "passthrough",
                                  "-pix_fmt", "+" + format_name, "-f", "rawvideo", "-"], stdout=subprocess.PIPE,
                                 stderr=errors)
        try:
            yield child
        finally:
            child.stdout.close()
            if child.poll() is None:
                child.terminate()
            child.wait()


def verify_picture(manifest, source, output, spans, ffprobe, ffmpeg):
    source_streams, output_streams = streams(ffprobe, source, "v"), streams(ffprobe, output, "v")
    if len(source_streams) != 1 or len(output_streams) != 1:
        raise EvidenceUnavailable("Exact picture comparison requires one video stream per file")
    src, dst = source_streams[0], output_streams[0]
    keys = ("width", "height", "pix_fmt", "color_range", "color_space", "color_transfer", "color_primaries")
    if any(src.get(k) != dst.get(k) for k in keys):
        raise EvidenceUnavailable("Native picture formats, geometry or color metadata differ")
    fmt, w, h = src["pix_fmt"], src["width"], src["height"]
    layout = planes(w, h, fmt)
    size = sum(width * height * channels for width, height, _, channels in layout)
    allowed = approved_picture(manifest, w, h, fmt)
    deleted = [interval(row) for row in manifest.get("deletions", [])]
    source_pts, src_frames = timestamps(ffprobe, source, Fraction(src["time_base"]))
    output_pts, dst_frames = timestamps(ffprobe, output, Fraction(dst["time_base"]))
    if any((row["width"], row["height"], row["pix_fmt"]) != (w, h, fmt) for row in src_frames + dst_frames):
        raise EvidenceUnavailable("Picture format changes inside the clip")
    pairs = {}
    for index, pts in enumerate(source_pts):
        target = mapped(pts, spans)
        if (target is None) != contains(pts, deleted):
            raise EvidenceUnavailable("Time map does not match authorized source deletions at " + str(pts))
        if target is not None:
            pairs[target] = index
    wholly_mutable = [span for span, region in allowed if region is None]
    dst_set = set(output_pts)
    if any(pts not in dst_set and not contains(pts, wholly_mutable) for pts in pairs):
        raise EvidenceUnavailable("Source picture timestamps lack exact output matches")
    if any(pts not in pairs and not contains(pts, wholly_mutable) for pts in output_pts):
        raise EvidenceUnavailable("Output picture timestamps lack exact source matches")

    mismatches, checked, source_index = [], 0, -1
    original = b""
    with decode(ffmpeg, source, fmt) as old, decode(ffmpeg, output, fmt) as new:
        for pts in output_pts:
            frame = new.stdout.read(size)
            if len(frame) != size:
                raise EvidenceUnavailable("Output decode ended before the reported timestamps")
            permission = next(((span, rect) for span, rect in allowed if span[0] <= pts < span[1]), None)
            if permission and permission[1] is None:
                continue
            while source_index < pairs[pts]:
                original = old.stdout.read(size)
                source_index += 1
                if len(original) != size:
                    raise EvidenceUnavailable("Source decode ended before the reported timestamps")
            checked += 1
            if not same_outside(original, frame, layout, permission[1] if permission else None) and len(mismatches) < 12:
                mismatches.append(str(pts))
        while source_index + 1 < len(source_pts):
            if len(old.stdout.read(size)) != size:
                raise EvidenceUnavailable("Source decode ended before the reported timestamps")
            source_index += 1
        if old.stdout.read(1) or new.stdout.read(1) or old.wait() or new.wait():
            raise EvidenceUnavailable("Decode count or exit status differs")
    return {"status": "FAIL" if mismatches else "PASS", "compared_frames": checked,
            "mismatch_output_pts": mismatches, "native_pixel_format": fmt}


def packets(ffprobe, path, index, clock):
    rows = ffjson(ffprobe, ["-select_streams", f"a:{index}", "-show_packets", "-show_data_hash", "sha256"],
                  path, "packets")
    result = {}
    for row in rows:
        pts = int(row["pts"]) * clock
        if pts in result:
            raise EvidenceUnavailable("Repeated audio PTS")
        duration = int(row["duration"]) * clock
        if duration <= 0:
            raise EvidenceUnavailable("Unknown or invalid packet duration")
        result[pts] = (duration, row["data_hash"], row.get("side_data_list", []))
    if not result:
        raise EvidenceUnavailable("Missing audio packets")
    return result


def approved_audio(manifest, index):
    rows = [row for row in manifest.get("audio_changes", []) if row["track"] == index]
    return ([interval(row["source"]) for row in rows], [interval(row["output"]) for row in rows])


def audio_pts(pts, duration, spans, protected_exclusions):
    if any(pts < end and start < pts + duration for start, end in protected_exclusions):
        if any(start <= pts and pts + duration <= end for start, end in protected_exclusions):
            return None
        raise EvidenceUnavailable("Authorized audio boundary splits a packet at " + str(pts))
    for start, end, target, _ in spans:
        if start <= pts and pts + duration <= end:
            return target + pts - start
    # Encoder priming is part of the locked track when both timelines begin at zero.
    if pts < 0 and spans[0][0] == spans[0][2] == 0 and pts + duration <= spans[0][1]:
        return pts
    raise EvidenceUnavailable("Audio packet cannot be mapped exactly at " + str(pts))


def verify_audio(manifest, source, output, spans, ffprobe):
    originals, revisions = streams(ffprobe, source, "a"), streams(ffprobe, output, "a")
    if len(originals) != len(revisions):
        raise EvidenceUnavailable("Audio stream count differs")
    if any(type(row["track"]) is not int or not 0 <= row["track"] < len(originals)
           for row in manifest.get("audio_changes", [])):
        raise EvidenceUnavailable("Authorized audio track does not exist")
    results = []
    identity_map = [(out, end, out, end) for _, _, out, end in spans]
    deletions = [interval(row) for row in manifest.get("deletions", [])]
    for index, (src, dst) in enumerate(zip(originals, revisions)):
        source_mutable, output_mutable = approved_audio(manifest, index)
        if any(src.get(k) != dst.get(k) for k in ("codec_name", "sample_rate", "channels", "channel_layout", "extradata_hash")):
            raise EvidenceUnavailable(f"Audio track {index} codecs or format differ; packet proof unavailable")
        old, new = packets(ffprobe, source, index, Fraction(src["time_base"])), packets(ffprobe, output, index, Fraction(dst["time_base"]))
        expected, actual = {}, {}
        for pts, data in old.items():
            target = audio_pts(pts, data[0], spans, deletions + source_mutable)
            if target is not None:
                expected[target] = data
        for pts, data in new.items():
            if audio_pts(pts, data[0], identity_map, output_mutable) is not None:
                actual[pts] = data
        if expected.keys() != actual.keys():
            raise EvidenceUnavailable(f"Audio track {index} cannot establish one-to-one protected packet timestamps")
        bad = [str(pts) for pts in sorted(expected) if expected[pts] != actual[pts]]
        results.append({"track": index, "status": "FAIL" if bad else "PASS",
                        "compared_packets": len(expected), "mismatch_output_pts": bad[:12]})
    return results


def check(manifest, source, output, ffprobe, ffmpeg):
    spans = mapping(manifest)
    result = {}
    for name, function, tools in (("picture", verify_picture, (ffprobe, ffmpeg)),
                                 ("audio", verify_audio, (ffprobe,))):
        try:
            value = function(manifest, source, output, spans, *tools)
            result[name] = value if name == "picture" else {
                "status": "FAIL" if any(x["status"] == "FAIL" for x in value) else "PASS", "tracks": value}
        except (OSError, KeyError, ValueError, TypeError, ZeroDivisionError, subprocess.CalledProcessError) as exc:
            result[name] = {"status": "BLOCKED", "reason": str(exc)}
    states = {x["status"] for x in result.values()}
    return {"status": "FAIL" if "FAIL" in states else "BLOCKED" if "BLOCKED" in states else "PASS", **result}
