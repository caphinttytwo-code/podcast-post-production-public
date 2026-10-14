#!/usr/bin/env python3
"""Combine editorial checks, review state, technical QA, and human approval."""

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args


import argparse
import json
import sys
from pathlib import Path


def read_json(path, label):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise ValueError(f"could not read {label}: {path}") from None
    except json.JSONDecodeError:
        raise ValueError(f"{label} is not valid JSON: {path}") from None


def transcript_has_content(path):
    try:
        if path.stat().st_size <= 0:
            return False
        if path.suffix.lower() != ".json":
            return bool(path.read_text(encoding="utf-8").strip())
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if isinstance(data.get("events"), list):
        return bool(data["events"])
    chunks = data.get("chunks")
    if not isinstance(chunks, list):
        return False
    return any(
        event.get("type") == "transcript.text.delta" and event.get("delta")
        for chunk in chunks if isinstance(chunk, dict)
        for event in chunk.get("events", []) if isinstance(event, dict)
    )


def reference_comparison_state(path):
    if path is None:
        return {
            "provided": False,
            "pending": 0,
            "sensitive_pending": 0,
            "resolved": True,
        }
    data = read_json(path, "reference comparison")
    if data.get("schema_version") != 1 or data.get("analysis_type") != "human-reference-edit-comparison":
        raise ValueError("reference comparison has an unsupported schema")
    events = []
    for field in ("content_events", "pause_events"):
        items = data.get(field, [])
        if not isinstance(items, list):
            raise ValueError(f"reference comparison {field} must be a list")
        events.extend(items)
    for index, event in enumerate(events, 1):
        if not isinstance(event, dict):
            raise ValueError(f"reference comparison event #{index} must be an object")
        if event.get("review_status") not in {"pending", "accepted", "rejected"}:
            raise ValueError(
                f"reference comparison event #{index} must have pending, accepted, or rejected review_status"
            )
    pending_events = [event for event in events if event.get("review_status") == "pending"]
    return {
        "provided": True,
        "event_count": len(events),
        "pending": len(pending_events),
        "sensitive_pending": sum(bool(event.get("sensitive_flags")) for event in pending_events),
        "resolved": not pending_events,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("edl", type=Path)
    parser.add_argument("post_edit_transcript", type=Path)
    parser.add_argument("audio_qa", type=Path)
    parser.add_argument("--sentence-pass", action="store_true")
    parser.add_argument("--logic-pass", action="store_true")
    parser.add_argument("--pacing-pass", action="store_true")
    parser.add_argument("--persona-pass", action="store_true")
    parser.add_argument("--reference-comparison", type=Path)
    parser.add_argument("--editorial-reviewer", required=True)
    parser.add_argument("--editorial-reviewed-at", required=True)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--require-release-ready", action="store_true")
    args = parser.parse_args()
    protect_output_args(args)

    edl = read_json(args.edl, "EDL")
    audio = read_json(args.audio_qa, "audio QA")
    if edl.get("version") != 3:
        raise ValueError("editorial QA requires EDL version 3")
    candidates = edl.get("review_candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("EDL review_candidates must be a list")
    invalid_candidate = next(
        (
            index
            for index, candidate in enumerate(candidates, 1)
            if not isinstance(candidate, dict)
            or candidate.get("status") not in {"pending", "rejected"}
        ),
        None,
    )
    if invalid_candidate is not None:
        raise ValueError(
            f"review candidate #{invalid_candidate} must have pending or rejected status"
        )
    pending = sum(
        candidate.get("status") == "pending"
        for candidate in candidates
    )
    transcript_present = transcript_has_content(args.post_edit_transcript)
    reference_state = reference_comparison_state(args.reference_comparison)
    checks = {
        "post_edit_transcript_present": transcript_present,
        "sentence_integrity": args.sentence_pass,
        "logic_integrity": args.logic_pass,
        "pacing_integrity": args.pacing_pass,
        "persona_integrity": args.persona_pass,
        "no_pending_review_candidates": pending == 0,
        "reference_comparison_resolved": reference_state["resolved"],
    }
    editorial_passed = all(checks.values())
    technical_passed = audio.get("technical_passed") is True
    human_review = audio.get("human_full_length_listen", {})
    human_approved = (
        isinstance(human_review, dict)
        and human_review.get("status") == "approved"
        and bool(human_review.get("reviewer"))
        and bool(human_review.get("reviewed_at"))
    )
    release_ready = editorial_passed and technical_passed and human_approved
    report = {
        "schema_version": 1,
        "edl_version": 3,
        "post_edit_transcript": str(args.post_edit_transcript),
        "checks": checks,
        "pending_review_candidates": pending,
        "reference_comparison": reference_state,
        "editorial_review": {
            "reviewer": args.editorial_reviewer,
            "reviewed_at": args.editorial_reviewed_at,
        },
        "editorial_passed": editorial_passed,
        "technical_passed": technical_passed,
        "human_full_length_listen": human_review,
        "release_ready": release_ready,
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(output + "\n", encoding="utf-8")
    if args.require_release_ready and not release_ready:
        return 1
    if not release_ready and not args.report_only:
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValueError as exc:
        raise SystemExit(f"editorial QA failed: {exc}") from exc
