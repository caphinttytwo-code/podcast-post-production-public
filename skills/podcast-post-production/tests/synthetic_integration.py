#!/usr/bin/env python3
"""Offline synthetic media verification; no real episode or human approval."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import wave
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.files import outside_package, sha256
from shared.fonts import font_path, load_font

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--review-ffmpeg', default='ffmpeg', help='Explicit capable build for Review burn-in')
    parser.add_argument('--font', type=Path, help='Explicit CJK font for every synthetic text path')
    args = parser.parse_args()
    chosen_font = font_path(args.font)
    chosen_family = load_font(chosen_font, 20).getname()[0]
    work = outside_package(args.work_dir).resolve()
    if work.exists():
        raise FileExistsError('Use a fresh synthetic work directory')
    work.mkdir(parents=True)
    logs = work / 'logs'; logs.mkdir()
    results = []
    report = {'synthetic_only': True, 'cloud_calls': 0, 'paid_calls': 0, 'font_path': str(chosen_font), 'font_sha256': sha256(chosen_font),
              'human_review': 'not_performed', 'release_ready': False, 'steps': results}

    def save(path, obj):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
        return path
    def run(name, command):
        result = subprocess.run([str(x) for x in command], capture_output=True, text=True,
                                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1'})
        (logs / (name + '.txt')).write_text(result.stdout + result.stderr)
        results.append({'step': name, 'exit_code': result.returncode, 'log': 'logs/' + name + '.txt'})
        save(work / 'integration-summary.json', report)
        if result.returncode:
            raise RuntimeError(name + ': ' + result.stderr[-1000:])
        return result
    def tool(mode, name, *args):
        return [sys.executable, ROOT / 'modules' / mode / 'scripts' / name, *args]
    def ff(name, *args):
        return run(name, ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *args])
    def wav(path, samples, rate=48000):
        with wave.open(str(path), 'wb') as out:
            out.setnchannels(1); out.setsampwidth(2); out.setframerate(rate)
            out.writeframes((np.clip(samples, -1, 1) * 26000).astype('<i2').tobytes())
    def probe(path):
        return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)], text=True))

    try:
        # Deterministic nonrepeating spectral content makes acoustic matching observable.
        rate = 48000; duration = 24; t = np.arange(rate * duration) / rate
        rng = np.random.default_rng(20261008)
        freqs = rng.uniform(140, 850, duration * 5)
        f = freqs[np.minimum((t * 5).astype(int), len(freqs) - 1)]
        phase = np.cumsum(2 * np.pi * f / rate)
        audio = .24 * (np.sin(phase) + .35 * np.sin(phase * 2.17)) * (.65 + .35 * np.sin(t * 1.9) ** 2)
        source_wav = work / 'source.wav'; wav(source_wav, audio)
        reference = work / 'reference.wav'; wav(reference, np.concatenate([audio[:8*rate], audio[12*rate:20*rate]]))
        source_video = work / 'source.mp4'
        ff('source-video', '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=30:duration=24', '-i', source_wav,
           '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-shortest', source_video)
        protected = {str(p): sha256(p) for p in [source_wav, source_video, reference]}
        edl = save(work / 'audio-edl.json', {'schema_version': 1, 'branch': 'rigorous-explainer',
                    'delivery_formats': ['wav'], 'cuts': [{'start': 8, 'end': 12}],
                    'fixture_notice': 'synthetic technical test, not real editorial authorization'})
        mastered = work / 'mastered.wav'
        run('audio-render', tool('audio-edit', 'render_podcast_edl.py', source_wav, edl, mastered))
        run('audio-qa', tool('audio-edit', 'audio_qa.py', mastered, '--json-out', work / 'audio-qa.json'))

        # Actual acoustic EDL, sample, full continuous-reference render and content QA.
        conform_project = work / 'conform'
        run('acoustic-edl', tool('video-conform', 'build_acoustic_edl.py', '--source-video', source_video,
                '--reference-audio', reference, '--project-root', conform_project, '--job-id', 'synthetic'))
        manifest = conform_project / 'manifests/synthetic.json'
        if not manifest.exists():
            matches = list((conform_project / 'manifests').glob('*.json'))
            if len(matches) != 1: raise RuntimeError('Expected one acoustic manifest')
            manifest = matches[0]
        run('conform-sample', tool('video-conform', 'make_approval_sample.py', manifest, '--output-dir', work / 'sample'))
        conformed = work / 'conformed.mp4'
        run('conform-render', tool('video-conform', 'render_reference_conform.py', manifest, '--output', conformed, '--preset', 'ultrafast', '--execute'))
        result = run('conform-qa', tool('video-conform', 'validate_edl.py', manifest, '--output', conformed, '--content-check', '--full-decode'))
        save(work / 'conform-qa.json', json.loads(result.stdout))
        if abs(float(probe(conformed)['format']['duration']) - 16) > .08:
            raise RuntimeError('Conform duration drift')

        # Trailer content is an explicitly specified synthetic fixture, no real story approval.
        subtitles = work / 'clip.srt'
        subtitles.write_text('1\n00:00:00,000 --> 00:00:02,000\n合成测试\n多行字幕\n\n2\n00:00:02,000 --> 00:00:05,000\n技术验收\n')
        clip = work / 'clip.mp4'
        job = {'id': 'synthetic', 'source': str(source_video), 'output': str(clip),
               'width': 320, 'height': 480, 'video_height': 180, 'video_y': 150, 'fps': 30,
               'clips': [{'in': 0, 'out': 3}, {'in': 4, 'out': 7}], 'transition': .1,
               'subtitles': {'path': str(subtitles), 'font_size': 20, 'font': str(chosen_font)}}
        batch = save(work / 'batch.json', {'defaults': {'preset': 'ultrafast'}, 'jobs': [job]})
        run('trailer-render', tool('trailers', 'render_batch.py', batch))
        run('trailer-qa', tool('trailers', 'qa_outputs.py', batch))
        ff('trailer-decode', '-i', clip, '-f', 'null', '-')
        photo = work / 'synthetic-photo.png'
        Image.new('RGB', (320, 240), '#678c9b').save(photo)
        visual_cfg = save(work / 'visual.json', {'output_dir': str(work / 'visual'), 'title': [], 'partnership_label': '', 'separator': False,
                         'photo': {'path': str(photo), 'box': [0, 656, 1080, 608], 'fade_top': 0, 'fade_bottom': 0}})
        run('static-visuals', tool('trailers', 'build_visuals.py', visual_cfg))
        for filename, size in [('frame-preview.png', (1080, 1920)), ('frame-mobile.png', (270, 480)), ('frame-overlay.png', (1080, 1920))]:
            with Image.open(work / 'visual' / filename) as image:
                if image.size != size: raise RuntimeError('Visual dimensions')

        # Review burn-in really encodes with an isolated capable FFmpeg build.
        review = save(work / 'review.json', {'root': str(work), 'output_dir': str(work / 'review'),
                         'items': [{'video': str(clip), 'srt': str(subtitles)}], 'width': 320, 'height': 480,
                         'ffmpeg': args.review_ffmpeg,
                         'timecode_font_file': str(chosen_font), 'subtitle_font_dir': str(chosen_font.parent),
                         'subtitle_font_name': chosen_family})
        run('review-encode', tool('trailers', 'render_review_proxies.py', review))

        # Three-track parent and a timeline-neutral, equally faded three-track deletion.
        parent = work / 'parent-3tracks.mp4'; revised = work / 'revised-3tracks.mp4'
        ff('three-track-parent', '-i', source_video, '-f', 'lavfi', '-i', 'sine=frequency=220:sample_rate=48000:duration=5',
           '-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=48000:duration=5', '-t', '5', '-map', '0:v', '-map', '0:a', '-map', '1:a', '-map', '2:a', '-c:v', 'copy', '-c:a', 'aac', '-disposition:a:0', 'default', '-disposition:a:1', '0', '-disposition:a:2', '0', parent)
        protected[str(parent)] = sha256(parent)
        graph = '[0:v]split=2[v0][v1];[v0]trim=0:1,setpts=PTS-STARTPTS[x0];[v1]trim=2:5,setpts=PTS-STARTPTS[x1];[x0][x1]concat=n=2:v=1:a=0[v]'
        for i in range(3):
            graph += f';[0:a:{i}]asplit=2[a{i}0][a{i}1];[a{i}0]atrim=0:1,asetpts=PTS-STARTPTS,afade=t=out:st=0.985:d=0.015[b{i}0];[a{i}1]atrim=2:5,asetpts=PTS-STARTPTS,afade=t=in:d=0.015[b{i}1];[b{i}0][b{i}1]concat=n=2:v=0:a=1[a{i}]'
        ff('three-track-revision', '-i', parent, '-filter_complex', graph, '-map', '[v]', '-map', '[a0]', '-map', '[a1]', '-map', '[a2]', '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', '-ar', '48000', '-disposition:a:0', 'default', '-disposition:a:1', '0', '-disposition:a:2', '0', revised)
        parent_srt = work / 'parent.srt'
        parent_srt.write_text('1\n00:00:00,000 --> 00:00:01,000\n保留\n\n2\n00:00:01,000 --> 00:00:02,000\n删除\n\n3\n00:00:02,000 --> 00:00:05,000\n保留\n')
        edits = save(work / 'edits.json', {'deletions': [{'start': 1, 'end': 2, 'reason': 'synthetic fixture'}]})
        output_srt = work / 'revised.srt'
        run('locked-subtitles', tool('locked-revision', 'retime_srt.py', '--input', parent_srt, '--edits', edits, '--output', output_srt, '--report', work / 'retime-qa.json'))
        revision = save(work / 'revision.json', {'schema_version': 1, 'id': 'synthetic', 'source': str(parent), 'source_sha256': sha256(parent), 'output': str(revised), 'output_subtitle': str(output_srt), 'deletions': [{'start': 1, 'end': 2}], 'locked': {'geometry': True, 'frame_rate': True, 'audio_layout': True}})
        run('locked-qa', tool('locked-revision', 'validate_locked_revision.py', revision, '--report', work / 'locked-qa.json'))
        ff('locked-decode', '-i', revised, '-map', '0', '-f', 'null', '-')

        # Current-hash backup evidence and inventory must not modify scanned files.
        audit_root = work / 'audit-fixture'; backup_root = work / 'backup-fixture'; audit_root.mkdir(); backup_root.mkdir()
        for folder in [audit_root, backup_root]:
            shutil.copy2(source_wav, folder / 'retain.wav'); shutil.copy2(reference, folder / 'process.wav')
        audit_before = {str(p): sha256(p) for p in audit_root.iterdir()}
        for name, folder in [('source', audit_root), ('backup', backup_root)]:
            cfg = save(work / (name + '-inventory.json'), {'roots': [{'id': 'fixture', 'path': str(folder)}], 'output_dir': str(work / (name + '-audit')), 'rules': {'retain': ['retain.wav'], 'quarantine': ['process.wav']}, 'hash_mode': 'all'})
            run(name + '-inventory', tool('project-audit', 'inventory_project.py', cfg))
        run('backup-check', tool('project-audit', 'verify_backups.py', work / 'source-audit/inventory.json', work / 'backup-audit/inventory.json', '--report', work / 'backup-qa.json'))
        if any(sha256(Path(p)) != h for p, h in {**protected, **audit_before}.items()):
            raise RuntimeError('Protected synthetic inputs changed')

        index_spec = save(work / 'index-spec.json', {'workflow': 'video-conform', 'module_version': '0.1.0-rc.6.1',
                'inputs': [{'role': 'source_video', 'path': str(source_video)}, {'role': 'reference_audio', 'path': str(reference)}],
                'artifacts': [{'role': 'conformed_master', 'path': str(conformed), 'timebase': 'final'}], 'review_refs': []})
        run('project-index', [sys.executable, ROOT / 'scripts/project_index.py', '--spec', index_spec, '--output', work / 'project-index.json'])
        report['protected_inputs_unchanged'] = True
        report['protected_input_sha256_before'] = {**protected, **audit_before}
        report['protected_input_sha256_after'] = {p: sha256(Path(p)) for p in {**protected, **audit_before}}
        report['ok'] = True
        report['ffmpeg'] = shutil.which('ffmpeg'); report['ffprobe'] = shutil.which('ffprobe')
        report['review_ffmpeg'] = str(Path(args.review_ffmpeg).resolve()) if Path(args.review_ffmpeg).exists() else args.review_ffmpeg
        save(work / 'integration-summary.json', report)
        print(json.dumps({'ok': True, 'steps': len(results), 'cloud_calls': 0}))
    except Exception as exc:
        report['ok'] = False; report['error'] = str(exc)
        save(work / 'integration-summary.json', report)
        raise


if __name__ == '__main__': main()
