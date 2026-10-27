"""Run the actual packaged entrypoints with small, explicitly synthetic inputs."""
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import wave
from .files import sha256, child_output

ROOT = Path(__file__).resolve().parents[1]


def probe(mode, feature, binaries, font, directory):
    directory = Path(directory).resolve()
    logs = []
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1'}
    parents = [str(Path(binaries[k]['path']).parent) for k in ('ffmpeg', 'ffprobe') if binaries.get(k)]
    env['PATH'] = os.pathsep.join(dict.fromkeys(parents + [env.get('PATH', '')]))
    for kind in ('ffmpeg', 'ffprobe'):
        if binaries.get(kind):
            actual = shutil.which(kind, path=env['PATH'])
            if not actual or Path(actual).resolve() != Path(binaries[kind]['path']).resolve():
                raise ValueError('Production PATH differs from selected ' + kind)

    def save(name, data):
        path = child_output(directory, name)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return path
    def run(name, command, expected_exit=0):
        result = subprocess.run([str(x) for x in command], capture_output=True, text=True,
                                encoding='utf-8', errors='replace', env=env, timeout=120)
        child_output(directory, name + '.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        logs.append({'step': name, 'command': [str(x) for x in command], 'exit_code': result.returncode,
                     'expected_exit': expected_exit})
        if result.returncode != expected_exit:
            raise RuntimeError(name + ': ' + result.stderr[-1200:])
        return result
    def script(module, name, *args):
        return [sys.executable, '-B', ROOT / 'modules' / module / 'scripts' / name, *args]
    def ff(name, *args):
        return run(name, [binaries['ffmpeg']['path'], '-v', 'error', *args])
    protected = {}

    if mode == 'editorial-plan':
        source = save('synthetic-plan.json', {
            'schema_version':'1.0', 'revision':'synthetic-only',
            'sources':[{'id':'main','sample_rate':48000,'frames':4800000}],
            'base':{'source_id':'main','start_frame':0,'end_frame':4800000},
            'items':[{'id':'cut','action':'remove','start_frame':480000,'end_frame':2400000,
                      'reason':'Synthetic repetitive passage; no human decision'}],
            'recommended_ids':['cut'], 'choices':{}})
        protected[str(source)] = sha256(source)
        report = directory/'planning-check.json'
        run('planning-budget-and-pending-choices',script(mode,'check_plan.py',source,'--report',report),expected_exit=2)
        data = json.loads(report.read_text())
        if (data['recommendation']['estimated_seconds'] != 60 or
            data['recorded_apply_choices']['estimated_seconds'] != 100 or
            data['pending_recommended_ids'] != ['cut'] or data['executable'] or data['approval_generated']):
            raise RuntimeError('Planning probe manufactured decisions or miscounted duration')
    elif mode == 'audio-edit' and feature in ('paragraph-review','preserve-source','synchronized-multitrack'):
        import importlib.util
        scripts=ROOT/'modules/audio-edit/scripts'
        def module(name):
            sys.path.insert(0,str(scripts))
            spec=importlib.util.spec_from_file_location('probe_'+name,scripts/(name+'.py'));value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
        if feature=='synchronized-multitrack':
            import numpy as np
            pcm=module('preserve_pcm');rng=np.random.default_rng(915);signals=[rng.normal(0,.07,24000) for _ in range(3)]
            project={'version':1,'id':'synthetic','recording_mode':'synchronized-multitrack','tracks':[]}
            for i,x in enumerate(signals+[sum(x*(i+1)/3 for i,x in enumerate(signals))]):
                path=directory/(f't{i}.wav')
                with wave.open(str(path),'wb') as f:f.setparams((1,3,8000,0,'NONE','not compressed'));f.writeframes(pcm.encode(x[:,None]*8388608,3))
                item={'id':f't{i}','path':path.name,'sha256':sha256(path)};protected[str(path)]=sha256(path)
                if i<3:project['tracks'].append(item)
                else:project['reference_mix']=item
            proj=save('project.json',project)
            plan=save('plan.json',{'version':1,'id':'v01','project_sha256':sha256(proj),'edits':[{'id':'cut','type':'delete','start_frame':4000,'end_frame':6000}], 'user_decisions':{'authority':'user','recorded_at':'synthetic-test-only','items':{'cut':{'choice':'delete'}}}})
            run('multitrack-inspect',script(mode,'multitrack.py','inspect',proj))
            run('multitrack-compile',script(mode,'multitrack.py','compile',proj,plan,directory/'compiled.json'))
            run('multitrack-render',script(mode,'multitrack.py','render',proj,plan,directory/'delivery'))
            run('multitrack-verify',script(mode,'multitrack.py','verify',proj,plan,directory/'delivery'))
        else:
            source=directory/'source.wav'
            with wave.open(str(source),'wb') as f:f.setparams((1,2,8000,0,'NONE','not compressed'));f.writeframes(b''.join(struct.pack('<h',int(5000*math.sin(i*.17))) for i in range(24000)))
            protected[str(source)]=sha256(source)
            if feature=='paragraph-review':
                spec=save('review-spec.json',{'version':'synthetic','source_audio':str(source),'items':[{'id':'a','start_ms':0,'end_ms':1000,'text':'合成试听','suggestion':'uncertain'}]})
                run('paragraph-review-build',script(mode,'review.py','build',spec,directory/'review'))
                value=json.loads((directory/'review/state.json').read_text());assert value['revision']==0 and value['items']['a']['decision']=='pending'
            else:
                pcm=module('preserve_pcm');report=pcm.assemble(source,directory/'preserved.wav',{'cuts':[{'start':1,'end':2}],'crossfade_seconds':.02})
                assert all(pcm.verify(source,directory/'preserved.wav',report).values())
                save('preserve-verification.json',report);logs.append({'step':'preserve-api-render-and-sample-verify','exit_code':0})
        if any(sha256(path)!=old for path,old in protected.items()):raise RuntimeError('Protected synthetic input changed')
        return {'steps':logs,'protected_sha256_before':protected,'protected_sha256_after':{p:sha256(p) for p in protected},'human_full_review':'NOT RUN','cloud_calls':0}
    elif mode == 'audio-edit' or mode == 'video-conform' and feature == 'full':
        rate = 48000
        samples = [int(11000 * math.sin(2 * math.pi * (330 + 17 * (i // rate)) * i / rate)) for i in range(4 * rate)]
        raw = b''.join(struct.pack('<h', x) for x in samples)
        source = child_output(directory, 'source.wav')
        with wave.open(str(source), 'wb') as out:
            out.setnchannels(1); out.setsampwidth(2); out.setframerate(rate); out.writeframes(raw)
        protected[str(source)] = sha256(source)
        if mode == 'audio-edit':
            edl = save('edl.json', {'schema_version': 1, 'branch': 'rigorous-explainer',
                                   'delivery_formats': ['wav'], 'cuts': [{'start': 1, 'end': 2}],
                                   'fixture_notice': 'synthetic technical probe; no editorial authorization'})
            output = directory / 'production.wav'
            run('production-audio-render', script(mode, 'render_podcast_edl.py', source, edl, output))
            run('production-audio-qa', script(mode, 'audio_qa.py', output, '--json-out', directory / 'audio-qa.json'))
            ff('production-audio-decode', '-i', output, '-f', 'null', '-')
        else:
            reference = child_output(directory, 'reference.wav')
            with wave.open(str(reference), 'wb') as out:
                out.setnchannels(1); out.setsampwidth(2); out.setframerate(rate)
                out.writeframes(raw[:rate*2] + raw[rate*4:rate*6])
            video = directory / 'source.mp4'
            ff('production-source-video', '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=30:duration=4',
               '-i', source, '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', video)
            protected.update({str(video): sha256(video), str(reference): sha256(reference)})
            segments = []
            for index, source_in in enumerate((0, 2)):
                segments.append({'index': index, 'source_media_in_seconds': source_in, 'reference_duration': 1,
                                 'reference_in': f'00:00:0{index}.000', 'reference_out': f'00:00:0{index+1}.000',
                                 'reference_in_seconds': index, 'reference_out_seconds': index + 1})
            manifest = save('manifest.json', {'job_id': 'alpha-probe', 'audio_strategy': 'reference-audio-continuous',
                                            'source_video': str(video), 'reference_audio': str(reference),
                                            'reference_duration_seconds': 2, 'segments': segments,
                                            'source_timing': {'requires_seek_calibration': False},
                                            'output_spec': {'fps': 30, 'soft_frames': 3}})
            output = directory / 'production.mp4'
            run('production-conform-render', script(mode, 'render_reference_conform.py', manifest, '--output', output, '--preset', 'ultrafast', '--execute'))
            ff('production-conform-decode', '-i', output, '-map', '0', '-f', 'null', '-')
            result = run('production-conform-probe', [binaries['ffprobe']['path'], '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', output])
            data = json.loads(result.stdout)
            video_stream = next(x for x in data['streams'] if x['codec_type'] == 'video')
            if int(video_stream['nb_read_frames']) != 60 or abs(float(data['format']['duration']) - 2) > .08:
                raise RuntimeError('Conform probe frame count or timeline changed')
    elif mode == 'trailers' and feature in ('full', 'images', 'subtitles'):
        if feature == 'images':
            from PIL import Image
            photo = directory / 'photo.png'; Image.new('RGB', (320, 240), '#678c9b').save(photo)
            protected[str(photo)] = sha256(photo)
            cfg = save('visual.json', {'output_dir': str(directory / 'visual'), 'title': [], 'partnership_label': '',
                                     'separator': False, 'photo': {'path': str(photo), 'box': [0, 656, 1080, 608], 'fade_top': 0, 'fade_bottom': 0}})
            run('production-visuals', script(mode, 'build_visuals.py', cfg))
        else:
            srt = directory / 'production.srt'
            srt.write_text('1\n00:00:00,000 --> 00:00:01,000\n合成测试\n多行字幕\n', encoding='utf-8')
            protected[str(srt)] = sha256(srt)
            if feature == 'full':
                source = directory / 'source.mp4'
                ff('production-trailer-source', '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=30:duration=2',
                   '-f', 'lavfi', '-i', 'sine=duration=2', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', source)
                protected[str(source)] = sha256(source)
                batch = save('batch.json', {'defaults': {'preset': 'ultrafast'}, 'jobs': [{
                    'id': 'alpha-probe', 'source': str(source), 'output': str(directory / 'trailer.mp4'),
                    'width': 320, 'height': 480, 'video_height': 180, 'video_y': 150, 'fps': 30,
                    'clips': [{'in': 0, 'out': 1.2}],
                    'subtitles': {'path': str(srt), 'font_size': 20, 'font': font['path']}}]})
                run('production-trailer-render', script(mode, 'render_batch.py', batch))
                run('production-trailer-qa', script(mode, 'qa_outputs.py', batch))
                ff('production-trailer-decode', '-i', directory / 'trailer.mp4', '-map', '0', '-f', 'null', '-')
                frames = save('headframes.json', {'output_dir': str(directory / 'headframes'), 'font_file': font['path'],
                                                 'jobs': [{'id': 'probe', 'video': str(directory / 'trailer.mp4'), 'timestamps': [.2, .8]}]})
                run('production-headframes', script(mode, 'extract_headframe_candidates.py', frames))
            else:
                run('production-subtitle-qa', script(mode, 'subtitle_qa.py', srt))
    elif mode == 'video-conform' and feature == 'subtitles':
        srt = directory / 'source.srt'; srt.write_text('1\n00:00:00,000 --> 00:00:01,000\n合成测试\n', encoding='utf-8')
        protected[str(srt)] = sha256(srt)
        run('production-subtitle-validate', script(mode, 'validate_srt.py', srt, '--media-duration', '1'))
    elif mode == 'locked-revision':
        srt = directory / 'source.srt'; srt.write_text('1\n00:00:00,000 --> 00:00:01,000\n保留\n\n2\n00:00:01,000 --> 00:00:02,000\n删除\n\n3\n00:00:02,000 --> 00:00:04,000\n保留\n', encoding='utf-8')
        protected[str(srt)] = sha256(srt)
        edits = save('edits.json', {'deletions': [{'start': 1, 'end': 2, 'reason': 'synthetic probe'}]})
        run('production-retime', script(mode, 'retime_srt.py', '--input', srt, '--edits', edits, '--output', directory / 'retimed.srt', '--report', directory / 'retime-report.json'))
    elif mode == 'project-audit':
        fixture = directory / 'inventory-fixture'; fixture.mkdir()
        item = fixture / 'retain.txt'; item.write_text('synthetic inventory', encoding='utf-8')
        protected[str(item)] = sha256(item)
        cfg = save('inventory-config.json', {'roots': [{'id': 'probe', 'path': str(fixture)}],
                                            'output_dir': str(directory / 'inventory'), 'hash_mode': 'all'})
        run('production-inventory', script(mode, 'inventory_project.py', cfg))
    if any(sha256(path) != old for path, old in protected.items()):
        raise RuntimeError('Protected synthetic input changed')
    return {'steps': logs, 'protected_sha256_before': protected,
            'protected_sha256_after': {p: sha256(p) for p in protected},
            'scope': 'actual entrypoints with synthetic inputs; not full project/human QA'}
