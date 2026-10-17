"""Beta setup orchestration; local probes, opt-in tests, no model requests."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

from . import environment
from .files import outside_package
from .package_identity import verify, extract_fixtures, digest

ROOT = Path(__file__).resolve().parents[1]
LABELS = {'PASS': '已验证可用', 'READY': '资源齐备，尚未验证',
          'BLOCKED': '缺少资源', 'FAIL': '测试失败', 'NOT RUN': '尚未验证'}
LIMITATIONS = [
    '软件补齐不能保证内容判断、数字语义或艺术表达正确；仍需实际审阅。',
    '缺失时间轴映射、已审核版本、素材或删改授权时，不能猜测或继续修改。',
    '账号模型权限、服务可用性、额度和真实费用未通过安装检测验证。',
    '安装副本核验不证明宿主已加载 Skill 或正确路由；宿主路由需实际测试。',
    '合成测试不等于人工完整审听／审看，也不提供清理、发布或切换授权。',
]


def selections(value):
    all_features = [(m, f) for m, fs in environment.FEATURES.items() for f in fs]
    if value == 'all':
        return all_features
    chosen = []
    for item in value.split(','):
        mode, feature = item.strip().split(':', 1)
        if mode not in environment.FEATURES or feature not in environment.FEATURES[mode]:
            raise ValueError('Unsupported feature: ' + item)
        if (mode, feature) not in chosen:
            chosen.append((mode, feature))
    if not chosen:
        raise ValueError('Choose at least one feature')
    return chosen


def external_services():
    # Do not read Keychain, print key values, or query any account/billing endpoint.
    configured = any(bool(os.environ.get(key)) for key in ('STEPFUN_API_KEY', 'STEP_API_KEY'))
    return {
        'local': {'network': False, 'model_api_fee': False,
                  'note': '本地制作、有效缓存复用及合成测试不调用模型 API；宿主费用另计。'},
        'new_transcription': {
            'provider': 'StepFun', 'default_model': 'stepaudio-2.5-asr',
            'configured_environment_key': configured, 'keychain': 'NOT CHECKED',
            'network_required': True, 'audio_upload': True,
            'billing': '可能计费或消耗套餐额度；当前账号与此模型的计费规则 UNKNOWN',
            'account_permission': 'NOT VERIFIED', 'quota': 'NOT VERIFIED',
            'price': 'UNKNOWN', 'estimated_cost': 'UNKNOWN',
            'official_sources': ['https://platform.stepfun.com/step-plan',
                                 'https://platform.stepfun.com/docs/zh/guides/pricing/details'],
            'source_checked_date': '2026-10-13',
            'source_status': '官方平台可查；详细价格页获取失败，未确认特定 ASR 单价',
            'endpoint_override': 'Custom endpoint billing/data policy must be checked before use',
            'required_before_call': ['指定服务和模型', '上传素材范围', '官方计费方式及日期',
                                     '可计算的费用估计或明确未知', '对应用户授权'],
        },
        'new_role_transcription': {
            'provider':'Aliyun Bailian / DashScope', 'suggested_model':'qwen-audio-3.1-asr-flash-filetrans',
            'entrypoint':'bl speech recognize', 'cli_path':shutil.which('bl'),
            'cli_parameter_support':'NOT VERIFIED', 'account_permission':'NOT VERIFIED', 'region':'UNKNOWN',
            'quota':'NOT VERIFIED', 'price':'UNKNOWN', 'estimated_cost':'UNKNOWN',
            'network_required':True, 'audio_upload':True, 'billing':'可能计费、消耗账户额度或另购服务；调用前核验',
            'native_api':'Only after an identified CLI capability gap and explicit user authorization',
            'official_sources':['https://help.aliyun.com/zh/model-studio/speech-recognition'],
            'source_checked_date':None, 'source_status':'未在安装检测中联网核验费用',
        },
        'multitrack_local':{'network_required':False,'model_api_fee':False,'cached_projection_is_actual_output_asr':False},
        'other_providers': '仅依实际支持流程和用户选择列入，不自动切换服务或调用。',
        'host': 'Codex/TRAE/Claude Code/Qwen Work/Doubao Work/WorkBuddy 的订阅或模型费用由宿主决定，UNKNOWN。',
        'ci': {'automatic': False, 'billing': 'GitHub Actions 费用取决于仓库、运行器与账户规则；本库公开且默认不运行，未核验账户。',
               'source': 'https://docs.github.com/en/billing/concepts/product-billing/github-actions',
               'source_checked_date': '2026-10-13'},
        'model_calls': 0, 'paid_model_calls': 0,
    }


def capability_report(chosen, args, smoke_base=None):
    rows = []
    for mode, feature in chosen:
        ffmpeg = args.review_ffmpeg if feature == 'review' and args.review_ffmpeg else args.ffmpeg
        _, _, _, _, images, review = environment.profile(mode, feature)
        probe = environment.inspect(mode, feature=feature, ffmpeg=ffmpeg,
                                    ffprobe=args.ffprobe, font=args.font if images or review else None,
                                    smoke_dir=(smoke_base / (mode + '-' + feature)) if smoke_base else None,
                                    output_dir=args.work_dir)
        rows.append({'id': mode + ':' + feature,
                     'status': ('PASS' if smoke_base else 'READY') if probe['ok'] else probe['status'],
                     'missing': probe['missing'], 'evidence': probe,
                     'validation_scope': 'smoke' if smoke_base and probe['ok'] else 'resource_inspection',
                     'full_automatic_status': 'NOT RUN', 'blocked_by': probe['missing']})
    return rows


def fingerprint(rows):
    fields = []
    for row in rows:
        ev = row['evidence']
        fields.append({'id': row['id'], 'binaries': ev['binaries'],
                       'packages': {k: v for k, v in ev['packages'].items()
                                    if k not in ('smoke', 'output_directory')},
                       'font': ev['font'], 'checks': [c for c in ev['checks']
                                                    if c['check'] not in ('synthetic smoke', 'output directory')]})
    return hashlib.sha256(json.dumps({'python': sys.version, 'executable': sys.executable,
                                     'platform': platform.platform(), 'features': fields},
                                    sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def markdown(report):
    channel_label = report['channel'].capitalize()
    lines = [f'# {channel_label} 安装与能力报告', '',
             f"版本：{report['identity']['version']}（{channel_label}）。安装状态：{report['installation_status']}。",
             f"包树 SHA-256：`{report['identity']['tree_sha256']}`。", '',
             f"{channel_label} 测试版；分发：{report['distribution']}。包公开许可不等于项目发布授权或人工审核。", '',
             '最低要求：Python 3.10；需要媒体工具的功能使用 FFmpeg／FFprobe 8.1.1 或以上，并具备所需编码器、滤镜。', '',
             '| 功能 | 当前状态 | 验证范围 | 缺项／原因 |', '|---|---|---|---|']
    for row in report['capabilities']:
        errors = [c.get('error', '') for c in row['evidence']['checks'] if c['status'] != 'PASS']
        reason = '; '.join(row['missing'] + errors + [row.get('validation_note', '')]).replace('|', '/').replace('\n', ' ')
        scope={'full_automatic':'所列案例自动验收','smoke':'小型合成冒烟','resource_inspection':'仅资源检测'}.get(row.get('validation_scope'),'尚未验证')
        lines.append(f"| {row['id']} | {LABELS.get(row['status'], row['status'])} | {scope} | {reason or '见逐项测试证据'} |")
    lines += ['', '补齐方法：', '',
              '- NumPy：独立 Python 环境中安装 numpy>=1.24；Pillow：Pillow>=10.1；完整验证另需 PyYAML>=6。',
              '- FFmpeg／FFprobe：安装适合系统的配对构建，最低 8.1.1；Review 另需 subtitles、drawtext，版本高不代表滤镜完整。',
              '- 中文字体：配置具有实际字形覆盖、可读且有使用许可的字体；不分发系统字体。',
              '- 工作目录：包外可写目录；实际项目所需空间和素材仍须单独检查。', '',
              '外部 API 与费用：', '',
              '- 本地制作、有效缓存复用和包内合成测试不产生模型 API 调用；宿主订阅／模型费用另计。',
              '- 同步多轨本地装配和角色缓存投影不依赖云端 ASR；新角色识别可按用户选择经百炼 CLI，另需 CLI 能力、账号、地域、网络与上传授权，费用未知。',
              '- 新转写使用 StepFun 时需网络、凭据及音频上传，可能计费或消耗套餐额度；具体价格、权限、额度均未验证。',
              '- 安装流程不试扣费、不访问 Keychain、不显示密钥、不调用模型；其他服务不会自动代替 StepFun。',
              '- Python 依赖补齐会访问软件包源；GitHub Actions 手动运行费用取决于仓库、执行器与账户配置。', '',
              '测试与下一步：', '', f"- 本轮测试选择：{report['test_choice']}。",
              f"- 环境变化需要重测：{report['retest_required']}。",
              '- 阅读包内 references/alpha-testing.md，按需执行快速／完整测试；宿主路由和人工审核另行记录。',
              '- 精确环境、逐项命令、返回码和哈希见配套 JSON 与日志。', '',
              '| 测试组 | 结果 |', '|---|---|']
    lines += [f"| {item['group']} | {item['status']} |" for item in report['tests']]
    if not report['tests']:
        lines.append('| 本轮测试 | NOT RUN |')
    if report.get('post_install_check'):
        lines.append(f"| 安装后快速／资源检查 | {report['post_install_check']['status']} |")
    lines += ['', '安装后快速通过不能覆盖安装前完整失败；失败组、NOT RUN 和日志保留在本报告中。', '',
              '补齐环境后仍存在的限制：', ''] + ['- ' + x for x in LIMITATIONS]
    lines += ['', '未支持的工作：包外业务能力、自动补造时间轴、自动批准编辑／清理／发布、用模拟结果生成真人审核结论。',
              '', '宿主实际路由：NOT RUN。人工完整审听／审看：NOT RUN。release_ready=false。', '']
    return '\n'.join(lines)


def execute(command, name, directory, env=None):
    result = subprocess.run([str(x) for x in command], capture_output=True, text=True,
                            encoding='utf-8', errors='replace',
                            env=env or {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1'})
    (directory / (name + '.stdout.log')).write_text(result.stdout, encoding='utf-8')
    (directory / (name + '.stderr.log')).write_text(result.stderr, encoding='utf-8')
    log = result.stdout + result.stderr
    blocked = 'WinError 1314' in log or 'BLOCKED: Windows symlink permission' in log
    skipped = bool(re.search(r'OK\s*\(skipped=\d+', log))
    count = re.search(r'Ran (\d+) tests?', log)
    return {'group': name, 'status': 'BLOCKED' if blocked or skipped else 'PASS' if result.returncode == 0 else 'FAIL',
            'exit_code': result.returncode, 'command': [str(x) for x in command],
            'stdout': name + '.stdout.log', 'stderr': name + '.stderr.log',
            'unittest_count': int(count.group(1)) if count else None, 'skipped': skipped}


def full_tests(directory, args):
    fixtures = extract_fixtures(ROOT / 'tests/resources/frozen-sources.zip', directory / 'fixtures')
    stages = [
        ('interfaces', [sys.executable, '-B', ROOT / 'scripts/check_interfaces.py', '--frozen-sources', fixtures / 'sources', '--report-dir', directory / 'interfaces']),
        ('new-interfaces',[sys.executable,'-B',ROOT/'scripts/check_new_interfaces.py','--report-dir',directory/'new-interfaces']),
        ('compatibility-103', [sys.executable,'-B',ROOT/'scripts/run_compatibility.py','--report-dir',directory/'compatibility-103']),
        ('regression', [sys.executable, '-B', ROOT / 'scripts/run_tests.py', '--frozen-sources', fixtures / 'sources', '--report-dir', directory / 'regression']),
        ('package-protection', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', ROOT / 'tests/package_protection', '-v']),
        ('synthetic', [sys.executable, '-B', ROOT / 'tests/synthetic_integration.py', '--work-dir', directory / 'synthetic', '--review-ffmpeg', args.review_ffmpeg or args.ffmpeg]),
        ('product-acceptance', [sys.executable, '-B', ROOT / 'tests/product_acceptance.py', '--work-dir', directory / 'synthetic', '--report-dir', directory / 'acceptance']),
        ('production-protection', [sys.executable, '-B', ROOT / 'tests/production_protection.py', '--work-dir', directory / 'synthetic', '--report-dir', directory / 'production-protection']),
        ('subtitle-e2e', [sys.executable, '-B', ROOT / 'tests/subtitle_integration.py', '--work-dir', directory / 'subtitle-e2e']),
    ]
    selected_font = args.font
    if not selected_font:
        from .fonts import font_path
        try:
            selected_font = font_path()
        except FileNotFoundError:
            selected_font = None
    if selected_font:
        for name, command in stages:
            if name in ('synthetic', 'product-acceptance', 'production-protection'):
                command.extend(['--font', selected_font])
    results = []
    runtime = runtime_env(args)
    for name, command in stages:
        row = execute(command, name, directory, runtime)
        results.append(row)
        paths = {'synthetic':'synthetic/integration-summary.json',
                 'product-acceptance':'acceptance/results.json',
                 'production-protection':'production-protection/protection-results-run02.json', 'regression':'regression/summary.json','compatibility-103':'compatibility-103/results.json','interfaces':'interfaces/results.json','new-interfaces':'new-interfaces/results.json'}
        if name in paths and (directory/paths[name]).is_file():
            data=json.loads((directory/paths[name]).read_text())
            items=data if isinstance(data,list) else data.get('steps',data.get('items',data.get('suites',[])))
            row['items']=items
            statuses={x['status'] for x in items}
            row['status']='FAIL' if 'FAIL' in statuses else 'BLOCKED' if 'BLOCKED' in statuses else 'NOT RUN' if 'NOT RUN' in statuses else row['status']
            row['counts']={status:sum(x['status']==status for x in items) for status in statuses}
    write_json(directory / 'full-results.json', {'groups': results, 'host_routing': 'NOT RUN',
               'human_full_review': 'NOT RUN', 'release_ready': False})
    return results


def apply_validation_scope(rows, groups):
    for row in rows:
        mode=row['id'].split(':',1)[0]
        relevant=[];common=[]
        for group in groups:
            if group['group'] in ('alpha-setup','package-protection'):
                common.append(group);continue
            items=group.get('items',[])
            if not items and group.get('status')=='FAIL':common.append(group)
            if group['group'] in ('regression','compatibility-103'):
                for suite in items:
                    if suite.get('suite')==mode:
                        if suite['status']!='PASS':common.append(suite)
                        relevant += [x for x in suite.get('cases',[]) if x.get('feature')==row['id']]
                    elif suite.get('suite')=='shared' and suite['status']=='FAIL':common.append(suite)
            elif group['group'] in ('interfaces','new-interfaces'):
                common += [x for x in items if x.get('case','').startswith(mode+'/') and x['status']!='PASS']
            else:
                relevant += [x for x in items if x.get('feature')==row['id']]
                if group['group']=='subtitle-e2e' and row['id']=='video-conform:subtitles':common.append(group)
        failures=[x for x in common+relevant if x['status']!='PASS']
        complete=bool(relevant) and not failures
        row['full_automatic_status']='PASS' if complete else 'FAIL' if any(x['status']=='FAIL' for x in failures) else 'BLOCKED' if any(x['status']=='BLOCKED' for x in failures) else 'NOT RUN'
        row['full_status']=row['full_automatic_status']
        row['full_validation_evidence']=[x.get('step',x.get('case',x.get('group'))) for x in relevant]
        row['blocked_by']=[x.get('reason',x.get('case',x.get('group',x.get('suite')))) for x in failures]
        row['validation_scope']='full_automatic' if complete else 'smoke' if row['status']=='PASS' else 'resource_inspection'
        if failures and row['status']=='PASS':
            row['quick_status']='PASS';row['status']='READY'
            row['validation_note']='Smoke passed; relevant full checks incomplete or failed. See full_automatic_status and blocked_by.'


def runtime_env(args):
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1'}
    parents = []
    for name, value in [('ffmpeg', args.ffmpeg), ('ffprobe', args.ffprobe)]:
        path = shutil.which(str(value))
        if path:
            if Path(path).stem != name:
                raise ValueError('Standard production tool must have its canonical name: ' + name)
            parents.append(str(Path(path).resolve().parent))
    env['PATH'] = os.pathsep.join(dict.fromkeys(parents + [env.get('PATH', '')]))
    for name, value in [('ffmpeg', args.ffmpeg), ('ffprobe', args.ffprobe)]:
        expected = shutil.which(str(value))
        actual = shutil.which(name, path=env['PATH'])
        if expected and (not actual or Path(actual).resolve() != Path(expected).resolve()):
            raise ValueError('Selected tool differs from production PATH: ' + name)
    return env


def prepare_work(path):
    original = Path(path).expanduser()
    outside_package(original)
    for parent in [original] + list(original.parents):
        if parent.is_symlink():
            raise ValueError('Evidence path must not contain symbolic links')
    original.mkdir(parents=True, exist_ok=False)
    return original.resolve()


def install_copy(destination, identity, work):
    destination = Path(destination).expanduser()
    outside_package(destination)
    for parent in [destination] + list(destination.parents):
        if parent.is_symlink():
            raise ValueError('Installation path must not contain symbolic links')
    if destination.exists():
        raise FileExistsError('Existing installation is protected; choose a new destination')
    dest = destination.resolve()
    if dest == work or dest in work.parents:
        raise ValueError('Installation must not contain the evidence directory')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pp-alpha-', dir=destination.parent) as tmp:
        stage = Path(tmp) / 'podcast-post-production'
        shutil.copytree(ROOT, stage, ignore=shutil.ignore_patterns('__pycache__', '.DS_Store', '.git'))
        if verify(stage) != identity:
            raise RuntimeError('Installation staging identity changed')
        # Destination was absent. Never replace an existing directory.
        if destination.exists() or destination.is_symlink():
            raise FileExistsError('Destination appeared during installation')
        stage.rename(destination)
    if verify(destination) != identity:
        raise RuntimeError('Installed package identity changed')
    return destination.resolve()


def dependency_environment(args, work):
    selected = selections(args.features)
    packages = set()
    for mode, feature in selected:
        packages.update(environment.profile(mode, feature)[0])
    requirements = [{'numpy': 'numpy>=1.24', 'Pillow': 'Pillow>=10.1'}[p] for p in sorted(packages)]
    if args.test == 'full':
        requirements = ['numpy>=1.24', 'Pillow>=10.1', 'PyYAML>=6']
    target = work / 'python-environment'
    result = execute([sys.executable, '-m', 'venv', '--copies', target], 'create-venv', work)
    if result['status'] != 'PASS':
        raise RuntimeError('Independent Python environment creation failed; see create-venv logs')
    python = target / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if requirements:
        result = execute([python, '-m', 'pip', 'install', *requirements], 'install-python-dependencies', work)
        if result['status'] != 'PASS':
            raise RuntimeError('Python dependency installation failed; see dependency logs')
    return python


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['inspect', 'test', 'install'])
    p.add_argument('--work-dir', type=Path, required=True, help='Fresh evidence directory outside Skill')
    p.add_argument('--features', default='all', help='all or comma-separated MODE:FEATURE')
    p.add_argument('--test', choices=['quick', 'full', 'skip'])
    p.add_argument('--dest', type=Path)
    p.add_argument('--ffmpeg', default='ffmpeg')
    p.add_argument('--ffprobe', default='ffprobe')
    p.add_argument('--review-ffmpeg')
    p.add_argument('--font', type=Path)
    p.add_argument('--previous-report', type=Path)
    p.add_argument('--install-python', action='store_true', help='Explicit opt-in: download dependencies into a new isolated environment')
    p.add_argument('--allow-limited', action='store_true', help='Explicitly accept listed missing/failed features; never bypass identity/protection')
    args = p.parse_args(argv)
    identity = verify(ROOT)
    if args.action == 'install' and not args.dest:
        p.error('install requires --dest; no host destination is guessed')
    chosen = selections(args.features)
    work = prepare_work(args.work_dir)
    before = capability_report(chosen, args)
    fp = fingerprint(before)
    previous = json.loads(args.previous_report.read_text(encoding='utf-8')) if args.previous_report else None
    metadata = json.loads((ROOT / 'package-manifest.json').read_text(encoding='utf-8'))
    report = {'identity': identity, 'channel': metadata['channel'], 'distribution': metadata['distribution'],
              'public_distribution_ready': metadata['public_distribution_ready'],
              'public_distribution_blockers': metadata['public_distribution_blockers'],
              'date_utc': datetime.now(timezone.utc).isoformat(),
              'installation_status': 'NOT INSTALLED', 'capabilities': before,
              'test_choice': args.test or 'NOT RUN', 'tests': [], 'environment_fingerprint': fp,
              'retest_required': previous is None or previous.get('environment_fingerprint') != fp or previous.get('identity') != identity,
              'external_services': external_services(), 'limitations': LIMITATIONS,
              'human_full_review': 'NOT RUN', 'host_routing': 'NOT RUN', 'release_ready': False,
              'installation_performed': False, 'old_skills_modified': False}
    write_json(work / 'environment-before.json', report)
    (work / 'environment-before.md').write_text(markdown(report), encoding='utf-8')
    print(markdown(report))
    if args.action != 'inspect' and args.test is None:
        if not sys.stdin.isatty():
            p.error('Choose --test quick (recommended), full, or skip explicitly after reviewing the preview')
        answer = input('安装前测试：1 快速（推荐） / 2 完整 / 3 跳过 [1]：').strip() or '1'
        if answer not in ('1', '2', '3'):
            p.error('Invalid test selection')
        args.test = {'1': 'quick', '2': 'full', '3': 'skip'}[answer]
        report['test_choice'] = args.test
    if args.install_python:
        print('将下载 Python 软件包到独立环境；不会升级全局 Python 或调用模型 API。')
        try:
            python = dependency_environment(args, work)
        except (OSError, RuntimeError) as exc:
            report.update(installation_status='STOPPED: dependency installation failed', installation_error=str(exc), ok=False)
            report['identity_end'] = verify(ROOT)
            write_json(work / 'installation-report.json', report)
            (work / 'installation-report.md').write_text(markdown(report) + '\n错误：' + str(exc), encoding='utf-8')
            return 2
        # Keep the initial report; the child writes a new evidence directory under it.
        child_work = work / 'after-dependencies'
        child_work.mkdir()
        forwarded = list(argv if argv is not None else sys.argv[1:])
        forwarded.remove('--install-python')
        if '--test' not in forwarded and args.test:
            forwarded += ['--test', args.test]
        idx = forwarded.index('--work-dir'); forwarded[idx + 1] = str(child_work)
        # _prepared-work requires the venv to be adjacent to the evidence directory.
        # Use a normal fresh child directory and no private re-entry flag instead.
        child_work.rmdir()
        result = execute([python, '-B', ROOT / 'scripts/setup_skill.py', *forwarded], 'after-dependencies', work)
        if result['exit_code']:
            print('依赖补齐后的流程未完成，请查看 after-dependencies 日志和报告。')
        else:
            print('最终报告：' + str(child_work / 'installation-report.md'))
        return result['exit_code']
    if args.test in ('quick', 'full'):
        testdir = work / 'tests'; testdir.mkdir()
        guard = execute([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', ROOT / 'tests/alpha', '-v'], 'alpha-setup', testdir)
        report['tests'].append(guard)
        if guard['status'] != 'PASS':
            report['installation_status'] = 'STOPPED: protection/self-test failure'
        else:
            report['capabilities'] = capability_report(chosen, args, work / 'quick-probes')
            if args.test == 'full':
                report['tests'] += full_tests(testdir, args)
                apply_validation_scope(report['capabilities'],report['tests'])
    errors = any(x['status'] in ('FAIL', 'BLOCKED') for x in report['capabilities'])
    suite_errors = any(x['status'] != 'PASS' for x in report['tests'])
    protection_failure = any(x['status'] != 'PASS' and x['group'] in ('alpha-setup', 'package-protection', 'production-protection') for x in report['tests'])
    if args.action == 'install':
        if protection_failure:
            report['installation_status'] = 'STOPPED: protection test failed/blocked'
        elif (errors or suite_errors) and not args.allow_limited:
            report['installation_status'] = f"STOPPED: choose missing resources or explicitly accept limited {report['channel'].capitalize()}"
        else:
            try:
                installed = install_copy(args.dest, identity, work)
            except (OSError, ValueError, RuntimeError) as exc:
                report.update(installation_status='STOPPED: installation copy failed', installation_error=str(exc), ok=False)
                report['identity_end'] = verify(ROOT)
                write_json(work / 'installation-report.json', report)
                (work / 'installation-report.md').write_text(markdown(report) + '\n错误：' + str(exc), encoding='utf-8')
                return 2
            report['installation_performed'] = True
            report['installation_status'] = 'INSTALLED; host loading NOT VERIFIED'
            report['installed_path'] = str(installed)
            command = [sys.executable, '-B', installed / 'scripts/setup_skill.py', 'test' if args.test != 'skip' else 'inspect',
                       '--work-dir', work / 'post-install', '--features', args.features,
                       '--ffmpeg', args.ffmpeg, '--ffprobe', args.ffprobe]
            if args.test != 'skip': command += ['--test', 'quick']
            if args.font: command += ['--font', args.font]
            if args.review_ffmpeg: command += ['--review-ffmpeg', args.review_ffmpeg]
            post = execute(command, 'post-install', work)
            report['post_install_check'] = post
            postreport = work / 'post-install/installation-report.json'
            if postreport.exists():
                report['capabilities'] = json.loads(postreport.read_text(encoding='utf-8'))['capabilities']
                if args.test == 'full':
                    apply_validation_scope(report['capabilities'],report['tests'])
            if post['status'] != 'PASS':
                report['installation_status'] = 'INSTALLED; post-install checks incomplete/failed'
    report['identity_end'] = verify(ROOT)
    if report['identity_end'] != identity:
        raise RuntimeError('Original candidate changed during setup')
    report['ok'] = (not errors and not suite_errors and not protection_failure and
                    not report['installation_status'].startswith('STOPPED') and
                    report.get('post_install_check', {}).get('status', 'PASS') == 'PASS')
    write_json(work / 'installation-report.json', report)
    (work / 'installation-report.md').write_text(markdown(report), encoding='utf-8')
    print('报告：' + str(work / 'installation-report.md'))
    return 0 if report['ok'] else 1
