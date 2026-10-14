# Multi-ASR Subtitle Calibration

Use this workflow only when multiple ASR results are available or the user explicitly requests cross-provider calibration. One complete, reliable transcript is preferable to several incomplete ones.

## Evidence roles

- Use the provider with the most reliable timestamps as the timing spine. StepFun timestamp events are the default when available.
- Use the strongest complete Chinese transcript as the wording draft. Treat provider wording as evidence, not authority.
- Use additional providers to challenge names, numbers, terminology, omissions, and repeated tails.
- Preserve every raw response and identify incomplete or retried results in the audit. Never silently splice an incomplete tail into the final transcript.

## Cue construction

1. Decode one locked audio track and submit the identical audio to every provider being compared.
2. Normalize response formats without destroying the raw responses.
3. Prepare proofread cue text with at most two visual lines. Keep project-specific terminology in a supplied term list, not in scripts.
4. Use `scripts/build_srt_from_timestamps.py` to align the proofread cue characters to the timestamp spine.
5. Review every non-equal alignment block. A high aggregate ratio does not prove that names or short phrases are correct.
6. Run `scripts/subtitle_qa.py` against the final media duration and project term rules.

Timestamp events locate speech; they do not prove an edit boundary. Confirm complete words and breaths with audio, waveform evidence, and frame boundaries before changing picture or sound.

Technical subtitle QA is not a human proofread. Keep `release_ready=false` until the required full-length viewing, listening, and subtitle review are recorded.
