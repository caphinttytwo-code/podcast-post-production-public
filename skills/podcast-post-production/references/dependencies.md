# 最小安装环境与执行前检查

当前候选：0.2.0-rc.6.3-beta。最低声明、工具能力与通过验证的版本组合是不同信息；安装成功不能代替渲染和媒体 QA。

## 最小资源

| 资源 | 声明下限 / 能力 | 使用范围 |
|---|---|---|
| Python | 3.10+；有 venv 和 pip | 所有脚本 |
| FFmpeg / FFprobe | 最低配对 8.1.1+；还需实际编码器、滤镜、解码器 | 媒体制作与探测 |
| NumPy | >=1.24；选择支持当前 Python 的发行版本 | 完整声学对版、音频参考比较 |
| Pillow | >=10.1；能加载 FreeType 字体 | 片花字幕图片、封面、头帧；文字环境诊断 |
| 中文字体 | 覆盖实际文字的 TTF/OTF/TTC；可读且能加载 | 有中文的文字产物 |
| PyYAML | >=6，仅开发验证使用 | Skill 元数据检查 |
| 工作目录 | 包外可写目录；容量按 PCM、缓存、输出和临时文件估算 | 所有生成步骤 |

Python 3.10 是代码声明下限，尚未证明所有 Python/包版本组合兼容。第三方发行版的 Python 要求必须满足。Pillow 10.1 提供封面默认字体所使用的 size 参数。[Pillow 官方说明](https://pillow.readthedocs.io/en/stable/reference/ImageFont.html#PIL.ImageFont.load_default)

无需 GPU、CUDA、Node.js、Git、管理员权限或模型 SDK。基础制作和缓存复用无需网络/API Key；仅已授权的新转写检查相应服务和安全凭据。完整保护测试另需能创建文件/目录符号链接，缺权限记 BLOCKED，不自动提权。

## 按功能检查

从包根执行 `python scripts/check_environment.py --mode MODE`，保留既有 `--mode` / `--require-review` 参数。默认 full 覆盖所选模块的主要制作需求；更小的任务可用：

| 模块 | feature | 需要 |
|---|---|---|
| audio-edit | full / basic | full 加 NumPy；basic 只用标准库与 FFmpeg/FFprobe；MP3 libmp3lame、WAV pcm_s24le、loudnorm 等 |
| video-conform | subtitles | 纯校对、数字检查与决定应用，仅标准库；本地复听页需浏览器访问127.0.0.1 |
| video-conform | review-clips | 可选上下文音频片段：FFmpeg/FFprobe、libmp3lame，不要求NumPy/Pillow/字体 |
| video-conform | full | NumPy、配对工具、libx264/aac、fps/trim/tpad/overlay/concat 等；另做内容与帧数 QA |
| trailers | full | Pillow、中文字体、配对工具、libx264/aac、xfade/acrossfade/overlay 等 |
| trailers | images / subtitles | Pillow、中文字体；纯图片/字幕资产检查无需 FFmpeg |
| trailers | review | 字幕 subtitles；时间码 drawtext；编码 libx264。Review 渲染器是标准库，环境文字诊断另需 Pillow |
| locked-revision | full / subtitles | full 检查媒体修编与验收工具；subtitles 纯重计时仅需标准库 |
| project-audit | full / inventory | full 需 FFprobe；inventory 纯哈希/路径盘点仅需标准库 |

输出 JSON 包含真实导入、包版本、实际工具路径/版本/哈希、编码器/滤镜、字体字形诊断、PASS/FAIL/BLOCKED/NOT RUN。不会安装或调用云模型。新环境用 `--smoke-dir /ABS/NEW/DIR` 加小型合成编码/全解码；目录必须全新且位于包外。`--report /ABS/NEW/environment.json` 保存证据，拒绝覆盖现有文件；`--output-dir` 只检查计划输出父目录及可用空间，不估算具体作业容量。检查通过没有自动生成完整对版、剪辑质量或人工审核结论。

```text
python scripts/check_environment.py --mode audio-edit --feature basic --smoke-dir /ABS/NEW/audio-smoke --report /ABS/NEW/audio-environment.json
python scripts/check_environment.py --mode trailers --font /ABS/CJK/font.otf --smoke-dir /ABS/NEW/trailer-smoke --report /ABS/NEW/trailer-environment.json
python scripts/check_environment.py --mode trailers --feature review --ffmpeg /ABS/REVIEW/ffmpeg --ffprobe /ABS/ffprobe --font /ABS/CJK/font.otf --smoke-dir /ABS/NEW/review-smoke
python scripts/check_environment.py --mode locked-revision --feature subtitles
python scripts/check_environment.py --mode project-audit --feature inventory
```

Review 的旧构建必须显式用 `--feature review --allow-review-legacy --smoke-dir ...`，仅作为当前 Review 合成诊断，不证明完整对版兼容。历史旧构建曾使完整对版少两帧；不得用于完整对版。更高版本、滤镜存在或 full 名称同样不能替代实测。FFmpeg subtitles 需构建包含 libass，drawtext 需对应字体库；采用能力完整的现成构建即可，不要求手工安装这些底层库。[FFmpeg 官方滤镜文档](https://ffmpeg.org/ffmpeg-filters.html)

## 最小安装

在 Skill 包外的新项目目录创建隔离环境。只做一项功能时按表安装所需包；使用五模块完整制作时安装两个包：

macOS/Linux：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install "numpy>=1.24" "Pillow>=10.1"
```

Windows PowerShell：

```powershell
python -m venv --copies .venv
.\.venv\Scripts\python.exe -m pip install "numpy>=1.24" "Pillow>=10.1"
```

开发检查再安装 `PyYAML>=6`。直接调用环境解释器，无需更改 PowerShell 执行策略。[Python venv 官方说明](https://docs.python.org/3/library/venv.html)

FFmpeg/FFprobe 使用与操作系统和 CPU 匹配的配对构建，可放项目工具目录并只更改本次会话 PATH；`--ffmpeg/--ffprobe` 仅选择检查工具，若制作脚本通过 PATH 选工具，也必须使其 PATH 指向同一构建。不给出自动全局安装/升级动作。宽松 >= 清单不是版本锁；审计另输出精确环境记录。

## 中文字体

显式路径优先；无效路径明确失败。自动查找 macOS 宋体/苹方、Linux Noto CJK、Windows 当前 WINDIR 下的微软雅黑/黑体；找不到就要求配置，不用 Arial/DejaVu 冒充中文字体。

- 片花字幕：`subtitles.font`；封面：`fonts.title`、`fonts.sans`；头帧文字：`font_file`。
- Review 中文字幕：`subtitle_font_name` 指定家族，`subtitle_font_dir` 指定项目字体目录并传给 libass fontsdir。
- Review 时间码：`timecode_font_file`，保留 `font_file` 兼容入口。它与中文字幕字体独立。

项目字体可以使用 [Noto CJK 官方资源](https://github.com/notofonts/noto-cjk)或已有授权的字体，不需要将 Pillow 用字体全局安装。记录来源、许可证、字体路径/哈希；不分发用户系统字体。Review 字体目录不存在时明确失败；libass 实际字体选择仍须核对日志和抽帧。

片花生成前做缺字 mask 检查，阻止明显 .notdef 方框；该保守检查不能证明所有文字排版正确。使用实际中英文、标点、数字、单行与多行抽查生成图片和视频，确认无缺字、方框、替代字体或裁切。字体配置不是对封面/标题/画面方案的批准。

## 缓存与验收

旧 ASR 缓存文件名仅标识 chunk stem；复用前核对源/分块哈希、模型与参数证据，证据缺失时先解决有效性。有效完整缓存复用无需凭据和新请求。保留原始响应，不重新上传已有内容。

缺包/字体/编码器只阻塞依赖该能力的步骤；继续独立盘点时不能把制作阻塞改判 PASS。前置检查 PASS 不表示完整审听/审看、安装切换或发布授权。见 [离线验证](validation.md)；经过验证的平台/版本组合与精确哈希在包外交付审计中记录。

## Beta 包内安装与自测

安装前能力表、API／费用与限制、快速／完整／跳过选择和安装后报告由 [包内入口](alpha-installation.md) 提供。测试所需冻结资料已经随包提供，无需下载旧私有仓库。满足最低版本只是前提；合成探测实际调用音频与完整对版制作脚本。费用和服务条件见 [API 说明](api-and-costs.md)。

## rc6.3 audio capability separation

| Capability | Minimum resources | Verification and limits |
|---|---|---|
| audio-edit:paragraph-review | Python >=3.10; FFprobe >=8.1.1 for duration | Build pending, bound local paragraph review; real listening remains separate |
| audio-edit:preserve-source | Python >=3.10, NumPy >=1.24; compatible integer PCM WAV | Preserve mono/stereo 16/24/32-bit format and verify body/fade samples; no mastering |
| audio-edit:synchronized-multitrack | Python >=3.10, NumPy >=1.24; FFmpeg/FFprobe >=8.1.1, pcm_s24le for compressed preparation | Equal decoded frames/rate and reliable sync evidence; stop on offset/drift/insufficient evidence |

Local multitrack assembly and cached role-transcript projection use no cloud ASR. A projection is not actual output ASR. New recognition may need the user-selected service/CLI, account, region, network, upload and fee authorization. Package detection never calls a model, uploads audio or queries private billing. No personal balance, budget, price or expiry snapshot is a public default.
