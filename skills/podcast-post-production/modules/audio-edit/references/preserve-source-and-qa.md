# Preserve source sound and report review status truthfully

Choose this profile when the user says not to process sound, or that mastering is already complete. This does not authorize extra deletions. Keep the confirmed delivery format and original media intact.

## PCM-only edit path

Set `sound_processing` to `preserve_source_no_mastering` in the EDL. Omission keeps `standard_mastering` and its existing behavior. The first preserve implementation accepts integer 16/24/32-bit PCM WAV, mono or stereo, and delivers WAV at the original sample rate, channels and bit depth. Reject incompatible sources/deliveries and explicit gain, high-pass or format changes; never silently fall back to mastering. NumPy is required for mixing and verification; use an isolated or host-bundled environment rather than changing global Python.

Keep the v3 authorization, stage and cut fields. Specify a 15–30 ms `crossfade_seconds` (default 20 ms). Non-overlapping retained PCM is copied byte for byte; local linear crossfades use only the indicated source contributors. Never merge a positive unapproved gap to make a short kept word disappear. Refine a too-short segment's boundaries instead. Version outputs; preserve mode never overwrites an existing WAV or its assembly report, even with the legacy `--force` option.

```bash
python3 scripts/render_podcast_edl.py SOURCE.wav EDL.json OUTPUT.wav --dry-run
python3 scripts/render_podcast_edl.py SOURCE.wav EDL.json OUTPUT.wav --review-copy
python3 scripts/audio_qa.py OUTPUT.wav --profile preserve-source \
  --source SOURCE.wav --edl EDL.json --assembly-map OUTPUT.wav.assembly.json \
  --json-out QA.json
```

The assembly report binds the source and output hashes, sample counts, retained spans and both source contributors for every fade. QA reconstructs the layout from the supplied approved EDL and compares every retained body and crossfade against the actual source. Loudness and long pauses remain measurements, not forced mastering targets in this profile. Exact equality plus convex fades prevents newly introduced PCM clipping; source clipping is not silently repaired.

## Timing and caches

```bash
python3 scripts/prepare_asr_chunks.py SOURCE.wav PROJECT/chunks
python3 scripts/transcribe_stepfun.py PROJECT/chunks PROJECT/asr \
  --manifest PROJECT/chunks/manifest.json
```

Preparation makes independent proxies and an exact source-sample manifest without uploading. The ASR cache binds proxy hash, model, parameters, endpoint and offset; complete responses survive failures and only incomplete/missing chunks are retried. A binding mismatch stops instead of reusing or silently uploading different material. Explicit `--adopt-legacy-cache` is available only after verifying legacy source provenance; it leaves raw responses unchanged. Previous replaced caches are archived.

Legacy calls without a manifest remain usable. PCM offsets use exact frame sums; lossy container-duration offsets are marked `container_estimate_requires_review` and cannot be treated as verified edit or final subtitle boundaries. Do not call those locators exact. Missing, invalid or overlapping timestamps stay in raw responses and `timing-issues.json`; they are not replaced by zero. Zero-duration events may join a real neighboring interval, never receive invented durations. For actual rendered-output ASR, prepare proxies from that WAV and pass `--transcript-role post-edit` with its manifest. The result records the output hash and role. Preserve-source editorial QA requires that hash to match audio QA; known staged/projection transcripts cannot satisfy the actual-output check. Clearly label source-cache projection separately from actual rendered-output ASR.

## Categories and actual listening

A content cut that also trims attached work silence is `content-with-pause-trim`, with `trims_adjacent_pause: true`, pause role, original/retained gap and ASR/waveform evidence. Do not rename it `false-start` to bypass the listening requirement. A normal executable pause cut still requires listening evidence. `--review-copy` permits already-approved content to be rendered without listening evidence as an explicitly unlistened draft; it does not permit unapproved cuts, unresolved manual treatments or executing review candidates. Every renderer audit starts with `delivery_state: review` and `release_ready: false`.

No actual listening capability means deliver only a clearly labelled review draft with the unresolved join list. Playing a browser control, matching ASR text or inspecting a waveform is not listening. Human full-length approval remains separate.

## Structured QA

Reports keep legacy boolean `checks` and add `check_statuses`: `passed`, `failed`, `not_run`, `blocked`, `not_applicable`. Unset editorial flags map to `not_run`, not a demonstrated failure. Legacy explicit pass flags remain reviewer attestations for older consumers; never set them based on browser or ASR success alone.

For new review drafts use `editorial_qa.py --review-records RECORDS.json`. Each of `sentence_integrity`, `logic_integrity`, `pacing_integrity`, `persona_integrity`, `join_listen` has a status. A passed record requires `reviewer`, `reviewed_at` and `evidence`; passed pacing, persona and join records also require `method: actual_listening`. Missing records remain `not_run`. Do not invent reviewers or evidence. All required checks, resolved content and signed full-length human listening must pass before the combined editorial QA can report release readiness. Audio measurement QA alone never grants publication readiness.
