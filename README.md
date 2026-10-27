# 播客音视频后期 — 0.2-rc6.3beta 候选

**公开 Beta 测试版；包内版本 0.2.0-rc.6.3-beta，MIT 许可，非稳定版。当前仅 PR 候选，尚未合并、未发布新 Release。**

候选开发与审阅：[PR #1](https://github.com/caphinttytwo-code/podcast-post-production-public/pull/1)。本分支完成审计后提供 `candidates/podcast-post-production-v0.2.0-rc.6.3-beta.zip` 和 SHA256SUMS。完整 ZIP 内含五模块、安装检测、费用提示、测试、离线来源/夹具和报告模板。已发布 rc6.2 的 [固定 Release](https://github.com/caphinttytwo-code/podcast-post-production-public/releases/tag/v0.2.0-rc.6.2-beta) 保持不变。

音频来源为正式 v1.7.0，固定 46eefcdfa5cc7c4af68da87990850a23593ecf93；字幕增强来自 OPEN 源 PR #4，固定 b84c5ed7660721a23bf9abb5f46dbc27984cc144，仍待源审阅。迁移、适配和兼容性见 `source-lock.json` 与 `validation/rc63-source-migration.md`；另外三个模块保留既有修复。

下载并核验候选后，先读取包内 SKILL.md 与 references/alpha-installation.md。运行 `python3 -B scripts/setup_skill.py inspect --work-dir /ABS/NEW/preflight`，展示现有能力、缺项、外部条件及费用；再选择快速（推荐）/完整/跳过测试，按需使用包外独立依赖环境。安装目标必须是新增目录，不覆盖旧 Skills；安装后复测并展示 installation-report.md/JSON。

最低 Python 3.10；标准媒体工具 FFmpeg/FFprobe >=8.1.1，仍须任务需要的编码器、滤镜和中文字体。段落审阅、保留音质 PCM、同步多轨分别检测；audio-edit:full 仍表示单口链。不同长度/采样率、偏移、漂移或同步证据不足的多轨会停止，不能自动修复。

测试仅使用合成素材和模拟响应，不调用制作模型、不上传节目、不试扣费；宿主模型费用另计。多人新转写可按用户选择经百炼 CLI，需要账号、地域、网络、上传授权与可能费用，检测不验证真实权益。费用未知保留未知，不内置个人预算/额度。

缺项允许用户明确选择受限安装，身份或原件保护失败必须停止。测试报告区分 PASS/FAIL/BLOCKED/NOT RUN、冒烟/自动验收/实际宿主路由/人工审听。完整证据留在维护者本地，公开仅提供去个人信息摘要。工作流仅手动触发，本轮未触发。

本次只同步 PR，不自动合并、发布 Release、合并字幕源 PR、安装或切换现用 Skills。候选 ZIP 不代表生产项目获准发布。
