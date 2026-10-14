"""Capability checks for local production; no installation or network calls."""
import importlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from .files import child_output, distinct_output, outside_package, sha256
from .fonts import font_path, load_font, check_glyphs


FEATURES = {
    'audio-edit': ('full', 'basic'),
    'video-conform': ('full', 'subtitles', 'review-clips'),
    'trailers': ('full', 'images', 'subtitles', 'review'),
    'locked-revision': ('full', 'subtitles'),
    'project-audit': ('full', 'inventory'),
}
TEXT = '合成测试\n技术验收 Audio 12'


def numeric_version(value):
    match = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', str(value))
    if not match:
        raise ValueError('Unrecognized version: ' + str(value))
    return tuple(int(part or 0) for part in match.groups())


def run(command):
    return subprocess.run([str(x) for x in command], capture_output=True,
                          text=True, encoding='utf-8', errors='replace', timeout=120)


def tool_info(value, kind):
    path = shutil.which(str(value))
    if not path:
        raise FileNotFoundError(kind + ' executable missing: ' + str(value))
    result = run([path, '-version'])
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or kind + ' -version failed')
    match = re.search(kind + r' version (\S+)', result.stdout)
    if not match:
        raise ValueError('Unrecognized ' + kind + ' version output')
    return {'path': str(Path(path).resolve()), 'version': match.group(1),
            'sha256': sha256(path), 'version_output': result.stdout}


def names(ffmpeg, option):
    result = run([ffmpeg, '-hide_banner', option])
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or option + ' inspection failed')
    return {line.split()[1] for line in result.stdout.splitlines()
            if re.match(r'^\s*[A-Z.]{2,6}\s+\S+', line)}


def profile(mode, feature):
    if feature not in FEATURES[mode]:
        raise ValueError(f'{feature} is not a supported feature for {mode}')
    packages, tools, encoders, filters = {}, [], set(), set()
    images = mode == 'trailers' and feature in ('full', 'images', 'subtitles')
    review = mode == 'trailers' and feature == 'review'
    pure = (mode == 'video-conform' and feature == 'subtitles') or (mode == 'locked-revision' and feature == 'subtitles') or (mode == 'project-audit' and feature == 'inventory')
    if images or review:
        packages['Pillow'] = ('PIL', (10, 1, 0))
    if (mode == 'video-conform' and feature == 'full') or (mode == 'audio-edit' and feature == 'full'):
        packages['numpy'] = ('numpy', (1, 24, 0))
    if not pure and not (mode == 'trailers' and feature in ('images', 'subtitles')):
        tools = ['ffprobe'] if mode == 'project-audit' else ['ffmpeg', 'ffprobe']
    if 'ffmpeg' in tools:
        if mode == 'audio-edit':
            encoders = {'libmp3lame', 'pcm_s24le', 'flac'}
            filters = {'atrim', 'asetpts', 'concat', 'loudnorm', 'afade'}
        else:
            encoders = {'libx264', 'aac'}
            filters = {'scale', 'pad', 'fps', 'trim', 'setpts', 'atrim', 'asetpts', 'concat'}
        if mode == 'video-conform' and feature == 'review-clips':
            encoders = {'libmp3lame'}
            filters = {'atrim', 'asetpts', 'aresample'}
        if mode == 'video-conform' and feature == 'full':
            filters |= {'tpad', 'overlay', 'fade', 'aresample'}
        if mode == 'trailers' and not review:
            filters |= {'xfade', 'acrossfade', 'overlay', 'loudnorm', 'amix', 'adelay'}
            if feature == 'full':
                encoders |= {'png'}
        if mode == 'locked-revision':
            filters |= {'split', 'asplit', 'afade'}
        if review:
            filters = {'scale', 'pad', 'subtitles', 'drawtext'}
    return packages, tools, encoders, filters, images, review


def inspect(mode, require_review=False, *, feature='full', ffmpeg='ffmpeg',
            ffprobe='ffprobe', font=None, text=TEXT, smoke_dir=None,
            output_dir=None, allow_review_legacy=False):
    # Old --require-review checks the ordinary module plus Review capabilities.
    packages, tools, encoders, filters, images, review = profile(mode, feature)
    if require_review:
        if 'ffmpeg' not in tools:
            tools = ['ffmpeg', 'ffprobe']
        filters |= {'subtitles', 'drawtext'}
        encoders |= {'libx264', 'aac'}
        review = True
    checks, details, missing = [], {}, []
    def check(label, action, blocked=False):
        try:
            value = action()
            checks.append({'check': label, 'status': 'PASS'})
            return value
        except Exception as exc:
            status = 'BLOCKED' if blocked else 'FAIL'
            checks.append({'check': label, 'status': status, 'error': str(exc)})
            missing.append(label)
            return None
    check('Python>=3.10', lambda: _at_least(sys.version_info[:3], (3, 10, 0)), True)
    for distribution, (module, minimum) in packages.items():
        def package(distribution=distribution, module=module, minimum=minimum):
            importlib.import_module(module)
            value = version(distribution)
            _at_least(numeric_version(value), minimum)
            return value
        details[distribution] = check(distribution, package, True)
    binaries = {}
    for kind in tools:
        binaries[kind] = check(kind, lambda kind=kind: tool_info(ffmpeg if kind == 'ffmpeg' else ffprobe, kind), True)
    for kind, info in binaries.items():
        if info and not (allow_review_legacy and feature == 'review'):
            check(kind + '>=8.1.1', lambda info=info: _at_least(numeric_version(info['version']), (8, 1, 1)), True)
    if all(binaries.get(key) for key in ('ffmpeg', 'ffprobe')) and feature != 'review':
        check('paired tool versions', lambda: _equal(numeric_version(binaries['ffmpeg']['version']), numeric_version(binaries['ffprobe']['version'])), True)
    actual_filters = set()
    if binaries.get('ffmpeg'):
        selected = binaries['ffmpeg']['path']
        actual_filters = check('filter inspection', lambda: names(selected, '-filters'), True) or set()
        actual_encoders = check('encoder inspection', lambda: names(selected, '-encoders'), True) or set()
        for name in sorted(filters):
            check('filter:' + name, lambda name=name: _present(name, actual_filters), True)
        for name in sorted(encoders):
            check('encoder:' + name, lambda name=name: _present(name, actual_encoders), True)
        if mode == 'trailers' and feature == 'full':
            decoders = check('decoder inspection', lambda: names(selected, '-decoders'), True) or set()
            check('decoder:png', lambda: _present('png', decoders), True)
    font_info = None
    if images or font or smoke_dir and review:
        def font_probe():
            path = font_path(font)
            loaded = load_font(path, 24)
            check_glyphs(loaded, text)
            from PIL import Image, ImageDraw
            canvas = Image.new('RGBA', (640, 240))
            ImageDraw.Draw(canvas).multiline_text((8, 8), text, font=loaded, fill='white')
            return {'path': str(path), 'sha256': sha256(path), 'family': loaded.getname()[0],
                    'glyph_mask_check': 'pass', 'visual_review': 'not_performed'}
        font_info = check('font load and glyphs', font_probe, True)
    if output_dir:
        def directory_probe():
            destination = outside_package(output_dir).resolve()
            parent = destination
            while not parent.exists():
                parent = parent.parent
            if not parent.is_dir() or not os.access(parent, os.W_OK):
                raise PermissionError('Output parent is not writable')
            return {'path': str(destination), 'available_bytes': shutil.disk_usage(parent).free,
                    'capacity_for_actual_job': 'not_estimated'}
        details['output_directory'] = check('output directory', directory_probe, True)
    if smoke_dir:
        if missing:
            checks.append({'check': 'synthetic smoke', 'status': 'NOT RUN', 'error': 'Prerequisites did not pass'})
        else:
            details['smoke'] = check('synthetic smoke', lambda: smoke(mode, feature, binaries, font_info, text, smoke_dir, review))
    ok = all(item['status'] == 'PASS' for item in checks)
    return {'mode': mode, 'feature': feature, 'python': sys.executable,
            'python_version': sys.version, 'ffmpeg': binaries.get('ffmpeg', {}).get('path') if binaries.get('ffmpeg') else None,
            'ffprobe': binaries.get('ffprobe', {}).get('path') if binaries.get('ffprobe') else None,
            'binaries': binaries, 'packages': details,
            'font': font_info, 'review_filters': {name: name in actual_filters for name in ('drawtext', 'subtitles')},
            'checks': checks, 'missing': missing, 'ok': ok,
            'status': 'PASS' if ok else 'FAIL' if any(x['status'] == 'FAIL' for x in checks) else 'BLOCKED',
            'synthetic_smoke_requested': bool(smoke_dir), 'human_review': 'not_performed',
            'release_ready': False, 'installation_performed': False}


def _at_least(actual, minimum):
    if actual < minimum:
        raise ValueError(f'Version {actual} is below {minimum}')


def _equal(left, right):
    if left != right:
        raise ValueError(f'FFmpeg/FFprobe versions differ: {left}, {right}')


def _present(name, available):
    if name not in available:
        raise ValueError('Required capability missing: ' + name)


def smoke(mode, feature, binaries, font_info, text, directory, review):
    destination = outside_package(directory)
    if destination.exists():
        raise FileExistsError('Use a fresh smoke directory')
    destination.mkdir(parents=True)
    logs = []
    def execute(label, command):
        result = run(command)
        child_output(destination, label + '.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
        logs.append({'step': label, 'exit_code': result.returncode})
        if result.returncode:
            raise RuntimeError(label + ': ' + result.stderr[-1000:])
        return result
    if font_info:
        from PIL import Image, ImageDraw
        image = Image.new('RGB', (640, 240), '#101010')
        ImageDraw.Draw(image).multiline_text((16, 16), text, font=load_font(font_info['path'], 24), fill='white', stroke_width=2)
        image.save(child_output(destination, 'text-preview.png'))
    if 'ffmpeg' not in binaries:
        from .production_probe import probe
        production = probe(mode, feature, binaries, font_info, destination)
        return {'steps': logs, 'production': production, 'media_encoding': 'not_requested', 'directory': str(destination), 'visual_review': 'not_performed'}
    ffmpeg = binaries['ffmpeg']['path']
    if mode == 'video-conform' and feature == 'review-clips':
        output = child_output(destination, 'context.mp3')
        execute('encode-context', [ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=1', '-ac', '1', '-ar', '24000', '-c:a', 'libmp3lame', output])
        execute('decode-context', [ffmpeg, '-v', 'error', '-i', output, '-f', 'null', '-'])
    elif mode == 'audio-edit' and not review:
        for ext, codec in [('mp3', 'libmp3lame'), ('wav', 'pcm_s24le')]:
            output = child_output(destination, 'smoke.' + ext)
            execute('encode-' + ext, [ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=1', '-af', 'loudnorm', '-c:a', codec, output])
            execute('decode-' + ext, [ffmpeg, '-v', 'error', '-i', output, '-f', 'null', '-'])
    else:
        output = child_output(destination, 'smoke.mp4')
        command = [ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=30:duration=1', '-f', 'lavfi', '-i', 'sine=duration=1']
        if review:
            # Use the production Review filter chain, with separate subtitle and timecode fonts.
            import importlib.util
            module_path = Path(__file__).resolve().parents[1] / 'modules/trailers/scripts/render_review_proxies.py'
            spec = importlib.util.spec_from_file_location('environment_review', module_path)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            srt = child_output(destination, 'smoke.srt'); srt.write_text('1\n00:00:00,000 --> 00:00:01,000\n' + text + '\n', encoding='utf-8')
            config = {'_base': str(destination), 'width': 320, 'height': 240, 'fps': 30,
                      'subtitle_font_name': font_info['family'], 'subtitle_font_dir': str(Path(font_info['path']).parent),
                      'timecode_font_file': font_info['path']}
            command += ['-vf', module.filter_chain({'srt': srt}, config)]
        command += ['-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', output]
        execute('encode-video', command)
        execute('decode-video', [ffmpeg, '-v', 'error', '-i', output, '-map', '0', '-f', 'null', '-'])
        data = json.loads(execute('probe-video', [binaries['ffprobe']['path'], '-v', 'error', '-show_streams', '-show_format', '-of', 'json', output]).stdout)
        if not {'video', 'audio'} <= {stream['codec_type'] for stream in data['streams']}:
            raise RuntimeError('Smoke output is missing video/audio')
    production = None
    if not review:
        from .production_probe import probe
        production = probe(mode, feature, binaries, font_info, destination)
    return {'steps': logs, 'production': production, 'directory': str(destination), 'visual_review': 'not_performed',
            'scope': 'actual production entrypoint smoke; full production QA still required'}
