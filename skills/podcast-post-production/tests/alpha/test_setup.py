import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared import setup
from shared.package_identity import verify, extract_fixtures, inventory, tree_digest


class AlphaSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pp-alpha-test-')
        self.base = Path(self.temp.name).resolve()
        self.identity = verify(ROOT)

    def tearDown(self):
        self.assertEqual(verify(ROOT), self.identity)
        self.temp.cleanup()

    def args(self, **changes):
        values = dict(features='video-conform:subtitles', ffmpeg='ffmpeg', ffprobe='ffprobe',
                      review_ffmpeg=None, font=None, work_dir=self.base / 'evidence', test='skip')
        values.update(changes)
        return argparse.Namespace(**values)

    def test_stdlib_capability_without_media_tools(self):
        with patch('shared.environment.shutil.which', return_value=None):
            rows = setup.capability_report([('video-conform', 'subtitles')], self.args())
        self.assertEqual(rows[0]['status'], 'READY')
        self.assertFalse(rows[0]['evidence']['binaries'])

    def test_missing_tools_only_block_dependent_feature(self):
        with patch('shared.environment.shutil.which', return_value=None):
            rows = setup.capability_report([('audio-edit', 'basic'), ('project-audit', 'inventory')], self.args())
        self.assertEqual(rows[0]['status'], 'BLOCKED')
        self.assertEqual(rows[1]['status'], 'READY')

    def test_missing_numpy_only_blocks_full_comparison(self):
        with patch('shared.environment.importlib.import_module', side_effect=ImportError('missing numpy')):
            rows = setup.capability_report([('audio-edit', 'full')], self.args())
        self.assertIn('numpy', rows[0]['missing'])

    def test_invalid_font_blocks_text_only(self):
        rows = setup.capability_report([('trailers', 'images')], self.args(font=self.base / 'missing.ttf'))
        self.assertNotEqual(rows[0]['status'], 'READY')
        self.assertIn('font load and glyphs', rows[0]['missing'])

    def test_api_configuration_not_permission_and_no_key_leak(self):
        with patch.dict(os.environ, {'STEPFUN_API_KEY': 'synthetic-private-key'}, clear=False), \
                patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')), \
                patch('subprocess.check_output', side_effect=AssertionError('Keychain forbidden')):
            services = setup.external_services()
        self.assertTrue(services['new_transcription']['configured_environment_key'])
        self.assertEqual(services['new_transcription']['account_permission'], 'NOT VERIFIED')
        self.assertEqual(services['new_transcription']['price'], 'UNKNOWN')
        self.assertNotIn('synthetic-private-key', json.dumps(services))
        self.assertEqual(services['paid_model_calls'], 0)

    def test_no_key_is_not_local_blocker(self):
        with patch.dict(os.environ, {}, clear=True):
            services = setup.external_services()
        self.assertFalse(services['new_transcription']['configured_environment_key'])
        self.assertFalse(services['local']['model_api_fee'])

    def test_changed_dependency_changes_fingerprint(self):
        rows = setup.capability_report([('video-conform', 'subtitles')], self.args())
        old = setup.fingerprint(rows)
        rows[0]['evidence']['packages']['numpy'] = 'future-version'
        self.assertNotEqual(setup.fingerprint(rows), old)

    def test_output_path_not_part_of_resource_fingerprint(self):
        rows = setup.capability_report([('video-conform', 'subtitles')], self.args())
        old = setup.fingerprint(rows)
        rows[0]['evidence']['packages']['output_directory'] = {'path': 'other-project', 'available_bytes': 1}
        self.assertEqual(setup.fingerprint(rows), old)

    def test_existing_destination_preserved_after_normal_install(self):
        dest = self.base / 'normal/podcast-post-production'
        work = self.base / 'evidence'; work.mkdir()
        setup.install_copy(dest, self.identity, work)
        self.assertEqual(verify(dest), self.identity)
        with self.assertRaises(FileExistsError):
            setup.install_copy(dest, self.identity, work)
        self.assertEqual(verify(dest), self.identity)

    def test_install_inside_candidate_rejected(self):
        with self.assertRaises(ValueError):
            setup.install_copy(ROOT / 'dangerous-install', self.identity, self.base)

    def test_symlink_destination_preserves_target(self):
        target = self.base / 'target'; target.mkdir(); marker = target / 'keep.txt'; marker.write_text('original')
        link = self.base / 'alias'
        try: link.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            if os.name == 'nt': raise RuntimeError('BLOCKED: Windows symlink permission: ' + str(exc))
            raise
        with self.assertRaises(ValueError): setup.install_copy(link, self.identity, self.base / 'evidence')
        self.assertEqual(marker.read_text(), 'original')
        self.assertTrue(link.is_symlink())

    def test_symlink_evidence_path_rejected(self):
        target = self.base / 'target'; target.mkdir()
        alias = self.base / 'alias'
        try: alias.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            if os.name == 'nt': raise RuntimeError('BLOCKED: Windows symlink permission: ' + str(exc))
            raise
        with self.assertRaises(ValueError): setup.prepare_work(alias / 'report')
        self.assertFalse((target / 'report').exists())

    def test_hardlinked_package_rejected(self):
        copy = self.base / 'copy'; shutil.copytree(ROOT, copy)
        source = copy / 'SKILL.md'; backup = self.base / 'source.txt'; shutil.copy2(source, backup)
        source.unlink(); os.link(backup, source)
        with self.assertRaises(ValueError): verify(copy)
        self.assertEqual(backup.read_bytes(), (ROOT / 'SKILL.md').read_bytes())

    def test_interrupted_copy_never_creates_final_destination(self):
        with patch('shared.setup.shutil.copytree', side_effect=OSError('simulated interrupted copy')):
            with self.assertRaises(OSError): setup.install_copy(self.base / 'dest', self.identity, self.base / 'evidence')
        self.assertFalse((self.base / 'dest').exists())

    def test_tamper_rejected_under_optimized_python(self):
        copy = self.base / 'tampered'; shutil.copytree(ROOT, copy)
        (copy / 'shared/setup.py').write_text('raise RuntimeError("SHOULD NEVER IMPORT")\n')
        for flag in ('-B', '-O'):
            result = subprocess.run([sys.executable, flag, copy / 'scripts/setup_skill.py', 'inspect', '--work-dir', self.base / ('work' + flag)],
                                    capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('identity mismatch', result.stderr)
            self.assertNotIn('SHOULD NEVER IMPORT', result.stderr)

    def test_pyc_tampering_rejected_before_import(self):
        copy = self.base / 'tampered'; shutil.copytree(ROOT, copy)
        cache = copy / 'shared/__pycache__'; cache.mkdir(); (cache / 'injected.pyc').write_bytes(b'fake bytecode')
        with self.assertRaises(ValueError): verify(copy)

    def test_fixture_archive_normal_then_traversal_rejected(self):
        normal = self.base / 'normal.zip'
        with zipfile.ZipFile(normal, 'w') as archive: archive.writestr('sources/ok.txt', 'data')
        dest = extract_fixtures(normal, self.base / 'normal')
        self.assertEqual((dest / 'sources/ok.txt').read_text(), 'data')
        danger = self.base / 'danger.zip'
        with zipfile.ZipFile(danger, 'w') as archive: archive.writestr('../keep.txt', 'overwrite')
        with self.assertRaises(ValueError): extract_fixtures(danger, self.base / 'danger')
        self.assertFalse((self.base / 'keep.txt').exists())

    def test_skip_produces_unverified_report(self):
        work = self.base / 'skip-report'
        code = setup.main(['test', '--work-dir', str(work), '--features', 'video-conform:subtitles', '--test', 'skip'])
        report = json.loads((work / 'installation-report.json').read_text())
        self.assertEqual(code, 0)
        self.assertEqual(report['capabilities'][0]['status'], 'READY')
        self.assertFalse(report['installation_performed'])
        self.assertEqual(report['human_full_review'], 'NOT RUN')

    def test_actual_partial_install_and_post_install_report(self):
        work = self.base / 'install-report'; dest = self.base / 'installation/podcast-post-production'
        code = setup.main(['install', '--work-dir', str(work), '--dest', str(dest), '--features', 'video-conform:subtitles', '--test', 'skip'])
        report = json.loads((work / 'installation-report.json').read_text())
        self.assertEqual(code, 0)
        self.assertTrue(report['installation_performed'])
        self.assertEqual(report['post_install_check']['status'], 'PASS')
        self.assertEqual(report['capabilities'][0]['status'], 'READY')
        self.assertEqual(verify(dest), self.identity)

    def test_existing_report_not_overwritten(self):
        work = self.base / 'existing'; work.mkdir(); marker = work / 'original'; marker.write_text('keep')
        with self.assertRaises(FileExistsError): setup.main(['inspect', '--work-dir', str(work), '--features', 'video-conform:subtitles'])
        self.assertEqual(marker.read_text(), 'keep')

    def test_capability_preview_precedes_interactive_test_question(self):
        stream = io.StringIO()
        def answer(prompt):
            self.assertIn('当前状态', stream.getvalue())
            self.assertIn('外部 API 与费用', stream.getvalue())
            self.assertIn('video-conform:subtitles', stream.getvalue())
            return '3'
        with contextlib.redirect_stdout(stream), patch('sys.stdin.isatty', return_value=True), patch('builtins.input', side_effect=answer):
            self.assertEqual(setup.main(['test', '--work-dir', str(self.base / 'interactive'), '--features', 'video-conform:subtitles']), 0)

    def test_complete_failure_is_visible_after_limited_post_install_pass(self):
        normal = setup.capability_report([('project-audit', 'inventory')], self.args())
        normal[0]['status'] = 'PASS'
        def mocked_execute(command, name, directory, env=None):
            if name == 'post-install':
                post = directory / 'post-install'; post.mkdir()
                (post / 'installation-report.json').write_text(json.dumps({'capabilities': normal}))
            return {'group': name, 'status': 'PASS', 'exit_code': 0}
        simulated_groups = [{'group': 'regression', 'status': 'FAIL', 'reason': 'simulated ordinary failure'},
                            {'group': 'package-protection', 'status': 'PASS'}, {'group': 'production-protection', 'status': 'PASS'}]
        work = self.base / 'limited-report'
        with patch.object(setup, 'execute', side_effect=mocked_execute), patch.object(setup, 'full_tests', return_value=simulated_groups):
            code = setup.main(['install', '--work-dir', str(work), '--dest', str(self.base / 'limited-install'),
                               '--features', 'project-audit:inventory', '--test', 'full', '--allow-limited'])
        report = json.loads((work / 'installation-report.json').read_text())
        self.assertEqual(code, 1)
        self.assertEqual(report['capabilities'][0]['status'], 'READY')
        self.assertEqual(report['capabilities'][0]['quick_status'], 'PASS')
        self.assertIn('| regression | FAIL |', (work / 'installation-report.md').read_text())

    def test_missing_png_decoder_is_detected_before_render(self):
        info = {'path': '/synthetic/ffmpeg', 'version': '8.1.1'}
        _, _, encoders, filters, _, _ = setup.environment.profile('trailers', 'full')
        def names(path, option):
            return encoders if option == '-encoders' else filters if option == '-filters' else set()
        with patch.object(setup.environment, 'tool_info', return_value=info), patch.object(setup.environment, 'names', side_effect=names):
            result = setup.environment.inspect('trailers', feature='full')
        self.assertFalse(result['ok'])
        self.assertIn('decoder:png', result['missing'])

    def test_skipped_unittest_never_reports_pass(self):
        result = subprocess.CompletedProcess([], 0, '', 'Ran 2 tests\nOK (skipped=1)\n')
        with patch.object(setup.subprocess, 'run', return_value=result):
            row = setup.execute(['synthetic-command'], 'skipped', self.base)
        self.assertEqual(row['status'], 'BLOCKED')
        self.assertTrue(row['skipped'])

    def test_existing_install_failure_has_final_report(self):
        dest = self.base / 'existing-install'; dest.mkdir()
        marker = dest / 'keep'; marker.write_text('protected')
        work = self.base / 'failure-report'
        code = setup.main(['install', '--work-dir', str(work), '--dest', str(dest),
                           '--features', 'project-audit:inventory', '--test', 'skip'])
        report = json.loads((work / 'installation-report.json').read_text())
        self.assertEqual(code, 2)
        self.assertFalse(report['ok'])
        self.assertFalse(report['installation_performed'])
        self.assertIn('Existing installation is protected', report['installation_error'])
        self.assertEqual(marker.read_text(), 'protected')

    def test_dependency_failure_has_final_report(self):
        work = self.base / 'dependency-failure'
        with patch.object(setup, 'dependency_environment', side_effect=RuntimeError('synthetic pip failure')):
            code = setup.main(['install', '--work-dir', str(work), '--dest', str(self.base / 'new-dest'),
                               '--features', 'project-audit:inventory', '--test', 'skip', '--install-python'])
        report = json.loads((work / 'installation-report.json').read_text())
        self.assertEqual(code, 2)
        self.assertFalse(report['installation_performed'])
        self.assertIn('synthetic pip failure', (work / 'installation-report.md').read_text())

    def test_missing_png_encoder_is_detected_before_headframes(self):
        info = {'path': '/synthetic/ffmpeg', 'version': '8.1.1'}
        _, _, encoders, filters, _, _ = setup.environment.profile('trailers', 'full')
        def names(path, option):
            return encoders - {'png'} if option == '-encoders' else filters if option == '-filters' else {'png'}
        with patch.object(setup.environment, 'tool_info', return_value=info), patch.object(setup.environment, 'names', side_effect=names):
            result = setup.environment.inspect('trailers', feature='full')
        self.assertIn('encoder:png', result['missing'])


if __name__ == '__main__': unittest.main()
