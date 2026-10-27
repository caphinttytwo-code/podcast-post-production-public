# Headframe Candidates

Use this workflow only for visual selection from immutable source or approved video. Lock EDL, timing, audio, subtitles, and the video itself.

## Inputs and outputs

`scripts/extract_headframe_candidates.py` accepts JSON jobs with a video plus either explicit timestamps or bounded sampling windows. Automated sampling produces candidates, not a final choice.

Each successful job creates:

- full-resolution PNG frames;
- full-frame delivery previews on a configurable canvas;
- phone previews;
- a labeled contact sheet;
- a manifest containing source and output hashes;
- a Markdown selection record.

## Selection and approval

Inspect the full frames for natural expression, open eyes, clear gesture, clean composition, motion blur, and available title/subtitle space. Provide two or three useful alternatives when requested.

Keep old candidate sets and their audits. Write a new version directory, do not overwrite a reviewed candidate set, and verify the source hash again after extraction.

The default state is `candidate_pending_user_confirmation` with `release_ready=false`. Technical extraction and image QA never imply that the user selected a final frame.
