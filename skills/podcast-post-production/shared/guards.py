"""Output guards for module functions, including derived files and local review state."""
from pathlib import Path
from .files import outside_package, distinct_output


def guard_path(path, *inputs):
    path = Path(path).expanduser()
    outside_package(path)
    for part in (path, *path.parents):
        system_alias = str(part) in ('/tmp', '/var') and str(part.resolve()) == '/private' + str(part)
        if part.is_symlink() and not system_alias:
            raise ValueError('Output path contains a symbolic link')
    if path.exists() and path.is_file() and path.stat().st_nlink != 1:
        raise ValueError('Output is a hard-linked file')
    distinct_output(path, *[x for x in inputs if x is not None])
    return path


def guard_directory(path, *inputs):
    path = guard_path(path, *inputs)
    resolved = path.resolve()
    for item in inputs:
        if item is not None and Path(item).resolve().is_relative_to(resolved):
            raise ValueError('Output directory contains a protected input')
    if path.exists():
        if not path.is_dir():
            raise ValueError('Expected output directory')
        for child in path.rglob('*'):
            guard_path(child, *inputs)
    return path
