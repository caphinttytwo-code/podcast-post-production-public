# 续作已审核的原声剪辑

适用于已完成一版 PCM 试听，只执行该版上新增的明确删改决定。先用原段落试听页以父版为源记录决定。在工作区内保留父版、基线稿、试听记录与历次交付。

运行 `python modules/audio-edit/scripts/revise_pcm.py review REQUEST.json NEW_REVISION_DIR`。请求 schema_version 为 1，包含 `parent`、`parent_sha256`、`parent_version`、`version`、`review_dir`、`review_state_sha256`、`transcript_basis`（`source` 和 `mechanical` 文件）及 `cuts`。路径相对请求文件。试听页 version 对应 parent_version。每项 cut 填写一个已保存 delete 的 `id` 和 `parent_frames: [start, end]`，使用父版采样帧的半开区间。逐项确认具体剪点，以试听位置和真实声学证据核对，避免用文字推算。可显式指定 `crossfade_seconds`，默认 20 ms。

输出新目录中的原声 WAV、兼容 EDL、逐样本核验、父新版映射与接点复听清单。未选择和未确认项保留。发生版本、哈希、决定或边界冲突时，先完成审阅。技术复核用 `python modules/audio-edit/scripts/revise_pcm.py verify REQUEST.json REVISION_DIR`。试听状态仍需记录实际用户决定。
