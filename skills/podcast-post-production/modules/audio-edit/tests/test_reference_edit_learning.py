import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPARE = ROOT / "scripts" / "compare_reference_edit.py"
EDITORIAL_QA = ROOT / "scripts" / "editorial_qa.py"


def transcript(events):
    return {
        "provider": "StepFun",
        "model": "stepaudio-2.5-asr",
        "chunks": [{
            "chunk": "synthetic.mp3",
            "offset_ms": 0,
            "events": [
                {
                    "type": "transcript.text.delta",
                    "delta": text,
                    "start_time": start,
                    "end_time": end,
                }
                for text, start, end in events
            ],
        }],
    }


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class ReferenceComparisonTests(unittest.TestCase):
    def run_compare(self, baseline, reference, extra=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        baseline_path = base / "baseline.json"
        reference_path = base / "reference.json"
        output_path = base / "comparison.json"
        write_json(baseline_path, baseline)
        write_json(reference_path, reference)
        command = [
            sys.executable,
            "-B",
            str(COMPARE),
            str(baseline_path),
            str(reference_path),
            "--json-out",
            str(output_path),
        ]
        if extra:
            command.extend(extra(base))
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(output_path.read_text(encoding="utf-8"))

    def test_detects_progressive_rerecord_as_mechanical_candidate(self):
        report = self.run_compare(
            transcript([
                ("开场", 0, 300),
                ("我先说", 500, 900),
                ("我先说明结论", 1000, 2000),
                ("结束", 2200, 2500),
            ]),
            transcript([
                ("开场", 0, 300),
                ("我先说明结论", 500, 1500),
                ("结束", 1700, 2000),
            ]),
        )
        self.assertEqual(1, report["summary"]["content_event_count"])
        event = report["content_events"][0]
        self.assertEqual("mechanical-omission-candidate", event["proposed_classification"])
        self.assertEqual("pending", event["review_status"])
        self.assertFalse(report["privacy"]["contains_transcript_text"])
        self.assertNotIn("deleted_text", event)

    def test_flags_deleted_qualification_for_sensitive_review(self):
        report = self.run_compare(
            transcript([
                ("我们先说明", 0, 900),
                ("也许", 1100, 1400),
                ("也允许继续", 1500, 2300),
                ("下一句", 2500, 2900),
            ]),
            transcript([
                ("我们先说明", 0, 900),
                ("也允许继续", 1100, 1900),
                ("下一句", 2100, 2500),
            ]),
        )
        event = report["content_events"][0]
        self.assertIn("qualification", event["sensitive_flags"])
        self.assertEqual("sensitive-review", event["proposed_classification"])

    def test_separates_independent_pause_compression(self):
        report = self.run_compare(
            transcript([("前句", 0, 400), ("后句", 1400, 1800)]),
            transcript([("前句", 0, 400), ("后句", 700, 1100)]),
        )
        self.assertEqual(0, report["summary"]["content_event_count"])
        self.assertEqual(1, report["summary"]["pause_event_count"])
        self.assertAlmostEqual(0.7, report["pause_events"][0]["estimated_removed_seconds"])

    def test_maps_candidate_boundaries_back_to_source(self):
        def extra(base):
            edl = base / "edl.json"
            write_json(edl, {
                "version": 3,
                "crossfade_seconds": 0.02,
                "cuts": [{"start": 0.0, "end": 1.0}],
            })
            return ["--baseline-edl", str(edl), "--source-duration", "10"]

        report = self.run_compare(
            transcript([
                ("开场", 0, 300),
                ("我先说", 500, 900),
                ("我先说明结论", 1000, 2000),
                ("结束", 2200, 2500),
            ]),
            transcript([
                ("开场", 0, 300),
                ("我先说明结论", 500, 1500),
                ("结束", 1700, 2000),
            ]),
            extra,
        )
        self.assertIn("source_start", report["content_events"][0])
        self.assertGreaterEqual(report["content_events"][0]["source_start"]["seconds"], 1.0)

    def test_rejects_project_evidence_output_inside_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            baseline = base / "baseline.json"
            reference = base / "reference.json"
            write_json(baseline, transcript([("合成文本", 0, 500)]))
            write_json(reference, transcript([("合成文本", 0, 500)]))
            forbidden = ROOT / "synthetic-comparison-output.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(COMPARE),
                    str(baseline),
                    str(reference),
                    "--json-out",
                    str(forbidden),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("episode workspace", result.stderr)
            self.assertFalse(forbidden.exists())


class ReferenceEditorialGateTests(unittest.TestCase):
    def run_editorial_qa(self, status):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            edl = base / "edl.json"
            transcript_path = base / "post-edit.json"
            audio = base / "audio.json"
            comparison = base / "comparison.json"
            output = base / "editorial.json"
            write_json(edl, {
                "version": 3,
                "review_candidates": [],
            })
            write_json(transcript_path, {"events": [{"text": "合成成片转写"}]})
            write_json(audio, {
                "technical_passed": True,
                "human_full_length_listen": {
                    "status": "approved",
                    "reviewer": "Synthetic Reviewer",
                    "reviewed_at": "2026-07-21T12:00:00+08:00",
                },
            })
            write_json(comparison, {
                "schema_version": 1,
                "analysis_type": "human-reference-edit-comparison",
                "content_events": [{
                    "id": "C001",
                    "review_status": status,
                    "sensitive_flags": ["qualification"],
                }],
                "pause_events": [],
            })
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(EDITORIAL_QA),
                    str(edl),
                    str(transcript_path),
                    str(audio),
                    "--reference-comparison",
                    str(comparison),
                    "--sentence-pass",
                    "--logic-pass",
                    "--pacing-pass",
                    "--persona-pass",
                    "--editorial-reviewer",
                    "Synthetic Editor",
                    "--editorial-reviewed-at",
                    "2026-07-21T12:30:00+08:00",
                    "--json-out",
                    str(output),
                    "--report-only",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            return json.loads(output.read_text(encoding="utf-8"))

    def test_pending_reference_finding_blocks_release(self):
        report = self.run_editorial_qa("pending")
        self.assertFalse(report["checks"]["reference_comparison_resolved"])
        self.assertFalse(report["release_ready"])
        self.assertEqual(1, report["reference_comparison"]["sensitive_pending"])

    def test_accepted_reference_finding_allows_other_gates_to_pass(self):
        report = self.run_editorial_qa("accepted")
        self.assertTrue(report["checks"]["reference_comparison_resolved"])
        self.assertTrue(report["release_ready"])


if __name__ == "__main__":
    unittest.main()
