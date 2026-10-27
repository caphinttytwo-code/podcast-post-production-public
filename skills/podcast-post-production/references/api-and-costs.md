# 外部服务、上传与费用提示

信息核对日期：2026-10-13。不是账号权限或费用承诺，安装检测不产生模型请求。

| 能力 | 外部 API／上传 | 费用和条件 |
|---|---|---|
| 本地剪辑、对版、包装、锁版修订、盘点 | 无模型 API；本地素材和工具 | 不产生模型 API 费用；硬件、宿主订阅等另计 |
| 已验证完整转写缓存复用 | 无新转写请求 | 不产生新转写 API 费用；先核对源、分块、模型和参数证据 |
| 新 StepFun 转写 | 网络、服务凭据、音频上传；包中默认模型 stepaudio-2.5-asr | 可能计费或消耗套餐额度；此模型的具体单价、套餐适用性、权限与余额 UNKNOWN |
| 用户另选服务 | 只走已有且确实可用的对应流程 | 重新核对上传范围、入口、计费和权限，不能自动切换 |
| 包内合成／模拟测试 | 无制作模型 API，无真实节目上传 | 不产生制作模型调用费用；宿主模型交互费用由宿主决定 |
| 隔离 Python 依赖安装 | 软件包下载 | 不调用制作模型；用户选择后下载到独立环境 |
| GitHub Actions | 手动触发的云端测试 | 费用取决于仓库、执行器及账户规则；本库公开且默认不运行，账户状态未验证 |

[StepFun 官方平台](https://platform.stepfun.com/)及 [Step Plan](https://platform.stepfun.com/step-plan)可供核对服务规则；本次详细[价格页](https://platform.stepfun.com/docs/zh/guides/pricing/details)获取失败，不能给特定 ASR 单价或免费额度承诺。[GitHub 官方费用说明](https://docs.github.com/en/billing/concepts/product-billing/github-actions)用于核对仓库、运行器与账户计费规则；本包工作流只允许手动触发，本轮不运行。

凭据配置存在不证明账号可用；不在日志、命令、清单或报告记录原值，不为安装检查读取 Keychain 内容。实际转写可以依原模块安全凭据流程读取，但必须满足具体服务／上传授权。自定义 API 地址的归属、数据政策和计费另行核对，不能套用默认服务说明。

真实调用前提示服务／模型、上传的素材及范围、计费方式与核对日期、已有缓存、可计算的费用估计；缺少单价／配额时明确写未知，不用 0 元代替。沿用有效授权或等待相应授权后执行。宿主工具的订阅、模型套餐和自身网络服务不由本包收费表代为保证。

本包为 **0.5.0-beta 本地开发候选**，按 MIT 及保留的来源许可分发，非稳定版。新转写拒绝所有跳转；操作及缓存边界见 [asr-security.md](asr-security.md)。

## Conditional role ASR for synchronized multitrack

Local PCM assembly and valid cached-source role projections have no model API requirement. Projections are never actual-output ASR evidence. New speaker/role recognition can use user-selected Qwen FileTrans (`qwen-audio-3.1-asr-flash-filetrans`) through installed Bailian CLI `bl speech recognize`. It requires a compatible CLI parameter surface, account/model permission, region, network, media upload authorization and potentially usage fees/plan allowance or an additional service purchase. CLI presence is not entitlement. Official documentation: https://help.aliyun.com/zh/model-studio/speech-recognition . Price, quota, billing entitlement and current service availability: UNKNOWN, not verified by installation. Check live official terms and task-specific estimated cost before an authorized real request. No balance/budget/expiry snapshot is a public default. A native API capability gap must be explained and explicitly authorized; do not silently switch providers or routes. Installation and synthetic tests call no model and read no secret values.
