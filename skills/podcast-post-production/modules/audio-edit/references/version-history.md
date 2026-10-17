# Version history

## Version

- v1.7.0 adds an opt-in synchronized-multitrack recording mode: strict equal-frame/rate admission and independent-reference/common-clock evidence, one integer-frame edit/assembly timeline, whole/fine rerecord operations, bound durable review, PCM verification, projected role transcripts and cumulative decision/version history. Unsupported synchronization is never repaired automatically. Existing solo EDLs and commands remain compatible. GitHub CI uses synthetic local media only.
  The solo renderer also probes filter-file flag support so both older FFmpeg's `-filter_complex_script` and modern `-/filter_complex` remain usable; unrelated probe errors are surfaced.

- v1.6.0 adds complete-paragraph listening review, source-bound durable saves and three-way conflict recovery, integer PCM preserve-source assembly/QA, exact sample-frame proxy manifests and bound ASR caches, explicit unlistened review drafts and per-check status reporting. It includes the existing FFmpeg 9 filter-file and ASR redirect-security fixes.

- Skill release: `v1.7.0`.
- Editorial branches: `casual-non-rigorous` and `rigorous-explainer`.
- Both branches use the shared staged-transcript, editorial-decision, pause-shaping, and post-edit QA workflow. Keep their content tolerance and pacing profiles distinct.
- v1.4 adds ChatCut-aware reference roles, bidirectional source alignment, complete project-local difference memory, and a local acoustic fallback when a rendered reference has no usable transcript.
- v1.4.1 standardizes every StepFun endpoint on the `https://api.stepfun.com/step_plan/v1` API base.
- v1.5 adds an explicit reference-author approval state and a guarded path for promoting repeated, non-sensitive qualitative patterns into a named branch's personal defaults.
- v1.5.1 hardens local rendered-reference comparison with direct baseline-to-reference alignment, EDL-backed source mapping, staged-transcript support, safe source-tail exhaustion, 0.1-second micro-edit retention, and duration reconciliation.

- `scripts/review.py`: build, launch and serve version-bound paragraph review.
- `scripts/prepare_asr_chunks.py`: create resumable proxies with exact source sample offsets.
- `scripts/preserve_pcm.py`: source-format PCM assembly and sample verification, routed by the existing renderer.
