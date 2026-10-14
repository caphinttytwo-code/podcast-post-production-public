# 播客音视频后期 — 0.2-rc6.2beta

**公开 Beta 测试版；包内版本 0.2.0-rc.6.2-beta，MIT 许可，非稳定版。**

唯一获取入口：[指定 Beta Release](https://github.com/caphinttytwo-code/podcast-post-production-public/releases/tag/v0.2.0-rc.6.2-beta)。下载完整 ZIP，核对可信发布页 SHA-256，再解压。包包含五模块、安装与环境检查、API/费用提示、快速/完整测试、全部离线夹具与报告模板。

先读取 SKILL.md 与 references/alpha-installation.md，再用 `python3 -B scripts/setup_skill.py inspect --work-dir /ABS/NEW/preflight` 检查。展示能做什么、缺什么、外部条件和可能费用；选择快速（推荐）/完整/跳过以及是否补齐包外独立 Python 环境后，使用包内安装入口。目标必须是新增目录，不覆盖旧 Skills；安装后复测并展示 installation-report.md/JSON。

最低 Python 3.10；媒体功能最低 FFmpeg/FFprobe 8.1.1，仍须相应编码器、滤镜和中文字体。测试仅用合成素材/模拟响应，不调用制作模型、不上传节目、不试扣费；宿主模型费用另计。普通缺项允许用户明确选择受限安装，身份/保护失败必须停止。

来源/许可见 NOTICE.md；本版改动见 references/beta-release.md；实际验证范围见 references/release-validation.md。软件补齐不能保证内容判断正确、恢复缺失时间轴、完成宿主路由或真人审听。测试通过不授权切换、清理或发布节目。旧私有仓库和旧包保持不变。
