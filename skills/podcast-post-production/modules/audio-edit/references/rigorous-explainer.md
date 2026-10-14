# Rigorous Explainer Branch

- Skill release: `v1.5.1`.
- Branch ID: `rigorous-explainer`.
- Status: active; ChatCut/agent-reference and complete-memory gates added in `v1.4.0`; StepFun API base standardized in `v1.4.1`; guarded human-calibrated personal defaults added in `v1.5.0`; rendered-reference comparison reliability hardened in `v1.5.1` without changing editorial thresholds.

Use this branch for episodes whose value depends on exact claims, evidence, sources, numbers, policies, procedures, cases, qualifications, or logical continuity.

Read [editorial-decision-rules.md](editorial-decision-rules.md) first. Apply this file only for branch-specific factual and logical safeguards.

## Editorial Objective

Produce a tighter spoken explanation without changing its factual meaning or argumentative structure. Do not target a deletion ratio or runtime.

## Preserve

- Every unique claim, number, date, policy, source, case, condition, caveat, causal step, transition, and conclusion, even when shortening adjacent pauses.
- Enough setup for pronouns, comparisons, callbacks, examples, and evidence to remain intelligible.
- Natural speech and meaningful pauses when they support comprehension.

## Remove

- Explicit rerecords and spoken editing instructions.
- Abandoned sentences, recording accidents, consecutive errors, immediate repetitions, and abnormal pauses.
- A repeated explanation only when it adds no fact or qualification and the retained version preserves every dependency.

## Pause Shaping

- Run pause shaping after macro selection and surface cleanup. Read [pause-shaping.md](pause-shaping.md) before creating pause-related EDL entries.
- Preserve intra-clause micro-rhythm by default. Review clause, sentence, and section gaps more actively when they slow comprehension without adding emphasis.
- Inspect both sides of every content removal and trim redundant surrounding dead air without clipping breaths, consonants, or the setup for the retained argument.
- Do not shorten a pause merely because it exceeds a numeric threshold. Preserve pauses that signal a new premise, qualification, contrast, example, or conclusion.
- When a human reference is supplied, learn only general pacing evidence. Do not copy unique factual deletions, mastering, source identifiers, or a single episode's numeric profile into branch defaults.

## Human-Calibrated Personal Defaults

Apply these qualitative defaults only after the user selects `rigorous-explainer`. They remain subordinate to the semantic-unit and sensitive-field gates.

- In the rendered-candidate residual scan, actively remove repair debris beside a complete take: abandoned fragments, progressive starts, repeated subject or predicate fragments, and immediate self-corrections. Require the retained take to cover the full meaning and program function.
- When adjacent expressions make the same claim, prefer the complete or more precise version and remove the broader duplicate only when it adds no condition, contrast, evidence, transition, or emotional function.
- In introductions, recaps, and transitions, compress repeated navigation or self-reference while keeping an explicit destination and every dependency needed later.
- After content is stable, review non-semantic silence more actively while retaining the hierarchy `section/rhetorical > sentence > clause > intra-clause`. Never derive fixed pause targets from one reference.

When uncertain, keep the source passage and mark it for review.

## Reference Edits

Read [reference-edit-learning.md](reference-edit-learning.md) before using a human or agent reference. Also read [chatcut-reference-workflow.md](chatcut-reference-workflow.md) when ChatCut created or modified it.

- Treat a human or agent edit as an editorial and pacing reference, not as the render source or master timeline.
- Keep the original recording as the source timeline and render the final result from the highest-quality source.
- Transcribe the source, reference, and candidate with the same StepFun model for final semantic decisions. When upload is not authorized, local source-transcript projection may support a non-executable comparison report but cannot clear sensitive fields.
- Do not copy a reference edit's loudness, noise treatment, music, intro, or outro unless the confirmed plan explicitly requests them.
- Keep reference audio, transcripts, excerpts, file names, timecodes, and project statistics out of the Skill repository and public Git history.
- Treat changes to numbers, negations, qualifications, causal steps, transitions, references, conclusions, persona, or section navigation as human-review items even when alignment confidence is high.
- Compare both directions and flag alternate-take choices; do not assume an agent reference only deletes from the candidate.
- When the reference author asks to make confirmed content or pacing a personal default, apply the explicit gate in [reference-edit-learning.md](reference-edit-learning.md); do not infer that request from the existence of a human edit.

## StepFun and Content QA

1. Use `stepaudio-2.5-asr` for every compared version.
2. If a five-minute chunk is risk-blocked, split that chunk into about one-minute proxies and retry while retaining all successful caches.
3. If a smaller proxy remains blocked, preserve the corresponding source content, record the exact gap, and do not infer its words from surrounding context.
4. After rendering, transcribe the candidate and compare it with the selected reference or approved transcript.
5. Report retained-text coverage, macro passages present in only one version, and any material difference in numbers, sources, qualifications, or conclusions.
6. Treat ASR spelling and number disagreements as review flags, not automatic evidence that the audio is wrong. Resolve them by listening and checking the cited source.
7. Run sentence, logic, pacing, and persona checks on the rendered candidate; factual preservation does not excuse broken delivery or clipped joins.

## Approval Gate

Do not upload, transcribe, create an EDL, or render until the user confirms a plan that names this branch, the source and reference roles, delivery formats, exclusions, and QA requirements.
