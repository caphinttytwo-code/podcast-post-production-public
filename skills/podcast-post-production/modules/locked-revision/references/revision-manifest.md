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

## 精确保留区验证

Schema 2 沿用上述字段并要求父版 SHA-256。提供 `time_map`，每段有 `source_start`、`output_start`、`duration`，以实际时间戳定义无变速、单调、一对一的半开保留区间。时间采用整数秒或十进制、分数字符串；有删除时保留映射须与批准的 `deletions` 对应。只修改局部文字时使用整条源到成片的恒等映射。

- `picture_changes` 每条含输出轴 `start`、`end`。指定 `region: [x,y,width,height]` 时仅允许该矩形内差异，省略 region 时整帧可变。比较原生 yuv420p、yuv444p 或 rgb24 的解码样本，YUV420 区域边界须按偶数像素对齐。像素格式、颜色元数据与帧时间戳需要可精确对齐。
- `audio_changes` 每条含从零开始的 `track`、父版 `source: {start,end}` 与新版 `output: {start,end}`。按包边界记录已批准的变化。保留的各音轨按映射后的实际 PTS 比较负载 SHA-256、时长和包侧数据。
- 运行原验证命令，可用 `--ffmpeg` 指定配对媒体工具。缺少映射、原生格式不支持或无法按时间戳建立配对时报告 BLOCKED。实际检测到锁定区变化时报告 FAIL，并列出对应轨号或帧时间戳。通过后仍需按项目记录人工审看和试听。
