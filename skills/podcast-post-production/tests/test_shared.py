import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared import stepfun_asr
from shared.files import child_output, distinct_output, outside_package, sha256
from shared.project_index import build_index
from shared.subtitles import parse_srt


def load(name, path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SharedAsrTests(unittest.TestCase):
    def fixture(self, root):
        chunks, out = root / 'chunks', root / 'out'
        chunks.mkdir(); out.mkdir()
        events = [{'type': 'transcript.text.delta', 'delta': '测试', 'timestamp': [0, 1000]},
                  {'type': 'transcript.text.done', 'text': '测试'}]
        for n in [1, 2]: (chunks / f'chunk-{n:03d}.mp3').write_bytes(b'synthetic')
        return chunks, out, events

    def invoke(self, chunks, out):
        with mock.patch.object(sys, 'argv', ['asr', str(chunks), str(out)]), mock.patch.object(stepfun_asr, 'duration_ms', return_value=1000), contextlib.redirect_stdout(io.StringIO()):
            stepfun_asr.main()

    def test_complete_cache_requires_neither_credentials_nor_network(self):
        with tempfile.TemporaryDirectory() as td:
            chunks, out, events = self.fixture(Path(td))
            for n in [1, 2]: (out / f'chunk-{n:03d}.json').write_text(json.dumps(events))
            with mock.patch.object(stepfun_asr, 'credential', side_effect=AssertionError('credential access')), mock.patch.object(stepfun_asr, 'transcribe', side_effect=AssertionError('network')):
                self.invoke(chunks, out)
            raw = json.loads((out / 'raw-transcript.json').read_text())
            self.assertEqual(raw['chunks'][0]['events'], events)
            self.assertEqual(raw['chunks'][1]['offset_ms'], 1000)

    def test_partial_failure_preserves_completed_chunk_and_resumes_only_missing(self):
        with tempfile.TemporaryDirectory() as td:
            chunks, out, events = self.fixture(Path(td))
            with mock.patch.object(stepfun_asr, 'credential', return_value='mock-only'), mock.patch.object(stepfun_asr, 'transcribe', side_effect=[events, RuntimeError('mock failed chunk')]):
                with self.assertRaisesRegex(RuntimeError, 'mock failed'):
                    self.invoke(chunks, out)
            cached = sha256(out / 'chunk-001.json')
            self.assertFalse((out / 'chunk-002.json').exists())
            with mock.patch.object(stepfun_asr, 'credential', return_value='mock-only'), mock.patch.object(stepfun_asr, 'transcribe', return_value=events) as call:
                self.invoke(chunks, out)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(call.call_args.args[0].name, 'chunk-002.mp3')
            self.assertEqual(sha256(out / 'chunk-001.json'), cached)

    def test_raw_sse_events_remain_unmodified(self):
        original = [{'type': 'transcript.text.delta', 'delta': '原文', 'custom': {'a': 1}}]
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def __iter__(self): return iter([('data: ' + json.dumps(x) + '\n').encode() for x in original] + [b'data: [DONE]\n'])
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'x.mp3'; p.write_bytes(b'synthetic')
            from argparse import Namespace
            args = Namespace(language='zh', hotword=[], model='mock', format='mp3', channels=1, url='https://example.invalid/asr', timeout=1)
            with mock.patch.object(stepfun_asr.urllib.request, 'build_opener') as opener:
                opener.return_value.open.return_value = Response()
                self.assertEqual(stepfun_asr.transcribe(p, 'mock-only', args), original)

    def test_frozen_asr_cache_outputs_match_both_originals(self):
        frozen = Path(os.environ['PP_FROZEN_SOURCES'])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chunks, candidate, events = self.fixture(root)
            for n in [1, 2]: (candidate / f'chunk-{n:03d}.json').write_text(json.dumps(events))
            with mock.patch.object(stepfun_asr, 'credential', side_effect=AssertionError('credential')), mock.patch.object(stepfun_asr, 'transcribe', side_effect=AssertionError('network')):
                self.invoke(chunks, candidate)
            for mode in ['audio-edit', 'trailers']:
                original = load('asr_baseline_' + mode, frozen / mode / 'scripts/transcribe_stepfun.py')
                out = root / mode; out.mkdir()
                for n in [1, 2]: (out / f'chunk-{n:03d}.json').write_text(json.dumps(events))
                with mock.patch.object(sys, 'argv', ['asr', str(chunks), str(out)]), mock.patch.object(original, 'duration_ms', return_value=1000), mock.patch.object(original, 'credential', return_value='mock-only'), mock.patch.object(original, 'transcribe', side_effect=AssertionError('network')), contextlib.redirect_stdout(io.StringIO()):
                    original.main()
                for name in ['raw-transcript.json', 'raw-transcript.txt', 'raw-transcript.srt']:
                    self.assertEqual((out / name).read_bytes(), (candidate / name).read_bytes())

    def test_derived_asr_outputs_cannot_follow_link_into_package(self):
        with tempfile.TemporaryDirectory() as td:
            chunks, out, events = self.fixture(Path(td))
            (out / 'raw-transcript.json').symlink_to(ROOT / 'SKILL.md')
            with mock.patch.object(stepfun_asr, 'credential', side_effect=AssertionError('credential')):
                with self.assertRaises(ValueError): self.invoke(chunks, out)


class SharedBoundaryTests(unittest.TestCase):
    def test_sample_id_cannot_escape_into_package_before_render(self):
        module = load('sample_guard', ROOT / 'modules/video-conform/scripts/make_approval_sample.py')
        with tempfile.TemporaryDirectory() as td:
            base = Path(td); manifest = base / 'manifest.json'
            cut = {'cut_id': 'CUT-001', 'reference_join_seconds': 2, 'removed_duration': 1}
            manifest.write_text(json.dumps({'audio_strategy': 'reference-audio-continuous', 'source_video': str(base / 'source.mp4'), 'reference_audio': str(base / 'reference.wav'), 'reference_duration_seconds': 5, 'job_id': 'fixture', 'cuts': [cut]}))
            for bad_id in [str(ROOT / 'shared' / 'sample'), '../../escaped']:
                argv = ['sample', str(manifest), '--output-dir', str(base / 'out'), '--sample-id', bad_id, '--pre', '1', '--post', '1']
                with mock.patch.object(sys, 'argv', argv), mock.patch.object(module, 'render_clip', side_effect=AssertionError('should not render')):
                    with self.assertRaises(ValueError): module.main()
            self.assertFalse((base / 'out').exists())

    def test_subtitle_assets_must_stay_outside_package(self):
        module = load('subtitle_asset_guard', ROOT / 'modules/trailers/scripts/render_batch.py')
        with tempfile.TemporaryDirectory() as td:
            base = Path(td); srt = base / 'clip.srt'
            srt.write_text('1\n00:00:00,000 --> 00:00:01,000\n合成测试\n')
            job = {'id': 'fixture', 'source': str(base / 'source.mp4'), 'output': str(base / 'clip.mp4'), 'subtitles': {'path': str(srt), 'asset_dir': str(ROOT / 'shared')}}
            with self.assertRaises(ValueError): module.render_subtitle_layers(job, 320, 480, 2)

    def test_inventory_derived_output_cannot_overwrite_config_or_scanned_file(self):
        script = ROOT / 'modules/project-audit/scripts/inventory_project.py'
        for alias_type in ['symlink', 'hardlink']:
            with tempfile.TemporaryDirectory() as td:
                base = Path(td); project = base / 'project'; project.mkdir()
                (project / 'retained.txt').write_text('retained')
                out = base / 'out'; out.mkdir()
                config = base / 'config.json'
                config.write_text(json.dumps({'roots': [{'id': 'fixture', 'path': str(project)}], 'output_dir': str(out), 'hash_mode': 'all'}))
                before = sha256(config)
                if alias_type == 'symlink': (out / 'inventory.json').symlink_to(config)
                else: os.link(config, out / 'inventory.json')
                result = subprocess.run([sys.executable, str(script), str(config)], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(sha256(config), before)
                self.assertFalse((out / 'inventory.tsv').exists())

    def test_acoustic_work_symlink_is_rejected_before_extraction(self):
        module = load('acoustic_guard', ROOT / 'modules/video-conform/scripts/build_acoustic_edl.py')
        with tempfile.TemporaryDirectory() as td:
            base = Path(td); project = base / 'project'; project.mkdir()
            (project / 'work').symlink_to(ROOT / 'shared', target_is_directory=True)
            source = base / 'source.mp4'; source.write_bytes(b'synthetic source')
            reference = base / 'reference.wav'; reference.write_bytes(b'synthetic reference')
            argv = ['edl', '--source-video', str(source), '--reference-audio', str(reference), '--project-root', str(project)]
            with mock.patch.object(sys, 'argv', argv), mock.patch.object(module, 'extract_pcm', side_effect=AssertionError('should not extract')):
                with self.assertRaises(ValueError): module.main()
            self.assertFalse((project / 'manifests').exists())

    def test_retime_temporary_cannot_replace_original_input(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td); source = base / '.new.srt.tmp'; output = base / 'new.srt'
            source.write_text('1\n00:00:00,000 --> 00:00:01,000\n保留\n')
            edits = base / 'edits.json'; edits.write_text('{"deletions": []}')
            before = sha256(source)
            result = subprocess.run([sys.executable, str(ROOT / 'modules/locked-revision/scripts/retime_srt.py'), '--input', str(source), '--edits', str(edits), '--output', str(output), '--report', str(base / 'report.json')], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Output aliases a protected input', result.stderr)
            self.assertTrue(source.exists()); self.assertEqual(sha256(source), before)
            self.assertFalse(output.exists())

    def test_cleanup_execute_keeps_sources_and_writes_safe_placeholders(self):
        script = ROOT / 'modules/video-conform/scripts/cleanup_conform.py'
        with tempfile.TemporaryDirectory() as td:
            base = Path(td); work = base / 'work/audio'; work.mkdir(parents=True)
            source = base / 'source.mp4'; source.write_bytes(b'source')
            final = base / 'final.mp4'; final.write_bytes(b'final')
            (work / 'cache.wav').write_bytes(b'regenerable dummy')
            result = subprocess.run([sys.executable, str(script), str(base), '--source', str(source), '--final', str(final), '--execute'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(source.read_bytes(), b'source'); self.assertEqual(final.read_bytes(), b'final')
            self.assertFalse((work / 'cache.wav').exists())
            self.assertTrue((base / 'SOURCE_FILES_PLACEHOLDER.md').exists())

    def test_derived_visual_names_cannot_escape_or_alias_assets(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'out'; out.mkdir()
            photo = out / 'photo.png'; photo.write_bytes(b'fixture')
            for name in ['../escaped.png', str(ROOT / 'x.png'), 'photo.png']:
                with self.assertRaises(ValueError): child_output(out, name, photo)

    def test_stage_prefix_outputs_cannot_alias_source_transcript(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); transcript = root / 'source.json'; edl = root / 'edl.json'
            transcript.write_text(json.dumps({'chunks': [{'offset_ms': 0, 'events': [{'type': 'transcript.text.delta', 'delta': '保留', 'start_time': 0, 'end_time': 1000}]}]}))
            edl.write_text(json.dumps({'version': 3, 'transcript_basis': {'semantic_based_on': 'mechanical'}, 'cuts': []}))
            before = sha256(transcript)
            result = subprocess.run([sys.executable, str(ROOT / 'modules/audio-edit/scripts/build_stage_transcript.py'), str(transcript), str(edl), str(root / 'source')], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Output aliases a protected input', result.stderr)
            self.assertEqual(sha256(transcript), before)

    def test_whole_package_and_symlink_alias_outputs_rejected(self):
        for p in [ROOT / 'shared' / 'x.json', ROOT / 'modules' / 'trailers' / 'x.json']:
            with self.assertRaises(ValueError): outside_package(p)
        with tempfile.TemporaryDirectory() as td:
            alias = Path(td) / 'alias'; alias.symlink_to(ROOT, target_is_directory=True)
            with self.assertRaises(ValueError): outside_package(alias / 'x.json')

    def test_force_cannot_alias_inputs_or_hardlinks(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'source.wav'; p.write_bytes(b'synthetic')
            q = Path(td) / 'hardlink.wav'; os.link(p, q)
            for output in [p, q]:
                with self.assertRaises(ValueError): distinct_output(output, p)

    def test_index_checks_identity_timebase_and_does_not_generate_approval(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'source.wav'; p.write_bytes(b'synthetic')
            spec = {'workflow': 'audio-edit', 'module_version': 'fixture', 'inputs': [{'role': 'source', 'path': p.name}], 'artifacts': [{'role': 'master', 'path': p.name, 'timebase': 'final'}]}
            index = build_index(spec, p.parent)
            self.assertFalse(index['approval_generated'])
            self.assertEqual(index['inputs'][0]['sha256'], sha256(p))
            spec['artifacts'][0]['timebase'] = 'guessed'
            with self.assertRaises(ValueError): build_index(spec, p.parent)
            spec['artifacts'][0]['timebase'] = 'final'
            spec['inputs'][0]['sha256'] = '0' * 64
            with self.assertRaises(ValueError): build_index(spec, p.parent)

    def test_cleanup_ignores_external_file_and_directory_links(self):
        script = ROOT / 'modules/video-conform/scripts/cleanup_conform.py'
        with tempfile.TemporaryDirectory() as td:
            base = Path(td); project = base / 'project'; work = project / 'work'; work.mkdir(parents=True)
            source = project / 'source.mp4'; final = project / 'final.mp4'
            source.write_bytes(b'source'); final.write_bytes(b'final')
            external = base / 'external.wav'; external.write_bytes(b'external')
            (work / 'link.wav').symlink_to(external)
            (work / 'external-dir').symlink_to(base, target_is_directory=True)
            result = subprocess.run([sys.executable, str(script), str(project), '--source', str(source), '--final', str(final)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['delete_count'], 0)
            self.assertTrue(external.exists())


class SubtitleCompatibilityTests(unittest.TestCase):
    def test_original_parsing_behavior_and_separate_profiles(self):
        cases = ['', 'bad', '1\n00:00:00,000 --> 00:00:01,000\n啊\n', '2\n00:00:01,000 --> 00:00:02,000\n句子，\n', '1\r\n00:00:00,000 --> 00:00:01,000\r\n正常\r\n']
        frozen = Path(os.environ['PP_FROZEN_SOURCES'])
        for mode, filename in [('video-conform', 'validate_srt.py'), ('trailers', 'subtitle_qa.py')]:
            original = load('baseline_' + mode, frozen / mode / 'scripts' / filename)
            migrated = load('candidate_' + mode, ROOT / 'modules' / mode / 'scripts' / filename)
            for case in cases:
                a, ea = original.parse_srt(case); b, eb = parse_srt(case)
                self.assertEqual([vars(x) for x in a], [vars(x) for x in b]); self.assertEqual(ea, eb)
                expected = original.validate_srt(case, media_duration=2)
                actual = migrated.validate_srt(case, media_duration=2)
                self.assertEqual(expected, {key: actual[key] for key in expected})
                if mode == 'video-conform':
                    self.assertEqual(set(actual) - set(expected), {'profile', 'limits'})
                    self.assertIsNone(actual['profile'])
                    self.assertEqual(actual['limits'], {'max_chars': 16, 'max_lines': None, 'max_screen_chars': None})
                else:
                    self.assertEqual(expected, actual)
        conform = load('profile_conform', ROOT / 'modules/video-conform/scripts/validate_srt.py')
        clips = load('profile_clips', ROOT / 'modules/trailers/scripts/subtitle_qa.py')
        srt = '1\n00:00:00,000 --> 00:00:01,000\n啊\n'
        self.assertTrue(conform.validate_srt(srt, media_duration=2)['ok'])
        self.assertFalse(clips.validate_srt(srt, media_duration=2)['ok'])


class ProbeCompatibilityTests(unittest.TestCase):
    def test_frozen_probe_fields_outputs_and_errors_are_preserved(self):
        frozen = Path(os.environ['PP_FROZEN_SOURCES'])
        payload = {'format': {'duration': '2.000', 'format_name': 'mp4'}, 'streams': [
            {'codec_type': 'video', 'width': 320, 'height': 240, 'avg_frame_rate': '30/1', 'r_frame_rate': '30/1', 'pix_fmt': 'yuv420p'},
            {'codec_type': 'audio', 'sample_rate': '48000', 'channels': 1, 'channel_layout': 'mono', 'disposition': {'default': 1}}]}
        cases = [('audio-edit', 'audio_qa.py', 'probe', False),
                 ('video-conform', 'validate_edl.py', 'probe', False),
                 ('video-conform', 'build_acoustic_edl.py', 'probe_media', False),
                 ('trailers', 'qa_outputs.py', 'probe', False),
                 ('trailers', 'extract_headframe_candidates.py', 'probe', True),
                 ('trailers', 'render_review_proxies.py', 'probe', True),
                 ('locked-revision', 'validate_locked_revision.py', 'probe', True),
                 ('project-audit', 'inventory_project.py', 'probe_media', True)]
        for mode, filename, function, explicit in cases:
            original = load('probe_original_' + mode + filename, frozen / mode / 'scripts' / filename)
            candidate = load('probe_candidate_' + mode + filename, ROOT / 'modules' / mode / 'scripts' / filename)
            args = [Path('fixture.mp4')] + (['ffprobe'] if explicit else [])
            commands, outputs = [], []
            for module in [original, candidate]:
                with mock.patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), '')) as call:
                    outputs.append(getattr(module, function)(*args))
                    commands.append(call.call_args.args[0])
            self.assertEqual(outputs[0], outputs[1], (mode, filename))
            # Order of independent FFprobe options may change; values and selectors may not.
            self.assertEqual(sorted(commands[0]), sorted(commands[1]), (mode, filename))
            failures = []
            def failed_probe(command, **kwargs):
                if kwargs.get('check'):
                    raise subprocess.CalledProcessError(1, command, stderr='synthetic probe failure')
                return subprocess.CompletedProcess(command, 1, '', 'synthetic probe failure')
            for module in [original, candidate]:
                with mock.patch.object(subprocess, 'run', side_effect=failed_probe):
                    try: failures.append(('returned', getattr(module, function)(*args)))
                    except Exception as exc: failures.append((type(exc).__name__, str(exc)))
            self.assertEqual(failures[0], failures[1], (mode, filename))


if __name__ == '__main__': unittest.main()
