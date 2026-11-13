import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from revise_pcm import run_revision, verify_revision
from review import build
from shared.files import sha256


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.parent = self.root / "parent.wav"
        with wave.open(str(self.parent), "wb") as out:
            out.setparams((2, 2, 8000, 0, "NONE", ""))
            out.writeframes(b"".join(struct.pack("<hh", i % 1024, -(i % 1024)) for i in range(24000)))
        (self.root / "text.json").write_text("{}")
        spec = self.root / "review-spec.json"
        spec.write_text(json.dumps({"version": "v02", "source_audio": self.parent.name, "items": [
            {"id": key, "start_ms": start, "end_ms": end, "text": "synthetic", "suggestion": "uncertain"}
            for key, start, end in [("K01", 500, 600), ("K02", 1100, 1200), ("K03", 2000, 2100)]]}))
        self.review = self.root / "review"
        with contextlib.redirect_stdout(io.StringIO()):
            build(spec, self.review)
        self.state = self.review / "state.json"
        saved = json.loads(self.state.read_bytes())
        saved["items"]["K01"]["decision"] = "delete"
        saved["items"]["K03"]["decision"] = "delete"
        saved["revision"] = 1
        self.state.write_text(json.dumps(saved))
        self.request = self.root / "revision.json"
        self.data = {"schema_version": 1, "parent_version": "v02", "version": "v03",
                     "parent": self.parent.name, "parent_sha256": sha256(self.parent),
                     "review_dir": self.review.name, "review_state_sha256": sha256(self.state),
                     "transcript_basis": {"source": "text.json", "mechanical": "text.json"},
                     "cuts": [{"id": "K01", "parent_frames": [4000, 4800]}]}
        self.request.write_text(json.dumps(self.data))
        self.output = self.root / "v03"

    def test_selected_edit_and_one_retained_sample_change(self):
        result = run_revision(self.request, self.output)
        self.assertEqual(result["selected"], [{"id": "K01", "parent_frames": [4000, 4800],
                                              "new_join_frames": [3840, 4000]}])
        self.assertEqual(result["pending_review_ids"], ["K02"])
        self.assertEqual(result["approved_unselected_ids"], ["K03"])
        self.assertTrue(all(verify_revision(self.request, self.output).values()))
        wav = self.output / "review.wav"
        with wav.open("r+b") as out:
            out.seek(44 + 100 * 4)
            value = out.read(1)
            out.seek(-1, 1)
            out.write(bytes([value[0] ^ 1]))
        self.assertFalse(verify_revision(self.request, self.output)["retained_samples_equal"])

    def test_changed_parent_and_missing_mapping_are_blocked(self):
        self.data["cuts"][0].pop("parent_frames")
        self.request.write_text(json.dumps(self.data))
        with self.assertRaises(KeyError):
            run_revision(self.request, self.output)
        self.data["cuts"][0]["parent_frames"] = [4000, 4800]
        self.request.write_text(json.dumps(self.data))
        with self.parent.open("ab") as out:
            out.write(b"altered")
        with self.assertRaisesRegex(ValueError, "Parent SHA"):
            run_revision(self.request, self.output)
        self.assertFalse(self.output.exists())

    def test_pending_decision_cannot_execute(self):
        self.data["cuts"] = [{"id": "K02", "parent_frames": [8800, 9600]}]
        self.request.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError, "unapproved"):
            run_revision(self.request, self.output)
