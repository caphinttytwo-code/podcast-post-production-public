# Vertical visual system

## Approval gate

Before rendering video, deliver:

1. a 1080×1920 static preview with a real source frame in the center window;
2. a 270×480 phone thumbnail;
3. a matching cover when the job includes covers.

Do not scale the batch until title size, font, color, frame geometry, and all logos are approved.

Approve surfaces in this order when covers are requested: title text and color, 9:16 layout, 3:4 layout, 4:3 layout, then video frame. Do not spend a full video encode to test typography.

## Standard geometry

- Canvas: 1080×1920.
- Center video: 1080×608 at `y=656` through `1264`.
- Top and bottom are static information fields.
- Preserve the full horizontal source image with `contain`/letterbox behavior; never stretch it.
- Keep subtitles within the center source image and visible.

The geometry is a default, not a mandate. Store approved alternatives in the visual JSON and batch manifest.

## Deterministic composition

- Render Chinese title, subtitle, separators, and labels with installed fonts.
- Paste official logo pixels. Mask simple shapes only when the source asset includes unwanted square corners.
- Prefer transparent logo files. If removing a background, key it deterministically and inspect the edge at 200%.
- Never generate or redraw logo text with an image model.
- AI-generated imagery may supply only non-semantic textures or decorative backgrounds.
- Schedule PIP, supporting clips, and pre-generated quote/flower-text assets with the manifest `timed_layers` field. Keep them away from eyes, mouth, subtitle zones, and emotion-bearing gestures.
- Prefer one final encode through `render_batch.py`; do not burn the same layer through multiple intermediate masters.

## Suggested hierarchy

- Two-line title, 64–84 px on 1080-wide canvas.
- One or two accent segments in a brand color; remaining title in ink/dark color.
- Subtitle 28–38 px with more tracking/air than the title.
- Logos grouped by relationship, optically aligned rather than forced into identical boxes.
- Use a thin separator and one small partnership label only when it clarifies hierarchy.
- Add explicit spacing between differently colored title runs. Chinese serif glyph overhang can make mathematically adjacent runs look overlapped; use a measured `title_segment_gap` rather than inserting ordinary spaces into the title string.
- When background architecture or texture obscures the first phrase, move the entire title group and use one alignment edge. Move the separator, subtitle, and explanation with it.

## Shared cover and frame title system

- Store `title_align`, title edge, segment gap, separator, subtitle edge, and explanation edge once.
- For a right-aligned system, align both title lines, the separator end, subtitle, and explanation to the same right edge.
- Reversing title colors is a valid legibility repair: for example, first phrase in accent and the following noun phrase in ink. Keep the approved mapping identical on linked surfaces.
- If the user says only 9:16 and 3:4 should change, leave 4:3 and video unchanged. Propagate only after explicit approval.
- When the video must match 9:16, build its transparent overlay from the same title configuration and retain the approved 1080×608 center window.

## Multi-ratio cover set

- 9:16: 1080×1920.
- 3:4: 1080×1440.
- 4:3: 1440×1080.
- Use a complete 16:9 source screenshot when the user asks to reference the landscape frame. Keep all speakers and burned subtitles visible.
- Compose each ratio independently. A vertical title block may sit above a 16:9 screenshot; a 4:3 cover may use a left-title/right-image split.
- Keep required explanation text on every ratio. When adding a missing line, move the screenshot and brand rows together instead of squeezing or overlapping them.

## Photo-cover variant

- Use original source/V01 photo pixels and crop away old titles and logos.
- Blend the photo into the frame background with a 120–220 px top fade and 180–320 px bottom fade.
- Keep faces, microphones, hands, and key gestures intact.
- Apply only subtle exposure/contrast correction; do not alter identity or skin tone.

## Visual JSON for `build_visuals.py`

```json
{
  "output_dir": "/absolute/path/work/previews",
  "background": "/optional/paper-or-texture.png",
  "center_frame": "/optional/real-video-frame.png",
  "colors": {"paper": "#F4F1EA", "ink": "#2A2825", "accent": "#A4372E"},
  "fonts": {"title": "/path/to/title.ttf", "sans": "/path/to/sans.ttf"},
  "title": [
    [{"text": "入场卡", "color": "accent"}, {"text": "被收走时", "color": "ink"}],
    [{"text": "红楼一梦", "color": "accent"}, {"text": "才真正结束", "color": "ink"}]
  ],
  "title_align": "right",
  "title_right": 940,
  "title_segment_gap": 26,
  "separator_line": [260, 354, 940, 354],
  "subtitle_align": "right",
  "subtitle_right": 940,
  "tagline_align": "right",
  "tagline_right": 940,
  "subtitle": "像暑假突然结束的那一刻",
  "tagline": "沉浸  ·  入梦  ·  告别",
  "logos": [
    {"path": "/logo/a.png", "box": [250, 1384, 132, 132], "shape": "rounded", "radius": 18},
    {"path": "/logo/b.png", "box": [474, 1384, 132, 132], "shape": "circle"}
  ],
  "wordmarks": [
    {"path": "/logo/c.png", "box": [165, 1655, 330, 142], "key_background": "dark"}
  ],
  "photo": {
    "path": "/optional/source-cover.jpg",
    "crop": [0, 250, 1080, 1180],
    "box": [0, 430, 1080, 930],
    "fade_top": 160,
    "fade_bottom": 260
  }
}
```

Omit `photo` when only a frame overlay/preview is needed. Omit `center_frame` when only a cover is needed.

For the approved `VNN-secNN` continuation pattern and exact review/archive/outro contract, read [approved-series-template.md](approved-series-template.md).
