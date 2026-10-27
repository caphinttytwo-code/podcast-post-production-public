# ChatCut Reference Workflow

Read this file when ChatCut created, modified, or exported a comparison version. Treat the ChatCut timeline as an editable agent reference, not as ground truth or the lossless master.

## Verify Current Behavior

ChatCut changes independently from this Skill. When the user asks for the latest behavior, verify the official documentation before relying on numeric defaults:

- Transcript editing: <https://chatcut.io/docs/transcript-editing>
- Version history: <https://chatcut.io/docs/version-history>
- Editing and audio tools: <https://chatcut.io/docs/editing-tools>
- Agent/plugin behavior: <https://chatcut.io/docs/agent-plugin>

The behavior below was verified against official documentation on 2026-07-22. If the current product differs, record the observed version/settings in the episode workspace and follow the current official behavior.

## Current Evidence Model

- Transcript deletion splits at word boundaries, removes the selected range, and ripples only the edited track.
- Paragraph and clip views can represent the same timeline differently; capture which view or cut history supplied evidence.
- The Pauses control can reset pauses across a track. Its documented range is 0–2000 ms in 50 ms steps, with a documented default of 500 ms.
- The documented automatic cleanup compresses pauses over 3 seconds to 200 ms and pauses over 1 second to 600 ms by default.
- Automatic filler cleanup targets unambiguous English fillers plus Chinese `呃` and `额`; it intentionally leaves ambiguous Chinese responses such as `嗯`, `啊`, and `哦`.
- Saved versions snapshot the timeline and referenced assets, while continuous autosave and undo remain separate mechanisms.

These are tool behaviors, not branch defaults. A ChatCut export with no pauses above two seconds may reflect one global operation rather than a human preference for every semantic role.

## Capture Before Comparing

1. Record `reference_role: chatcut_reference` and whether a human reviewed it.
2. Record the project ID, job ID, named version, export format, prompt, pause setting, filler cleanup, and relevant audio processing only when the user supplies or authorizes access to them.
3. Prefer a named pre-edit and post-edit version plus word-timed transcript or timeline diff over reverse engineering a rendered export.
4. Preserve the original source outside ChatCut and render any accepted podcast result from that source.
5. Do not submit media to ChatCut or another cloud service unless the confirmed plan explicitly authorizes the upload, account action, cost, and destination.

## Compare Without Assuming a Subset

- Compute `chatcut_removes_more` and `candidate_removes_more` independently.
- Mark a rerecord difference as `alternate-take` when both versions keep different complete takes.
- Separate content-bearing deletion, independent pause adjustment, crossfade/track ripple, and unresolved residual.
- Detect duplicated stereo channels, loudness changes, voice isolation, fades, or other mastering changes separately from edit selection.
- Never infer that the shorter or louder export is the better edit.

Use same-model ASR for final semantic comparison. If upload is unavailable, run `scripts/compare_audio_reference.py` with the immutable source, candidate, rendered ChatCut export, and existing source transcript. Treat projected text and source boundaries as review guides, not final word-level proof.

## Learn Safely

- Store every episode-specific difference and status in project-local memory.
- Learn repeated relative tendencies only after explicit user acceptance across independent episodes.
- Do not promote ChatCut's global pause values, filler list, cut density, export loudness, channel layout, or noise treatment into branch defaults.
- Preserve sensitive changes to numbers, names, negations, qualifications, causality, attribution, conclusions, persona, and navigation for human review.
