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
