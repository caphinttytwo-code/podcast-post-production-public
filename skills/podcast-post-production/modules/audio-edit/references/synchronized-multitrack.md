# Synchronized multitrack mode

Use `scripts/multitrack.py` for `synchronized-multitrack`; the existing solo renderer and EDL v1–v3 are unchanged. This mode supports one already synchronized recording group, not automatic alignment or combining differently timed sessions. Keep real episode media, names, transcripts and absolute paths in its workspace, never in the reusable Skill repository.

## Admission and source preservation

After approved preparation, decode compressed files once to integer PCM WAV at their native rate/channels; compressed sources use 24-bit working PCM. Copy compatible WAV sources unchanged (16/24/32-bit, mono/stereo). This does not restore lost MP3 information. Preparation binds original and working hashes, retains originals and atomically publishes a new cache directory only if admission succeeds.

All participating stems and an independent Mix must have exactly equal decoded frame counts and sample rates. Container duration, ASR timecodes and identical file lengths alone are not proof. The inspector checks nine distributed anchors at native sample rate, removes other stems from the independent Mix by local linear regression, and measures target/residual lag. High-confidence nonzero lag at any anchor stops the mode. Each track needs usable zero-lag evidence in the beginning, middle and final thirds. Quiet, periodic, nonlinear or poorly identifiable anchors remain insufficient, not passed.

If independent signal evidence is unavailable, accept only an explicitly verified common sample clock/session and sample-zero provenance, recording its reviewer. Report this as `explicit-common-clock-evidence`, never as signal-verified alignment. Such evidence cannot override a detected offset/drift. A generated Mix is circular evidence and is never used to prove synchronization. Do not use acoustic arrival differences between microphones as proof of different recording start times.

**Strong failure message:** “本 Skill 不支持不同长度、不同采样率或未同步的音轨；请先完成外部对齐。不会自动补齐、拉伸或修复。” Insufficient evidence also stops rendering. No hidden padding, frame removal, stretching, resampling or per-track solo fallback. Original files remain unchanged.

## Project and timeline interfaces

Project v1 is separate from the solo EDL. Media paths resolve relative to its JSON file. IDs are stable ASCII identifiers; roles are annotations, not a four-person limit. Preparation fills `sha256` from current reads; direct PCM inputs must already have correct hashes. Optional clock evidence requires all shown fields and genuine verification, not an assistant-invented attestation.

```json
{
  "version": 1,
  "id": "episode",
  "recording_mode": "synchronized-multitrack",
  "tracks": [
    {"id": "host", "path": "host.wav", "sha256": "CURRENT_SHA256", "speaker": "Host"},
    {"id": "guest", "path": "guest.wav", "sha256": "CURRENT_SHA256", "speaker": "Guest"}
  ],
  "reference_mix": {"id": "mix", "path": "mix.wav", "sha256": "CURRENT_SHA256"}
}
```

When verified common-clock provenance is needed, add:

```json
{"clock_evidence": {"type": "common-sample-clock", "confirmed": true,
 "session": "verified recorder/session identifier", "sample_zero": "verified frame-zero basis",
 "reviewer": "person who actually verified this"}}
```

An edit plan v1 binds the project hash and records explicit user decisions, or points to a bound durable review directory. All coordinates are integer **frames**, with half-open `[start,end)` ranges. The default base is the whole source and the default per-block buffer is **zero**. An optional shortened base (e.g. excluding a rerecord workspace) needs its own approved decision. Never mistake workspace rejection for blank audio.

```json
{
  "version": 1, "id": "v01", "project_sha256": "PROJECT_JSON_SHA256",
  "crossfade_frames": 960,
  "base_range": [0, 480000], "base_range_decision_id": "body",
  "user_decisions": {
    "authority": "user", "recorded_at": "actual-confirmation-time",
    "items": {
      "body": {"choice": "adopt", "note": "Confirmed body end"},
      "retake": {"choice": "adopt", "note": "Use the full corrected take"},
      "aside": {"choice": "keep", "note": "User chose to retain"}
    }
  },
  "edits": [
    {"id": "retake", "type": "replace", "start_frame": 96000, "end_frame": 144000,
     "source_start_frame": 528000, "source_end_frame": 624000,
     "block_mode": "whole", "buffer_frames": 24000},
    {"id": "aside", "type": "delete", "start_frame": 288000, "end_frame": 312000}
  ]
}
```

This example requires sources long enough for the insertion and assumes 48 kHz solely for its example values. Use the actual source rate: 20 ms is `round(rate*0.02)` frames. Buffers add time; adjacent-source crossfades subtract their overlap. A half-second buffer, when requested, is `round(rate*0.5)`; do not force 48 kHz on other source rates.

Operations:

- `delete`: consume `start_frame/end_frame` on the authorized base.
- `insert`: place `source_start_frame/source_end_frame` at `at_frame`, without consuming that source elsewhere. Reuse is intentional only when the user approved it.
- `replace`: consume the target interval and insert its selected source at the target start.
- `move`: consume exactly its source interval and insert it at an outside destination. Use insertion from outside the shortened base for a tail rerecord block.

`block_mode` is `whole` or `fine` for inserts/replacements/moves. Whole mode uses a contiguous unedited block. Treat consecutive rerecord items as one source range when the user groups them; do not add buffers inside that block. Fine mode requires the specific finer edits to have been authorized. Events at the same destination retain list order. Overlapping removals/replacements or destinations inside another removed interval are rejected; combine the overlapping decision first.

Choices are `keep`, `delete`, `adopt`, `pending`, `uncertain` or `custom`. Only approved `delete` operations and approved `adopt` operations execute. Keep ranges block overlapping deletes. Pending/custom/uncertain entries stay in the report and never execute. P0/P1/P2 labels do not grant authority by themselves. User correction, take choice and factual verification are separate; do not use a model's factual opinion to override an approved take.

Compilation yields immutable `copy`, `silence`, `fade` and `crossfade` nodes with source contributors and output frame ranges. All outputs use this same timeline; they do not independently seek low energy or reshape pauses. Search joint low-energy candidates when planning, preserving complete words, overlaps and every participant's context. Uniform positions do not imply every join is silent. Retained PCM bodies are copied byte-for-byte; local linear fades are 15–30 ms (default 20 ms). Silence buffers remain exactly zero and exactly the requested length. No gain, denoising or loudness target is applied.

## Commands and approval boundaries

```bash
# Initial inspection is read-only; lossy inputs first need approved preparation.
python3 scripts/multitrack.py prepare episode/project.json episode/pcm-v01
python3 scripts/multitrack.py inspect episode/pcm-v01/project.json
python3 scripts/multitrack.py compile episode/pcm-v01/project.json episode/plan-v01.json episode/timeline-v01.json

# Optional Mix-first listening and later stems reuse the exact same plan hash.
python3 scripts/multitrack.py render episode/pcm-v01/project.json episode/plan-v01.json episode/mix-v01 --selection mix
python3 scripts/multitrack.py render episode/pcm-v01/project.json episode/plan-v01.json episode/stems-v01 --selection tracks
# Or --selection all when all outputs are already authorized.
python3 scripts/multitrack.py verify episode/pcm-v01/project.json episode/plan-v01.json episode/stems-v01
```

The optional `--transcript episode/transcript.json` generates a role MD and projection evidence with render. Outputs are source-format WAV; the existing source-preserve MP3 review encoding procedure can make a listening copy without treating it as the source. With no independent Mix, a fixed-average, explicitly labelled `analysis-mix.wav` is generated for listening only after common-clock admission. It is not a final mix/master.

Every output directory must be new and outside the Skill repository. Rendering stages the complete selected group, reconstructs every output against the frozen source/timeline, then atomically publishes the directory. Each delivery also includes portable `接点试听.html`, actual rendered join WAV excerpts (up to 12 seconds before / 18 after), exact clip-relative join positions, and human-readable `时间映射.csv`. Tracks-only delivery may include a labelled auxiliary listening reference; it is not counted as an extra formal stem or master. `verify` independently recompiles the timeline and checks selected artifacts, PCM, fades, silence, preview PCM against the rendered reference and file hashes. A failed group does not leave a partial published delivery. Technical success never sets release readiness true.

## Bound listening confirmation

Use the existing paragraph-review UI and Store, not a new browser-local-only confirmation table:

```bash
python3 scripts/multitrack.py review episode/pcm-v01/project.json episode/review-spec.json episode/review-v01
python3 scripts/review.py launch episode/review-v01
```

Review items contain their full `operation` object with the same ID and fields as the plan. Their ordinary `start_ms/end_ms` locate complete listening context on the source Mix. For non-deletion edits use `proposed_decision: "adopt"`; the UI offers “采用本段建议”. A generic “delete” choice cannot authorize a move, replacement or insertion. Build one complete candidate card for overlapping replacements, rather than mutually contradictory independent cuts.

The adapter binds the project JSON and **all** stems, including quiet stems, as well as the listening Mix. It reuses durable project saves, revision history, browser recovery, explicit-ID bulk adoption and three-way conflict handling. Set `review_directory` in the plan (relative to the source project JSON) instead of `user_decisions`. Compilation freezes the review revision/hash and verifies that each plan operation exactly matches its reviewed operation. If the user changes/withdraws a decision during render, atomic publication stops. Changed coordinates/semantics require a new review version; a custom note remains unresolved. Text corrections never authorize audio cuts or replace the actual spoken wording.

## Role transcript and version records

Source transcript JSON binds `project_sha256` and contains `sentences[]` with `id`, `speaker`, `text`, integer `start_frame/end_frame`, and optional `words[]` with text/punctuation and source frame ranges. Preserve uncertain identities and overlapping utterances. Crossfade/copy contributors with identical source-to-output offsets are merged before projection so fade boundaries do not duplicate words. Partial sentences require word timings; without them stop rather than copying removed words back. Zero-duration events remain unresolved timing evidence, never invented ranges.

Generated transcripts are marked `cached-source-transcript-projection`, with actual output ASR and human proofreading `not_run`/`not_completed`. Do not pass them to the existing editorial QA as proof of actual-output ASR. Keep technical QA, model comparison, source projection, actual rendered recognition, human join listening and full-length listening separate.

Each delivery includes `timeline.json`, current decisions and executed operations in `version-record.json`, WAVs, checksums, optional role MD, and a cumulative `全版本处理记录.md`. The node map is the precise source/output operation result, including all buffers and fade overlap. Use `parent_record` relative to the plan file and `parent_record_sha256` to bind earlier records. Parent paths in output records are rewritten relative to that delivery; cycle/tamper checks apply.

When revising from the **same original project**, supply a cumulative plan and carry forward all previous user decisions. Changing/removing an earlier operation or changing a prior choice requires explicit renewed approval and its ID in `revised_ids`. An omitted old cut cannot silently restore previously removed audio. Alternatively prepare the already-rendered parent outputs as the next source project; every source hash must match the parent's selected outputs. Then new coordinates refer to that parent audio. Clearly label version-specific clocks in reports.

Follow the existing full-human-listen gate. The tool does not certify subjective joins by playing a browser control or inspecting a waveform. Use the media audit/cleanup skill for approved quarantine; first preserve final audio/text, all decisions, timelines and necessary historical evidence independently of disposable old caches. Historical raw ASR and old audio are not completely reproduced by a summary; say so before deletion.

## ASR and cost boundaries

Reuse complete source-hash-matching caches first. For new role transcripts, prefer `qwen-audio-3.1-asr-flash-filetrans` through the installed Bailian skills and `bl speech recognize`; check current CLI support, region, live allowance and task budget first. A model's presence in a catalog does not prove every parameter is exposed. Do not extract DashScope keys or silently switch to native API; a capability gap follows the user's existing native-API confirmation rule.

Clear solo speech continues to use StepFun 2.5. Check actual Plan validity; do not switch to its pay-as-you-go endpoint early because of an error or an ambiguous expiry timezone. After confirmed expiry follow the user's authorized pay-as-you-go route without renewing a subscription merely for ASR. For ambiguous/professional/overlapping content, use an authorized alternative model or StepFun 3 Max on local segments; default 3 Max review scope is at most 10% of original duration. Whole-file dual runs or expanded scope need project justification and authorization. Retry only failed segments; do not silently upgrade providers/models/billing routes.

Before an authorized paid batch, show task estimation and remaining-budget evidence under the user's current global policy. Historical free-token counts, prices, budget plans and expiry snapshots are not live balances, hard billing caps or automatic monitors. Missing bills are unknown, not zero cost. Follow an explicitly configured user ASR budget, if any; reconcile known bills, outstanding estimates and unknowns across projects before assuming budget remains. Never call ASR merely to exhaust credits or measure costs.

Keep `asr-cost-ledger.jsonl` per project: timestamp, source hash, submitted intervals/duration, provider, model, billing endpoint, region, request/task ID, attempt, input/output tokens (unknown if absent), verified allowance offset, price/check date, estimated cost and verified bill cost (otherwise unknown). Count overlap/retries in submitted duration. Do not record credentials or signed URLs. Multitrack tools and CI themselves make **no ASR calls**.
