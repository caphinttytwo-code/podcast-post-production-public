"""Observed rc.2 failures and meaningful preflight/renderer boundaries."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared import environment, fonts


def load(name, filename):
    path = ROOT / 'modules/trailers/scripts' / filename
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class SubtitleImageTests(unittest.TestCase):
    def test_single_multiline_cjk_and_latin_produce_nonempty_bounded_images(self):
        from PIL import Image
        renderer = load('rc3_subtitle', 'render_batch.py')
        for text in ('合成测试', '合成测试\n技术验收', 'Audio test', 'Audio test\nsecond line'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as td:
                base = Path(td); source = base / 'source'; source.write_bytes(b'synthetic')
                srt = base / 'input.srt'; srt.write_text('1\n00:00:00,000 --> 00:00:01,000\n' + text + '\n', encoding='utf-8')
                before = srt.read_bytes()
                job = {'id': 'synthetic', 'source': str(source), 'output': str(base/'out.mp4'),
                       'subtitles': {'path': str(srt), 'font': str(fonts.font_path()), 'font_size': 24, 'stroke_width': 3}}
                self.assertEqual(len(renderer.render_subtitle_layers(job, 320, 480, 2)), 1)
                image_path = base / '.out-subtitle-assets/cue-00001.png'
                with Image.open(image_path) as image:
                    self.assertGreater(image.width, 0); self.assertLessEqual(image.width, 320)
                    bbox = image.getbbox(); self.assertIsNotNone(bbox)
                    self.assertGreater(bbox[0], 0); self.assertGreater(bbox[1], 0)
                    self.assertLess(bbox[2], image.width); self.assertLess(bbox[3], image.height)
                self.assertEqual(srt.read_bytes(), before)

    def test_invalid_explicit_font_does_not_use_installed_fallback(self):
        with self.assertRaises(FileNotFoundError): fonts.load_font('/absent/invalid.ttf', 24)

    def test_missing_cjk_glyph_is_rejected(self):
        class Mask:
            size = (2, 2)
            def __bytes__(self): return b'xxxx'
        class MissingFont:
            def getmask(self, char): return Mask()
        with self.assertRaisesRegex(ValueError, 'missing glyphs'):
            fonts.check_glyphs(MissingFont(), '播客')

    def test_no_font_available_fails_explicitly(self):
        with mock.patch.object(fonts, 'candidates', return_value=[]):
            with self.assertRaisesRegex(FileNotFoundError, 'configure'): fonts.font_path()

    def test_windows_font_candidates_use_current_windows_directory(self):
        with tempfile.TemporaryDirectory() as td:
            font = Path(td) / 'Fonts/msyh.ttc'; font.parent.mkdir(); font.write_bytes(b'fixture')
            with mock.patch.dict('os.environ', {'WINDIR': td}):
                self.assertIn(font, fonts.candidates())


class ReviewFontTests(unittest.TestCase):
    def test_subtitle_directory_and_timecode_file_are_separate(self):
        review = load('rc3_review', 'render_review_proxies.py')
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            chain = review.filter_chain({'srt': base/'clip.srt'}, {'_base': td, 'subtitle_font_dir': td,
                        'subtitle_font_name': 'Test CJK', 'timecode_font_file': str(base/'clock.ttf')})
            subtitle, timecode = chain.split(',drawtext=')
            self.assertIn('fontsdir=', subtitle); self.assertNotIn('clock.ttf', subtitle)
            self.assertIn('clock.ttf', timecode)

    def test_invalid_subtitle_directory_does_not_silently_fallback(self):
        review = load('rc3_review_invalid', 'render_review_proxies.py')
        with self.assertRaises(NotADirectoryError):
            review.filter_chain({'srt': Path('clip.srt')}, {'subtitle_font_dir': '/missing-font-directory'})


class EnvironmentTests(unittest.TestCase):
    def test_pure_srt_retime_needs_no_numpy_pillow_or_ffmpeg(self):
        with mock.patch.object(environment, 'tool_info', side_effect=AssertionError('tool lookup')), mock.patch.object(environment.importlib, 'import_module', side_effect=AssertionError('package import')):
            self.assertTrue(environment.inspect('locked-revision', feature='subtitles')['ok'])

    def test_hash_inventory_needs_no_media_tools(self):
        with mock.patch.object(environment, 'tool_info', side_effect=AssertionError('tool lookup')):
            self.assertTrue(environment.inspect('project-audit', feature='inventory')['ok'])

    def test_import_failure_is_blocked_even_if_package_metadata_exists(self):
        with mock.patch.object(environment.importlib, 'import_module', side_effect=ImportError('native import failure')):
            result = environment.inspect('trailers', feature='images', font=fonts.font_path())
        self.assertFalse(result['ok']); self.assertIn('Pillow', result['missing'])

    def test_package_version_below_api_floor_is_blocked(self):
        with mock.patch.object(environment, 'version', return_value='10.0.0'):
            result = environment.inspect('trailers', feature='images', font=fonts.font_path())
        self.assertFalse(result['ok']); self.assertIn('Pillow', result['missing'])

    def test_smoke_is_not_run_when_prerequisites_fail(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(environment, 'tool_info', side_effect=FileNotFoundError('missing')):
            destination = Path(td) / 'new'
            result = environment.inspect('audio-edit', feature='basic', smoke_dir=destination)
            self.assertFalse(destination.exists())
            self.assertEqual(result['checks'][-1]['status'], 'NOT RUN')

    def test_environment_report_cannot_overwrite_package_or_existing_evidence(self):
        script = ROOT / 'scripts/check_environment.py'
        with tempfile.TemporaryDirectory() as td:
            existing = Path(td)/'report.json'; existing.write_text('retained')
            for output in (existing, ROOT/'SKILL.md'):
                before = output.read_bytes()
                result = subprocess.run([sys.executable, '-B', str(script), '--mode', 'project-audit', '--feature', 'inventory', '--report', str(output)], capture_output=True)
                self.assertNotEqual(result.returncode, 0); self.assertEqual(output.read_bytes(), before)

    def test_invalid_feature_for_mode_is_rejected(self):
        with self.assertRaises(ValueError): environment.inspect('audio-edit', feature='images')

    def test_filter_listing_supports_two_and_three_flag_columns(self):
        listing = "Filters:\n .. loudnorm A->A Normalize\n ... subtitles V->V Render\n TS scale V->V Scale\n"
        with mock.patch.object(environment, 'run', return_value=subprocess.CompletedProcess([], 0, listing, '')):
            self.assertEqual(environment.names('synthetic', '-filters'), {'loudnorm', 'subtitles', 'scale'})

    def test_missing_required_filter_is_blocked(self):
        info = {'path': '/synthetic/ffmpeg', 'version': '8.1.1'}
        with mock.patch.object(environment, 'tool_info', return_value=info), mock.patch.object(environment, 'names', side_effect=lambda path, option: {'libmp3lame', 'pcm_s24le'} if option == '-encoders' else set()):
            result = environment.inspect('audio-edit', feature='basic')
        self.assertFalse(result['ok']); self.assertIn('filter:loudnorm', result['missing'])

    def test_mismatched_standard_binary_pair_is_blocked(self):
        def info(path, kind):return {'path': path, 'version': '8.1.1' if kind == 'ffmpeg' else '9.0.0'}
        with mock.patch.object(environment, 'tool_info', side_effect=info), mock.patch.object(environment, 'names', return_value=set()):
            result = environment.inspect('audio-edit', feature='basic')
        self.assertIn('paired tool versions', result['missing'])


if __name__ == '__main__': unittest.main()
