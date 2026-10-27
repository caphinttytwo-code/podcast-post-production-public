#!/usr/bin/env python3
"""Resumable StepFun StepAudio SSE transcription for pre-chunked audio."""

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from .files import outside_package, child_output


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


class ASRRedirectError(RuntimeError):
    """The caller must approve an endpoint change before credentials are sent."""


class RejectASRRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # No redirect target is contacted; never log headers or Location values.
        if fp is not None:
            fp.close()
        raise ASRRedirectError(
            f"ASR HTTP {code} redirect rejected; verify the endpoint before retrying"
        )


def transcribe(path, api_key, args):
    payload = {
        "audio": {
            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
            "input": {
                "transcription": {
                    "language": args.language,
                    "hotwords": args.hotword,
                    "model": args.model,
                    "enable_itn": True,
                    "enable_timestamp": True,
                },
                "format": {"type": args.format, "channel": args.channels},
            },
        }
    }
    request = urllib.request.Request(
        args.url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    events = []
    try:
        with urllib.request.build_opener(RejectASRRedirects()).open(request, timeout=args.timeout) as response:
            for raw in response:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                event = json.loads(data)
                if event.get("type") == "error":
                    raise RuntimeError(event.get("message", "StepFun ASR error"))
                events.append(event)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:800]}") from exc
    return events


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
    return cues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chunks", type=Path, help="directory containing ordered audio chunks")
    parser.add_argument("output", type=Path)
    parser.add_argument("--glob", default="chunk-*.mp3")
    parser.add_argument(
        "--api-base-url",
        default=os.environ.get("STEPFUN_API_BASE_URL", STEPFUN_API_BASE_URL),
    )
    parser.add_argument("--model", default="stepaudio-2.5-asr")
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
    args.url = api_url(args.api_base_url, ASR_PATH)

    chunks = sorted(args.chunks.glob(args.glob))
    if not chunks:
        raise SystemExit(f"No chunks matched {args.glob!r} in {args.chunks}")
    offsets, cursor = [], 0
    for chunk in chunks:
        offsets.append(cursor)
        cursor += duration_ms(chunk)
    if args.dry_run:
        print(json.dumps({"api_base_url": args.api_base_url, "url": args.url, "model": args.model, "chunks": [str(p) for p in chunks], "offsets_ms": offsets}, ensure_ascii=False, indent=2))
        return

    outside_package(args.output)
    for name in [f"{chunk.stem}.json" for chunk in chunks] + ["raw-transcript.json", "raw-transcript.txt", "raw-transcript.srt"]:
        child_output(args.output, name, *chunks)
    args.output.mkdir(parents=True, exist_ok=True)
    api_key = None
    all_events, delta_records, full_texts = [], [], []
    for index, (chunk, offset) in enumerate(zip(chunks, offsets), 1):
        cache = args.output / f"{chunk.stem}.json"
        if cache.exists() and not args.force:
            events = json.loads(cache.read_text(encoding="utf-8"))
            print(f"[{index}/{len(chunks)}] cached {chunk.name}", flush=True)
        else:
            if api_key is None:
                api_key = credential(args.key_env, args.keychain_service)
            print(f"[{index}/{len(chunks)}] transcribing {chunk.name}", flush=True)
            events = transcribe(chunk, api_key, args)
            cache.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
        all_events.append({"chunk": chunk.name, "offset_ms": offset, "events": events})
        done = next((e for e in reversed(events) if e.get("type") == "transcript.text.done"), None)
        if done and done.get("text"):
            full_texts.append(done["text"])
        for event in events:
            if event.get("type") != "transcript.text.delta" or not event.get("delta"):
                continue
            delta_records.append({
                "delta": event["delta"],
                "global_start_ms": offset + int(event.get("start_time", 0)),
                "global_end_ms": offset + int(event.get("end_time", 0)),
                "chunk": chunk.name,
            })

    (args.output / "raw-transcript.json").write_text(
        json.dumps({"provider": "StepFun", "model": args.model, "chunks": all_events}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.output / "raw-transcript.txt").write_text("\n".join(full_texts), encoding="utf-8")
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
