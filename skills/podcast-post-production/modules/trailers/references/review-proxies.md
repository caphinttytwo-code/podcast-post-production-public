# Review Proxies

Use review proxies to expose subtitles and frame timecode without modifying or replacing source media.

## Configuration

`scripts/render_review_proxies.py` accepts one JSON configuration file. Required fields are `root` and `output_dir`; paths relative to the config file are resolved from that file.

Optional fields include `exclude_dirs`, `suffix`, `width`, `height`, `fps`, `font_file`, subtitle and timecode styling, audit destinations, and explicit `items`. Without `items`, the script recursively pairs MP4 and same-stem SRT files.

## Invariants

- Exclude the output directory, quarantine/delete directories, and existing review files from discovery.
- Skip an existing output unless `--force` is explicitly supplied.
- Render to a temporary sibling and replace the requested review only after validation succeeds.
- Preserve every source audio stream with optional mapping. Review video re-encoding is expected; source modification is forbidden.
- Continue after one item fails and report success, skipped, planned, and failed items separately.
- Verify readable output, intended dimensions and frame rate, source/output duration tolerance, and audio-stream count.

Run `--dry-run` before encoding. Confirm the actual FFmpeg has both subtitle and timecode filters before a batch that requires them.

## Project subtitle fonts

Set `subtitle_font_dir` to an existing project font directory and `subtitle_font_name` to the intended family. This directory is passed to libass `fontsdir`; validate actual glyph selection in logs and frames. `timecode_font_file` (or legacy `font_file`) controls timecodes only. Missing explicit font resources fail before rendering. Do not reuse an output path that aliases a font file.
