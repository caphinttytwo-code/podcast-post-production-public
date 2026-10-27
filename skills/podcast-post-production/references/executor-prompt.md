# 给宿主执行器的包内要求

你正在测试本目录的 podcast-post-production rc.6.2 Beta。先读取 SKILL.md、alpha-installation.md、alpha-testing.md 与 api-and-costs.md。展示当前资源能做什么、全功能缺什么、即便补齐仍有哪些条件和限制、哪些需要外部 API／上传／可能付费。询问快速（推荐）／完整／跳过测试和补齐独立 Python 环境的选择，再执行选定流程。

不要索取另一份测试计划，不访问旧私有仓库，不修改候选，不升级全局环境，不读取或展示密钥，不调用制作模型，不上传真实节目，不替换旧 Skills。测试材料全部在包中。使用全新包外目录，保留开始／结束身份、命令、退出码、逐项状态和日志；未经实际测试的事项不要标 PASS。

宿主路由请求：五种能力各直接／间接一条（10 条）；仅改封面、仅做字幕、旧项目续做、授权不足、显式清理、缺失跨时间轴映射（6 条）；同轴字幕续校、数字争议、部分确认、需要新时间边界的重计时（4 条）。对每条提供合理的合成素材／记录，实际向当前宿主发出请求，记录选择模块、范围、是否请求必要证据及是否扩大授权。不得实际进行未授权项目改动。不能执行宿主动态路由时保持 NOT RUN。

安装只在用户选定宿主、目标和安装范围后执行。安装后展示包生成的能力报告。最终交付报告、JSON、日志、图片／媒体验收证据、哈希清单及证据 ZIP；技术通过、宿主路由、人工完整审听／审看分开。报告需写实际宿主和模型，不根据名称猜测。真实 API 权限／额度／费用仍未通过合成测试验证。

本包为 **0.2.0-rc.6.3-beta 公开 Beta 测试版**，按 MIT 及保留的来源许可分发，非稳定版。新转写拒绝所有跳转；操作及缓存边界见 [asr-security.md](asr-security.md)。


rc6.3 additions: use only the package's current entries and original 103 compatibility runner. Verify source v1.7.0 and fixed pending subtitle PR provenance. Run new audio capability probes independently. Do not convert multitrack to solo EDL or use cached projections as output ASR. Test environment-blocked branches and report per-case PASS/FAIL/BLOCKED/NOT RUN with source hashes even after failure; do not stop unrelated tests when Review fails. No real model or paid API calls. Keep actual host routing, platform coverage and human listening as NOT RUN unless performed.
