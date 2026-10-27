# Reference Audio Video Conform

The edited reference is the complete content and timing target. Keep every reference passage in order and remove only source-picture spans absent from it.
Maintain the repository copy; installed copies are validated runtime copies.

## Operating contract

- Preserve source media and approved finals. Never overwrite, move, rename, or delete them.
- Do not perform candidate selection, story extraction, cover design, titles, framing, grading, or other packaging unless separately requested.
- Create subtitles only when separately requested. Derive their timebase from the locked final video, or an explicitly designated audio with that same timebase; do not use a pre-conform source or superseded render.
- Treat the reference audio as the complete editorial target, not as a guide for selecting excerpts.
- Align the source video directly to the chosen reference. Do not inherit old cut points from an earlier audio edition when cumulative drift exists.
- Keep real on-camera events—including a person temporarily leaving frame—when their corresponding reference audio remains.
- Default to B: retained source picture plus the uninterrupted reference audio. Do not stitch source audio in B.
- Default to three softened frames at 30 fps. Permit 3–5 frames after sample review. Keep the output timeline unchanged.
- Require an approval sample before the full render unless the user explicitly waives it.
- Treat structural EDL validity as necessary but insufficient. Require content-aware acoustic checks before approval.
- Detect variable/irregular frame rate and stream-start anomalies. Calibrate every input seek before sampling or rendering risky media.
- Refuse existing output paths. Render to a partial filename, validate it, then atomically rename it.
- Delete intermediates only after explicit user authorization and a dry-run inventory.

## Route the task

- Full conform: read [startup and layout](references/production-workflow.md#start-the-job), then the acoustic EDL, sample, render, and QA sections before their corresponding steps.
- Continue: reuse the exact chosen reference, approved EDL/sample, and complete caches. Confirm that the requested work still matches those inputs and the locked specification.
- Subtitle-only or same-timebase audio continuation: lock the chosen final picture/audio and the approved proofreading range; read [subtitle workflow](references/subtitle-workflow.md) and [proofread SRT procedure](references/production-workflow.md#optional-proofread-srt). Do not reopen the conform or story selection. Reuse approved text, caches and listening decisions; choose the existing style or the optional `compact-clean` profile. For contextual listening and saved decisions, read [review tools](references/subtitle-review.md).
- Cleanup-only: read [manifest and cleanup](references/manifest-and-cleanup.md) and [cleanup procedure](references/production-workflow.md#safe-cleanup-and-placeholders). Inventory first; execute only explicitly authorized paths.
- Story selection or vertical packaging belongs to `trailers` module. Exact removals or local fixes to an approved master belong to `locked-revision` module.

## Conform workflow

1. Identify exactly one source and target reference, hash/probe inputs, and record timing risks and output specification. Ambiguous reference versions require clarification. Default to `B/reference-audio`; use `A/source-audio` only when explicitly requested.
2. Read [direct acoustic EDL](references/production-workflow.md#build-the-direct-acoustic-edl). Use `scripts/build_acoustic_edl.py`; verify multiple opening anchors and every retained region with `scripts/validate_edl.py --content-check` before any render. Stop on reordered, missing, or unstable reference content.
3. Read [B approval sample](references/production-workflow.md#make-the-b-approval-sample). Generate the ≤2-minute sample with `scripts/make_approval_sample.py`, including representative and risky joins; lock the exact EDL, audio strategy, join style, and specification after approval.
4. Read [full B render](references/production-workflow.md#render-the-full-b-conform). When seek calibration is required, use `scripts/calibrate_manifest_seeks.py` for the exact manifest revision and reject unsafe segments. Inspect the dry-run before `scripts/render_reference_conform.py --execute`.
5. Validate picture duration against continuous reference sound, inspect/listen around every join and key checkpoints, and fully decode the output. Follow [QA and delivery](references/production-workflow.md#qa-and-delivery); version and delivery-copy hashes must match.

## Acceptance and delivery

- Preserve original geometry and the approved timeline. Do not add framing, covers, titles, grading, subtitles, or other packaging without the corresponding request.
- When subtitles are requested, use real timestamps from the locked final timebase and run `scripts/validate_srt.py` against that video. Structural, timing, house-style, or glossary failures block subtitle delivery.
- Deliver only the approved master and requested same-basename UTF-8 SRT. Keep samples, raw ASR, timestamp evidence, PCM, features, filters, manifests, and QA outside delivery.
- Keep technical checks distinct from human viewing, listening, and subtitle proofreading; do not claim a human pass or release readiness without an actual review record.
- A user-accepted issue remains a documented exception with exact time range, symptom, date, version/hash, and later-version fix requirement; acceptance does not turn a failed check into a pass.
- Cleanup requires a dry-run inventory and exact authorization; recheck protected inputs and outputs afterward. Never infer that an older reference may be deleted.
- Find existing script roles in [resources](references/production-workflow.md#resources); resolve commands from the skill directory.

## rc6.3 subtitle source adaptation

The opt-in numeric style/review scope, exact punctuation exceptions, explicitly selected adjacent-cue merges, cue-number mapping and source/zero-duration audit come from pinned upstream PR #4 commit b84c5ed7660721a23bf9abb5f46dbc27984cc144 (OPEN, not merged).
Read [subtitle workflow](references/subtitle-workflow.md) and [contextual review](references/subtitle-review.md) for these options. Defaults stay spoken style and uncertain-only review. Unselected/uncertain items remain pending or unchanged; never manufacture time boundaries.
These rules apply only here. Do not alter trailer or locked-revision subtitle rules or restart conform/story editing for same-timebase subtitle continuation.
