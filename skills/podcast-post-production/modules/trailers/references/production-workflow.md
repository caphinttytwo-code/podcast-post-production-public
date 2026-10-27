# Production workflow

Read only the sections needed for the current task. Commands and backticked `scripts/`, `assets/`, and `references/` paths are relative to the selected module directory (the directory containing module `workflow.md`), not this reference file. Resolve that directory before running commands.

## Start Every Job

1. Inspect the source directory, existing versions, source duration/resolution/fps/audio, subtitles, and available brand assets.
2. Classify the request:
   - `lightweight-talking-head`: one selected talking-head or口播 source needs cleanup, subtitles, a simple cover, PIP, or direct export. Skip the candidate pool unless structural story editing is requested.
   - `standard-clipping`: a long source needs transcript-wide candidate discovery and story selection.
   - `heavy-collab`: multiple outputs, teammates, assets, or high-stakes review require the full brief, asset log, version log, and review package.
   - `new`: no transcript or cut plan exists.
   - `continue`: reuse existing transcript, candidates, and caches.
   - `series-continue`: reuse the approved pilot EDL conventions, visual system, cover ratios, version prefix, and brand assets for the next `secNN` trailer.
   - `visual-only`: do not touch the edit; replace only frame/cover assets.
   - `review-proxy`: keep source media and SRT unchanged; create or refresh review copies only.
   - `subtitle-calibration`: preserve the locked picture edit while building or refining editable subtitles.
   - `revision`: preserve approved EDL/audio and change only requested layers.
   - `batch`: use one approved pilot as the template for remaining jobs.
3. Create a non-destructive project structure:

```text
project/
  sources/            # references or symlinks, never rewritten
  work/
    audio/
    transcript/
    candidates/
    previews/
  manifests/
  versions/
    videos/
    covers/
  delivery/
```

4. Write or update the manifest described in [references/batch-manifest.md](batch-manifest.md).
5. Read [references/workflow-and-handoff.md](workflow-and-handoff.md) when the job includes subtitles, PIP, reviewed revisions, or teammate handoff.

## Workflow

### 1. Ingest and transcribe

- Probe every source with `ffprobe`; record exact duration, streams, frame rate, rotation, and embedded/burned subtitle state.
- Extract mono speech audio without modifying the source. Split long audio into stable chunks and retain caches.
- If StepFun is available, use `scripts/transcribe_stepfun.py`. Run `--dry-run` first to verify chunk order, offsets, hotwords, and destinations.
- Use `https://api.stepfun.com/step_plan/v1` as the single StepFun API base. Derive service paths from it and override the base only through `STEPFUN_API_BASE_URL` or `--api-base-url`.
- Review the entire transcript before claiming exact candidate windows. Do not present invented timecodes from a partial transcript.
- Correct only recognition errors that affect meaning, names, punctuation, or subtitle readability. Preserve speaker intent.

### 2. Discover candidate stories

- For `standard-clipping` and `heavy-collab`, record purpose, audience, primary platform, target duration, core information, cold-viewer promise, source/transcript coverage, must-keep/remove constraints, and visual expectations before selecting clips.
- Translate vague style requests into concrete opening, pacing, subtitle, overlay, cover, and viewer-response decisions. Do not put “高级一点” or “节奏好一点” into an executable cut plan.
- Find self-contained tensions, reversals, realizations, anecdotes, or emotional turns rather than isolated quotable lines.
- Rank candidates with the gates in [references/story-and-editing.md](story-and-editing.md).
- For each candidate, record: hook, setup, escalation, payoff, start/end time, risks, proposed title, and why it stands alone.
- Default target is 5–10 minutes. Prefer a shorter complete story over a longer fragmented one.
- If the user requests only one, select the strongest candidate and finish it before expanding the batch.
- For an already selected lightweight talking-head source, record only platform, duration, keep/remove requirements, subtitle treatment, cover title, and any PIP assets; do not manufacture a candidate pool.

### 3. Build the cut plan

- Cut on complete clauses and natural breaths. Preserve the inhalation or room beat that makes a sentence feel human.
- Avoid abrupt cut-ins, clipped consonants, unfinished references, and reactions without their cause.
- Keep source boundaries in `HH:MM:SS.mmm`; never hand-convert transcript timecodes to raw seconds. Round-trip every parsed timestamp before render and compare it with the transcript.
- Prefer one continuous source interval over several adjacent micro-clips. If two selected intervals are separated by 0.5 seconds or less, merge them unless the gap contains material that must be removed.
- Record the first and last spoken words for every interval. Leave 4–12 frames before the first consonant and enough room tone after the complete clause or response to survive the audio crossfade.
- Default transition is 0.20 seconds; use 0.15–0.25 seconds when adjacent shots need softening. Do not dissolve across a meaning-changing pause.
- Keep original burned subtitles when the user requests them. If replacing subtitles, cover/remove the old layer cleanly; never stack two subtitle systems.
- Keep EDL decisions separate from the visual frame so a visual-only revision cannot silently change the story edit.
- Protect the buildup to an emotional peak. Never cut directly from setup to tears or cover eyes and mouth with a full-screen card.
- For book or product stories, establish why the person or problem matters before introducing the item, then explain viewer value before any sales close.

### 4. Name the trailer

- Give every trailer its own editorial title, even when the source episode already has a title.
- Prefer a concrete moment plus emotional consequence, typically 8–18 Chinese characters per line and no more than two lines on a phone cover.
- Maintain exact title text in the manifest; reuse the same string for cover, frame, filename slug, and QA.
- For multiple trailers under one approved visible version, keep the series version and advance the section: `v04-sec01`, `v04-sec02`, `v04-sec03`. Do not invent `v05` merely because a new story window is selected.

### 5. Build one visual preview

- Read [references/visual-system.md](visual-system.md) before composing frames or covers.
- Read [references/subtitles-and-timed-layers.md](subtitles-and-timed-layers.md) before adding replacement subtitles, image/video PIP, or quote-card layers.
- Use `scripts/build_visuals.py` for deterministic title/logo placement and photo fades.
- For a standard 1080×1920 layout, preserve a 1080×608 center video window at `y=656–1264` unless the project specifies another approved geometry.
- Generate a full-size static preview and a 270×480 phone thumbnail. Confirm both before video rendering.
- When continuing an approved series, read [references/approved-series-template.md](approved-series-template.md) and reuse its shared title/brand system. Generate every requested cover ratio as a separately composed layout, not a mechanical crop.
- If the frame must match the 9:16 cover, approve the 9:16 title block first, then generate the video overlay from the same typography configuration.
- Keep the video image, original subtitles, faces, microphones, and gestures unblocked.
- Generate quote cards and flower-text as deterministic transparent assets, then schedule them through `timed_layers`; do not require an external composition skill.

### 6. Render the pilot, then the batch

- Put approved EDLs and outputs into the JSON manifest.
- Put replacement subtitles in `subtitles` and scheduled image/video assets in `timed_layers`. Keep source, overlay, subtitle, and asset paths explicit.
- Run `scripts/subtitle_qa.py` before rendering any replacement SRT. Treat a structural or house-style failure as blocking.
- Run `scripts/render_batch.py MANIFEST --dry-run` and inspect every source/output pair.
- Read the EDL audit printed by the dry-run. Resolve timestamp round-trip mismatches, unexpectedly short clips, and adjacent-clip merge warnings before encoding.
- Render only the pilot first. Review opening, speaker introductions, emotional peak, all transitions, subtitles, and ending.
- After pilot approval, render the remaining jobs with resume behavior. Never overwrite finals unless the user explicitly authorizes `--force`.
- Before a forced revision, copy the previously reviewed master into `versions/archive/<job>-<reason>/`.
- Keep the final spoken clause intact. Configure `outro.fade_to_black` and optional `outro.black_hold` in the manifest instead of truncating speech to create an ending.

### 7. Validate and deliver

- Run `scripts/qa_outputs.py MANIFEST`.
- Inspect at least five frames per video: opening, early setup, midpoint, emotional peak, and closing.
- Listen across every join with headphones; image-only QA cannot catch clipped breaths or audio clicks.
- Review one second before and after every join, not only representative frames. A sentence-level subtitle ending on the out-frame is not proof that the spoken syllable or breath is complete.
- Verify exact title/subtitle strings and all logos visually at full size and phone-thumbnail size.
- Inspect every PIP/quote-card interval for face, mouth, subtitle, and product obstruction. Listen to every inserted video layer whose audio is mixed.
- Deliver only approved masters and requested covers. Keep process assets in `work/` or `versions/`, not `delivery/`.
- For the standard four-file package, deliver exactly one video plus 9:16, 3:4, and 4:3 covers. Keep QA, manifests, previews, and archived revisions outside `delivery/`.

## Revision Boundaries

When the user says the video content does not need changing, lock EDL, timing, audio, center-window pixels, and subtitles. Change only the top/bottom frame, title, background, and logos. When the user asks for a cover only, do not render or modify video.

When a title layout changes, update only the surfaces explicitly named by the user. Do not silently propagate a 9:16/3:4 alignment change to 4:3 or video. If the user later asks to unify the video frame with 9:16, render the frame from the approved 9:16 title configuration.

When a change would alter story meaning, duration, speaker representation, or approved brand identity, stop and request confirmation rather than treating it as a cosmetic revision.

Classify reviewed changes:

- Light: wording, term correction, cover text/color, or a timing change around 0.5 seconds. Version the affected surface and log it.
- Medium: add/drop/reorder a segment, replace PIP, move subtitles, change cover frame, transition, or audio treatment. Update the manifest, edit notes, and version log.
- Heavy: change the topic, audience, platform, duration, promise, story arc, or emotional peak. Summarize affected scope and obtain confirmation before revising the cut plan.

Preserve timecoded reviewer wording in the review log and translate it into the smallest concrete change.

## Failure Handling

- API authentication fails: verify endpoint family, key source, and user/account compatibility without printing the key.
- ASR request fails: retain chunk caches and resume only missing chunks.
- Font missing: select a local licensed fallback, regenerate the preview, and recheck Chinese glyph coverage.
- Logo has a white/black box: obtain the original transparent asset or apply deterministic background removal; do not AI-redraw it.
- Render fails midway: preserve completed versions, fix only the failing job, and resume.
- Exact edit is uncertain: expose the candidate and risk in the cut plan; do not hide uncertainty behind precise-looking timestamps.
- Speech feels rushed or incomplete: archive the reviewed master, compare every EDL boundary with the transcript, correct any timestamp conversion error, merge adjacent source clips, then extend handles before changing transition duration.
- A new MP4 reports `moov atom not found`: do not copy or QA it yet. Wait for `ffprobe` to read a stable duration; rerender only if the file remains unreadable after the bounded stability check.

## Resources

- [references/batch-manifest.md](batch-manifest.md): batch schema and naming conventions.
- [references/story-and-editing.md](story-and-editing.md): story gates, cut rhythm, subtitle, and audio rules.
- [references/visual-system.md](visual-system.md): configurable vertical frames, covers, logos, and approval previews.
- [references/approved-series-template.md](approved-series-template.md): reusable `VNN-secNN` continuation, multi-ratio cover, shared frame, archive, and outro rules distilled from an approved production.
- [references/subtitles-and-timed-layers.md](subtitles-and-timed-layers.md): Chinese subtitle house style, strict SRT QA, PIP/quote-card manifest fields, and single-encode rules.
- [references/multi-asr-subtitles.md](multi-asr-subtitles.md): optional multi-provider evidence roles, timestamp-to-cue alignment, and human-proofread boundaries.
- [references/review-proxies.md](review-proxies.md): idempotent MP4/SRT discovery, review rendering, and per-file QA.
- [references/headframe-candidates.md](headframe-candidates.md): source-immutable still candidates, previews, contact sheets, and selection status.
- [references/workflow-and-handoff.md](workflow-and-handoff.md): brief gates, lightweight/standard/heavy profiles, asset logging, review, versioning, and delivery.
- `scripts/transcribe_stepfun.py`: resumable StepAudio SSE transcription from chunked audio.
- `scripts/build_visuals.py`: deterministic frame overlay, static preview, mobile preview, and gradient cover.
- `scripts/subtitle_qa.py`: validate SRT structure, timing, length, house style, fillers, and project bad terms.
- `scripts/build_srt_from_timestamps.py`: align proofread cue text to timestamp evidence without hard-coded project terms or paths.
- `scripts/render_review_proxies.py`: discover paired MP4/SRT inputs and render isolated review copies with JSON and Markdown audits.
- `scripts/extract_headframe_candidates.py`: extract configured still candidates and create original, delivery, mobile, contact-sheet, and manifest outputs.
- `scripts/render_batch.py`: render EDL jobs, subtitles, static framing, timed PIP/quote assets, optional inserted audio, and soft transitions in one encode.
- `scripts/qa_outputs.py`: structural batch, duration, subtitle, cover, fade, and media validation.
- `assets/templates/`: copyable asset log, review, version log, and QA templates.
