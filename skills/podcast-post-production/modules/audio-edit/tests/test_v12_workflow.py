import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage = load_module("build_stage_transcript", ROOT / "scripts/build_stage_transcript.py")
renderer = load_module("render_podcast_edl", ROOT / "scripts/render_podcast_edl.py")


def source_transcript():
    return {
        "provider": "StepFun",
        "model": "stepaudio-2.5-asr",
        "chunks": [
            {
                "chunk": "chunk-001.mp3",
                "offset_ms": 0,
                "events": [
                    {
                        "type": "transcript.text.delta",
                        "delta": "我先说明。",
                        "start_time": 0,
                        "end_time": 500,
                    },
                    {
                        "type": "transcript.text.delta",
                        "delta": "呃",
                        "start_time": 600,
                        "end_time": 800,
                    },
                    {
                        "type": "transcript.text.delta",
                        "delta": "然后",
                        "start_time": 1000,
                        "end_time": 1300,
                    },
                ],
            },
            {
                "chunk": "chunk-002.mp3",
                "offset_ms": 1400,
                "events": [
                    {
                        "type": "transcript.text.delta",
                        "delta": "解释结论。",
                        "start_time": 100,
                        "end_time": 400,
                    }
                ],
            },
        ],
    }


def v3_edl(cuts=None, candidates=None):
    return {
        "version": 3,
        "branch": "casual-non-rigorous",
        "transcript_basis": {
            "source": "work/transcript/raw-transcript.json",
            "mechanical": "work/transcript/mechanical-v01.json",
            "semantic_based_on": "mechanical",
        },
        "crossfade_seconds": 0.02,
        "delivery_formats": ["mp3"],
        "cuts": cuts or [],
        "review_candidates": candidates or [],
        "manual_treatments": [],
    }


def approved_cut(start, end, editorial_pass="mechanical", category="filler"):
    return {
        "start": start,
        "end": end,
        "pass": editorial_pass,
        "decision_status": "approved",
        "category": category,
        "reason": "Synthetic approved cut",
        "confidence": "high",
    }


class StageTranscriptTests(unittest.TestCase):
    def test_removes_standalone_filler_and_preserves_contextual_connector(self):
        events = stage.source_events(source_transcript())
        cuts = stage.mechanical_cuts(v3_edl([approved_cut(0.55, 0.85)]))
        retained = stage.retained_events(events, cuts)
        stage.annotate_edit_timing(retained, cuts, 20)
        self.assertEqual("我先说明。然后解释结论。", "".join(e["text"] for e in retained))
        connector = next(event for event in retained if event["text"] == "然后")
        self.assertEqual(1000, connector["source_start_ms"])
        self.assertEqual(680, connector["edit_start_ms"])
        final = next(event for event in retained if event["text"] == "解释结论。")
        self.assertEqual(1500, final["source_start_ms"])

    def test_rejects_partial_event_cut(self):
        events = stage.source_events(source_transcript())
        cuts = stage.mechanical_cuts(v3_edl([approved_cut(0.65, 0.75)]))
        with self.assertRaisesRegex(ValueError, "partially overlaps"):
            stage.retained_events(events, cuts)

    def test_rejects_empty_stage_transcript(self):
        events = stage.source_events(source_transcript())
        cuts = stage.mechanical_cuts(v3_edl([approved_cut(0.0, 2.0)]))
        with self.assertRaisesRegex(ValueError, "remove every"):
            stage.retained_events(events, cuts)

    def test_cli_writes_json_text_and_srt(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            transcript_path = base / "source.json"
            edl_path = base / "edl.json"
            output_prefix = base / "mechanical-v01"
            transcript_path.write_text(
                json.dumps(source_transcript(), ensure_ascii=False), encoding="utf-8"
            )
            edl_path.write_text(
                json.dumps(v3_edl([approved_cut(0.55, 0.85)]), ensure_ascii=False),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "scripts/build_stage_transcript.py"),
                    str(transcript_path),
                    str(edl_path),
                    str(output_prefix),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(output_prefix.with_suffix(".json").exists())
            self.assertNotIn("呃", output_prefix.with_suffix(".txt").read_text(encoding="utf-8"))
            self.assertIn("然后", output_prefix.with_suffix(".srt").read_text(encoding="utf-8"))


class EdlV3Tests(unittest.TestCase):
    def test_keeps_v1_and_v2_compatible(self):
        self.assertEqual(1, renderer.validate_edl({"version": 1}))
        self.assertEqual(
            2,
            renderer.validate_edl({
                "version": 2,
                "cuts": [{
                    "category": "pause-compression",
                    "pause_role": "sentence",
                    "original_gap_seconds": 1.2,
                    "retained_gap_seconds": 0.6,
                    "boundary_evidence": ["asr", "waveform"],
                }],
            }),
        )

    def test_accepts_valid_v3_with_non_executable_candidate(self):
        candidate = {
            "start": 2.0,
            "end": 3.0,
            "pass": "semantic",
            "proposed_action": "remove",
            "category": "macro-repetition",
            "reason": "Synthetic ambiguous repetition",
            "confidence": "medium",
            "risk_flags": ["meaning", "emotion"],
            "status": "pending",
        }
        self.assertEqual(
            3,
            renderer.validate_edl(v3_edl([approved_cut(0.55, 0.85)], [candidate])),
        )

    def test_rejects_unapproved_cut(self):
        cut = approved_cut(0.55, 0.85)
        cut["decision_status"] = "pending"
        with self.assertRaisesRegex(ValueError, "not approved"):
            renderer.validate_edl(v3_edl([cut]))

    def test_v3_pause_requires_listening_evidence(self):
        cut = approved_cut(0.55, 0.85, "pause", "pause-compression")
        cut.update({
            "pause_role": "sentence",
            "original_gap_seconds": 1.2,
            "retained_gap_seconds": 0.6,
            "boundary_evidence": ["asr", "waveform"],
        })
        with self.assertRaisesRegex(ValueError, "listening"):
            renderer.validate_edl(v3_edl([cut]))


class EditorialQaTests(unittest.TestCase):
    def run_qa(self, pending):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            candidate = {
                "start": 2.0,
                "end": 3.0,
                "pass": "semantic",
                "proposed_action": "remove",
                "category": "macro-repetition",
                "reason": "Synthetic candidate",
                "confidence": "medium",
                "risk_flags": ["meaning"],
                "status": "pending",
            }
            edl = v3_edl(candidates=[candidate] if pending else [])
            audio = {
                "technical_passed": True,
                "human_full_length_listen": {
                    "status": "approved",
                    "reviewer": "Synthetic Reviewer",
                    "reviewed_at": "2026-07-16T12:00:00+08:00",
                },
            }
            transcript = {"events": [{"text": "合成成品逐字稿"}]}
            paths = {
                "edl": base / "edl.json",
                "audio": base / "audio.json",
                "transcript": base / "post-edit.json",
                "report": base / "editorial.json",
            }
            paths["edl"].write_text(json.dumps(edl), encoding="utf-8")
            paths["audio"].write_text(json.dumps(audio), encoding="utf-8")
            paths["transcript"].write_text(json.dumps(transcript), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "scripts/editorial_qa.py"),
                    str(paths["edl"]),
                    str(paths["transcript"]),
                    str(paths["audio"]),
                    "--sentence-pass",
                    "--logic-pass",
                    "--pacing-pass",
                    "--persona-pass",
                    "--editorial-reviewer",
                    "Synthetic Editor",
                    "--editorial-reviewed-at",
                    "2026-07-16T12:30:00+08:00",
                    "--json-out",
                    str(paths["report"]),
                    "--report-only",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            return json.loads(paths["report"].read_text(encoding="utf-8"))

    def test_release_ready_requires_all_gates(self):
        report = self.run_qa(pending=False)
        self.assertTrue(report["editorial_passed"])
        self.assertTrue(report["release_ready"])

    def test_pending_candidate_blocks_release(self):
        report = self.run_qa(pending=True)
        self.assertFalse(report["editorial_passed"])
        self.assertFalse(report["release_ready"])

    def test_invalid_candidate_status_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            candidate = {
                "start": 2.0,
                "end": 3.0,
                "pass": "semantic",
                "proposed_action": "remove",
                "category": "macro-repetition",
                "reason": "Synthetic candidate",
                "confidence": "medium",
                "risk_flags": ["meaning"],
                "status": "approved",
            }
            edl_path = base / "edl.json"
            transcript_path = base / "post-edit.json"
            audio_path = base / "audio.json"
            edl_path.write_text(
                json.dumps(v3_edl(candidates=[candidate])), encoding="utf-8"
            )
            transcript_path.write_text(
                json.dumps({"events": [{"text": "合成成品逐字稿"}]}), encoding="utf-8"
            )
            audio_path.write_text(
                json.dumps({
                    "technical_passed": True,
                    "human_full_length_listen": {
                        "status": "approved",
                        "reviewer": "Synthetic Reviewer",
                        "reviewed_at": "2026-07-16T12:00:00+08:00",
                    },
                }),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "scripts/editorial_qa.py"),
                    str(edl_path),
                    str(transcript_path),
                    str(audio_path),
                    "--editorial-reviewer",
                    "Synthetic Editor",
                    "--editorial-reviewed-at",
                    "2026-07-16T12:30:00+08:00",
                    "--report-only",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("pending or rejected", result.stderr)


if __name__ == "__main__":
    unittest.main()
