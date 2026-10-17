#!/usr/bin/env python3
"""Compare retained CLI parameters with bundled, frozen old interfaces."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared.files import outside_package
from shared.package_identity import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen-sources', type=Path, required=True)
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    verify(ROOT)
    out = outside_package(args.report_dir)
    out.mkdir(parents=True, exist_ok=False)
    baseline = json.loads((ROOT / 'tests/resources/cli-interface-baseline.json').read_text(encoding='utf-8'))
    results = []
    for row in baseline['scripts']:
        options, codes, logs = [], [], []
        for role, path in [('old', args.frozen_sources / row['mode'] / row['script']),
                           ('candidate', ROOT / 'modules' / row['mode'] / row['script'])]:
            command = [sys.executable, '-B', str(path), '--help']
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
            name = row['mode'] + '-' + Path(row['script']).stem + '-' + role + '.log'
            (out / name).write_text(result.stdout + result.stderr, encoding='utf-8')
            options.append(set(re.findall(r'--[a-zA-Z][\w-]*', result.stdout)))
            codes.append(result.returncode)
            logs.append({'command': command, 'exit_code': result.returncode, 'log': name})
        approved = {
            ('video-conform','scripts/validate_srt.py'): {'--profile','--max-lines','--max-screen-chars','--numeric-style','--format-exceptions'},
            ('audio-edit','scripts/render_podcast_edl.py'): {'--review-copy'},
            ('audio-edit','scripts/audio_qa.py'): {'--profile','--assembly-map','--source','--edl'},
            ('audio-edit','scripts/editorial_qa.py'): {'--review-records'},
            ('audio-edit','scripts/transcribe_stepfun.py'): {'--manifest','--adopt-legacy-cache','--transcript-role'},
        }
        additions = approved.get((row['mode'],row['script']),set())
        ok = codes == [0, 0] and options[0] == set(row['expected_old_options']) and options[1] == options[0] | additions
        results.append({'case': row['mode'] + '/' + row['script'], 'status': 'PASS' if ok else 'BLOCKED' if any('ModuleNotFoundError' in (out/item['log']).read_text() for item in logs) else 'FAIL', 'runs': logs})
    report = {'items': results, 'ok': all(x['status'] == 'PASS' for x in results)}
    (out / 'results.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'interfaces': len(results), 'ok': report['ok']}))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
