#!/usr/bin/env python3
"""Run each module in its own process to avoid same-name import collisions."""
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.files import outside_package, child_output
from shared.package_identity import extract_fixtures, verify


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frozen-sources', type=Path, help='Optional external baseline; bundled fixture is the default')
    p.add_argument('--report-dir', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = outside_package(args.report_dir); out.mkdir(parents=True, exist_ok=True)
    verify(root)
    frozen = args.frozen_sources or extract_fixtures(root / 'tests/resources/frozen-sources.zip', out / 'fixtures') / 'sources'
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1', 'PP_FROZEN_SOURCES': str(frozen.resolve())}
    reports = []
    for name, folder in [(x.name, x / 'tests') for x in sorted((root / 'modules').iterdir())] + [('shared', root / 'tests')]:
        result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(folder), '-v'], env=env, capture_output=True, text=True, encoding='utf-8')
        log = result.stdout + result.stderr
        child_output(out, name + '.txt').write_text(log, encoding='utf-8')
        count = re.search(r'Ran (\d+) tests?', log)
        reports.append({'suite': name, 'tests': int(count.group(1)) if count else 0, 'exit_code': result.returncode, 'skipped': 'skipped' in log, 'log': name + '.txt'})
    report = {'suites': reports, 'tests': sum(x['tests'] for x in reports), 'ok': all(x['exit_code'] == 0 and not x['skipped'] for x in reports)}
    child_output(out, 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__': raise SystemExit(main())
