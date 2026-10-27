# Revision Manifest

Use JSON with `schema_version: 1`.

```json
{
  "schema_version": 1,
  "id": "clip-v02.1",
  "source": "versions/clip-v02.mp4",
  "source_sha256": "optional expected hash",
  "output": "versions/clip-v02.1.mp4",
  "source_subtitle": "versions/clip-v02.srt",
  "output_subtitle": "versions/clip-v02.1.srt",
  "deletions": [
    {"start": "00:00:51.933", "end": "00:00:54.117", "reason": "approved sentence removal"}
  ],
  "audio_join": {"mode": "non_overlap_fade", "frames": 2, "all_tracks": true},
  "locked": {"speed": true, "geometry": true, "frame_rate": true, "audio_layout": true},
  "release_ready": false
}
```

Paths are resolved relative to the manifest. `source` and `output` must differ, output paths must not already exist before rendering, and deletion intervals must be ordered, non-overlapping, and expressed on the parent timeline.

`expected_output_duration` may be supplied when the render includes an explicitly approved hold or another documented duration adjustment. Otherwise the validator expects source duration minus deletion duration.

`source_sha256` is recommended. A stored historical hash is not a current read unless the source is hashed during this run.

Keep `release_ready` false in machine-generated manifests. Human review status belongs in a separate recorded approval or a later manifest revision.
