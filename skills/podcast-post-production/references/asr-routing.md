# ASR 选路、缓存与费用

单人口播、多轨角色稿和字幕使用同一选路顺序。先核对已有完整缓存及对应源文件、代理、时间轴、模型和参数；已有匹配结果可直接继续，缺证据的旧缓存按原模块的来源验证方式处理。用户指定路由优先，其次项目配置、宿主配置。新提交前须有明确的服务商、模型、上传区间、计费入口和任务授权。公开包未指定默认服务商、账户、预算或到期日。

- 百炼走已安装的 bailian-gen / bailian-protocol 和 `bl speech recognize`，核对所选 FileTrans 模型、地域、参数、额度与费用。传本地授权文件路径。每次请求仅一个文件，保留原始响应。CLI 能力不等价时记录具体缺口，按已获批准的原生 API 范围继续。CLI 临时失败不能替代能力核验。
- StepFun 按项目或宿主所选入口与模型执行，现有 StepFun 脚本及旧缓存可继续使用。已授权的局部复核默认不超过源音频时长 10%，按实际提交时长计入重叠及重试。不同费用入口分别核实账户和价格。
- 时间轴采用源、母版或成片的确切版本。候选模型共识不代替复听。仅在对应时间戳真实、有效且对齐时生成字幕。用已批准模型和参数比较版本。只重试失败或尚未提交的片段，待结算任务先按请求 ID 核查状态。
- 本地转写计划和账本脚本不会调用网络。计划生成后，宿主按所选服务的预检、费用与实际授权执行。记录每次实际提交，原始响应、归一化结果及费用记录分别保存。

## 包外命令

`python scripts/asr_route.py plan REQUEST.json --output PLAN.json`

请求中的 `mode` 为 `solo`、`multitrack` 或 `subtitles`，`purpose` 为 `primary` 或 `review`。填入 `source`（相对请求目录）、`source_sha256`、`timebase`、`sample_rate`、`frames` 和 `segments`（各含唯一 `id`、`start_frame`、`end_frame`，半开区间）。填入实际 `parameters`，其中包括与转写有关的语言、时间戳、说话人及代理身份。路由对象含 `provider`（`bailian-cli`、`stepfun` 或获准的 `bailian-native`）、`model`（可省略以选对应推荐模型）、`billing_route` 和 `region`。传给 `explicit_route` 或 `project_routes` / `host_routes` 中对应的 purpose。已授权上传填 `upload_authorized: true`。百炼计划填 `cli_capability: "supported"`，或记录 `"missing"`、`cli_gap` 与所获的 `native_authorized`。续作复核按账本累计填入 `prior_review_submitted_frames`（同一源已提交的全部复核帧数）。超限复核须具有 `expanded_review_authorized`，价格缺失保留 null。

缓存每项含 `id`、`status`、`binding`、`response`、`response_sha256`。binding 为上次计划 route 去掉 entrypoint，加上该段 ID 和两端样本帧。失败重跑和待核对条目也记录原 binding，来源或路由变化时建立新工作记录。兼容旧缓存须先完成现有模块的旧缓存来源检查。生成的计划有 `CACHE_HIT`、`SELECT_PROVIDER`、`BLOCKED` 和 `READY_FOR_AUTHORIZED_HOST` 状态，最后一项仍需宿主核对实际费用和授权。

`python scripts/asr_route.py record PLAN.json ATTEMPT.json --project PROJECT`

传入真实尝试的 `segment_id`、`attempt`、`status`、`timestamp`、`request_id`，以及可得的 `input_tokens`、`output_tokens`、`quota_verification`、`price_checked_date`、`estimated_cost_cny`、`actual_cost_cny`。追加到项目包外 `asr-cost-ledger.jsonl`。未知用量和费用填 null。账本不接收原始响应、临时地址或密钥。

## 缓存覆盖与时间戳报告

计划始终输出 requested_coverage、cached_coverage、planned_submission_seconds 和 actual_submission_seconds。
覆盖范围按采样帧半开区间求并集，另列源总时长和 covers_source。CACHE_HIT 只表示请求范围内缓存命中。

每个条目的 timestamp_evidence 区分纯 text JSON 的 MISSING、检测到常见时间戳容器的 PRESENT_UNVERIFIED、
无法解释的响应 UNKNOWN 和无有效缓存 NO_VALID_CACHE。字幕模式的 subtitle_readiness 保持 NEEDS_TIMING_VALIDATION，
须由对应模块核实格式、真实时间、来源和成片映射。时间戳字段存在本身不提供可用字幕证据。

规划阶段 actual_submission_seconds 恒为 0。旧 submitted_seconds 字段保留原语义，表示计划提交时长，
新增 planned_submission_seconds 表达同一计划量。记录实际尝试时，成功结果或 submission_confirmed=true
可记录完整请求区间的提交时长；明确 submission_confirmed=false 记录 0，其他失败或待定结果保持 null，
含只有请求 ID 的失败。submitted_seconds 旧账本字段继续表示所记录尝试的区间时长。
未知实际用量、账单及费用仍为 null，不从计划量推定真实扣费。
