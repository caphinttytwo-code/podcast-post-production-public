# 一个包内完成检测、测试与安装

版本 0.6.0-beta，公开 Beta 预发布版。从 [GitHub Release](https://github.com/caphinttytwo-code/podcast-post-production-public/releases/tag/v0.6.0-beta) 下载完整 ZIP 和 SHA256SUMS.txt，先核对外部 SHA-256 再解压。安装入口会核对包内文件清单。先选定宿主、目标目录与安装范围。版本沿革见 [本地升级说明](local-050-upgrade.md)。

## 安装前

使用 Python 3.10 或以上，在解压后的根目录运行 `scripts/setup_skill.py inspect --work-dir /ABS/NEW/preflight`。这里及下文的 /ABS 是用户选择的绝对路径，不是需要原样使用的目录。Python 不存在时先安装 Python；不要把无法运行检查写成测试通过。

检测按功能展示现有资源能实现什么、缺项、补齐方法、尚需的素材／映射／账号／授权，以及软件补齐不能解决的问题。外部 API 的账号权限、单价和额度都不通过安装探测验证，密钥不显示。读取 [费用说明](api-and-costs.md)。

安装不是模型调用授权。依赖补齐只安装到包外 venv，会访问软件包源；不升级全局 Python、FFmpeg、字体或模型 SDK。不支持的 Python／包组合明确报错，不静默调整下限。

## 三个测试选择

```text
python3 -B scripts/setup_skill.py test --work-dir /ABS/NEW/quick --test quick
python3 -B scripts/setup_skill.py test --work-dir /ABS/NEW/full --test full --review-ffmpeg /ABS/TOOLS/ffmpeg --font /ABS/FONT/CJK.ttf
```

快速测试运行包级保护和所选功能的合成探测。完整测试运行原回归、CLI 对比、保护反例、21 步制作、产物验收和字幕流程；冻结来源已压缩在包内，解压到证据目录后使用，不需拉取旧仓库。选择 skip 时状态保持“资源齐备，尚未验证”。非交互式调用必须显式选择 `--test quick|full|skip`。

## 用户选定安装后

目标必须是宿主认可的 Skill 目录下一个尚不存在的新目录，通常命名 podcast-post-production。执行器先确认用户选择的宿主及目标；不猜测目录、不删除旧 Skills。安装入口复制完整包，包含以后自测所需材料。

```text
python3 -B scripts/setup_skill.py install --work-dir /ABS/NEW/setup --dest /ABS/HOST/SKILLS/podcast-post-production --test quick
```

用户选择补齐 Python 时加 `--install-python`；依赖在 `/ABS/NEW/setup/python-environment` 中，补齐后重跑检测／测试并安装，最终报告在该工作目录的 `after-dependencies` 下。生产使用报告记录的 Python 解释器，不能随后改用缺依赖的全局 Python。

只需部分功能时用 `--features video-conform:subtitles,project-audit:inventory` 等。所有可选 feature 见 [最低环境要求](dependencies.md)。其他功能仍保留在包内；本轮报告只证明选定功能，其余需要检测后再用。

有资源缺项或普通测试失败时默认停止安装；用户看过具体限制后可显式加 `--allow-limited`。身份不符、包级／制作保护测试失败或权限阻塞不能用该参数绕过。已有目标、旧报告、符号链接路径均拒绝；中断复制不会覆盖旧版本。安装后重新检查副本并运行对应快速检查，产生 installation-report.md／JSON。完整测试的安装前结果保留，安装后的快速探测不替代它。

## 工具路径与以后使用

`--ffmpeg`、`--ffprobe` 选择标准制作工具，要求实际可执行文件名为 ffmpeg／ffprobe（Windows 为 .exe），并能在选定 PATH 中解析成同一文件。`--review-ffmpeg` 只供 Review 选用；不能静默用于完整对版。用户提示只有最低 8.1.1；精确版本／哈希保存到 JSON。

从其他安装器直接复制的首次使用没有安装前证据，应先报告这一点并展示三种测试选择。复制包本身不保证宿主已加载或支持测试对话，宿主实际路由须按包内计划验证。更新工具、依赖或字体后再检查；传 `--previous-report /ABS/OLD/installation-report.json` 比较环境指纹，匹配仅表示资源未变，不自动伪造本轮测试。

所有报告、夹具、venv、缓存和项目媒体必须在包外。返回 report.md、JSON、日志和证据哈希；人工审听／审看仍单独记录。失败后保留本轮证据，在新目录重试。

本包为 **0.6.0-beta 公开预发布版**，按 MIT 及保留的来源许可分发，非稳定版。新转写拒绝所有跳转；操作及缓存边界见 [asr-security.md](asr-security.md)。

## macOS 宿主升级后的复验

已配置本机绑定的宿主使用 `pp-setup revalidate --work-dir /ABS/NEW/revalidation`。该入口由宿主安装在包外，调用包外留存的 `scripts/revalidate_runtime.py` 副本。已有部署未配置此入口时，可用绑定的 Python 以 `-I -B` 运行该脚本，指定 `--runtime-root` 为已有绑定的配置目录、`--work-dir` 为新的包外目录。复验会检查所有已绑定文件及安装包身份，执行全套快速合成探测和 Review 探测。全部通过后记录并更新系统版本与配置指纹。发生其他绑定变化时，按差异完成环境验收再重新绑定。
