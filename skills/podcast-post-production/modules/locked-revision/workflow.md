# Locked Video Surgical Revision

Make the smallest explicitly requested change to an approved master and prove what stayed locked.

## Operating contract

- Preserve the source master, its subtitles, prior reviews, and prior QA. Write a new version; never overwrite.
- Before rendering, identify the exact mutable interval and surfaces: picture, each audio track, subtitles, ending, or review copy. Treat everything else as locked.
- Do not reopen topic selection, pacing, title, visual design, or unrelated subtitle wording unless the user requests it.
- Record a revision manifest using [references/revision-manifest.md](references/revision-manifest.md). Stop when the target file already exists or the requested boundary is ambiguous.
- Render through a temporary sibling and promote it only after it is readable and structurally valid.
- Apply the same join treatment to every retained audio track. Read [references/multitrack-join-qa.md](references/multitrack-join-qa.md) before modifying audio.

## Workflow

1. Probe and hash the parent master and subtitle; record duration, frame rate, geometry, stream layout, and the requested deletion intervals.
2. Confirm complete words, breaths, and frame boundaries around every edit. ASR timestamps are candidate locations, not edit boundaries.
3. Render only the authorized change into a new version path. Preserve original speed, geometry, audio ordering and defaults unless explicitly unlocked.
4. Use `scripts/retime_srt.py` for deletions whose subtitle cues do not cross an edit boundary. Manually resolve and document boundary-crossing cues before retrying.
5. Use `scripts/validate_locked_revision.py` to compare the parent and output against the revision manifest and write a QA report.
6. Generate a Review only when requested or after the master passes technical QA. Keep `release_ready=false` until full human viewing, listening, and subtitle proofread are recorded.

## Boundaries

- A visual-only frame or cover request belongs to a long-video visual workflow, not this skill.
- A complete edited reference audio track that controls the whole picture timeline belongs to reference-audio video conforming.
- A request that changes topic, story order, or multiple unbounded sections is a new edit plan, not a surgical revision.

## Resources

- [references/revision-manifest.md](references/revision-manifest.md): manifest fields, timeline rules, and approval state.
- [references/multitrack-join-qa.md](references/multitrack-join-qa.md): safe joins and required audio checks.
- `scripts/retime_srt.py`: remove deleted cues, shift later cues, and emit a change report.
- `scripts/validate_locked_revision.py`: validate source identity, expected duration, stream locks, subtitles, hashes, and release state.
