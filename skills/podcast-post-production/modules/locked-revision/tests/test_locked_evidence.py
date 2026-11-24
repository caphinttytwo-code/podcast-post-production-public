import json
import contextlib
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from locked_evidence import check
import hashlib
import validate_locked_revision as validator


class ExactEvidenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")
        self.assertTrue(self.ffmpeg and self.ffprobe, "Exact evidence tests require bound media tools")
        self.source = self.root / "source.nut"
        self.manifest = {"time_map": [{"source_start": 0, "output_start": 0, "duration": 1}],
                         "picture_changes": [{"start": "1/4", "end": "1/2", "region": [0, 0, 8, 8]}]}
        self.make(self.source)

    def make(self, path, edit=None, audio=False, frame=1):
        args = [self.ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=32x32:r=4:d=1",
                "-f", "lavfi", "-i", "sine=f=440:r=8000:d=1",
                "-f", "lavfi", "-i", "sine=f=880:r=8000:d=1",
                "-map", "0:v", "-map", "1:a", "-map", "2:a",
                "-c:v", "ffv1", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le"]
        if audio:
            args += ["-filter:a:0", r"aeval=val(0)+if(eq(n\,100)\,0.1\,0)"]
        if edit:
            args += ["-vf", f"drawbox=x={edit}:y=0:w=8:h=8:color=white:t=fill:enable='eq(n,{frame})'"]
        subprocess.run([*args, str(path)], check=True, capture_output=True)

    def test_region_and_outside_frame(self):
        output = self.root / "within.nut"
        self.make(output, edit="0")
        result = check(self.manifest, self.source, output, self.ffprobe, self.ffmpeg)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["picture"]["compared_frames"], 4)
        output = self.root / "outside.nut"
        self.make(output, edit="16")
        result = check(self.manifest, self.source, output, self.ffprobe, self.ffmpeg)
        self.assertEqual(result["picture"]["mismatch_output_pts"], ["1/4"], result)

    def test_approved_tail_but_not_prior_picture(self):
        self.manifest["picture_changes"] = [{"start": "3/4", "end": 1}]
        output = self.root / "tail.nut"
        self.make(output, edit="16", frame=3)
        result = check(self.manifest, self.source, output, self.ffprobe, self.ffmpeg)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["picture"]["compared_frames"], 3)
        output = self.root / "before-tail.nut"
        self.make(output, edit="16", frame=2)
        result = check(self.manifest, self.source, output, self.ffprobe, self.ffmpeg)
        self.assertEqual(result["picture"]["mismatch_output_pts"], ["1/2"], result)

    def test_locked_audio_independent_tracks(self):
        output = self.root / "changed.nut"
        self.make(output, audio=True)
        result = check(self.manifest, self.source, output, self.ffprobe, self.ffmpeg)
        self.assertEqual(result["status"], "FAIL", result)
        self.assertEqual([track["status"] for track in result["audio"]["tracks"]], ["FAIL", "PASS"], result)
        self.assertEqual(len(result["audio"]["tracks"][0]["mismatch_output_pts"]), 1)

    def test_cli_blocks_missing_map_and_fails_changed_parent(self):
        output = self.root / "copy.nut"
        self.make(output)
        script = Path(__file__).resolve().parents[1] / "scripts/validate_locked_revision.py"
        manifest = self.root / "manifest.json"
        data = {"schema_version": 2, "source": self.source.name, "output": output.name,
                "source_sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(), "expected_output_duration": 0.896}
        for bad_hash, expected in ((False, "BLOCKED"), (True, "FAIL")):
            report = self.root / f"{expected}.json"
            if bad_hash:
                data["source_sha256"] = "0" * 64
            manifest.write_text(json.dumps(data))
            run = subprocess.run([sys.executable, "-B", script, manifest, "--report", report,
                                  "--ffprobe", self.ffprobe, "--ffmpeg", self.ffmpeg], capture_output=True)
            self.assertEqual(json.loads(report.read_bytes())["status"], expected, run.stderr)

    def test_stdout_matches_file_report_without_writes_or_temporary_files(self):
        output = self.root / "within.nut"
        self.make(output, edit="0")
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps({**self.manifest, "schema_version": 2, "source": self.source.name,
                                       "source_sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
                                       "output": output.name}))
        report = self.root / "report.json"
        script = Path(validator.__file__)
        command = [sys.executable, "-B", script, manifest, "--ffmpeg", self.ffmpeg, "--ffprobe", self.ffprobe]
        control = subprocess.run([*command, "--report", report], text=True, capture_output=True)
        self.assertEqual(control.returncode, 0, control.stderr)
        expected = json.loads(report.read_bytes())
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()}
        captured = io.StringIO()
        with (patch.object(sys, "argv", [str(p) for p in [*command[2:], "--stdout"]]),
              patch.object(Path, "write_text", side_effect=AssertionError("Unexpected file write")),
              patch.object(Path, "mkdir", side_effect=AssertionError("Unexpected directory write")),
              patch("tempfile.TemporaryFile", side_effect=AssertionError("Unexpected temporary file")),
              contextlib.redirect_stdout(captured)):
            code = validator.main()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(captured.getvalue()), expected)
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()})

    def test_stdout_cli_preserves_fail_and_blocked_exit_codes(self):
        output = self.root / "outside.nut"
        self.make(output, edit="16")
        manifest = self.root / "manifest.json"
        data = {**self.manifest, "schema_version": 2, "source": self.source.name,
                "source_sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(), "output": output.name}
        command = [sys.executable, "-B", validator.__file__, manifest, "--stdout",
                   "--ffmpeg", self.ffmpeg, "--ffprobe", self.ffprobe]
        for missing_map, expected, code in [(False, "FAIL", 1), (True, "BLOCKED", 2)]:
            if missing_map:
                data.pop("time_map")
            manifest.write_text(json.dumps(data))
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, code, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], expected)
        both = subprocess.run([*command, "--report", self.root / "forbidden.json"], capture_output=True)
        self.assertEqual(both.returncode, 2)
        self.assertFalse((self.root / "forbidden.json").exists())
