# Batch Long Video Trailers

Turn long sources into complete vertical stories with consistent visuals, covers, versioning, and QA. Default story length is 5–10 minutes; prefer a shorter complete story when warranted.
Maintain the repository copy; installed copies are validated runtime copies.

## Operating Contract

- Preserve source media. Never overwrite source videos, approved masters, logos, or covers.
- Make one pilot trailer and one static visual preview before rendering a batch.
- Require approval of the pilot's story, cut rhythm, frame, title system, and logo treatment before scaling.
- Use original pixels for people and logos. Never ask an image model to redraw a face, Chinese title, or brand mark.
- Keep credentials out of commands, logs, manifests, and deliverables. Read StepFun keys from an environment variable or macOS Keychain.
- Do not delete intermediates unless the user explicitly asks. When asked, remove only identified process outputs and retain sources plus approved finals.
- Keep a batch resumable and idempotent: skip existing approved outputs by default; require an explicit overwrite flag.
- Treat the approved cover and video frame as one visual system. Shared title colors, alignment, spacing, subtitle, separator, paper, and logos must come from one configuration.
- Treat subtitles, timed layers, covers, assets, and reviewed renders as versioned project surfaces. Never overwrite a reviewed file.
- End on a complete clause or resolving reaction. When requested, preserve the complete final words before adding a full-frame fade to black.

## Route the task

Inspect sources, existing versions, brand assets, transcripts, and output requirements. Read the relevant [startup mode and layout](references/production-workflow.md#start-every-job).

- `lightweight-talking-head`: an already selected source needs cleanup, subtitles, a simple cover, PIP, or export. Do not create a candidate pool unless story editing is requested.
- `standard-clipping` / `heavy-collab`: discover stories across the transcript; use the full brief and asset/review records where collaboration or review risk requires them.
- `new` / `continue` / `batch`: start from source evidence, reuse approved transcripts/caches, or scale only after pilot approval.
- `series-continue`: read [approved series template](references/approved-series-template.md); preserve the approved frame, brand system, naming, and separately composed cover ratios.
- `visual-only` / cover-only: lock picture EDL, timing, audio, center-window pixels, and subtitles. Change only requested visual surfaces; do not render video for a cover-only request.
- `revision`: version and log the affected surfaces. Read [revision boundaries](references/production-workflow.md#revision-boundaries); changes to meaning, duration, speaker representation, or approved branding need confirmation.
- Exact removals or local timing/audio/subtitle fixes to an approved master use `locked-revision` module. Complete picture alignment to edited audio uses `video-conform` module.

## Specialized Modes

- For multi-provider Chinese subtitle calibration or rebuilding an SRT from timestamp evidence, read [references/multi-asr-subtitles.md](references/multi-asr-subtitles.md).
- For recursively discovering matching MP4/SRT pairs and creating review copies, read [references/review-proxies.md](references/review-proxies.md) and use `scripts/render_review_proxies.py`.
- For visual-only still-frame candidate work, read [references/headframe-candidates.md](references/headframe-candidates.md) and use `scripts/extract_headframe_candidates.py`.
- A request to remove or rearrange content in an already approved master is not a visual-only revision. Use a dedicated locked-revision workflow when available; otherwise stop and confirm the exact mutable surfaces before editing.

## Production routing

Read only the applicable [workflow steps](references/production-workflow.md#workflow) before carrying them out:

1. Probe and transcribe sources; reuse caches and correct only recognition errors. Never invent candidate timecodes from partial coverage.
2. Discover complete stories using [story and editing rules](references/story-and-editing.md), then build a source-timecode cut plan with complete clauses and natural handles.
3. Record exact titles and paths in the [batch manifest](references/batch-manifest.md); keep story EDL separate from visual design.
4. Before covers or frames, read [visual system](references/visual-system.md). Before subtitles, PIP, or quote cards, read [subtitles and timed layers](references/subtitles-and-timed-layers.md). Before subtitle/PIP/review/handoff work, read [workflow and handoff](references/workflow-and-handoff.md).
5. Generate the static full-size and phone previews, obtain the required approvals, validate replacement SRT, and inspect `scripts/render_batch.py MANIFEST --dry-run` before encoding.
6. Render and review the pilot before scaling. Resume approved outputs; version reviewed files and archive the prior master before an authorized forced revision.
7. Run `scripts/qa_outputs.py MANIFEST` and complete frame, subtitle, logo, PIP, ending, and every-join listening checks in [validation and delivery](references/production-workflow.md#7-validate-and-deliver).

## Acceptance and delivery

- Keep the final spoken clause intact and retain the approved outro treatment. Do not silently propagate a layout revision into other aspect ratios or video.
- Deliver approved masters and requested covers only. The standard package is one video plus separately composed 9:16, 3:4, and 4:3 covers; process assets and review archives remain outside delivery.
- Record only review actually performed. Technical checks and sampled inspections do not establish a full human viewing/listening pass or permission to publish.
- Preserve timecoded reviewer comments and apply the smallest authorized change. For uncertain edits or failed renders, read the relevant [failure handling](references/production-workflow.md#failure-handling) entry.
- Find existing scripts and copyable logs in [resources](references/production-workflow.md#resources); resolve commands from the skill directory.
