# Workflow profiles and handoff

## Brief gates

Before story selection, make these explicit or infer them from existing project files:

- purpose and concrete audience;
- primary platform and target duration;
- one core piece of information and the cold-viewer promise;
- source path, transcript coverage, glossary state, and asset availability;
- must-keep and must-remove constraints;
- subtitle, PIP, cover, audio, and anti-example expectations.

Do not claim full-source selection when transcript coverage is partial. Record open questions instead of inventing answers.

## Profiles

- `lightweight-talking-head`: one selected talking-head or口播 video. Ask only for platform/duration, keep/remove requirements, subtitle style, cover title, and requested assets. Skip candidate scoring and full story arc unless the user requests structural editing.
- `standard-clipping`: long livestream, interview, course, or video podcast. Require a full candidate pool, story roles, subtitle/visual plan, and QA.
- `heavy-collab`: multi-version or teammate work. Add the complete brief, asset log, version log, timecoded review, approval gates, and delivery package.

## Story readiness

For standard and heavy work, require every selected segment to serve one role: hook, context repair, stakes, turn, evidence, emotional peak, close, or a rare information-bearing bridge. The opening may use the strongest line, but the following section must repair who, what, why, and credibility for a cold viewer.

## Project records

Keep these records beside the batch manifest:

```text
work/transcript/
work/candidates/
work/previews/
manifests/
versions/videos/
versions/covers/
versions/subtitles/
versions/edit-notes/
versions/qa/
versions/version-log.md
media/assets/asset-log.md
reviews/review-vNN.md
delivery/
```

Use the templates under `assets/templates/`. Do not copy raw media, API keys, or user assets into the skill repository.

## Version and review rules

- For ordinary revisions, advance `vNN` when an existing story, audio, subtitle, timed layer, frame, title, logo or reviewed output changes. For approved-series continuation, follow `approved-series-template.md`: keep its series `vNN` and advance `secNN` for a new section. Changes to an already reviewed section require a distinct revision record and archived prior output; a stable visible filename is reused only when explicitly authorized.
- Preserve every user-reviewed output. A root-level `current` file may be a convenience copy, never the archive.
- Store reviewer feedback with output timecodes and the original wording.
- Record what changed, which feedback it addressed, what stayed locked, and which file is current.
- Deliver only approved masters and requested covers/subtitles. Keep manifests, previews, caches, and QA evidence outside `delivery/` unless requested.
