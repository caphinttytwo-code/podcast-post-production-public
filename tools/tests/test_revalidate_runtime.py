import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills/podcast-post-production/scripts"))
import revalidate_runtime as runtime


class RevalidationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        package = self.root / "package"
        package.mkdir()
        files = {"SKILL.md": hashlib.sha256(b"fixture").hexdigest()}
        (package / "SKILL.md").write_bytes(b"fixture")
        tree = hashlib.sha256(f"{files['SKILL.md']}  SKILL.md\n".encode()).hexdigest()
        manifest = package / "package-manifest.json"
        manifest.write_text(json.dumps({"files": files, "tree_sha256": tree, "version": "fixture"}))
        self.identity = {"version": "fixture", "tree_sha256": tree, "files": 1,
                         "manifest_sha256": runtime.sha(manifest)}
        self.profile = {"version": 1, "macos": "27.2", "python_version": sys.version,
                        "installed_package": str(package), "identity": self.identity}
        self.profile["bound_files"] = []
        for key in runtime.RESOURCES:
            resource = Path(sys.executable).absolute() if key == "python" else self.root / key
            if key != "python":
                resource.write_bytes(key.encode())
            self.profile[key] = str(resource)
            self.profile["bound_files"].append({"path": str(resource), "resolved": str(resource.resolve()),
                                                 "sha256": runtime.sha(resource)})
        self.profile["fingerprint"] = runtime.fingerprint(self.profile, compact=True)
        self.path = self.root / "runtime-profile.json"
        self.original = json.dumps(self.profile).encode()
        self.path.write_bytes(self.original)
        self.work = self.root / "evidence"

    def execute(self, fail=None):
        def capture(command, work, label, env):
            if label == "quick":
                if fail == "quick":
                    return subprocess.CompletedProcess(command, 1, "", "")
                (work / "quick").mkdir()
                (work / "quick/installation-report.json").write_text(json.dumps(
                    {"ok": True, "identity": self.identity,
                     "capabilities": [{"id": "fixture", "status": "PASS"}]}))
                if fail == "concurrent":
                    self.path.write_bytes(self.original + b"\n")
                return subprocess.CompletedProcess(command, 0, "", "")
            if label == "review-probe":
                return subprocess.CompletedProcess(command, 0, '{"streams":[{"codec_type":"audio"},{"codec_type":"video"}]}', "")
            return subprocess.CompletedProcess(command, int(fail == "post"),
                                               self.path.read_text(), "")
        argv = ["test", "--runtime-root", str(self.root), "--work-dir", str(self.work)]
        with patch.object(sys, "argv", argv), patch.object(runtime.platform, "mac_ver", return_value=("27.2.1", (), "")), \
                patch.object(runtime, "capture", side_effect=capture), contextlib.redirect_stdout(io.StringIO()):
            status = runtime.main()
        return status, json.loads((self.work / "revalidation-report.json").read_text())

    def test_os_only_updates_with_backup(self):
        status, result = self.execute()
        self.assertEqual((status, result["status"]), (0, "PASS"))
        self.assertEqual((self.work / "runtime-profile.before.json").read_bytes(), self.original)
        current = json.loads(self.path.read_bytes())
        self.assertEqual(current["macos"], "27.2.1")
        self.assertEqual(current["fingerprint"], runtime.fingerprint(current))

    def test_non_os_resource_change_blocks(self):
        (self.root / "font").write_bytes(b"modified")
        status, result = self.execute()
        self.assertEqual(status, 1)
        self.assertTrue(any("bound file changed" in x for x in result["changes"]))
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_probe_failure_keeps_profile(self):
        self.assertEqual(self.execute("quick")[0], 1)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_concurrent_change_preserved(self):
        status, result = self.execute("concurrent")
        self.assertEqual(status, 1)
        self.assertIn("concurrently", result["error"])
        self.assertEqual(self.path.read_bytes(), self.original + b"\n")

    def test_failed_post_check_rolls_back(self):
        status, result = self.execute("post")
        self.assertEqual(status, 1)
        self.assertEqual(result["rollback"], "RESTORED")
        self.assertEqual(self.path.read_bytes(), self.original)
