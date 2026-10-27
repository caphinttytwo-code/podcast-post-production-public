"""An evidence index, never an approval generator or an EDL converter."""
from pathlib import Path
from .files import file_identity, outside_package, package_root
from .package_identity import verify
import json

MODES = ('audio-edit', 'video-conform', 'trailers', 'locked-revision', 'project-audit')
TIMEBASES = ('source', 'reference', 'final', 'non-timed')


def build_index(spec, base):
    mode = spec['workflow']
    if mode not in MODES:
        raise ValueError('Unknown workflow')
    if not spec.get('module_version'):
        raise ValueError('Record the selected module version')
    def resolve(value):
        path = Path(value).expanduser()
        return path if path.is_absolute() else Path(base) / path
    def entry(item, artifact=False):
        if not item.get('role'):
            raise ValueError('Each file requires an explicit role')
        identity = file_identity(resolve(item['path']))
        if item.get('sha256') and identity['sha256'] != item['sha256']:
            raise ValueError('File does not match declared hash')
        result = {'role': item['role'], **identity}
        if artifact:
            if item.get('timebase') not in TIMEBASES:
                raise ValueError('Artifact requires explicit source/reference/final/non-timed timebase')
            result['timebase'] = item['timebase']
        return result
    root = package_root()
    identity = verify(root)
    channel = json.loads((root / 'package-manifest.json').read_text(encoding='utf-8'))['channel']
    return {
        'schema_version': '1.0', 'skill_version': identity['version'], 'skill_channel': channel,
        'workflow': mode, 'module_version': spec['module_version'],
        'inputs': [entry(x) for x in spec.get('inputs', [])],
        'artifacts': [entry(x, True) for x in spec.get('artifacts', [])],
        'review_refs': [file_identity(resolve(x)) for x in spec.get('review_refs', [])],
        'approval_generated': False,
    }
