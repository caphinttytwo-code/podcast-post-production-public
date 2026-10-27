#!/usr/bin/env python3
"""Read this Alpha's identity before loading capability/setup code."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]


def verify_before_import():
    manifest = root / 'package-manifest.json'
    if manifest.is_symlink() or manifest.stat().st_nlink > 1:
        raise ValueError('Unsafe package manifest')
    expected = json.loads(manifest.read_text(encoding='utf-8'))
    files = {}
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if '.git' in rel.parts or path.name == '.DS_Store' or rel.as_posix() == 'package-manifest.json':
            continue
        if path.is_symlink() or path.suffix in ('.pyc', '.pyo'):
            raise ValueError('Unsafe link or executable bytecode in package: ' + rel.as_posix())
        if path.is_file():
            if path.stat().st_nlink > 1:
                raise ValueError('Unsafe hard link in package: ' + rel.as_posix())
            files[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    tree = hashlib.sha256(''.join(f'{files[p]}  {p}\n' for p in sorted(files)).encode('utf-8')).hexdigest()
    if files != expected.get('files') or tree != expected.get('tree_sha256'):
        raise ValueError('Package identity mismatch; stop before importing Skill')


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    try:
        verify_before_import()
        sys.path.insert(0, str(root))
        from shared.setup import main
        raise SystemExit(main())
    except (ValueError, FileNotFoundError, FileExistsError, PermissionError, RuntimeError) as exc:
        print('STOPPED: ' + str(exc), file=sys.stderr)
        raise SystemExit(2)
