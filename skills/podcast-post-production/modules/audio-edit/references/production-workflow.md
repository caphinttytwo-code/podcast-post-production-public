# Production workflow

Read only the sections needed for the current task. Commands and backticked `scripts/`, `assets/`, and `references/` paths are relative to the skill directory (the directory containing `SKILL.md`), not this reference file. Resolve that directory before running commands.

## Start Every Job

1. Probe the source with `ffprobe`; record duration, codec, sample rate, channels, bit depth, bitrate, and metadata.
2. Classify the job as `new`, `continue`, `compare`, or `revision`.
3. Create a non-destructive layout:

```text
project/
  source/                 # source reference or symlink
  work/
    chunks/
    transcript/
      raw-transcript.json
      mechanical-vNN.json
      mechanical-vNN.txt
      mechanical-vNN.srt
      post-edit-vNN/
      reference-edited-vNN/
    audio/
  notes/
    edit-brief.md
    edl-vNN.json
    edit-notes-vNN.md
    reference-comparison-vNN.md
    reference-memory-vNN.json
  output/
    episode-vNN.mp3       # when MP3 is selected
    episode-vNN.wav       # when WAV is selected
  qa/
    qa-vNN.json           # one delivery format
    qa-vNN-mp3.json       # both formats
    qa-vNN-wav.json       # both formats
    editorial-qa-vNN.json
```

4. Reuse complete ASR caches and existing approved decisions. Never restart a full transcription merely because the sound master changes.

## Workflow

### 1. Transcribe and inspect

For exact source-sample proxy manifests, cache binding and legacy timing limits, read [preserve source and QA](preserve-source-and-qa.md#timing-and-caches). For a user confirmation page, read [paragraph review](paragraph-review.md) before generating candidates.

- Extract 16 kHz mono MP3 proxy chunks of about five minutes while preserving the source.
- Run `scripts/transcribe_stepfun.py CHUNKS OUTPUT --dry-run`, inspect order and offsets, then run without `--dry-run`.
- Use `https://api.stepfun.com/step_plan/v1` as the single StepFun API base; derive service-specific paths from it. Override the base only through `STEPFUN_API_BASE_URL` or `--api-base-url`.
- Read credentials from `STEPFUN_API_KEY`, then macOS Keychain service `STEPFUN_API_KEY`. Never print the key.
- Use `stepaudio-2.5-asr` by default for Chinese speech. Add only verified names and domain terms as hotwords.
- Review the transcript and waveform together. Treat ASR timecodes as edit guides, not unquestionable acoustic boundaries.
- If StepFun risk-blocks a five-minute chunk, preserve caches, split only that chunk into about one-minute proxies, and retry. If smaller chunks remain blocked, keep the affected source content, record the gap, and do not guess or silently substitute another ASR.

### 2. Build the mechanical pass

- Read [references/editorial-decision-rules.md](editorial-decision-rules.md) before classifying any filler, false start, rerecord, or uncertain passage.
- Put only deterministic defects in the mechanical pass: recording starts, technical interruptions, explicit edit instructions, clearly abandoned fragments, standalone non-semantic hesitation, coughs between clauses, immediate stutters, and work pauses.
- Never batch-delete context-sensitive words such as `嗯`, `啊`, `那个`, `就是`, `然后`, `所以`, `但是`, or `对`.
- Do not delete a cough that overlaps unique speech. Record it in `manual_treatments`, attenuate it on a lossless working copy, and mark it applied before EDL rendering; otherwise retain the words.
- Store approved mechanical removals in EDL v3 `cuts[]` with `pass: mechanical` and `decision_status: approved`. Put uncertainty in `review_candidates[]`; never render it.
- Scan for rerecord clusters, especially lists, abstract long sentences, transitions, summaries, previews, and sign-offs. Require the retained take to cover the removed take's complete meaning and program function.

### 3. Refresh the transcript

- Generate the mechanical-stage transcript before making semantic decisions:

```bash
python3 scripts/build_stage_transcript.py \
  work/transcript/raw-transcript.json notes/edl-vNN.json \
  work/transcript/mechanical-vNN
```

- Read `mechanical-vNN.txt` and use its JSON source/edit time mapping for the semantic pass. Do not continue editing from the original transcript.
- Keep final EDL intervals on the original source timeline. Do not render an intermediate lossy master.
- If a cut intersects only part of an ASR event or the refreshed transcript disagrees with the waveform, narrow or move the cut to review. Re-ASR an intermediate version only when transcript and acoustic evidence cannot otherwise be reconciled.

### 4. Build the semantic pass

- Apply the selected branch's macro rules to the refreshed transcript. Never mix the casual branch's tolerance for detail loss into a rigorous program.
- Select rerecords by completeness, accuracy, natural delivery, and continuity; prefer the later take only when those factors are equal.
- Treat grammar, meaning, logic, and program function as one deletion gate. Preserve necessary setup for pronouns, examples, punchlines, conclusions, callbacks, transitions, emotional beats, and speaker personality.
- Never synthesize a sentence by joining two incomplete takes that did not form that sentence in the recording.
- Store only approved decisions in `cuts[]`. Put ambiguous repetition, structure, emotion, or persona decisions in `review_candidates[]`.
- Store removal intervals using [references/edl-schema.md](edl-schema.md). Merge cuts separated by less than 100 ms unless the remaining sound is intentional.
- Review all macro cuts in refreshed-transcript context before rendering.

### 5. Shape pauses

- Read [references/pause-shaping.md](pause-shaping.md) before shaping pauses or learning from any reference edit.
- When a human or agent reference is supplied, also read [references/reference-edit-learning.md](reference-edit-learning.md) before comparison or project-memory work.
- When ChatCut created or modified the reference, read [references/chatcut-reference-workflow.md](chatcut-reference-workflow.md). Treat global pause settings and automatic filler cleanup as tool-setting evidence, not automatically as the user's editorial preference.
- Scan all inter-phrase gaps, including gaps shorter than two seconds. Use the episode's distribution and semantic context instead of a single global deletion threshold.
- Classify each candidate as intra-clause, clause, sentence, section, or intentional rhetorical pause. Preserve a clear hierarchy instead of flattening every pause to one duration.
- Use ASR to identify language structure and waveform or short-window energy evidence to locate acoustic boundaries. Neither signal is sufficient by itself.
- After removing a false start, repetition, or abandoned take, inspect both sides and trim only redundant dead air. Retain enough room tone, breath, and consonant onset for a natural join.
- Record pure timing edits as `pause-compression` and content edits that also tighten adjacent silence as `content-with-pause-trim`.
- Keep reference-derived numeric profiles provisional until multiple approved episodes support the same range. Never turn one episode's cut density, pause durations, or retained-text rate into a universal target.
- Attribute reference differences separately to content-bearing removal, independent pause compression, and unresolved residual. Never treat the total low-energy difference as pause compression.

### 6. Render the edit

Select the approved sound profile first. Omission keeps the standard mastering settings below. For an explicit no-processing request, follow [preserve source and QA](preserve-source-and-qa.md); do not apply the standard gain, high-pass, mono conversion or loudness target. Missing actual listening permits only an identified review copy; never fabricate listening evidence or relabel a pause trim.

- Run the matching dry-run and inspect duration, cut count, shortest keep segment, output formats, and filter settings:

```bash
# MP3 only
python3 scripts/render_podcast_edl.py SOURCE EDL episode-vNN.mp3 --dry-run

# WAV only
python3 scripts/render_podcast_edl.py SOURCE EDL episode-vNN.wav --dry-run

# MP3 and WAV
python3 scripts/render_podcast_edl.py SOURCE EDL episode-vNN.mp3 \
  --also-output episode-vNN.wav --dry-run
```

- Render only after the dry run passes. Use `--force` only when replacing an unreviewed output; version reviewed files instead.
- Use the shared sound design:
  - 48 kHz mono delivery
  - 128 kbps MP3 for standard distribution
  - 24-bit PCM WAV for lossless mastered delivery
  - target `-19 LUFS` integrated for mono
  - true peak no higher than `-1.0 dBTP`, preferably near `-1.2 dBTP`
  - 20 ms default crossfade
  - 3 dB pre-filter headroom
  - gentle 65 Hz high-pass by default; set `highpass_hz` to `0` only when measurement and listening show it is unnecessary or it thins the voice
- Avoid broadband denoising when technical silence already sits near the recording noise floor. Use the lightest treatment that solves a measured problem.
- Let the renderer assemble once, create a 24-bit mastered WAV, and encode MP3 only from that lossless master. Never create WAV from MP3. Compensate MP3 loudness drift from the mastered WAV.

### 7. Generate the post-edit transcript and perform editorial checks

- Chunk and transcribe the rendered candidate with the same StepAudio model and settings used for the source. Store it under `work/transcript/post-edit-vNN/`.
- Treat this transcript as evidence of what listeners actually receive, not as a regenerated source of edit decisions.
- Complete four editorial checks against the rendered audio and post-edit transcript:
  - sentence integrity: no fragments, missing subjects, broken causality, or clipped word onsets;
  - logic integrity: references, numbers, examples, callbacks, and conclusions retain their setup;
  - pacing integrity: no sustained over-tightening, flattened pause hierarchy, or abrupt slow sections;
  - persona integrity: natural hesitation, laughter, emotion, and speaker character remain coherent.
- Run a second mechanical residual scan on the post-edit transcript. Check adjacent failed starts, progressive list rerecords, immediate word corrections, and duplicated transitions, summaries, previews, or sign-offs.
- Audit changes to numbers, names, negations, qualifications, cause and effect, transitions, references, conclusions, persona, and section navigation. Put every newly discovered edit into review; do not patch it into the EDL silently.
- Record the reviewer and review time for the four checks. Do not compute final release readiness until technical QA and the human full-length listen are complete.

### 8. Validate sound and compare

- Run `scripts/audio_qa.py OUTPUT --json-out qa/qa-vNN.json` for each delivery.
- Verify complete decode, duration, 48 kHz mono, integrated loudness, true peak, and abnormal silence. For MP3 also verify 128 kbps; for WAV verify `pcm_s24le` and 24-bit depth.
- After technical checks pass, complete the full-length listen and rerun audio QA with `--human-approved`, `--human-reviewer`, and `--human-reviewed-at`.
- For an intentional pause longer than two seconds, pass `--allowed-long-silences N` and document its exact timecode and purpose in edit notes.
- Report pause distributions by semantic role, plus counts above one and two seconds. Treat these as review signals, not automatic deletion orders.
- Listen one second before and after every join. Check clipped consonants, missing breaths, doubled syllables, room-tone jumps, and meaning changes.
- When comparing versions, use the same ASR model for both and report:
  - duration and retained transcript coverage
  - macro passages present in only one version
  - standalone fillers and immediate-stutter patterns
  - integrated loudness, true peak, LRA, channel layout, bitrate, and size
- For a human, ChatCut, or other agent reference with complete transcripts, run `scripts/compare_reference_edit.py` and keep its detailed output in the episode workspace.
- When only rendered reference audio is available, prefer same-model ASR. If external transcription is not authorized or unavailable, run `scripts/compare_audio_reference.py` to map both edits back to the immutable source and project the existing source transcript. Label this result `local-acoustic-projection`, keep every finding non-executable, and do not use it to clear sensitive-field review.
- Compare both directions: material the reference removes but the candidate keeps, and material the candidate removes but the reference keeps. A reference edit is not necessarily a strict subset and may select a different take.
- Save every finding, status, source artifact checksum, and authoritative detailed-report path in project-local reference memory. Remembering a difference does not approve it. Use the cross-project reusable-learning gate by default; use the explicit personal-default gate in [references/reference-edit-learning.md](reference-edit-learning.md) only when the reference author confirms the intended scope and asks to make it a named branch default.
- Separate the reference's content strategy from its channel layout, loudness, noise processing, music, and true-peak treatment. Never inherit mastering merely because the content edit is useful.
- Resolve every pending sensitive or uncertain finding before editorial release.
- Prefer the version whose editing strategy matches the branch and whose master passes QA. Do not confuse a larger bitrate or shorter duration with a better edit.
- Run `scripts/editorial_qa.py` only after the approved audio QA JSON exists. Pending review candidates must keep `release_ready` false.

```bash
python3 scripts/editorial_qa.py \
  notes/edl-vNN.json work/transcript/post-edit-vNN/raw-transcript.json \
  qa/qa-vNN.json \
  --sentence-pass --logic-pass --pacing-pass --persona-pass \
  --editorial-reviewer REVIEWER --editorial-reviewed-at ISO8601_TIME \
  --json-out qa/editorial-qa-vNN.json --require-release-ready
```

- Set final `release_ready: true` only when editorial QA, technical QA, and the human full-length listen all pass.

## Delivery Contract

Deliver the formats confirmed in the plan:

```text
episode-vNN.mp3           # MP3 selected
episode-vNN.wav           # WAV selected
edl-vNN.json
edit-notes-vNN.md
qa-vNN.json               # one selected format
qa-vNN-mp3.json           # both selected
qa-vNN-wav.json           # both selected
editorial-qa-vNN.json
```

Keep ASR caches, source/mechanical/post-edit transcripts, proxies, and lossless assemblies under `work/`. Do not place them in the delivery folder unless requested.

Keep the two audit surfaces distinct:

- `edl-vNN.json` is machine-facing and retains exact source timecodes, pass metadata, confidence, boundary evidence, parameters, and review-candidate state.
- `edit-notes-vNN.md` is user-facing and summarizes the branch and transcript basis, approved removals by purpose, material retained for personality or context, pending decisions, four-check results, and final release status. Do not dump dense machine parameters into it.

Treat platform upload, account operation, title, description, chapters, cover art, and enriched ID3 metadata as separate publishing work. Do not infer authorization to publish merely because the user asks for an upload-ready audio file.

## Failure Handling

- StepFun authentication fails: check the environment and Keychain service without exposing the key.
- StepFun returns 429: keep per-chunk caches, wait for the rate-limit window, and resume missing chunks only.
- ASR and audio disagree: trust the waveform and listening review; widen or remove the questionable cut.
- A mechanical cut intersects only part of an ASR event: narrow it to a verified boundary or move it to `review_candidates[]`; do not invent partial-word timing.
- A semantic pass was built from the source transcript instead of the mechanical-stage transcript: stop and regenerate the staged transcript before continuing.
- An EDL contains a cut whose decision is not approved: stop before rendering; pending and rejected decisions never belong in `cuts[]`.
- A keep segment is shorter than twice the crossfade: merge adjacent removals or reduce the crossfade after listening.
- An unresolved `manual_treatments` entry exists: stop before rendering; apply and audit the attenuation on a lossless working copy or retain the original passage.
- Loudness misses target after MP3 encoding: measure the encoded MP3 and compensate from the lossless assembly, not from the MP3.
- True peak lacks headroom: lower gain before applying EQ or dynamics; never rely on the final encoder to hide clipping.
- Output suffix and `delivery_formats` disagree: stop and fix the plan or EDL; do not silently emit an unrequested format.
- A new content type fits neither branch: add a new branch reference and route explicitly rather than modifying an existing branch into a universal rule set.
- Technical QA passes but human review is unsigned: report `release_ready: false`; do not call the episode publication-ready.
- A human, ChatCut, or agent-reference comparison contains pending findings: keep `release_ready: false`; accept or reject each finding explicitly before rerunning editorial QA.
- A ChatCut reference globally normalizes pauses: record the current ChatCut setting or version when available, treat the result as tool-induced until the user confirms it as a preference, and preserve the branch's semantic pause hierarchy.
- Only a rendered ChatCut export is available and ASR upload is not authorized: use local acoustic projection for a report, disclose its boundary/text limits, and keep sensitive or uncertain differences pending.

## Resources

- [references/casual-non-rigorous.md](casual-non-rigorous.md): current light, non-rigorous editorial branch.
- [references/rigorous-explainer.md](rigorous-explainer.md): factual-integrity-first branch for research, policy, statistics, sources, and consequential explanations.
- [references/editorial-decision-rules.md](editorial-decision-rules.md): shared filler, rerecord, semantic-unit, and uncertainty rules.
- [references/pause-shaping.md](pause-shaping.md): semantic pause classification, privacy-safe reference learning, and pause QA.
- [references/reference-edit-learning.md](reference-edit-learning.md): human and agent reference roles, bidirectional comparison, confidence gates, complete project memory, and residual mechanical scanning.
- [references/chatcut-reference-workflow.md](chatcut-reference-workflow.md): current ChatCut transcript/pause behavior, version-aware evidence capture, and safeguards against learning tool defaults as editorial taste.
- [references/edl-schema.md](edl-schema.md): deterministic EDL v3, review candidates, transcript provenance, and audit fields.
- `scripts/transcribe_stepfun.py`: resumable StepAudio transcription for pre-chunked audio.
- `scripts/build_stage_transcript.py`: derive the mechanical-stage transcript with source/edit time mapping without another ASR call.
- `scripts/render_podcast_edl.py`: non-destructive EDL assembly and loudness mastering.
- `scripts/audio_qa.py`: final delivery measurements and pass/fail checks.
- `scripts/editorial_qa.py`: combine four editorial checks, pending review state, technical QA, and human approval into final release readiness.
- `scripts/analyze_pause_profile.py`: aggregate-only comparison of StepAudio timing and audio energy without transcript excerpts or source identifiers.
- `scripts/compare_reference_edit.py`: project-local character, pause, acoustic, and source-timeline alignment for a human reference edit.
- `scripts/compare_audio_reference.py`: local acoustic projection for rendered human or ChatCut exports, including direct candidate-to-reference comparison mapped back through the candidate EDL when complete compared-version transcripts are unavailable.
