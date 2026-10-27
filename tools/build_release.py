#!/usr/bin/env python3
"""Deterministic complete Beta ZIP; no imports of runtime media dependencies."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / 'skills/podcast-post-production'
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from shared.package_identity import inventory, tree_digest, verify


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--manifest-only', action='store_true')
    args = p.parse_args()
    files = inventory(ROOT)
    data = {'version': '0.2.0-rc.6.3-beta', 'channel': 'beta', 'distribution': 'public-beta',
            'public_distribution_ready': True, 'public_distribution_blockers': [],
            'display_version': '0.2-rc6.3beta', 'license': 'MIT', 'files': files,
            'tree_sha256': tree_digest(files),
            'algorithm': 'sha256 UTF-8 sorted <sha256>  <POSIX relative path> LF; manifest itself excluded',
            'base_rc61_zip_sha256': 'df9231ea213816cc1f356f403eaf89a421c2569882dd9a5a1105cf946d5b3e8e'}
    (ROOT / 'package-manifest.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    identity = verify(ROOT)
    if args.manifest_only:
        print(json.dumps(identity)); return
    out = args.output_dir.resolve()
    if out == ROOT or ROOT in out.parents:
        raise ValueError('Build artifacts must be outside the Skill')
    out.mkdir(parents=True, exist_ok=False)
    archive = out / 'podcast-post-production-v0.2.0-rc.6.3-beta.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as handle:
        for rel in sorted(list(files) + ['package-manifest.json']):
            info = zipfile.ZipInfo('podcast-post-production/' + rel, date_time=(2026, 10, 17, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            handle.writestr(info, (ROOT / rel).read_bytes())
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    release = {**identity, 'archive': archive.name, 'archive_sha256': checksum,
               'channel': 'beta', 'distribution': 'public-beta', 'public_distribution_ready': True, 'release_ready': False, 'human_full_review': 'NOT RUN'}
    (out / 'release.json').write_text(json.dumps(release, indent=2) + '\n', encoding='utf-8')
    (out / 'SHA256SUMS.txt').write_text(checksum + '  ' + archive.name + '\n', encoding='utf-8')
    print(json.dumps(release))


if __name__ == '__main__': main()
