# Podcast Removal EDL v3

Use seconds with millisecond precision and sort source-timeline intervals by start time. Version 3 adds editorial pass provenance, approved-only execution, staged-transcript provenance, and non-executable review candidates. The renderer remains compatible with versions 1 and 2.

Keep episode EDLs in the episode workspace. Do not commit real transcripts, source identifiers, absolute paths, or project statistics to the reusable Skill repository.

```json
{
  "version": 3,
  "branch": "rigorous-explainer",
  "transcript_basis": {
    "source": "work/transcript/raw-transcript.json",
    "mechanical": "work/transcript/mechanical-v01.json",
    "semantic_based_on": "mechanical"
  },
  "crossfade_seconds": 0.02,
  "pre_gain_db": -3.0,
  "highpass_hz": 65,
  "target_lufs": -19.0,
  "true_peak_dbtp": -1.2,
  "sample_rate": 48000,
  "channels": 1,
  "delivery_formats": ["mp3"],
  "bitrate_kbps": 128,
  "wav_bit_depth": 24,
  "cuts": [
    {
      "start": 35.68,
      "end": 48.96,
      "pass": "mechanical",
      "decision_status": "approved",
      "category": "false-start",
      "reason": "Removed a fictional abandoned take",
      "confidence": "high",
      "before": "previous complete words",
      "after": "next retained words"
    },
    {
      "start": 74.2,
      "end": 75.0,
      "pass": "pause",
      "decision_status": "approved",
      "category": "pause-compression",
      "reason": "Compressed a fictional work pause while retaining sentence space",
      "confidence": "high",
      "pause_role": "sentence",
      "original_gap_seconds": 1.4,
      "retained_gap_seconds": 0.6,
      "boundary_evidence": ["asr", "waveform", "listening"]
    }
  ],
  "review_candidates": [
    {
      "start": 110.2,
      "end": 124.6,
      "pass": "semantic",
      "proposed_action": "remove",
      "category": "macro-repetition",
      "reason": "May repeat the preceding explanation but carries a different emotional beat",
      "confidence": "medium",
      "risk_flags": ["meaning", "emotion", "persona"],
      "status": "pending"
    }
  ],
  "manual_treatments": [
    {
      "start": 312.4,
      "end": 312.9,
      "type": "cough-over-speech",
      "gain_db": -8.0,
      "fade_ms": 25,
      "reason": "Preserve the spoken word while softening the cough",
      "status": "pending",
      "applied_to": null
    }
  ]
}
```

## Version Compatibility

- Version 1 remains valid for legacy single-MP3 removal EDLs.
- Version 2 remains valid for pause-shaped EDLs and requires ASR plus waveform evidence.
- Version 3 is required for new or revised v1.2 jobs. It requires approved pass metadata and transcript provenance; approved pause cuts also require listening evidence.
- Never upgrade an old EDL by changing only its version number. Add and verify every required v3 field.

## Required v3 Fields

- `version`: integer `3`.
- `branch`: exact editorial branch ID.
- `transcript_basis.source`: project-relative path to the immutable source StepAudio JSON.
- `transcript_basis.mechanical`: project-relative path to the refreshed mechanical-stage JSON.
- `transcript_basis.semantic_based_on`: exactly `mechanical`.
- `cuts[]`: approved machine-executable removals only.
- `review_candidates[]`: optional non-executable suggestions requiring or documenting human judgment.
- `manual_treatments[]`: non-destructive work that cannot be represented as deletion.

## Approved Cuts

Every v3 cut requires:

- `start` and `end`: valid source-timeline seconds with `end > start`;
- `pass`: one of `mechanical`, `semantic`, or `pause`;
- `decision_status`: exactly `approved`;
- `category`: stable reason class;
- `reason`: human-readable rationale;
- `confidence`: one of `high`, `medium`, or `low`.

Approval is authoritative even when confidence is not high. Keep the confidence value to expose the original uncertainty. Pending or rejected decisions never belong in `cuts[]`.

For `pause-compression` and `content-with-pause-trim`, also require:

- `pause_role`: one of `intra-clause`, `clause`, `sentence`, `section`, or `rhetorical`;
- `original_gap_seconds` and `retained_gap_seconds`, with `0 <= retained <= original`;
- `boundary_evidence`: `asr`, `waveform`, and `listening` before rendering an approved v3 cut.

## Review Candidates

Every candidate requires:

- valid source-timeline `start` and `end`;
- `pass`: `mechanical`, `semantic`, or `pause`;
- `proposed_action`: `remove`, `compress`, or `keep`;
- `category`, `reason`, and `confidence`;
- `risk_flags`: a list drawn from `meaning`, `logic`, `reference`, `emotion`, `persona`, `rhythm`, and `boundary`;
- `status`: `pending` or `rejected`.

The renderer ignores the entire list. A pending candidate blocks final editorial release readiness. When a human approves a candidate, move it into `cuts[]`, set its executable fields, and remove it from `review_candidates[]`.

## Transcript Provenance

Generate `transcript_basis.mechanical` from the source StepAudio JSON and approved mechanical cuts with `scripts/build_stage_transcript.py`. The staged JSON retains source and edit timecodes.

Semantic decisions must use that refreshed transcript. All final intervals remain on the original source timeline so the renderer assembles once from the highest-quality recording.

## Delivery Fields

- `delivery_formats`: optional ordered subset of `mp3` and `wav`. Omit only for a legacy single-MP3 EDL.
- `bitrate_kbps`: MP3 bitrate, default `128`; ignored for WAV validation.
- `wav_bit_depth`: mastered PCM WAV bit depth, currently `24`.
- Output suffixes must match `delivery_formats`.
- MP3 and WAV must come from the same lossless assembly. Never decode MP3 into WAV.

## Recommended Categories

- `false-start`
- `technical-interruption`
- `macro-repetition`
- `digression`
- `over-detail`
- `filler`
- `stutter`
- `cough-between-clauses`
- `long-pause`
- `trailing-silence`
- `pause-compression`
- `content-with-pause-trim`

## Validation Rules

- Reject negative, reversed, out-of-range, or overlapping unmerged cuts.
- Merge approved cuts separated by less than 100 ms unless the retained sound is intentional.
- Keep every retained segment longer than twice the crossfade.
- Record first and last retained words around macro cuts.
- Reject unknown pass, status, confidence, action, risk, or pause-role values.
- Reject rendering while a cut is not approved or a manual treatment is not applied.
- Never execute `review_candidates[]`.
- Reject unknown, duplicate, or missing delivery formats and suffix/EDL mismatches.
- Reject unsupported schema versions.

## v1.6 sound profile and review drafts

Optional `sound_processing` is `standard_mastering` (the legacy default) or `preserve_source_no_mastering`. The preserve profile requires a v3 approved EDL and keeps supported PCM WAV source format unchanged. Read [preserve source and QA](preserve-source-and-qa.md) before using it.

Mark attached pause trimming with `trims_adjacent_pause: true` and `category: content-with-pause-trim`; supply the existing pause fields and ASR/waveform evidence. A renderer `--review-copy` may omit listening evidence only to generate an explicitly unlistened review draft. Pending content and manual treatments remain blocked. Normal pause execution still requires listening evidence. Never use a different category to bypass that distinction.
