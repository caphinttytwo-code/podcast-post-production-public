# Paragraph listening review

Use when the user wants manuscript-aligned review, rerecord selection or a listening confirmation page. Build complete groups before presenting uncertain choices; do not turn every ASR fragment into a separate user decision.

## Editorial preparation

Reuse the complete source ASR. Use the manuscript to correct recognition, spelling and punctuation, not to replace a coherent spoken rewrite or invent unrecorded words. Prefer the final take only when it preserves completeness, meaning, logic and context. Keep unique conditions, negations and causal connections; put unresolved cases in `uncertain`.

Construct a project-local JSON specification. The builder validates timing and grouping; it does not make editorial judgments. Use actual ASR or acoustic times. Isolate missing or zero-duration locators in a separate uncertainty report before building; never estimate their duration from text length.

```json
{
  "source_audio": "source.wav",
  "manuscript": "script.md",
  "version": "v01",
  "items": [
    {"id":"S1","start_ms":100,"end_ms":900,"text":"先保留条件。","suggestion":"keep"},
    {"id":"S2","start_ms":1500,"end_ms":2100,"text":"失败起句。","suggestion":"uncertain","proposed_decision":"delete","repeat_group_ids":["R1"],"reason":"比较两次说法，前次没有独有内容。"},
    {"id":"S3","start_ms":2500,"end_ms":3600,"text":"后次完整表达。","suggestion":"uncertain","proposed_decision":"keep","repeat_group_ids":["R1"],"manuscript_text":"原稿对应表达。"}
  ],
  "repeat_groups": [{"id":"R1","takes":[{"start_ms":1500,"end_ms":2100,"text":"失败起句。"},{"start_ms":2500,"end_ms":3600,"text":"后次完整表达。"}]}]
}
```

Paths are relative to the specification. Optional `playback_audio` points to an independent, time-preserving proxy; the builder binds both hashes and checks duration. `chapter` optionally labels cards. Connected `repeat_group_ids` become one card. Only uncertain rows are card targets; every utterance inside the complete group's span plus approximately five seconds each side supplies context. A proposal is available only when all targets have explicit `proposed_decision` values.

```bash
python3 scripts/review.py build PROJECT/review-spec.json PROJECT/review-v01
python3 scripts/review.py launch PROJECT/review-v01
```

The launcher starts a detached loopback service, verifies project identity via `/health`, and chooses a free port when necessary. Open the printed URL using the host browser tool or let the user open it. It reuses only a matching project service; never kill another process merely because it owns the preferred port. WAV/MP3 playback supports byte ranges.

## Decisions and reliable recovery

- Default to uncertain paragraphs; provide complete text search, manuscript comparison, separate takes, normal/slow playback and replay. Card decisions can affect only `target_ids`, never context.
- All items start pending. A submitted custom instruction remains `uncertain` until its audio meaning is resolved. Display full-source pending counts even when all visible cards were handled.
- “Adopt other definite suggestions” requires explicit user authorization and freezes the exact ID set. Preserve manual choices, uncertain rows and any later-discovered candidates. Record text corrections separately from audio decisions.
- Save to the project before advancing. Keep version-bound browser drafts, export/import, durable revision snapshots and audit history. Do not regenerate an existing review directory; create a new version and explicitly migrate applicable decisions.
- Three-way merge uses the server's durable base revision. Disjoint item/field edits can merge. Same-field conflicts return 409; preserve/export the local draft and explicitly choose local changed fields or the project record. Never silently replace a newer project with an older browser snapshot.
- Use `state.json` for saved decisions and inspect `history.jsonl` when reconciling “finished” claims. A browser count, local draft or successful download alone is not evidence that all audio decisions reached the project.

The review server exposes only `/`, `/audio`, `/data`, `/progress` and `/health`. Writes require same-origin loopback requests. The server rejects wrong bindings, forged IDs, card-context edits and unauthorized bulk adoption. Project files remain outside the Skill repository.

## Handoff

Freeze confirmed decisions against source, manuscript and review version before building an EDL. The review page approves content selection, not ASR-derived acoustic boundaries or mastering changes. Produce the concrete edit plan in the agreed sequence and reuse earlier authorization when its source, version and scope still apply.
