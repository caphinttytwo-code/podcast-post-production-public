# Review, continuity and handoff

## Keep current choices authoritative

Keep each proposal on a source identity and revision, with stable IDs and the exact preceding/rerecord/following role text. Read the real user review records. Suggested actions, source annotations and recording directions are not approvals. Explicit keep/reject decisions override later batch recommendations; custom ranges and comments remain unresolved until the exact revision/range is represented and confirmed.

Reuse the installed package's [paragraph review](../../audio-edit/references/paragraph-review.md) for supported review cases. Its `suggestion` is not a final choice. Do not extend its schema silently to fit structural operations. A complex placement table may use external, versioned review artifacts, but must retain the same source/version binding, individual choices, notes and recovery behavior. This candidate has not added a universal structural-audition UI.

When required, create independent A/B audition artifacts in the project workspace. Include the written plan and actual source comment (if any), original and candidate time, and context around both sides. Use at least the user-requested duration (normally 60 seconds before/after); document real file-edge exceptions. No synthetic bridge words, unauthorized edits or implicit master render. Playback/Range success is technical evidence, not human listening.

## Planning to execution

The handoff records:

- source/reference roles, paths, current fingerprints and clocks;
- plan revision/hash and exact item IDs;
- real user choice/approval records and their hashes, permitted whole/fine actions, protected content and unresolved issues;
- target requirement, chosen operation list, duration calculation and candidate boundary limitations;
- selected recording mode, existing execution module and expected deliverables.

Planning JSON and `check_plan.py` reports are **non-executable**. Human-authenticity of linked records is not inferred from a digest. Read their actual contents and resolve any conflict before translating to existing solo EDL or multitrack plans. Do not render unresolved items. Existing projects continue using their original records; no bulk schema migration or rerecording.

Read [target-runtime execution](../../audio-edit/references/target-runtime.md) only for a confirmed target-runtime/structural selection. Audio to video conform uses the approved actual complete edited audio, not the plan's projected duration. A trailer or locked revision still needs its own requested scope.

## Versions and recurring markers

Report adopted/rejected/pending changes, content loss, duration and necessary joins for each version. Recalculate a persistent manual marker from its true source identity. If the original utterance was removed, say so and distinguish a related topic locator from the old join. Replacements and moves require piecewise mappings; do not project through an unmatched rerecord interior.

Keep raw ASR, cache projections, actual new ASR, acoustic matches, local human listening, full human listening and publication as distinct evidence. This module does not imply any new ASR budget, alignment fix, mastering change, cleanup or public release.
