# Production workflow

Read only the sections needed for the current task. Commands and backticked `scripts/`, `assets/`, and `references/` paths are relative to the skill directory (the directory containing `SKILL.md`), not this reference file. Resolve that directory before running commands.

## Start the job

Use a Python runtime with NumPy plus `ffmpeg`/`ffprobe`. In Codex desktop, load the bundled workspace dependencies and use its Python executable when the default Python lacks NumPy.

1. Inspect all candidate media and identify exactly one source video, one target reference audio, and any older reference editions.
2. Probe duration, resolution, frame rate, audio layout, rotation, and stream start times with `ffprobe`.
3. Confirm the locked strategy:
   - `B/reference-audio` (default): edit source picture to the target and use the continuous reference audio in the final.
   - `A/source-audio` (only if explicitly requested): edit picture and source audio together, then microfade source-audio joins.
4. If filenames or the intended final audio are ambiguous, stop and ask. Never infer which edition may be deleted.
5. Create a non-destructive project layout:

```text
project/
  manifests/
  work/JOB_ID/{audio,features,previews,qa,scripts}/
  work/subtitles-v01/{audio,chunks,asr-raw,qa,scripts}/  # only when requested
  versions/videos/
  delivery/
```

6. Record absolute input paths, hashes, stream timing risk, the selected audio strategy, output specification, and overwrite policy in the manifest.

## Build the direct acoustic EDL

1. Extract 8 kHz mono signed-16-bit PCM from the source video and target audio. Retain these only as regenerable caches.
2. Establish the opening offset only when several overlapping 4–6 second anchors at different opening positions agree and beat alternate matches. Stop on ambiguity; never seed a full EDL from one short global match.
3. Establish a monotonic source-to-reference time map using coarse acoustic anchors, then refine it near every offset change on a 10 ms grid.
4. Reject reordered matches, backward source time, overlapping retained intervals, unstable short offset plateaus, and low-confidence content regions.
5. Convert offset changes into retained source intervals. Write source and reference timestamps in `HH:MM:SS.mmm` plus numeric seconds.
6. Run content-aware checks across every retained segment plus dedicated checkpoints throughout the first 30 seconds. A contiguous, monotonic EDL may still be wrong.
7. Audit every boundary around speech, breaths, room tone, and visible action. Automated alignment proposes boundaries; it does not waive listening and frame review.
8. Use `scripts/build_acoustic_edl.py` for the initial EDL and require `scripts/validate_edl.py --content-check` before any render.

Example:

```bash
python3 scripts/build_acoustic_edl.py \
  --source-video /absolute/project/source.mp4 \
  --reference-audio /absolute/project/2nd-edition.mp3 \
  --project-root /absolute/project \
  --job-id episode-reference-conform-v01

python3 scripts/validate_edl.py \
  /absolute/project/manifests/episode-reference-conform-v01.json \
  --content-check
```

If the reference contains rearranged passages, extensive music replacement, or speech not present in the source, stop and report that a monotonic direct conform cannot represent it safely.

## Make the B approval sample

- Use `scripts/make_approval_sample.py`; it automatically selects opening, middle, ending, largest-removal, early, and late joins while keeping the combined sample under two minutes. Use explicit `--cut-id` values when visible-action or low-confidence joins need priority.
- Select joins from the opening, middle, ending, the largest removals, and any visible action discontinuities.
- Keep the sample at or below two minutes. Put the real join at a consistent point within each excerpt.
- Use the exact B audio treatment: the corresponding continuous target-audio passage, not stitched source audio.
- Use the same visual join proposed for the final: hold the last outgoing frame while the first 3 frames of the incoming shot fade in, then continue from incoming frame 4. This softens the jump without shortening the timeline.
- Provide a contact sheet or labeled join index for review, but keep these outside `delivery/`.
- If requested, make an A/B pair with identical picture: A uses joined source audio; B uses continuous reference audio.

```bash
python3 scripts/make_approval_sample.py \
  /absolute/project/manifests/episode-reference-conform-v01.json \
  --output-dir /absolute/project/work/episode-reference-conform-v01/previews
```

After approval, lock audio strategy, join style, soft-frame count, EDL, and output specification. Record any exception per join rather than silently changing all joins.

## Optional proofread SRT

Read `references/subtitle-workflow.md` before transcription or subtitle delivery.

1. Confirm the final video is locked and check whether a usable same-timebase SRT already exists.
2. Extract 16 kHz mono audio from the locked final. Use StepAudio 2.5 first for Chinese text unless the user chooses another provider.
3. Require real word or utterance timestamps. Do not treat zero-filled SSE `start_time`/`end_time` values or character-proportional estimates as a final subtitle timeline.
4. Prefer the provider's asynchronous file ASR for timestamps. If a full file is blocked or unreliable, use overlapping three-minute windows; retry failed windows as overlapping one-minute windows. Deduplicate by each window's non-overlap core.
5. Produce a cleaned spoken-language SRT: correct verified names and terms, remove non-semantic fillers and stutters, preserve meaning and emphatic repetition, and follow the selected subtitle style for semantic segmentation, natural line breaks and screen length. The optional `compact-clean` profile and second-pass semantic review are defined in the subtitle workflow.
6. Save raw ASR and timestamp data outside `delivery/`. Deliver only a UTF-8 SRT beside the locked final with the same basename.
7. Run `scripts/validate_srt.py DRAFT.srt --video LOCKED_FINAL.mp4`, adding verified `--bad-term WRONG=CORRECT` pairs from the glossary. A structural, overlap, duration, length, punctuation, or terminology failure blocks delivery.
8. Close temporary tunnels, delete explicitly created cloud test files when authorized, validate the SRT, then use a partial filename and atomic rename. Never overwrite an existing subtitle.

## Render the full B conform

Use `scripts/render_reference_conform.py`. It consumes the EDL manifest, trims only source picture, applies timeline-neutral softened joins, and maps the uninterrupted target audio.

If `source_timing.requires_seek_calibration` is true, calibrate every segment first. The calibration must cover the exact manifest revision, report zero unsafe segments, retain correlation of at least 0.80, and keep residual error within 5 ms.

```bash
python3 scripts/calibrate_manifest_seeks.py \
  /absolute/project/manifests/episode-reference-conform-v01.json \
  --output /absolute/project/work/episode-reference-conform-v01/qa/seek-calibration.json
```

```bash
python3 scripts/render_reference_conform.py \
  /absolute/project/manifests/episode-reference-conform-v01.json \
  --seek-calibration /absolute/project/work/episode-reference-conform-v01/qa/seek-calibration.json \
  --output /absolute/project/versions/videos/episode-reference-conform-v01.mp4

# Inspect the dry-run summary, then explicitly render:
python3 scripts/render_reference_conform.py \
  /absolute/project/manifests/episode-reference-conform-v01.json \
  --seek-calibration /absolute/project/work/episode-reference-conform-v01/qa/seek-calibration.json \
  --output /absolute/project/versions/videos/episode-reference-conform-v01.mp4 \
  --execute
```

Default output: original geometry, H.264, manifest-locked fps, CRF 21, yuv420p, AAC stereo 48 kHz at 192 kbps, and `+faststart`. Do not add black frames, subtitles, covers, titles, borders, or grading.

## QA and delivery

1. Programmatically round-trip all timestamps and verify reference intervals are contiguous and source intervals are strictly increasing.
2. Require total picture duration to match reference audio within one output frame.
3. Listen and inspect at least one second around every join. Check consonants, repeated words, room-tone jumps, audio drift, held-frame artifacts, and action discontinuities.
4. Check opening, early section, midpoint, largest deletion, any temporary absence from frame, late section, final sentence, and final frame.
5. Verify the rendered output with `scripts/validate_edl.py MANIFEST --content-check --output VIDEO --full-decode`. Use `--delivery-copy DELIVERY` after copying to require identical hashes.
6. Copy only the approved master into `delivery/`. Hash the version and delivery copy and require equality.
7. Never place samples, PCM, features, filters, or QA assets in `delivery/`.
8. When subtitles are requested, require sequential cue numbers, valid monotonic non-overlapping timestamps, no empty cues, no overlong Chinese cues under the chosen house style, and a last cue within final-video duration. Spot-check opening, middle, ending, conform joins, and every corrected drift region.
9. If the user accepts a known issue, record its exact time range, observed symptom, automated-check limitation, user decision and date, affected version/hash, and the rule that any later fix must create a new version. Acceptance does not convert it into a passing automated check.

## Safe cleanup and placeholders

Read `references/manifest-and-cleanup.md` before cleanup. Then:

1. Inventory files larger than 10 MB and classify each as source, approved final, metadata/QA, or regenerable process data.
2. Run `scripts/cleanup_conform.py PROJECT_ROOT --source ... --final ...` without `--execute` and show the inventory.
3. Obtain explicit approval for every non-process file to be deleted, such as an older reference edition.
4. Run again with `--execute` and exact `--delete-extra` paths where authorized.
5. Leave `SOURCE_FILES_PLACEHOLDER.md`, `delivery/PLACEHOLDER.md`, and cache-directory `PLACEHOLDER.md` files. State that protected media remains in place until the user manually moves it.
6. Recheck protected file existence and hashes after cleanup.

The cleanup script may delete only recognized media/cache files under `work/` and `versions/videos/`, plus exact project-contained paths passed with `--delete-extra`. It must never infer that an older edition may be deleted.

## Resources

- `scripts/build_acoustic_edl.py`: generate a monotonic direct acoustic EDL and caches.
- `scripts/calibrate_fast_seek.py`: measure and correct actual ffmpeg input-seek landing against continuous PCM.
- `scripts/calibrate_manifest_seeks.py`: calibrate every retained segment and reject unsafe seeks.
- `scripts/make_approval_sample.py`: generate a ≤2-minute labeled B approval sample with calibrated joins when required.
- `scripts/render_reference_conform.py`: dry-run or render the B conform with continuous reference audio.
- `scripts/validate_edl.py`: validate EDL monotonicity, duration, and optional rendered output.
- `scripts/cleanup_conform.py`: dry-run-first cleanup with protected paths and placeholders.
- `scripts/validate_srt.py`: strict locked-final SRT structure, overlap, duration, house-style, length, and terminology validation.
- `references/manifest-and-cleanup.md`: manifest fields, audio strategies, directory boundaries, and cleanup rules.
- `references/subtitle-workflow.md`: provider selection, timestamp fallbacks, text cleanup, SRT construction, and subtitle QA.
