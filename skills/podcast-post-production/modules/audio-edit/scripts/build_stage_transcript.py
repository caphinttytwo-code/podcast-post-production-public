#!/usr/bin/env python3
"""Build a mechanical-stage transcript without another ASR call."""

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args, outside_package, distinct_output


import argparse
import json
import sys
from pathlib import Path


MERGE_GAP_SECONDS = 0.1
DEFAULT_CROSSFADE_SECONDS = 0.02


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise ValueError(f"could not read {path}") from None
    except json.JSONDecodeError:
        raise ValueError(f"{path} is not valid JSON") from None


def source_events(data):
    chunks = data.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("StepAudio transcript must contain a chunks list")
    events = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise ValueError("transcript chunk must be an object")
        try:
            offset = int(chunk.get("offset_ms", 0))
        except (TypeError, ValueError):
            raise ValueError("transcript chunk has invalid offset_ms") from None
        chunk_name = str(chunk.get("chunk", ""))
        for event in chunk.get("events", []):
            if not isinstance(event, dict) or event.get("type") != "transcript.text.delta":
                continue
            text = str(event.get("delta", ""))
            if not text:
                continue
            try:
                start = offset + int(event["start_time"])
                end = offset + int(event["end_time"])
            except (KeyError, TypeError, ValueError):
                raise ValueError("transcript event has invalid timing") from None
            if start < 0 or end < start:
                raise ValueError("transcript event has reversed or negative timing")
            events.append({
                "text": text,
                "source_start_ms": start,
                "source_end_ms": end,
                "chunk": chunk_name,
            })
    events.sort(key=lambda item: (item["source_start_ms"], item["source_end_ms"]))
    if not events:
        raise ValueError("source transcript contains no timed text events")
    return events


def mechanical_cuts(edl):
    if edl.get("version") != 3:
        raise ValueError("stage transcript generation requires EDL version 3")
    basis = edl.get("transcript_basis")
    if not isinstance(basis, dict) or basis.get("semantic_based_on") != "mechanical":
        raise ValueError("EDL v3 requires mechanical transcript provenance")
    cuts = []
    for index, item in enumerate(edl.get("cuts", []), 1):
        if item.get("pass") != "mechanical":
            continue
        if item.get("decision_status") != "approved":
            raise ValueError(f"mechanical cut #{index} is not approved")
        try:
            start = round(float(item["start"]) * 1000)
            end = round(float(item["end"]) * 1000)
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"mechanical cut #{index} has invalid timing") from None
        if start < 0 or end <= start:
            raise ValueError(f"mechanical cut #{index} has an invalid interval")
        cuts.append({"source_start_ms": start, "source_end_ms": end})
    cuts.sort(key=lambda item: item["source_start_ms"])
    merged = []
    merge_gap_ms = round(MERGE_GAP_SECONDS * 1000)
    for item in cuts:
        if merged and item["source_start_ms"] <= merged[-1]["source_end_ms"] + merge_gap_ms:
            merged[-1]["source_end_ms"] = max(
                merged[-1]["source_end_ms"], item["source_end_ms"]
            )
        else:
            merged.append(dict(item))
    return merged


def overlaps(start, end, cut):
    return max(start, cut["source_start_ms"]) < min(end, cut["source_end_ms"])


def retained_events(events, cuts):
    retained = []
    for event_index, event in enumerate(events, 1):
        covering = [
            cut for cut in cuts
            if cut["source_start_ms"] <= event["source_start_ms"]
            and cut["source_end_ms"] >= event["source_end_ms"]
        ]
        if covering:
            continue
        partial = [
            cut for cut in cuts
            if overlaps(event["source_start_ms"], event["source_end_ms"], cut)
        ]
        if partial:
            raise ValueError(
                f"mechanical cut partially overlaps ASR event #{event_index}; "
                "narrow the cut or move it to review"
            )
        retained.append(dict(event))
    if not retained:
        raise ValueError("mechanical cuts remove every timed transcript event")
    return retained


def annotate_edit_timing(events, cuts, crossfade_ms):
    for cut in cuts:
        cut["internal_join"] = (
            any(event["source_end_ms"] <= cut["source_start_ms"] for event in events)
            and any(event["source_start_ms"] >= cut["source_end_ms"] for event in events)
        )
    for event in events:
        completed = [cut for cut in cuts if cut["source_end_ms"] <= event["source_start_ms"]]
        removed_ms = sum(
            cut["source_end_ms"] - cut["source_start_ms"] for cut in completed
        )
        join_ms = crossfade_ms * sum(cut["internal_join"] for cut in completed)
        shift = removed_ms + join_ms
        event["edit_start_ms"] = event["source_start_ms"] - shift
        event["edit_end_ms"] = event["source_end_ms"] - shift
        if event["edit_start_ms"] < 0 or event["edit_end_ms"] < event["edit_start_ms"]:
            raise ValueError("computed edit timeline is invalid")
    return events


def srt_clock(ms):
    total, milli = divmod(max(0, int(ms)), 1000)
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milli:03d}"


def grouped_cues(events, max_chars, gap_ms):
    cues = []
    current = None
    soft_endings = set("。！？!?；;，,")
    hard_endings = set("。！？!?")
    for event in events:
        text = event["text"]
        start = event["edit_start_ms"]
        end = event["edit_end_ms"]
        if current is None:
            current = {"start": start, "end": end, "text": text}
        else:
            gap = start - current["end"]
            if (
                gap > gap_ms
                or len(current["text"]) >= max_chars
                or current["text"][-1:] in soft_endings
            ):
                cues.append(current)
                current = {"start": start, "end": end, "text": text}
            else:
                current["text"] += text
                current["end"] = max(current["end"], end)
        if (
            current
            and (
                len(current["text"]) >= max_chars
                or current["text"][-1:] in hard_endings
            )
        ):
            cues.append(current)
            current = None
    if current:
        cues.append(current)
    return cues


def output_paths(prefix):
    value = str(prefix)
    return {
        "json": Path(value + ".json"),
        "txt": Path(value + ".txt"),
        "srt": Path(value + ".srt"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_transcript", type=Path)
    parser.add_argument("edl", type=Path)
    parser.add_argument("output_prefix", type=Path)
    parser.add_argument("--max-chars", type=int, default=24)
    parser.add_argument("--gap-ms", type=int, default=900)
    args = parser.parse_args()
    protect_output_args(args)

    transcript = read_json(args.source_transcript)
    edl = read_json(args.edl)
    events = source_events(transcript)
    cuts = mechanical_cuts(edl)
    retained = retained_events(events, cuts)
    crossfade_ms = round(
        float(edl.get("crossfade_seconds", DEFAULT_CROSSFADE_SECONDS)) * 1000
    )
    if crossfade_ms < 0:
        raise ValueError("crossfade_seconds must not be negative")
    annotate_edit_timing(retained, cuts, crossfade_ms)
    cues = grouped_cues(retained, args.max_chars, args.gap_ms)
    paths = output_paths(args.output_prefix)
    for destination in paths.values():
        outside_package(destination)
        distinct_output(destination, args.source_transcript, args.edl)
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "schema_version": 1,
        "stage": "mechanical",
        "provider": transcript.get("provider"),
        "model": transcript.get("model"),
        "source_transcript": str(args.source_transcript),
        "edl": str(args.edl),
        "timeline_basis": "rendered-with-crossfades",
        "crossfade_ms": crossfade_ms,
        "summary": {
            "source_events": len(events),
            "retained_events": len(retained),
            "mechanical_cuts": len(cuts),
            "removed_source_ms": sum(
                item["source_end_ms"] - item["source_start_ms"] for item in cuts
            ),
        },
        "mechanical_cuts": cuts,
        "events": retained,
    }
    paths["json"].write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    paths["txt"].write_text(
        "\n".join(cue["text"] for cue in cues) + "\n", encoding="utf-8"
    )
    with paths["srt"].open("w", encoding="utf-8") as handle:
        for number, cue in enumerate(cues, 1):
            handle.write(
                f"{number}\n{srt_clock(cue['start'])} --> {srt_clock(cue['end'])}"
                f"\n{cue['text']}\n\n"
            )
    print(json.dumps({
        "outputs": {key: str(value) for key, value in paths.items()},
        **report["summary"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        raise SystemExit(f"stage transcript generation failed: {exc}") from exc
