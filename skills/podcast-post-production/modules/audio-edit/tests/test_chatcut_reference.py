import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compare_audio_reference.py"


def load_module():
    spec = importlib.util.spec_from_file_location("compare_audio_reference", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ChatCutReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_bidirectional_subtraction_keeps_independent_differences(self):
        baseline_cuts = [
            {"start": 0.0, "end": 2.0},
            {"start": 8.0, "end": 10.0},
        ]
        chatcut_cuts = [
            {"start": 0.0, "end": 3.0},
            {"start": 6.0, "end": 7.0},
        ]
        chatcut_more = self.module.subtract(chatcut_cuts, baseline_cuts)
        baseline_more = self.module.subtract(baseline_cuts, chatcut_cuts)
        self.assertEqual(
            [{"start": 2.0, "end": 3.0}, {"start": 6.0, "end": 7.0}],
            chatcut_more,
        )
        self.assertEqual([{"start": 8.0, "end": 10.0}], baseline_more)

    def test_micro_difference_is_retained_and_marked_uncertain(self):
        intervals = self.module.subtract(
            [{"start": 1.0, "end": 1.2}],
            [],
        )
        findings = self.module.annotate(
            intervals,
            [{"text": "口", "source_start_ms": 1000, "source_end_ms": 1200}],
            include_text=False,
        )
        self.assertEqual(1, len(findings))
        self.assertEqual("micro-edit", findings[0]["difference_type"])
        self.assertTrue(findings[0]["micro_edit"])
        self.assertEqual("uncertain", findings[0]["confidence"])

    def test_differences_below_minimum_are_ignored(self):
        intervals = self.module.subtract(
            [{"start": 1.0, "end": 1.05}],
            [],
        )
        self.assertEqual([], intervals)

    def test_duration_reconciliation_reports_residual(self):
        result = self.module.duration_reconciliation(
            100.0,
            90.0,
            [{"duration": 9.8}],
            [],
        )
        self.assertEqual(10.0, result["observed_reference_shorter_seconds"])
        self.assertEqual(0.2, result["unresolved_residual_seconds"])
        self.assertTrue(result["within_tolerance"])

    def test_align_stops_safely_when_source_is_exhausted(self):
        if self.module.np is None:
            self.skipTest("numpy is unavailable")
        source = self.module.np.ones((10, 4), dtype=self.module.np.float32)
        target = self.module.np.ones((20, 4), dtype=self.module.np.float32)
        result = self.module.align(source, target, 0.5, 1.0)
        self.assertTrue(result["diagnostics"]["source_exhausted_before_target_end"])

    def test_source_mapper_maps_direct_baseline_time(self):
        with tempfile.TemporaryDirectory() as directory:
            edl = Path(directory) / "edl.json"
            edl.write_text(
                json.dumps({
                    "version": 3,
                    "crossfade_seconds": 0.02,
                    "cuts": [{"start": 0.0, "end": 1.0}],
                }),
                encoding="utf-8",
            )
            mapping = self.module.source_mapper(edl, 10.0)
            mapped = mapping(2.0)
            self.assertAlmostEqual(3.0, mapped["seconds"])
            self.assertFalse(mapped["ambiguous_crossfade"])

    def test_read_source_events_accepts_staged_edit_timeline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "staged.json"
            path.write_text(
                json.dumps(
                    {
                        "model": "stepaudio-2.5-asr",
                        "events": [
                            {
                                "text": "测试",
                                "source_start_ms": 5000,
                                "source_end_ms": 5400,
                                "edit_start_ms": 1200,
                                "edit_end_ms": 1600,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            model, events = self.module.read_source_events(
                path,
                prefer_edit_timeline=True,
            )
            self.assertEqual("stepaudio-2.5-asr", model)
            self.assertEqual(
                [{"text": "测试", "source_start_ms": 1200, "source_end_ms": 1600}],
                events,
            )

    def test_sensitive_findings_stay_pending_without_text_by_default(self):
        findings = self.module.annotate(
            [{"start": 1.0, "end": 2.0}],
            [{"text": "但是这不一定成立", "source_start_ms": 1000, "source_end_ms": 2000}],
            include_text=False,
        )
        self.assertEqual("pending", findings[0]["review_status"])
        self.assertIn("negation", findings[0]["sensitive_flags"])
        self.assertIn("qualification", findings[0]["sensitive_flags"])
        self.assertIn("transition", findings[0]["sensitive_flags"])
        self.assertNotIn("source_transcript_excerpt", findings[0])

    def test_rejects_evidence_output_inside_skill(self):
        forbidden = ROOT / "synthetic-chatcut-comparison.json"
        with self.assertRaisesRegex(ValueError, "episode workspace"):
            self.module.require_project_output(forbidden)
        self.assertFalse(forbidden.exists())

    def test_allows_project_workspace_output(self):
        with tempfile.TemporaryDirectory() as directory:
            self.module.require_project_output(Path(directory) / "comparison.json")


if __name__ == "__main__":
    unittest.main()
