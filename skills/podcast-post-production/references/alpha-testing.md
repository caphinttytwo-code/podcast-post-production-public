# 剪辑导演 0.5.0-beta 包内封测计划

先核对包外指定的候选 ZIP 哈希和本轮审计，解压到宿主安装目录之外；未发布时不猜测 Release 地址，发布后也需核对指定来源与哈希。全部冻结来源、脚本、合成夹具、模板和执行提示随包提供；不得修改候选、安装旧版、上传真实媒体或调用制作模型。

1. 阅读 SKILL.md 和 alpha-installation.md；执行 inspect，向用户展示现有能力、缺项、限制、外部服务／上传／可能费用。
2. 提供 quick（推荐）、full、skip。用户需要补齐时独立安装 Python 依赖；工具和字体只指导补齐。检查实际工具能力，用户要求仅显示最低版本。
3. 快速测试：身份／保护测试，加选定功能的小型合成探测；音频与完整对版使用真实制作脚本。完整测试额外运行 103 项原回归、旧 29 CLI、15 项包级保护、Beta 新案例、21 步合成制作、28 项产物验收、18 项制作保护和13项字幕流程。实际数量以本轮结果为准，新案例单独计数，不重复累加。
4. 完整制作需 NumPy、Pillow、合格中文字体及媒体工具；Review 显式选择满足最低要求且含 subtitles／drawtext 的构建，不代替标准对版工具。全量解码、帧数、时间轴、三音轨、头帧、短尾相关性和源哈希均按既有验收执行。
5. 26 条宿主路由请求见包内 executor-prompt.md，实际以正常请求触发并记录可观察的工作流加载、原答复和动作边界；静态阅读或脚本指定模块只算检查。未选／拿不准／部分字幕确认不能变成全确认。
6. 经用户选择安装后，核对副本身份、完成安装后检查并交付能力报告。更新资源后检测指纹；旧报告不自动替代本轮测试。

保护反例先正常控制，再只改变危险条件；Windows 符号链接权限不足保持 BLOCKED，不提权、不以另一平台代替。身份失败立即停止；原件保护失效停止相关批次，修复候选须新版本／新证据重新验证。

返回 installation-report.md／JSON、逐组结果、命令、退出码、日志、图片／视频检查证据、开始和结束哈希及证据 ZIP。PASS、FAIL、BLOCKED、NOT RUN 分开，回归、制作步骤、产物检查及复用项分组计数。人工完整审听／审看和真实模型调用验证保持 NOT RUN，除非有实际独立证据。测试不触发旧 Skill 切换、删除或发布。

本轮固定来源兼容修复及适配差异在 `tests/resources/rc5-source-updates.zip`，其为离线数据，解压到包外查看；原回归冻结来源另见 `frozen-sources.zip`。本地开发验收范围见 [release-validation.md](release-validation.md)。

本包为 **0.5.0-beta 本地开发候选**，按 MIT 及保留的来源许可分发，非稳定版。新转写拒绝所有跳转；操作及缓存边界见 [asr-security.md](asr-security.md)。

## rc6.3 test inventory and status rules

0.3.0 的完整入口还会运行 editorial-plan 模块测试，以及无媒体工具的策划检查冒烟。保留约束、失效选择绑定、替换/搬移算式、whole/fine 和策划格式拒绝检查单独保留案例 ID；本轮实际数量从结果统计。此节其余条目为继续适用的 rc6.3 基线要求，不是本轮通过记录。

Run the packaged installer `test --test full` in a new external directory. It includes the original 103 compatibility cases (reruns, not new unique cases), migrated audio v1.7 cases (130, including earlier cases), subtitle source cases (35, including earlier cases), shared/setup/package checks, 29 legacy CLI comparisons, 21 production steps, 28 artifact checks, 18 production protections and subtitle end-to-end cases. Actual machine inventories and results determine totals; overlapping suites must not be added as unique tests.

The three source-manifest tests are adapted to the single integrated entrypoint/UI while preserving link and source-release consistency checks. Offline archives preserve the exact original source tests for independent comparison; no source repository fetch is needed.

Per-step resources and verified upstream outputs control execution. Missing version/filter/font/dependency is BLOCKED; an executed assertion/command failure is FAIL; unavailable upstream artifacts yield NOT RUN. These statuses never count as passes. Later independent subtitle, inventory, index-protection and retiming checks continue. Input start/end/final hashes are retained even on failure. Quick smoke, full automatic acceptance, host actual routing and human review are separate scopes.

Also run the same full suite on minimum 8.1.1 and 9.0.2. Supply Review FFmpeg explicitly. Test lower-version, missing-filter, missing-font and missing-dependency branches and verify unaffected checks still execute. Windows symlink permission failure stays BLOCKED without elevation.

New host routing cases: default solo, bound paragraph review, preserve PCM, equal synchronized multitrack, unequal/offset multitrack refusal, numeric review scope, partial subtitle decisions, exact format exceptions, selected adjacent merge and source-map missing evidence. Exercise actual host requests; reading instructions alone is NOT RUN for host routing.
