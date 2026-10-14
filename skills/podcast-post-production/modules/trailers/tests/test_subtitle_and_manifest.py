import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


subtitle_qa = load_module("subtitle_qa", ROOT / "scripts/subtitle_qa.py")
render_batch = load_module("render_batch", ROOT / "scripts/render_batch.py")


class SubtitleQaTests(unittest.TestCase):
    def test_valid_house_style_srt(self):
        report = subtitle_qa.validate_srt(
            "1\n00:00:00,000 --> 00:00:01,000\n这是第一句\n\n"
            "2\n00:00:01,100 --> 00:00:02,000\n这是第二句\n",
            media_duration=2.0,
        )
        self.assertTrue(report["ok"], report)

    def test_rejects_overlap_sequence_punctuation_and_overrun(self):
        report = subtitle_qa.validate_srt(
            "2\n00:00:00,000 --> 00:00:01,200\n嗯 这句话，有标点\n\n"
            "3\n00:00:01,000 --> 00:00:03,000\n第二句\n",
            media_duration=2.5,
        )
        self.assertFalse(report["ok"])
        joined = "\n".join(report["errors"])
        self.assertIn("cue order", joined)
        self.assertIn("overlaps", joined)
        self.assertIn("punctuation", joined)
        self.assertIn("beyond media duration", joined)


class ManifestCompatibilityTests(unittest.TestCase):
    def make_file(self, directory, name):
        path = Path(directory) / name
        path.write_bytes(b"x")
        return path

    def test_legacy_manifest_command_remains_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_file(directory, "source.mp4")
            job = {
                "id": "legacy",
                "source": str(source),
                "output": str(Path(directory) / "out.mp4"),
                "clips": [{"in": "00:00:00.000", "out": "00:00:02.000"}],
            }
            command = render_batch.ffmpeg_command(job, {}, False)
            filters = command[command.index("-filter_complex") + 1]
            self.assertIn("[framed]null[outv]", filters)
            self.assertNotIn("subtitles=", filters)

    def test_optional_subtitle_and_timed_layers_are_single_encode_filters(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_file(directory, "source.mp4")
            image = self.make_file(directory, "pip.png")
            subtitles = Path(directory) / "captions.srt"
            subtitles.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n字幕\n", encoding="utf-8"
            )
            job = {
                "id": "layers",
                "source": str(source),
                "output": str(Path(directory) / "out.mp4"),
                "clips": [{"in": 0, "out": 3}],
                "subtitles": {
                    "path": str(subtitles),
                    "asset_dir": str(Path(directory) / "subtitle-assets"),
                },
                "timed_layers": [{
                    "type": "image",
                    "path": str(image),
                    "start": 0.5,
                    "end": 2.0,
                    "x": 20,
                    "y": 30,
                    "width": 200,
                    "height": 120,
                }],
            }
            command = render_batch.ffmpeg_command(job, {}, False)
            filters = command[command.index("-filter_complex") + 1]
            self.assertIn("scale=1080:608", filters)
            self.assertIn("pad=1080:1920", filters)
            self.assertIn("between(t,0.500,2.000)", filters)
            self.assertIn("between(t,0.000,1.000)", filters)
            self.assertTrue((Path(directory) / "subtitle-assets/cue-00001.png").exists())
            self.assertEqual(command.count("-c:v"), 1)

    def test_video_layer_can_mix_delayed_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_file(directory, "source.mp4")
            layer = self.make_file(directory, "layer.mp4")
            job = {
                "id": "video-layer",
                "source": str(source),
                "output": str(Path(directory) / "out.mp4"),
                "clips": [{"in": 0, "out": 3}],
                "timed_layers": [{
                    "type": "video",
                    "path": str(layer),
                    "start": 0.75,
                    "end": 2.25,
                    "x": 10,
                    "y": 20,
                    "width": 320,
                    "height": 180,
                    "mix_audio": True,
                    "audio_gain": 0.25,
                }],
            }
            command = render_batch.ffmpeg_command(job, {}, False)
            filters = command[command.index("-filter_complex") + 1]
            self.assertIn("adelay=750|750", filters)
            self.assertIn("volume=0.250000", filters)
            self.assertIn("amix=inputs=2:duration=first", filters)


if __name__ == "__main__":
    unittest.main()
