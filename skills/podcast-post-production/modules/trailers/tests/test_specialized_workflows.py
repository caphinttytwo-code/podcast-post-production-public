import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


build_srt = load_module("build_srt_from_timestamps", ROOT / "scripts/build_srt_from_timestamps.py")
review = load_module("render_review_proxies", ROOT / "scripts/render_review_proxies.py")
headframes = load_module("extract_headframe_candidates", ROOT / "scripts/extract_headframe_candidates.py")


class TimestampSubtitleTests(unittest.TestCase):
    def test_aligns_proofread_cues_and_reports_manual_review(self):
        records = [
            {"text": "第一句话", "start_ms": 100, "end_ms": 900},
            {"text": "第二句话", "start_ms": 1000, "end_ms": 1900},
        ]
        cues = [
            {"display": "第一句话", "flat": "第一句话"},
            {"display": "第二句话", "flat": "第二句话"},
        ]
        srt, report = build_srt.build(records, cues, 2000)
        self.assertIn("00:00:00,060 -->", srt)
        self.assertEqual(report["cue_count"], 2)
        self.assertTrue(report["requires_human_review"])

    def test_rejects_oversized_visual_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cues.txt"
            path.write_text("一" * 17 + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exceeds 16"):
                build_srt.load_cues(path)


class ReviewProxyTests(unittest.TestCase):
    def test_recursive_discovery_excludes_review_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "episode"
            source.mkdir()
            (source / "clip.mp4").write_bytes(b"video")
            (source / "clip.srt").write_text("subtitle", encoding="utf-8")
            for excluded in ("Delete", "Review"):
                folder = root / excluded
                folder.mkdir()
                (folder / "ignored.mp4").write_bytes(b"video")
                (folder / "ignored.srt").write_text("subtitle", encoding="utf-8")
            config = {"root": str(root), "output_dir": str(root / "Review")}
            items = review.discover(config, root)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["output"].name, "clip - Review.mp4")
            self.assertEqual(items[0]["output"].parent, root / "Review" / "episode")

    def test_command_preserves_optional_audio_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = {"video": root / "a.mp4", "srt": root / "a.srt"}
            config = {"_base": str(root), "timecode": False}
            command = review.command_for(item, config, root / ".a.tmp.mp4")
            mappings = [command[index + 1] for index, value in enumerate(command[:-1]) if value == "-map"]
            self.assertEqual(mappings, ["0:v:0", "0:a?"])
            self.assertIn("-c:a", command)
            self.assertEqual(command[command.index("-c:a") + 1], "copy")

    def test_duration_and_audio_validation(self):
        source = {"duration": 2.0, "audio_tracks": 3}
        output = {"duration": 2.02, "audio_tracks": 3, "width": 1280, "height": 720}
        self.assertEqual(review.validate_output(source, output, {}), [])
        output["audio_tracks"] = 1
        self.assertTrue(any("audio track" in item for item in review.validate_output(source, output, {})))


class HeadframeTests(unittest.TestCase):
    def test_expands_windows_deterministically(self):
        candidates = headframes.expand_candidates({
            "id": "clip", "windows": [{"start": 10, "end": 14, "count": 3}]
        })
        self.assertEqual([item["time"] for item in candidates], [11.0, 12.0, 13.0])

    def test_preview_contains_full_image_without_crop(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "wide.png"
            Image.new("RGB", (400, 100), "red").save(source)
            preview = headframes.contain_preview(source, (200, 200), (0, 0, 0))
            self.assertEqual(preview.size, (200, 200))
            self.assertEqual(preview.getpixel((100, 100)), (255, 0, 0))
            self.assertEqual(preview.getpixel((100, 10)), (0, 0, 0))

    def test_safe_name_blocks_path_components(self):
        self.assertEqual(headframes.safe_name("../unsafe/name"), "unsafe-name")


if __name__ == "__main__":
    unittest.main()
