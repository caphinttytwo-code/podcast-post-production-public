# Human and Agent Reference Edit Learning

Read this reference when a user supplies a human-edited, ChatCut-edited, or other agent-edited version to compare with a Skill-generated candidate. Treat every reference as evidence, not ground truth.

## Roles and Authorization

- Keep `source` as the immutable highest-quality recording and original timeline.
- Treat `candidate` as the Skill-generated edit under review.
- Treat `human_reference` as an editorial and pacing reference, never as the master source.
- Treat `chatcut_reference` or `agent_reference` as tool output unless a human explicitly reviewed and approved every decision. Do not relabel it as human work.
- Use the same StepAudio model and language settings for compared versions.
- Upload only proxies covered by the confirmed plan. Do not infer publishing permission.
- Keep reference analysis read-only. Remembering or learning from a difference never authorizes an EDL mutation.

## Project-local Artifacts

Store reference proxies, ASR caches, detailed alignment, comparison notes, and project memory only in the episode workspace. Never copy real excerpts, file names, paths, timecodes, or episode statistics into this Skill or public history.

Recommended layout:

```text
work/transcript/reference-edited-vNN/
  chunks/
  raw-transcript.json
  raw-transcript.txt
  raw-transcript.srt
  alignment-analysis-vNN.json
notes/
  reference-comparison-vNN.md
  reference-memory-vNN.json
  skill-update-report-vNN.md
```

Keep detailed episode evidence and every finding in the comparison report and project memory. Put only reusable, de-identified rules in the Skill repository.

## Reference Roles

- `human_reference`: a human intentionally selected and reviewed the timeline.
- `chatcut_reference`: ChatCut created or materially changed the timeline; read [chatcut-reference-workflow.md](chatcut-reference-workflow.md).
- `agent_reference`: another automated or agentic editor created the timeline.
- `approved_reference`: a human has resolved all reference findings; this is a review state, not an input origin.

Do not assume a reference is a strict subset of the candidate. Both versions may remove material the other keeps or choose different takes from the same rerecord cluster.

## Comparison Workflow

1. Record the reference origin, tool/version when known, project or export role, and whether a human reviewed it.
2. Prefer structured project data in this order: source-linked timeline/cut history, word-timed transcript plus version diff, same-model ASR of each rendered version, then local acoustic projection.
3. Transcribe the candidate and reference with the same model when upload is authorized. If it is not, use `scripts/compare_audio_reference.py` only for a non-executable local report and label projected text as derived from the source transcript.
4. Align normalized character events while retaining both timelines.
5. If the candidate was rendered from an EDL, map candidate boundaries back to source time. Mark crossfade overlap as ambiguous.
6. Use local acoustic evidence to validate both sides of joins when audio is available. Do not infer missing words from waveform similarity.
7. Compare both directions and separate:
   - content-bearing removals, including silence carried inside discarded material;
   - independent pause compression between retained words;
   - unresolved duration residual.
8. Classify each difference as `mechanical-omission`, `semantic-condense`, `pause-adjustment`, `structural-choice`, `alternate-take`, `personal-style`, `mastering-only`, or `uncertain`.
9. Audit numbers, names, negations, qualifications, cause and effect, transitions, references, conclusions, persona, and section navigation.
10. Measure channel layout, duplicated channels, integrated loudness, true peak, LRA, sample rate, bit depth, and size separately from editorial choices.
11. Submit new edit candidates for approval. Never mutate the EDL or render from reference findings without explicit confirmation.

When a human reference is a second-pass edit of the rendered candidate, use direct-baseline mode as well as source alignment. Supply the candidate's EDL and timed transcript so direct acoustic findings can be mapped back to the immutable source timeline. Keep differences from 0.1 to less than 0.3 seconds as `micro-edit` findings with `confidence: uncertain`; do not silently drop them or treat them as safe word-level cuts. Reconcile the observed duration difference against both directional projected removals and report any residual separately as possible codec delay, padding, crossfade overlap, alignment uncertainty, or sub-threshold difference.

Use `scripts/compare_reference_edit.py` for deterministic alignment. Include transcript context only when writing to the episode workspace; the script rejects output inside the Skill directory.

```bash
python3 scripts/compare_reference_edit.py \
  work/transcript/post-edit-vNN/raw-transcript.json \
  work/transcript/reference-edited-vNN/raw-transcript.json \
  --baseline-audio output/episode-vNN.wav \
  --reference-audio REFERENCE_AUDIO \
  --baseline-edl notes/edl-vNN.json \
  --source-duration SOURCE_SECONDS \
  --include-text \
  --json-out work/transcript/reference-edited-vNN/alignment-analysis-vNN.json
```

For a rendered candidate followed by a human second pass without a complete reference transcript:

```bash
python3 scripts/compare_audio_reference.py \
  SOURCE_AUDIO BASELINE_AUDIO HUMAN_REFERENCE SOURCE_TRANSCRIPT \
  --reference-role human_reference \
  --direct-baseline \
  --baseline-edl notes/edl-vNN.json \
  --baseline-transcript work/transcript/post-edit-vNN/raw-transcript.json \
  --json-out work/transcript/reference-edited-vNN/alignment-analysis-vNN.json
```

Direct-baseline output remains non-executable. Its `start` and `end` fields use the baseline-candidate timeline, while `source_start` and `source_end` provide EDL-projected source positions when the mapping is continuous.

The script creates non-executable findings with `review_status: pending`. After review, mark each finding `accepted` or `rejected`; do not treat either status as an EDL edit instruction. Pass the resolved comparison to `scripts/editorial_qa.py --reference-comparison ...` when the project uses a reference.

## Complete Difference Memory

When the user asks to remember differences, create one project-local memory manifest that contains or checksums every detailed finding.

- Record input roles, relative artifact paths, hashes, comparison method, tool/version when known, counts, every finding ID, sensitive flags, and review status.
- Preserve bidirectional findings: `reference_removes_more` and `candidate_removes_more`.
- Keep the authoritative detailed JSON path and its checksum so no finding silently disappears during later summarization.
- Set `all_findings_remembered: true` only when the manifest count matches the detailed comparison count and IDs are unique.
- Keep all findings `pending` unless the user explicitly accepts or rejects them. Memory is an audit surface, not an approval surface.

## Confidence Gate

- `high`: stable text anchors on both sides, bilateral acoustic support when audio is supplied, a complete retained version, and no unresolved sensitive-field change.
- `medium`: semantic continuity is plausible but ASR spelling differs, only one acoustic side is stable, or the choice affects style or navigation.
- `uncertain`: alignment is unstable, content cannot be recovered safely, or the change may alter a number, negation, qualification, causal step, transition, reference, conclusion, or persona.

Local acoustic projection may locate a join with high acoustic confidence while its projected text remains semantically provisional. Never use acoustic confidence to clear a sensitive-field gate.

Sensitive-field changes always require human review regardless of alignment confidence. Do not promote them automatically.

## Reusable Learning Gate

- Promote only patterns explicitly accepted by the user and repeated across independent approved projects.
- Remember all episode findings when requested, but keep episode memory separate from reusable Skill learning.
- Keep one episode's cut density, runtime, retained-text rate, pause distribution, and exact durations project-local.
- Learn relative tendencies such as stricter failed-take cleanup or a clearer pause hierarchy, not numeric targets.
- Preserve counterexamples. A human edit can improve pacing while making a qualification or evaluation less precise.
- Treat global settings from an editor as tool-induced evidence until the user confirms the resulting style as an intentional preference.

## Explicit Personal-Default Gate

Use this exception only when the reference author directly confirms that the rendered content, pacing, or both are intentional and explicitly asks to make them a personal default for a named editorial branch.

1. Record `reference_authority`, `confirmed_scope`, `learning_scope`, and the target branch in project-local memory.
2. Mark confirmed project findings accepted without treating uncertain alignment as high confidence.
3. Promote a qualitative pattern only when it appears in at least two distinct findings, both sides have stable text anchors and acoustic support, the retained result passes grammar, meaning, logic, and program-function checks, and no finding carries a sensitive-field flag.
4. Keep one-off choices, alternate takes, uncertain alignments, and changes involving numbers, names, negations, qualifications, causality, transitions, references, conclusions, persona, or section navigation project-local.
5. Keep exact durations, cut ratios, pause values, excerpts, paths, hashes, and project statistics out of the Skill. Store only a de-identified relative tendency and its decision gate.
6. Apply the promoted default only to the named branch. Do not transfer a rigorous preference into the casual branch or turn a personal default into a universal rule.

This gate changes future recommendation defaults, not prior EDL approval. Never mutate or render an episode from a learned pattern without that episode's own confirmation.

## Post-edit Residual Scan

After rendering and transcribing the candidate, run a second mechanical scan for:

- adjacent abandoned starts followed by a complete take;
- lists or abstract sentences restarted several times;
- wrong words immediately replaced by the intended word;
- duplicated transitions, summaries, previews, or sign-offs;
- dead air still attached to a removed or abandoned take.

Require the retained version to cover the deleted region's complete meaning and function. Put every newly discovered item back through the user's confirmation gate.
