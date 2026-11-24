import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.asr_route import append_ledger, ledger_row, plan
from shared.package_identity import digest


class RouteTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        source = self.root / "source"
        source.write_bytes(b"synthetic source")
        self.spec = {"source": source.name, "source_sha256": digest(source),
                     "mode": "subtitles", "purpose": "primary", "timebase": "locked-v01",
                     "sample_rate": 48000, "frames": 480000,
                     "segments": [{"id": "a", "start_frame": 0, "end_frame": 24000},
                                  {"id": "b", "start_frame": 24000, "end_frame": 48000}],
                     "host_routes": {"primary": {"provider": "bailian-cli", "billing_route": "quota"}},
                     "cli_capability": "supported", "upload_authorized": True}

    def test_reuse_and_only_retry_failed(self):
        planned = plan(self.spec, self.root)
        raw = self.root / "response.json"
        raw.write_text('{"text":"synthetic response"}')
        route = {k: v for k, v in planned["route"].items() if k != "entrypoint"}
        self.spec["cache"] = []
        for segment in self.spec["segments"]:
            self.spec["cache"].append({"id": segment["id"], "binding": {**route, **segment},
                                       "response": raw.name, "response_sha256": digest(raw),
                                       "status": "complete" if segment["id"] == "a" else "failed"})
        planned = plan(self.spec, self.root)
        self.assertEqual([x["action"] for x in planned["segments"]], ["reuse", "retry"])
        self.assertEqual(planned["submitted_seconds"], 0.5)
        self.spec["cache"][1]["status"] = "complete"
        self.spec["upload_authorized"] = False
        self.assertEqual(plan(self.spec, self.root)["status"], "CACHE_HIT")
        raw.write_text("changed")
        self.assertEqual(plan(self.spec, self.root)["status"], "BLOCKED")

    def test_provider_choice_and_native_gap(self):
        self.spec["host_routes"] = {}
        self.assertEqual(plan(self.spec, self.root)["status"], "SELECT_PROVIDER")
        self.spec.update(explicit_route={"provider": "bailian-native", "billing_route": "payg"},
                         cli_capability="missing", cli_gap="word timestamps")
        self.assertEqual(plan(self.spec, self.root)["status"], "BLOCKED")
        self.spec["native_authorized"] = True
        self.assertEqual(plan(self.spec, self.root)["status"], "READY_FOR_AUTHORIZED_HOST")

    def test_review_cumulative_budget_and_unknown_ledger(self):
        self.spec.update(purpose="review", explicit_route={"provider": "stepfun", "billing_route": "payg"},
                         prior_review_submitted_frames=1)
        self.assertEqual(plan(self.spec, self.root)["status"], "BLOCKED")
        self.spec["prior_review_submitted_frames"] = 0
        planned = plan(self.spec, self.root)
        row = ledger_row(planned, {"segment_id": "a", "attempt": 1, "status": "failed",
                                   "timestamp": "2026-11-13T00:00:00Z", "raw": "ignored"})
        result = json.loads(append_ledger(self.root, row).read_text())
        self.assertIsNone(result["actual_cost_cny"])
        self.assertIsNone(result["input_tokens"])
        self.assertNotIn("raw", result)
        self.assertEqual(result["submitted_seconds"], 0.5)

    def complete_cache(self, payload):
        planned = plan(self.spec, self.root)
        raw = self.root / "cached.json"
        raw.write_text(json.dumps(payload))
        route = {k: v for k, v in planned["route"].items() if k != "entrypoint"}
        self.spec["cache"] = [{"id": segment["id"], "binding": {**route, **segment},
                               "response": raw.name, "response_sha256": digest(raw), "status": "complete"}
                              for segment in self.spec["segments"]]
        self.spec["upload_authorized"] = False

    def test_partial_cache_hit_reports_source_coverage_and_missing_timing(self):
        self.complete_cache({"text": "synthetic text"})
        result = plan(self.spec, self.root)
        self.assertEqual(result["status"], "CACHE_HIT")
        self.assertEqual(result["cached_coverage"]["covered_seconds"], 1)
        self.assertEqual(result["cached_coverage"]["source_seconds"], 10)
        self.assertFalse(result["cached_coverage"]["covers_source"])
        self.assertEqual(result["cached_coverage"]["ranges_frames"], [[0, 48000]])
        self.assertEqual([s["timestamp_evidence"] for s in result["segments"]], ["MISSING"] * 2)
        self.assertEqual(result["subtitle_readiness"], "NEEDS_TIMING_VALIDATION")
        self.assertEqual(result["planned_submission_seconds"], 0)
        self.assertEqual(result["actual_submission_seconds"], 0)

    def test_overlapping_cache_coverage_counts_union(self):
        self.spec["segments"] = [{"id": "a", "start_frame": 0, "end_frame": 48000},
                                 {"id": "b", "start_frame": 24000, "end_frame": 72000}]
        self.complete_cache({"words": [{"text": "synthetic", "start": 0, "end": 1}]})
        result = plan(self.spec, self.root)
        self.assertEqual(result["cached_coverage"]["covered_frames"], 72000)
        self.assertEqual(result["cached_coverage"]["covered_seconds"], 1.5)
        self.assertEqual([s["timestamp_evidence"] for s in result["segments"]], ["PRESENT_UNVERIFIED"] * 2)
        self.assertEqual(result["subtitle_readiness"], "NEEDS_TIMING_VALIDATION")

    def test_unknown_response_format_does_not_claim_missing_or_usable_timing(self):
        self.complete_cache({"result": {"sentences": [{"text": "synthetic", "begin_time": 0}]}})
        result = plan(self.spec, self.root)
        self.assertEqual([s["timestamp_evidence"] for s in result["segments"]], ["UNKNOWN"] * 2)
        self.assertEqual(result["subtitle_readiness"], "NEEDS_TIMING_VALIDATION")

    def test_segment_container_without_bounds_does_not_claim_timestamp_evidence(self):
        self.complete_cache({"segments": [{"text": "no timing"}]})
        result = plan(self.spec, self.root)
        self.assertEqual([s["timestamp_evidence"] for s in result["segments"]], ["UNKNOWN"] * 2)

    def test_blocked_plan_distinguishes_planned_from_actual(self):
        self.spec["upload_authorized"] = False
        result = plan(self.spec, self.root)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["submitted_seconds"], 1)
        self.assertEqual(result["planned_submission_seconds"], 1)
        self.assertEqual(result["actual_submission_seconds"], 0)
        self.assertIsNone(result["estimated_cost_cny"])

    def test_attempt_submission_evidence_and_legacy_plan(self):
        planned = plan(self.spec, self.root)
        # Persisted 0.6.0 plans contain none of the new reporting fields.
        for field in ("planned_submission_seconds", "actual_submission_seconds", "cached_coverage",
                      "requested_coverage", "subtitle_readiness"):
            planned.pop(field)
        attempt = {"segment_id": "a", "attempt": 1, "status": "failed", "timestamp": "2026-11-24T00:00:00Z"}
        self.assertIsNone(ledger_row(planned, attempt)["actual_submission_seconds"])
        self.assertEqual(ledger_row(planned, {**attempt, "submission_confirmed": False})["actual_submission_seconds"], 0)
        self.assertIsNone(ledger_row(planned, {**attempt, "request_id": "synthetic-id"})["actual_submission_seconds"])
        submitted = ledger_row(planned, {**attempt, "request_id": "synthetic-id", "submission_confirmed": True})
        self.assertEqual(submitted["actual_submission_seconds"], 0.5)
        self.assertEqual(submitted["planned_submission_seconds"], 0.5)
        self.assertEqual(submitted["submitted_seconds"], 0.5)
        self.assertIsNone(submitted["actual_cost_cny"])
        with self.assertRaisesRegex(ValueError, "conflicts"):
            ledger_row(planned, {**attempt, "request_id": "synthetic-id", "submission_confirmed": False})

    def test_full_source_coverage_is_independent_of_timing(self):
        self.spec["segments"] = [{"id": "all", "start_frame": 0, "end_frame": 480000}]
        self.complete_cache({"text": "synthetic full source"})
        result = plan(self.spec, self.root)
        self.assertTrue(result["cached_coverage"]["covers_source"])
        self.assertEqual(result["segments"][0]["timestamp_evidence"], "MISSING")
        self.assertEqual(result["subtitle_readiness"], "NEEDS_TIMING_VALIDATION")
