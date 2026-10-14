# Edit Solo Podcasts

Edit speech non-destructively; keep editorial selection separate from sound mastering.
Current release: `v1.5.1`. Read [version history](references/version-history.md) only for migration or historical behavior.
Maintain the repository copy; installed copies are validated runtime copies.

## Operating Contract

- Preserve the source. Never overwrite, normalize, or trim the only source file.
- Transcribe the full source before making content claims or macro cuts.
- Separate editorial branch rules from the shared sound-mastering chain.
- Keep exact source timecodes and a reason for every deleted region.
- Prefer complete clauses and whole low-value passages over dense chains of micro-cuts.
- Run the auditable editorial passes in this order: deterministic mechanical cleanup, refreshed staged transcript, semantic editing, then pause shaping.
- Base semantic decisions only on the mechanical-stage transcript, while mapping every final cut back to the original source timeline.
- Keep approved machine-executable cuts separate from unresolved human-review candidates.
- Keep human, ChatCut, and other agent-reference findings non-executable until the user explicitly approves them for the EDL.
- Add 15–30 ms fades or crossfades at assembled boundaries.
- Keep credentials out of commands, logs, EDLs, and project files.
- Require a human full-length listen before public release; technical QA is not subjective listening.

## Require a Confirmed Plan

For a continuation, first locate and verify the existing approved plan and current source/reference identity. When the object, version, branch, authorized changes, upload scope and delivery specifications still match that approval, continue its authorized steps without requesting duplicate approval. New or changed scope follows the steps below; a vague prior agreement does not authorize an executable cut.

1. Perform only read-only inspection before the plan: locate and probe sources, references, existing ASR caches, EDLs, notes, and delivery constraints.
2. Before writing project files, uploading audio, running ASR, building an EDL, rendering, or publishing, present a concrete plan and wait for explicit user confirmation.
3. If the user has not already selected them, ask for:
   - editorial branch: `casual-non-rigorous` or `rigorous-explainer`;
   - delivery: MP3, WAV, or both.
4. Do not repeat a question the user already answered. Record explicit choices in the plan, project brief, EDL, and edit notes.
5. The plan must state the source and reference roles, job type, branch, StepFun ASR scope, staged-transcript workflow, delivery formats and sound profile, exclusions, planned artifacts, editorial and technical QA, and human-listen gate. Identify a ChatCut export as `chatcut_reference`, not `human_reference`, unless a human explicitly made and approved the timeline decisions. When learning is requested, also record whether content, pacing, or both are confirmed and whether the result is project-only, reusable, or a named branch's personal default.
6. Treat plan confirmation as authorization only for the stated workflow. Platform publishing, account actions, and newly discovered scope still require separate authority.

## Route the Editorial Branch

1. Inspect the request, transcript, existing EDL, edit notes, and delivery target.
2. Use `casual-non-rigorous` only for light solo commentary, personal reflection, entertainment, informal knowledge sharing, or conversational shows where small detail loss does not create factual risk.
3. Read [references/editorial-decision-rules.md](references/editorial-decision-rules.md), then [references/casual-non-rigorous.md](references/casual-non-rigorous.md), before creating or changing that branch's EDL.
4. Use `rigorous-explainer` for research, policy, statistics, sources, procedures, news, or arguments that require exact factual and logical continuity. Read [references/editorial-decision-rules.md](references/editorial-decision-rules.md), then [references/rigorous-explainer.md](references/rigorous-explainer.md), before creating or changing that branch's EDL.
5. If neither branch fits, stop and propose a dedicated branch under `references/`; never stretch an existing branch into a universal policy.
6. Record the selected branch in the project manifest and edit notes.

## Workflow routing

- For `new` or `continue`, read [startup and layout](references/production-workflow.md#start-every-job) and [production workflow](references/production-workflow.md#workflow) before work. Probe the source and reuse complete ASR caches and approved decisions.
- Follow the staged sequence: source ASR → approved mechanical cuts → refreshed mechanical-stage transcript → approved semantic cuts → pause shaping → dry-run/render → post-edit transcript → editorial and technical QA. Keep every final cut on the original source timeline.
- Before changing an EDL, also read [EDL schema](references/edl-schema.md). Before pause work, read [pause shaping](references/pause-shaping.md).
- For `compare` or reference-derived learning, read [reference-edit learning](references/reference-edit-learning.md) and [comparison procedure](references/production-workflow.md#8-validate-sound-and-compare). Read [ChatCut workflow](references/chatcut-reference-workflow.md) only for a ChatCut-created or modified reference. Findings remain non-executable until explicitly approved.
- For `revision`, reuse the confirmed branch, input roles, caches, and delivery choices; change only the authorized scope. Read the affected production steps before changing cuts, audio, or output formats.
- For failures, read the relevant [failure handling](references/production-workflow.md#failure-handling) entry; preserve caches and unresolved content instead of guessing or silently changing providers.

## Acceptance and delivery

- Run the renderer's dry-run before rendering. Read [render settings](references/production-workflow.md#6-render-the-edit) for the unchanged mastering chain and MP3/WAV options.
- Review the rendered post-edit transcript for sentence, logic, pacing, and persona integrity. Listen around every join; newly discovered cuts require review rather than silent EDL changes.
- Run `scripts/audio_qa.py` for each selected format, then `scripts/editorial_qa.py`. Pending candidates, unresolved reference findings, or an unsigned full-length human listen keep `release_ready: false`.
- Read [delivery contract](references/production-workflow.md#delivery-contract). Deliver only the confirmed MP3/WAV formats plus EDL, edit notes, and QA; keep raw/staged/post-edit ASR and process media outside delivery.
- Publishing, account actions, artwork, chapters, and enriched metadata require their own authorization. An upload-ready file does not authorize publication.
- Script purposes are listed in [resources](references/production-workflow.md#resources); resolve commands from the skill directory.
