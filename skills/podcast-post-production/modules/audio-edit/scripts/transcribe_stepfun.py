#!/usr/bin/env python3
"""Resumable StepFun StepAudio SSE transcription for pre-chunked audio."""


from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args, package_root
from shared.guards import guard_path, guard_directory

import argparse
import base64
import json
import hashlib
import math
import wave
from fractions import Fraction
from urllib.parse import urlsplit
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


STEPFUN_API_BASE_URL = "https://api.stepfun.com/step_plan/v1"
ASR_PATH = "audio/asr/sse"


def api_url(base_url, path):
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def credential(env_name, keychain_service):
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    try:
        return subprocess.check_output(
            ["security", "find-generic-password", "-s", keychain_service, "-w"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise RuntimeError(
            f"No API key found in ${env_name} or macOS Keychain service {keychain_service!r}"
        )


def duration_ms(path):
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(round(float(proc.stdout.strip()) * 1000))


# Network request construction, credentials and redirect rejection have one implementation.
from shared.stepfun_asr import ASRRedirectError, RejectASRRedirects, transcribe, credential


def atomic_json(path, value):
    path = guard_path(path)
    tmp = guard_path(path.with_suffix(path.suffix + ".tmp"))
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def complete(events):
    return isinstance(events, list) and all(isinstance(e, dict) for e in events) and any(e.get("type") == "transcript.text.done" for e in events)


def chunk_timeline(chunks, manifest=None):
    if manifest is not None:
        data = json.loads(manifest.read_text())
        rate = data["sample_rate"]
        if type(rate) is not int or rate <= 0: raise ValueError("Invalid source sample rate")
        rows = data["chunks"]
        if [r["name"] for r in rows] != [c.name for c in chunks]:
            raise ValueError("Chunk manifest ordering or names differ")
        offsets = []; end = 0
        for path, row in zip(chunks, rows):
            start, frames = row["start_frame"], row["frames"]
            if type(start) is not int or type(frames) is not int or start < end or frames <= 0:
                raise ValueError("Invalid or overlapping source frame offsets")
            if row.get("sha256") != sha256(path): raise ValueError("Chunk manifest audio hash differs")
            end = start + frames
            if data.get("source_frames", end) < end: raise ValueError("Chunk extends past source")
            offsets.append(round(Fraction(start * 1000, rate)))
        return offsets, "source_sample_frames"
    offsets = []; cursor = Fraction(0); exact = True
    for path in chunks:
        offsets.append(round(cursor * 1000))
        try:
            with wave.open(str(path), "rb") as f: cursor += Fraction(f.getnframes(), f.getframerate())
        except (wave.Error, EOFError):
            exact = False
            cursor += Fraction(duration_ms(path), 1000)
    return offsets, "pcm_sample_frames" if exact else "container_estimate_requires_review"


def positive_cues(cues, gap_ms=900):
    result = []; pending = []
    for cue in cues:
        if cue["end"] > cue["start"]:
            if pending and cue["start"] - pending[-1]["end"] <= gap_ms:
                cue = {**cue, "text": "".join(c["text"] for c in pending) + cue["text"],
                       "start": min(pending[0]["start"], cue["start"])}
            pending = []
            result.append(cue)
        elif result and cue["start"] - result[-1]["end"] <= gap_ms:
            result[-1]["text"] += cue["text"]
            result[-1]["end"] = max(result[-1]["end"], cue["end"])
        else: pending.append(cue)
    return result


def srt_clock(ms):
    total, milli = divmod(max(0, int(ms)), 1000)
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milli:03d}"


def grouped_cues(records, max_chars, gap_ms):
    cues, current = [], None
    soft_endings = set("。！？!?；;，,")
    hard_endings = set("。！？!?")
    for item in records:
        text = item.get("delta", "")
        if not text:
            continue
        start, end = item["global_start_ms"], item["global_end_ms"]
        if current is None:
            current = {"start": start, "end": end, "text": text}
        else:
            gap = start - current["end"]
            if gap > gap_ms or len(current["text"]) >= max_chars or current["text"][-1:] in soft_endings:
                cues.append(current)
                current = {"start": start, "end": end, "text": text}
            else:
                current["text"] += text
                current["end"] = max(current["end"], end)
        if current and (len(current["text"]) >= max_chars or current["text"][-1:] in hard_endings):
            cues.append(current)
            current = None
    if current:
        cues.append(current)
    return positive_cues(cues, gap_ms)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chunks", type=Path, help="directory containing ordered audio chunks")
    parser.add_argument("output", type=Path)
    parser.add_argument("--glob", default="chunk-*.mp3")
    parser.add_argument("--manifest", type=Path, help="Ordered source sample-frame offsets and proxy hashes")
    parser.add_argument("--adopt-legacy-cache", action="store_true", help="Explicitly bind a verified existing raw cache without uploading")
    parser.add_argument(
        "--api-base-url",
        default=os.environ.get("STEPFUN_API_BASE_URL", STEPFUN_API_BASE_URL),
    )
    parser.add_argument("--model", default="stepaudio-2.5-asr")
    parser.add_argument("--transcript-role", choices=["source","post-edit"], default="source")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--format", default="mp3")
    parser.add_argument("--channels", type=int, default=1)
    parser.add_argument("--hotword", action="append", default=[])
    parser.add_argument("--key-env", default="STEPFUN_API_KEY")
    parser.add_argument("--keychain-service", default="STEPFUN_API_KEY")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-chars", type=int, default=24)
    parser.add_argument("--gap-ms", type=int, default=900)
    parser.add_argument("--force", action="store_true", help="ignore per-chunk JSON caches")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    protect_output_args(args)
    args.url = api_url(args.api_base_url, ASR_PATH)

    chunks = sorted(args.chunks.glob(args.glob))
    if not chunks:
        raise SystemExit(f"No chunks matched {args.glob!r} in {args.chunks}")
    parsed = urlsplit(args.url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("ASR endpoint must not contain embedded credentials, query or fragment")
    offsets, timing_basis = chunk_timeline(chunks, args.manifest)
    parent_audio_sha256 = None
    if args.manifest: parent_audio_sha256 = json.loads(args.manifest.read_text()).get("source_sha256")
    if args.transcript_role == "post-edit" and (not isinstance(parent_audio_sha256,str) or len(parent_audio_sha256)!=64):
        raise ValueError("Post-edit ASR requires a source-sample manifest bound to the actual output audio hash")
    if args.dry_run:
        print(json.dumps({"api_base_url": args.api_base_url, "url": args.url, "model": args.model, "chunks": [str(p) for p in chunks], "offsets_ms": offsets, "timing_basis": timing_basis}, ensure_ascii=False, indent=2))
        return

    guard_directory(args.output, *chunks, *([args.manifest] if args.manifest else []))
    args.output.mkdir(parents=True, exist_ok=True)
    api_key = None
    all_events, delta_records, full_texts, timing_issues = [], [], [], []
    segment_limits = None
    source_segments = {}
    if args.manifest:
        manifest = json.loads(args.manifest.read_text())
        source_segments = {r["name"]: {"source_sha256":manifest.get("source_sha256"), "sample_rate":manifest["sample_rate"], "start_frame":r["start_frame"], "frames":r["frames"]} for r in manifest["chunks"]}
        segment_limits = {r["name"]: float(Fraction(r["frames"] * 1000, manifest["sample_rate"])) for r in manifest["chunks"]}
    for index, (chunk, offset) in enumerate(zip(chunks, offsets), 1):
        cache = args.output / f"{chunk.stem}.json"
        binding_path = cache.with_suffix(".request.json")
        binding = {"audio_sha256": sha256(chunk), "model": args.model, "language": args.language,
                   "hotwords": args.hotword, "format": args.format, "channels": args.channels,
                   "url": args.url, "offset_ms": offset, "timing_basis": timing_basis, "source_segment":source_segments.get(chunk.name)}
        events = None
        if cache.exists() and not args.force:
            if not binding_path.exists():
                if not args.adopt_legacy_cache:
                    raise ValueError("Legacy cache has no binding; retain it and explicitly verify/adopt before reuse")
                if not complete(json.loads(cache.read_text())): raise ValueError("Legacy cache is incomplete")
                atomic_json(binding_path, {**binding, "response_sha256": sha256(cache)})
            metadata = json.loads(binding_path.read_text())
            if {k:v for k,v in metadata.items() if k != "response_sha256"} != binding:
                raise ValueError("Cache binding differs; use a new output directory or explicitly force affected chunks")
            candidate = json.loads(cache.read_text(encoding="utf-8"))
            if complete(candidate):
                if metadata.get("response_sha256") != sha256(cache):
                    raise ValueError("Cache response hash differs; preserve it and verify before reuse")
                events = candidate
        if events is not None:
            print(f"[{index}/{len(chunks)}] cached {chunk.name}", flush=True)
        else:
            if api_key is None: api_key = credential(args.key_env, args.keychain_service)
            print(f"[{index}/{len(chunks)}] transcribing {chunk.name}", flush=True)
            events = transcribe(chunk, api_key, args)
            if not complete(events): raise ValueError("Incomplete ASR response; completed chunks retained")
            if cache.exists():
                archive = cache.with_name(cache.stem + ".previous-" + sha256(cache)[:12] + ".json")
                if not archive.exists(): archive.write_bytes(cache.read_bytes())
            atomic_json(cache, events)
            atomic_json(binding_path, {**binding, "response_sha256": sha256(cache)})
        all_events.append({"chunk": chunk.name, "offset_ms": offset, "events": events})
        done = next((e for e in reversed(events) if e.get("type") == "transcript.text.done"), None)
        if done and done.get("text"):
            full_texts.append(done["text"])
        for event in events:
            if event.get("type") != "transcript.text.delta" or not event.get("delta"):
                continue
            start, end = event.get("start_time"), event.get("end_time")
            if type(start) not in (int, float) or type(end) not in (int, float) or not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
                timing_issues.append({"chunk": chunk.name, "text": event["delta"], "reason": "missing_or_invalid_timestamp"})
                continue
            if segment_limits and end > segment_limits[chunk.name] + 1:
                timing_issues.append({"chunk":chunk.name,"text":event["delta"],"reason":"timestamp_outside_source_segment"})
                continue
            if delta_records and offset + round(start) < delta_records[-1]["global_end_ms"]:
                timing_issues.append({"chunk":chunk.name,"text":event["delta"],"reason":"overlapping_timestamp"})
                continue
            if start == end:
                timing_issues.append({"chunk": chunk.name, "text": event["delta"], "time_ms": offset + round(start),
                                      "reason": "zero_duration_event_merged_if_neighbor_exists"})
            delta_records.append({"delta": event["delta"], "global_start_ms": offset + round(start),
                                  "global_end_ms": offset + round(end), "chunk": chunk.name})

    (args.output / "raw-transcript.json").write_text(
        json.dumps({"provider": "StepFun", "model": args.model, "timing_basis": timing_basis, "audio_role":args.transcript_role, "audio_sha256":parent_audio_sha256, "timing_review_required": timing_basis == "container_estimate_requires_review", "chunks": all_events}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.output / "raw-transcript.txt").write_text("\n".join(full_texts), encoding="utf-8")
    atomic_json(args.output / "timing-issues.json", {"timing_basis": timing_basis, "issues": timing_issues})
    cues = grouped_cues(delta_records, args.max_chars, args.gap_ms)
    with (args.output / "raw-transcript.srt").open("w", encoding="utf-8") as handle:
        for number, cue in enumerate(cues, 1):
            handle.write(f"{number}\n{srt_clock(cue['start'])} --> {srt_clock(cue['end'])}\n{cue['text']}\n\n")
    print(f"done: {len(chunks)} chunks, {len(cues)} cues", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
