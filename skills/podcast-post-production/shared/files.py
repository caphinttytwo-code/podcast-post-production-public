"""Current file identity and whole-package evidence protection."""
from pathlib import Path
import hashlib


def package_root(anchor=None):
    location = Path(anchor or __file__).resolve()
    for parent in location.parents:
        if (parent / 'SKILL.md').is_file():
            return parent
    raise RuntimeError('Cannot locate podcast-post-production package root')


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def outside_package(path):
    original = Path(path).expanduser()
    if original.is_symlink():
        raise ValueError('Project output must not be a symbolic link')
    resolved = original.resolve()
    root = package_root()
    if resolved == root or root in resolved.parents:
        raise ValueError('Project output must be outside the entire Skill package; use the episode workspace')
    # Validate the resolved target without changing the caller's path spelling.
    return original


def file_identity(path):
    resolved = Path(path).expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ValueError('Expected a regular file')
    before = resolved.stat()
    digest = sha256(resolved)
    after = resolved.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise RuntimeError('File changed while hashing')
    return {'path': str(resolved), 'size_bytes': after.st_size, 'sha256': digest}


def protect_output_args(args):
    """Check known project-output options without treating inputs as outputs."""
    output_names = ('output', 'also_output', 'output_dir', 'json_out', 'report',
                    'baseline_transcript_out', 'reference_transcript_out', 'project_root')
    inputs = []
    for name, value in vars(args).items():
        if name in output_names or name == 'output_prefix': continue
        if isinstance(value, Path): inputs.append(value)
        elif isinstance(value, list): inputs.extend(item for item in value if isinstance(item, Path))
    for name in output_names:
        value = getattr(args, name, None)
        if value is not None:
            from .guards import guard_path
            guard_path(value, *inputs)
            distinct_output(value, *inputs)
            for other in output_names:
                other_value = getattr(args, other, None)
                if other != name and other_value is not None: distinct_output(value, other_value)


def distinct_output(output, *inputs):
    """A force option cannot grant permission to overwrite source evidence."""
    destination = Path(output).expanduser().resolve()
    for value in inputs:
        source = Path(value).expanduser().resolve()
        if destination == source or (destination.exists() and source.exists() and destination.samefile(source)):
            raise ValueError('Output aliases a protected input file')


def child_output(directory, name, *inputs):
    root = Path(directory).expanduser().resolve()
    value = Path(name)
    if value.is_absolute():
        raise ValueError('Output filename must be relative to its output directory')
    target = (root / value).resolve()
    if target == root or root not in target.parents:
        raise ValueError('Output filename escapes its output directory')
    outside_package(Path(directory) / value)
    distinct_output(target, *inputs)
    return Path(directory) / value
