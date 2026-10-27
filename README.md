# 剪辑导演（Beta）— 0.5.0-beta 本地升级候选

技术 ID 继续为 `podcast-post-production`。本地准备、未推送、未发布；运行状态由本机部署报告记录。当前仓库可见性保持既有公开设置。此目录是现有维护仓库的隔离分支，基于 `a8dbcaa37d7bdacc6e44d2dbb9ab9e827b01624a`，不是新建远程仓库。

[Skill 入口](skills/podcast-post-production/SKILL.md)新增长节目内容筛选、目标时长取舍、补录编排与决策总结；保留原五执行模块、旧项目格式与命令。策划默认到方案为止，具体内容损失及 whole/fine 范围确认后才移交已有执行器。

- 当前来源及维护增量：[source-lock.json](source-lock.json)、[本地接续说明](skills/podcast-post-production/references/local-050-upgrade.md)。原许可及历史来源记录保留。
- 原 rc6.3 基线仍在 [PR #1](https://github.com/caphinttytwo-code/podcast-post-production-public/pull/1)；本轮不修改该远程 PR，不合并字幕源 PR。
- 已发布 rc6.2 的[固定 Release](https://github.com/caphinttytwo-code/podcast-post-production-public/releases/tag/v0.2.0-rc.6.2-beta)及仓库既有候选 ZIP 不覆盖。
- 本轮整合变更与实际本地验证摘要：[validation/director030-integration.md](validation/director030-integration.md)。完整原始日志、合成产物及本机路径保留在包外私有审计，不混入发行包。

安装检测、API/费用提示、包内完整测试和手动 Actions 工作流保留。纯策划使用 Python 标准库；媒体模块最低要求仍为配对 FFmpeg/FFprobe 8.1.1，另需所选能力的依赖、滤镜及字体。实际资源与模型权益分别核验，安装检测不调用模型、不上传、不试扣费。

本轮只形成可审阅本地结果。GitHub 更新、版本发布、运行版部署和整理须用户确认具体对象与范围；永久删除另行确认。测试通过、人工完整审听/审看与实际宿主路由分别记录。

0.5.0-beta 是按用户要求由 0.3 本地整合跨版本升级；原 0.3 验证摘要为历史资料。本轮验证与最终隐私/来源审计另见 validation/director050-upgrade.md；它们不生成远程发布授权。
