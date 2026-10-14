# Approved series continuation template

Use this reference when the user asks for the next cut under an already approved version and brand system.

## Identity and outputs

- Keep the visible series version stable and advance the section: `v04-sec01`, `v04-sec02`, `v04-sec03`.
- Deliver exactly four files unless requested otherwise:
  - `final-v04-secNN.mp4`
  - `cover-v04-secNN-9x16.jpg`
  - `cover-v04-secNN-3x4.jpg`
  - `cover-v04-secNN-4x3.jpg`
- Keep manifests, QA, previews, scripts, and archived revisions outside `delivery/`.

## Continue mode

1. Reuse the existing full transcript, candidate ranking, source probe, logos, paper texture, fonts, and approved geometry.
2. Select the next story window and build its own complete hook, context, turn, payoff, and restrained close.
3. Give the section its own editorial title while retaining the series version and brand system.
4. Approve all requested covers before video rendering.
5. Render the video only after the title system and linked frame are approved.

## Visual system

- Standard video: 1080×1920, 30fps, center source window 1080×608 at `y=656–1264`.
- Keep original source pixels and burned subtitles intact in the center window.
- Treat the approved 9:16 cover title block as the source of truth when the user asks for matching video packaging.
- For a right-aligned title block, use one right edge for both title lines, separator end, subtitle, and explanation.
- Use explicit inter-segment spacing to prevent Chinese serif glyph overhang from appearing as overlap.
- Recompose 9:16, 3:4, and 4:3 separately; do not crop one cover into the others.
- Preserve official logo pixels and their approved grouping. Archive fragile external texture, font, and logo inputs into the project before rendering.

## Revision discipline

- Cover approval is a hard gate before the final video encode.
- Change only the named surfaces. A request for 9:16 and 3:4 does not authorize changes to 4:3 or video.
- Before overwriting an explicitly authorized stable delivery filename, copy the reviewed file into `versions/archive/<job>-<reason>/`.
- Keep EDL/audio locked during visual-only changes.
- For a rhythm revision, retain the approved visual system and archive the current video before changing EDL boundaries.
- Diagnose rushed speech in this order: verify transcript-to-seconds conversion, merge adjacent source intervals, extend clause handles, then tune crossfade duration.
- If a continuous interaction contains the example and payoff, keep it as one clip; do not create internal transitions merely to remove harmless fillers.

## Ending and QA

- Extend the final source out-point through the complete resolving clause. Never clip the requested last words.
- Add a full-frame fade to black after the clause with manifest `outro.fade_to_black`; use `black_hold` only when a black hold is requested.
- QA the exact final subtitle/words, a late fade frame, and the last frame.
- Wait until the rendered MP4 has a readable `ffprobe` duration before copying it to `delivery/`.
- Verify video dimensions/fps/audio, every cover dimension, title strings, logo safety, and that `delivery/` contains only requested files.

## Per-item content approval

A series template or previous pilot approval covers only its specific approved surfaces. Each new story and source-timecode EDL requires its own content approval before video rendering. An approved cover may be reused only for the same approved cover content/version; new titles or new cover contents require their own review. Existing approvals are reused only for the exact approved item and version.
