# Subtitles and timed layers

## Chinese subtitle contract

- Correct verified people, pronouns, titles, products, places, organizations, numbers, and domain terms from a project glossary.
- Remove non-semantic fillers, abandoned starts, and obvious stutters. Preserve repetition that carries meaning or emotion.
- For the burned house style, use half-width spaces instead of ordinary Chinese punctuation and omit sentence-final punctuation.
- Keep each visible line near 16 Chinese characters, avoid orphan fragments, and do not split names or fixed terms.
- Align cues to spoken meaning and real timestamps. Never deliver zero-filled or character-proportional ASR timing as a final SRT.
- Never stack replacement subtitles over burned source subtitles.

Run structural and house-style QA before render:

```bash
python3 scripts/subtitle_qa.py subtitles-v01.srt \
  --media-duration 00:08:42.400 \
  --bad-term 何菜头=和菜头
```

The validator requires sequential cue numbers, valid positive time ranges, no overlaps, non-empty text, no media overrun, the chosen visible-length limit, and project terminology. `render_batch.py` then creates deterministic transparent PNGs in `asset_dir` and overlays them during the single final encode, so no ffmpeg `subtitles/libass` filter is required.

## Manifest fields

Add replacement subtitles to a job:

```json
{
  "subtitles": {
    "path": "/absolute/path/subtitles-v01.srt",
    "max_chars": 16,
    "house_style": true,
    "bad_terms": [
      {"wrong": "何菜头", "correct": "和菜头"}
    ],
    "asset_dir": "/absolute/project/work/subtitle-assets/v04-sec01",
    "font": "/absolute/path/PingFang.ttc",
    "font_size": 48,
    "color": "#FFFFFFFF",
    "stroke_color": "#000000E6",
    "stroke_width": 4,
    "margin_v": 150
  }
}
```

Schedule already prepared image/video assets:

```json
{
  "timed_layers": [
    {
      "type": "image",
      "path": "/absolute/path/guest-photo.png",
      "start": "00:01:12.000",
      "end": "00:01:19.500",
      "x": 680,
      "y": 700,
      "width": 330,
      "height": 330
    },
    {
      "type": "video",
      "path": "/absolute/path/supporting-clip.mp4",
      "start": 160.0,
      "end": 166.5,
      "x": 620,
      "y": 690,
      "width": 400,
      "height": 300,
      "mix_audio": true,
      "audio_gain": 0.35
    }
  ]
}
```

- Support `image` and `video` layer types. Create quote cards and flower-text as transparent images with `build_visuals.py` or another deterministic asset step.
- Require positive `width` and `height`, an explicit `end`, and a non-negative `start`.
- Keep PIP away from eyes, mouth, subtitles, important gestures, and product details.
- Reduce overlays during crying, silence, or other emotion-bearing moments.
- Set `mix_audio` only when a video asset has useful verified audio. Listen across the complete interval and document the gain in the asset log.
- Render frame, layers, subtitles, outro, and audio through the single `render_batch.py` encode.

## Asset and visual QA

For every layer, record source path or URL, rights/usage notes, output time range, placement, audio use, and reviewer status. Inspect the first, middle, and final visible frame of each timed layer plus every emotional-risk scene.
