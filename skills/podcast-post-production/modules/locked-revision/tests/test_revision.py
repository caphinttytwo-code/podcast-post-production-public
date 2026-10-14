import importlib.util
import sys
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


retime = load_module("retime_srt", ROOT / "scripts/retime_srt.py")
validate = load_module("validate_locked_revision", ROOT / "scripts/validate_locked_revision.py")


class RetimeTests(unittest.TestCase):
    def test_removes_inside_cue_and_shifts_later_cue(self):
        cues = retime.parse_srt(
            "1\n00:00:00,000 --> 00:00:01,000\n保留\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\n删除\n\n"
            "3\n00:00:02,000 --> 00:00:03,000\n后移\n"
        )
        result, removed = retime.retime(cues, [(1.0, 2.0, "approved")])
        self.assertEqual(removed, [2])
        self.assertEqual(result[1].start, 1.0)
        self.assertEqual([cue.number for cue in result], [1, 2])

    def test_rejects_boundary_crossing_cue(self):
        cues = retime.parse_srt("1\n00:00:00,500 --> 00:00:01,500\n跨界\n")
        with self.assertRaisesRegex(ValueError, "crosses deletion boundary"):
            retime.retime(cues, [(1.0, 2.0, "approved")])


class MetadataTests(unittest.TestCase):
    def test_accepts_locked_layout_and_expected_duration(self):
        source = {"duration": 10.0, "width": 1920, "height": 1080, "frame_rate": "60/1", "audio_layout": [{"channels": 2}]}
        output = {**source, "duration": 8.0}
        manifest = {"deletions": [{"start": 2, "end": 4}], "locked": {"geometry": True, "frame_rate": True, "audio_layout": True}}
        self.assertEqual(validate.validate_metadata(manifest, source, output), [])

    def test_rejects_audio_layout_change(self):
        source = {"duration": 10.0, "width": 1920, "height": 1080, "frame_rate": "60/1", "audio_layout": [{"channels": 2}]}
        output = {**source, "duration": 8.0, "audio_layout": []}
        manifest = {"deletions": [{"start": 2, "end": 4}], "locked": {"audio_layout": True}}
        self.assertIn("locked audio layout or disposition changed", validate.validate_metadata(manifest, source, output))


if __name__ == "__main__":
    unittest.main()
