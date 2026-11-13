#!/usr/bin/env python3
"""Assemble a new PCM review version from explicitly selected saved decisions."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import os
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.files import sha256
from shared.guards import guard_directory
from preserve_pcm import assemble, layout, pcm_info, verify
from render_podcast_edl import validate_edl
from review import Store, transaction_lock


def load(path):
    return json.loads(path.read_bytes())


def prepare(request):
    spec = load(request)
    if spec["schema_version"] != 1:
        raise ValueError("Unsupported PCM continuation schema")
    parent = (request.parent / spec["parent"]).resolve(strict=True)
    parent_version = spec["parent_version"]
    version = spec["version"]
    if not all(isinstance(x, str) and x.strip() for x in (parent_version, version)) or version == parent_version:
        raise ValueError("Require distinct parent and new version names")
    parent_hash = sha256(parent)
    if parent_hash != spec["parent_sha256"]:
        raise ValueError("Parent SHA-256 differs")
    review_dir = (request.parent / spec["review_dir"]).resolve(strict=True)
    review_files = {name: sha256(review_dir / name) for name in ("data.json", "manifest.json")}
    store = Store(review_dir)
    state_path = review_dir / "state.json"
    state_hash = sha256(state_path)
    state = store.read()
    if (store.binding["source_sha256"] != parent_hash or
            store.data["version"] != parent_version or
            state_hash != spec["review_state_sha256"] or sha256(state_path) != state_hash):
        raise ValueError("Review is not bound to this parent version and saved decision snapshot")

    info = pcm_info(parent)
    rate = info["sample_rate"]
    cuts, rows, seen = [], [], set()
    for item in spec["cuts"]:
        key = item["id"]
        if key in seen or key not in store.by or state["items"][key]["decision"] != "delete":
            raise ValueError("Missing, repeated or unapproved deletion: " + str(key))
        seen.add(key)
        start, end = item["parent_frames"]
        if (type(start) is not int or type(end) is not int or not 0 <= start < end <= info["frames"]):
            raise ValueError("Require exact parent sample frame mapping: " + key)
        cue = store.by[key]
        if (round(Decimal(start) * 1000 / rate), round(Decimal(end) * 1000 / rate)) != (
                cue["start_ms"], cue["end_ms"]):
            raise ValueError("Frame boundaries disagree with the approved review interval: " + key)
        cuts.append({"start": start / rate, "end": end / rate, "pass": "semantic",
                     "decision_status": "approved", "confidence": "high",
                     "category": "approved-content", "reason": "Bound review decision " + key})
        rows.append({"id": key, "parent_frames": [start, end]})
    if not rows:
        raise ValueError("No approved cuts selected")
    rows.sort(key=lambda row: row["parent_frames"])
    for left, right in zip(rows, rows[1:]):
        if left["parent_frames"][1] >= right["parent_frames"][0]:
            raise ValueError("Touching or overlapping decisions need a reconciled review interval")

    basis = {k: str((request.parent / spec["transcript_basis"][k]).resolve(strict=True))
             for k in ("source", "mechanical")}
    edl = {"version": 3, "branch": "approved-content-continuation", "source_sha256": parent_hash,
           "sound_processing": "preserve_source_no_mastering", "cuts": cuts,
           "transcript_basis": {**basis, "semantic_based_on": "mechanical"},
           "crossfade_seconds": spec.get("crossfade_seconds", .020)}
    validate_edl(edl, review_copy=True)
    layout(info, cuts, edl["crossfade_seconds"])
    evidence = {review_dir / name: digest for name, digest in review_files.items()}
    evidence.update({state_path: state_hash, parent: parent_hash})
    evidence.update({Path(path): sha256(Path(path)) for path in basis.values()})
    if any(sha256(path) != expected for path, expected in evidence.items()):
        raise ValueError("Continuation inputs changed during preparation")
    return spec, parent, store, state_hash, state, edl, rows, evidence


def write_json(path, data):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def run_revision(request, out):
    request = request.resolve(strict=True)
    request_hash = sha256(request)
    spec, parent, store, state_hash, state, edl, rows, evidence = prepare(request)
    out = guard_directory(out, request, parent, store.root, *[
        Path(edl["transcript_basis"][key]) for key in ("source", "mechanical")
    ]).absolute()
    if sha256(request) != request_hash:
        raise ValueError("Request changed during preparation")
    if out.exists():
        raise FileExistsError("Use a fresh revision directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=".pcm-review-", dir=out.parent))
    try:
        wave = staged / "review.wav"
        report = assemble(parent, wave, edl)
        # Boundary deletions have no crossfade and must not borrow another cut's join.
        by_boundaries = {(join["left_source_frames"][1], join["right_source_frames"][0]): join
                         for join in report["joins"]}
        for row in rows:
            join = by_boundaries.get(tuple(row["parent_frames"]))
            row["new_join_frames"] = ([join["output_start_frame"], join["output_end_frame"]] if join else None)
        write_json(staged / "edl.json", edl)
        record = {"schema_version": 1, "parent_version": spec["parent_version"], "version": spec["version"],
                  "parent_sha256": edl["source_sha256"], "request_sha256": request_hash,
                  "review_state_sha256": state_hash, "review_revision": state["revision"],
                  "input_sha256": {str(path): digest for path, digest in evidence.items()},
                  "selected": rows, "pending_review_ids": sorted(
                      key for key, value in state["items"].items() if value["decision"] in ("pending", "uncertain")),
                  "approved_unselected_ids": sorted(key for key, value in state["items"].items()
                                                    if value["decision"] == "delete" and key not in {x["id"] for x in rows}),
                  "sample_rate": report["source_spec"]["sample_rate"],
                  "retained_pcm_verification": report["verification"],
                  "human_join_listening": "NOT RUN", "human_full_review": "NOT RUN", "release_ready": False}
        write_json(staged / "continuation.json", record)
        with (staged / "接点复听.md").open("x", encoding="utf-8") as handle:
            handle.write("# 接点复听\n\n父版与新版均以样本帧表示。人工复听待完成。\n\n")
            handle.write("| 条目 | 父版删除帧 | 新版淡化帧 |\n|---|---|---|\n")
            for row in rows:
                handle.write(f"| {row['id']} | {row['parent_frames']} | {row['new_join_frames']} |\n")
            handle.write("\n待确认：" + "、".join(record["pending_review_ids"]) + "\n")
        with transaction_lock(store.root):
            if sha256(request) != request_hash or any(sha256(path) != digest for path, digest in evidence.items()):
                raise ValueError("Parent, request or review changed during assembly")
            if out.exists() or out.is_symlink():
                raise FileExistsError("Revision destination already exists")
            os.rename(staged, out)
        return record
    finally:
        if staged.exists():
            shutil.rmtree(staged)


def verify_revision(request, output):
    _, parent, _, state_hash, _, edl, rows, evidence = prepare(request)
    record = load(output / "continuation.json")
    report = load(output / "review.wav.assembly.json")
    keep, fade = layout(pcm_info(parent), edl["cuts"], edl["crossfade_seconds"])
    selected = [{"id": row["id"], "parent_frames": row["parent_frames"]} for row in record["selected"]]
    if (record["request_sha256"] != sha256(request) or record["review_state_sha256"] != state_hash
            or record["input_sha256"] != {str(path): digest for path, digest in evidence.items()}
            or selected != rows or keep != report["keep_segments"] or fade != report["crossfade_frames"]):
        raise ValueError("Revision record or assembly mapping differs")
    return verify(parent, output / "review.wav", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("review", "verify"))
    parser.add_argument("request", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    try:
        result = (run_revision(args.request, args.output_dir) if args.action == "review" else
                  verify_revision(args.request.resolve(strict=True), args.output_dir))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if args.action == "verify" and not all(result.values()) else 0
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
