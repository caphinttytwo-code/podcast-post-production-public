import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "conform_validate_srt", ROOT / "scripts/validate_srt.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["conform_validate_srt"] = module
    spec.loader.exec_module(module)
    return module


validate_srt = load_module()


class LockedFinalSubtitleTests(unittest.TestCase):
    def test_valid_locked_final_srt(self):
        report = validate_srt.validate_srt(
            "1\n00:00:00,100 --> 00:00:01,100\n第一句\n\n"
            "2\n00:00:01,200 --> 00:00:02,900\n第二句\n",
            media_duration=3.0,
        )
        self.assertTrue(report["ok"], report)

    def test_rejects_overlap_zero_duration_overrun_and_bad_term(self):
        report = validate_srt.validate_srt(
            "1\n00:00:00,100 --> 00:00:01,200\n错误名字\n\n"
            "2\n00:00:01,000 --> 00:00:01,000\n第二句。\n\n"
            "3\n00:00:02,000 --> 00:00:04,000\n第三句\n",
            media_duration=3.0,
            bad_terms=(("错误名字", "正确名字"),),
        )
        self.assertFalse(report["ok"])
        joined = "\n".join(report["errors"])
        self.assertIn("bad term", joined)
        self.assertIn("non-positive", joined)
        self.assertIn("overlaps", joined)
        self.assertIn("punctuation", joined)
        self.assertIn("beyond locked final", joined)


if __name__ == "__main__":
    unittest.main()
