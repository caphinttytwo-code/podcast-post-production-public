# 一个包内完成检测、测试与安装

版本 0.2.0-rc.6.3-beta，Beta。先核对 GitHub Release 展示的 ZIP SHA-256，再解压；setup 还会核验全部包文件，拒绝身份变化、链接及夹带的可执行字节码。包内清单用于完整性校验，可信 ZIP 哈希来自指定 Release，不能用被修改包自己提供的清单证明来源真实性。

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

本包为 **0.2.0-rc.6.3-beta 公开 Beta 测试版**，按 MIT 及保留的来源许可分发，非稳定版。新转写拒绝所有跳转；操作及缓存边界见 [asr-security.md](asr-security.md)。
