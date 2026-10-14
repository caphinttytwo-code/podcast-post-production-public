# Manifest and cleanup reference

## EDL manifest

Require these top-level fields:

```json
{
  "schema_version": "1.1",
  "job_id": "episode-reference-conform-v01",
  "source_video": "/absolute/source.mp4",
  "reference_audio": "/absolute/2nd-edition.mp3",
  "audio_strategy": "reference-audio-continuous",
  "source_audio_start_seconds": 0.0,
  "reference_duration_seconds": 4761.048,
  "source_timing": {
    "warnings": [],
    "requires_seek_calibration": false
  },
  "analysis_cache": {
    "source_pcm": "/absolute/project/work/JOB_ID/audio/source.pcm",
    "reference_pcm": "/absolute/project/work/JOB_ID/audio/reference.pcm",
    "sample_rate": 8000
  },
  "output_spec": {
    "fps": 30,
    "soft_frames": 3
  },
  "segments": []
}
```

Each segment must contain:

- `index`: one-based integer.
- `reference_in`, `reference_out`: `HH:MM:SS.mmm` strings.
- `reference_in_seconds`, `reference_out_seconds`, `reference_duration`: numeric seconds.
- `source_media_in`, `source_media_out`: `HH:MM:SS.mmm` strings.
- `source_media_in_seconds`, `source_media_out_seconds`: numeric seconds.
- `offset_seconds`: source-audio time minus reference time.

Require reference segments to begin at zero, remain contiguous, and end at `reference_duration_seconds`. Require source segments to be positive, ordered, non-overlapping, and contained by the source duration.

Also require input hashes, opening-anchor diagnostics, timing-risk findings, and absolute analysis-cache paths. A risky source must have a separate seek-calibration report tied to the exact manifest SHA-256. Each calibration row records desired media time, corrected seek time, actual verified time, residual error, and correlation.

## Approval and known-issue audit

After sample review, record the approved EDL revision, audio strategy, fps, softened-frame count, reviewer decision, and decision time. Do not silently reuse approval after changing a cut, input, timing parameter, or manifest.

For an accepted known issue, record:

- Exact reference/output time range and observable symptom.
- What automated checks did and did not prove.
- User decision and date.
- Locked output path and SHA-256.
- A requirement that later correction creates a new version and a new approval sample.

An accepted exception remains visible in QA and does not weaken validation thresholds globally.

## Audio strategies

### B: `reference-audio-continuous`

Use the reference audio as one continuous final track. Trim and join source picture only. Do not crossfade or concatenate source audio. This is the default workflow.

### A: `source-video-original`

Use retained source-video audio. This requires per-join listening, 3–10 ms microfades or a short equal-power crossfade, and a separate drift audit. Do not silently substitute A for B.

## Timeline-neutral soft join

For `N` soft frames:

1. Keep the outgoing segment through its last selected frame.
2. Hold that last frame for `N` frames.
3. Fade incoming frames `1..N` over the hold.
4. Continue incoming picture from frame `N+1`.

The transition contributes `N` frames while the incoming body omits the same `N` frames, so total duration is unchanged. Default `N=3` at 30 fps; cap normal use at 5 unless the user approves a longer stylistic transition.

## Cleanup boundary

Protected:

- Files explicitly passed as source media.
- Files explicitly passed as approved finals.
- EDLs, manifests, scripts, reports, transcripts, CSV/JSON annotations, QA still images, and placeholder files.

Regenerable process data:

- PCM/WAV/AAC/M4A/MP3 extracts and chunks under `work/`.
- NPY feature caches under `work/`.
- MP4/MOV/MKV approval samples and temporary renders under `work/`.
- Duplicate version renders under `versions/videos/` after the approved delivery has been verified.
- Encoder partials, concat lists, filter graphs, and `__pycache__`.

Never delete an older source/reference edition merely because a newer one exists. Delete it only when the user names or unmistakably authorizes that exact file.

Placeholders must name the protected files, say they remain until manually moved, and say not to delete, move, rename, overwrite, or auto-clean them. A placeholder does not replace the media while the media is still present.
