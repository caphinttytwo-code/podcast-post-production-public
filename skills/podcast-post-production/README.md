# 剪辑导演 — 0.6.0-beta

0.6.0-beta 是[公开 Beta 预发布版](https://github.com/caphinttytwo-code/podcast-post-production-public/releases/tag/v0.6.0-beta)，基于 0.5.0-beta，安装和切换状态以宿主报告为准。技术 ID 仍为 `podcast-post-production`，现有五模块及旧项目接续方式保留，新增 `editorial-plan` 内容策划入口与显式 `target-runtime` 音频内容分支。

先读取 [SKILL.md](SKILL.md)。长节目筛选、目标时长取舍与补录位置安排进入 [内容策划](modules/editorial-plan/workflow.md)；单项字幕、封面、校准或审计直接进入原模块，不要求先做全片策划。方案 JSON 是非执行资料，不会产生 EDL 或用户授权。

本版继承 0.5.0-beta 的来源、许可和冻结测试夹具。新增统一转写路由、缓存核验、项目费用账本及 macOS 运行环境复验。

版本沿革与兼容性见 [本地升级说明](references/local-050-upgrade.md)。最低环境与原 setup 命令见 [环境要求](references/dependencies.md)及[安装参考](references/alpha-installation.md)。包内项目输出保护、原件保护、费用与上传授权、人工审核区分继续有效。

0.6.0-beta 增加原声 PCM 二次精剪续作及锁版精确保留区验证。
