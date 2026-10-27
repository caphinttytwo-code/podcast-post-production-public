"""Standard-library identity gate. Keep this usable before importing the Skill."""
import hashlib
import json
from pathlib import Path
import stat
import zipfile

IGNORED = {'.git', '__pycache__', '.DS_Store'}
MANIFEST = 'package-manifest.json'


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def inventory(root):
    root = Path(root).resolve()
    values = {}
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if path.suffix in ('.pyc', '.pyo'):
            raise ValueError('Executable bytecode must not be carried in the package')
        if any(p in IGNORED for p in rel.parts) or rel.as_posix() == MANIFEST:
            continue
        if path.is_symlink():
            raise ValueError('Package contains a symbolic link: ' + rel.as_posix())
        if path.is_file():
            if path.stat().st_nlink > 1:
                raise ValueError('Package contains a hard-linked file: ' + rel.as_posix())
            values[rel.as_posix()] = digest(path)
    return values


def tree_digest(files):
    lines = ''.join(f'{files[p]}  {p}\n' for p in sorted(files))
    return hashlib.sha256(lines.encode('utf-8')).hexdigest()


def verify(root):
    root = Path(root).resolve(strict=True)
    path = root / MANIFEST
    if path.is_symlink() or path.stat().st_nlink > 1:
        raise ValueError('Identity manifest must be an independent regular file')
    data = json.loads(path.read_text(encoding='utf-8'))
    files = inventory(root)
    if files != data.get('files') or tree_digest(files) != data.get('tree_sha256'):
        changed = sorted(set(files) ^ set(data.get('files', {})) | {
            p for p in files if p in data.get('files', {}) and files[p] != data['files'][p]})
        raise ValueError('Package identity mismatch: ' + ', '.join(changed[:12]))
    entries = [p for p in files if Path(p).name == 'SKILL.md']
    if entries != ['SKILL.md']:
        raise ValueError('Expected exactly one effective SKILL.md entrypoint')
    return {'version': data['version'], 'tree_sha256': data['tree_sha256'],
            'files': len(files), 'manifest_sha256': digest(path)}


def extract_fixtures(archive, destination):
    """Expand bundled data only into a new directory; reject traversal and links."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Use a fresh fixture directory')
    with zipfile.ZipFile(archive) as handle:
        members = handle.infolist()
        seen = set()
        for item in members:
            name = item.filename
            path = Path(name)
            kind = stat.S_IFMT(item.external_attr >> 16)
            if ('\\' in name or ':' in name or path.is_absolute() or
                    any(part in ('..', '') for part in path.parts) or
                    name in seen or kind == stat.S_IFLNK):
                raise ValueError('Unsafe fixture archive member: ' + name)
            seen.add(name)
        destination.mkdir(parents=True, exist_ok=False)
        handle.extractall(destination)
    return destination
