#!/usr/bin/env python3
"""Check pinned professional commits and reproducible whole-package adapters."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--upstream-root', type=Path, required=True, help='Contains audio-edit and video-conform Git checkouts')
    args = p.parse_args()
    lock = json.loads((REPO / 'source-lock.json').read_text(encoding='utf-8'))
    for row in lock['renderer_updates'] + lock.get('asr_security_updates', []):
        source = args.upstream_root / row['mode']
        # Different professional files may pin different reviewed commits.
        payload = subprocess.check_output(['git', '-C', str(source), 'show', row['commit'] + ':' + row['script']])
        if hashlib.sha256(payload).hexdigest() != row['source_sha256']:
            raise ValueError('Changed pinned upstream file: ' + row['mode'])
        with tempfile.TemporaryDirectory(prefix='pp-source-adapter-') as tmp:
            root = Path(tmp); path = root / row['script']; path.parent.mkdir(parents=True); path.write_bytes(payload)
            subprocess.run(['git', 'apply', '--check', str(REPO / row['adapter'])], cwd=root, check=True)
            subprocess.run(['git', 'apply', str(REPO / row['adapter'])], cwd=root, check=True)
            adapted = path.read_bytes()
            if hashlib.sha256(adapted).hexdigest() != row['runtime_sha256'] or adapted != (REPO / row['runtime_path']).read_bytes():
                raise ValueError('Runtime adapter mismatch: ' + row['mode'])
        print(row['mode'] + ': pinned source and adapter PASS')


if __name__ == '__main__': main()
