# Batch manifest

Use UTF-8 JSON. Keep paths absolute when media lives outside the project directory. Do not store API keys.

```json
{
  "batch_id": "podcast-2026-07",
  "series_version": "v04",
  "defaults": {
    "transition": 0.2,
    "merge_threshold": 0.5,
    "fps": 30,
    "width": 1080,
    "height": 1920,
    "video_y": 656,
    "video_height": 608,
    "background": "#F4F1EA",
    "crf": 21,
    "audio_bitrate": "192k",
    "audio_sample_rate": 48000,
    "outro": {"fade_to_black": 0.0, "black_hold": 0.0}
  },
  "jobs": [
    {
      "id": "01-entry-card",
      "section": "sec01",
      "source": "/absolute/path/episode.mp4",
      "title": "入场卡被收走时｜红楼一梦才真正结束",
      "subtitle": "像暑假突然结束的那一刻",
      "overlay": "/absolute/path/frame-overlay.png",
      "subtitles": {
        "path": "/absolute/path/subtitles-v04-sec01.srt",
        "max_chars": 16,
        "house_style": true,
        "bad_terms": [{"wrong": "何菜头", "correct": "和菜头"}],
        "asset_dir": "/absolute/path/work/subtitle-assets/v04-sec01",
        "font": "/absolute/path/PingFang.ttc",
        "font_size": 48,
        "color": "#FFFFFFFF",
        "stroke_color": "#000000E6",
        "stroke_width": 4,
        "margin_v": 150
      },
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
        }
      ],
      "covers": [
        {"ratio": "9:16", "path": "/absolute/path/cover-v04-sec01-9x16.jpg", "width": 1080, "height": 1920},
        {"ratio": "3:4", "path": "/absolute/path/cover-v04-sec01-3x4.jpg", "width": 1080, "height": 1440},
        {"ratio": "4:3", "path": "/absolute/path/cover-v04-sec01-4x3.jpg", "width": 1440, "height": 1080}
      ],
      "output": "/absolute/path/final-v04-sec01.mp4",
      "outro": {"fade_to_black": 1.0, "black_hold": 0.0},
      "clips": [
        {"in": "00:08:05.200", "out": "00:09:55.440"},
        {"in": "00:13:20.000", "out": "00:17:55.000"}
      ]
    }
  ]
}
```

## Rules

- `id` is stable across revisions; filenames may advance from `v01` to `v02`.
- `series_version` is the visible family version. Use `section: secNN` to add another story under the same approved system, for example `final-v04-sec02.mp4`.
- `in` and `out` accept seconds or `HH:MM:SS.mmm`.
- Every clip must be longer than twice the transition duration.
- Keep `in` and `out` as `HH:MM:SS.mmm` strings copied from the transcript. The renderer prints normalized timestamps during EDL audit.
- `merge_threshold` controls the dry-run warning for adjacent source clips; the default is 0.5 seconds. Merge warned clips unless the tiny gap is an intentional removal.
- Clips are rendered in manifest order. They need not be chronological when the story plan explicitly calls for a cold open.
- `overlay` is a 1080×1920 PNG whose center video window is transparent.
- Omit `overlay` to render a plain-color top/bottom frame.
- `subtitles` is optional. It may be a path string or an object with `path`, `max_chars`, `house_style`, `bad_terms`, `asset_dir`, and deterministic Pillow font/color/stroke/margin fields.
- `timed_layers` is optional and accepts `image` or `video` assets with explicit output `start`, `end`, position, and positive dimensions. A video may set `mix_audio: true` and `audio_gain`.
- Omitting `subtitles` and `timed_layers` preserves the legacy rendering path.
- Run `scripts/subtitle_qa.py` before rendering and `scripts/qa_outputs.py` after rendering. The latter rechecks the subtitle against the actual media duration.
- `covers` is metadata for QA; rendering does not generate it. Compose each ratio independently. Legacy single-path `cover` remains supported.
- `outro.fade_to_black` adds a cloned-frame tail and full-frame fade only after the complete final clause. `outro.black_hold` optionally keeps a fully black hold after the fade. Both default to zero.
- Existing outputs are skipped by default. Use `--force` only after explicit overwrite approval.

## Version names

Use readable, non-destructive names:

```text
versions/videos/final-v01-<story-slug>.mp4
versions/covers/cover-v01-<story-slug>.jpg
work/previews/frame-v01-<story-slug>.png
```

Advance the version when story, audio, subtitles, visual frame, title, or logo treatment changes. Do not rename an old version into a new approval state.

Within an explicitly approved series version, use section names instead:

```text
versions/videos/final-v04-sec02.mp4
versions/covers/cover-v04-sec02-9x16.jpg
versions/covers/cover-v04-sec02-3x4.jpg
versions/covers/cover-v04-sec02-4x3.jpg
```
