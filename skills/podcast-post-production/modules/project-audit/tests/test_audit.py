import importlib.util
import json
import sys
import tempfile
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


inventory = load_module("inventory_project", ROOT / "scripts/inventory_project.py")
compare = load_module("compare_manifests", ROOT / "scripts/compare_manifests.py")
backups = load_module("verify_backups", ROOT / "scripts/verify_backups.py")


class InventoryTests(unittest.TestCase):
    def test_defaults_unmatched_files_to_pending_and_retain_wins(self):
        self.assertEqual(inventory.classify("delivery/final.txt", {"retain": ["delivery/**"], "quarantine": ["**"]})[0], "retain")
        self.assertEqual(inventory.classify("notes.txt", {})[0], "pending")

    def test_builds_current_hash_inventory_without_mutating_root(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, audit = base / "project", base / "audit"
            source.mkdir()
            (source / "keep.txt").write_text("durable", encoding="utf-8")
            config = {
                "roots": [{"id": "project", "path": str(source)}],
                "output_dir": str(audit), "hash_mode": "all",
                "rules": {"retain": ["keep.txt"]},
            }
            result, result_dir = inventory.build_inventory(config, base)
            self.assertEqual(result_dir, audit)
            self.assertEqual(result["counts"], {"files": 1, "retain": 1, "quarantine": 0, "pending": 0})
            self.assertTrue(result["records"][0]["hash_current_read"])
            self.assertFalse(result["mutation_performed"])

    def test_rejects_audit_output_inside_scanned_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            with self.assertRaisesRegex(ValueError, "outside every scanned root"):
                inventory.validate_roots({"roots": [{"path": str(root)}], "output_dir": str(root / "audit")}, Path(directory))


class ComparisonTests(unittest.TestCase):
    def record(self, name, digest, size=1):
        return {"root_id": "project", "relative_path": name, "sha256": digest, "size": size, "mtime_ns": 1}

    def test_reports_member_and_hash_changes(self):
        before = {"records": [self.record("same", "a"), self.record("changed", "b"), self.record("removed", "c")]}
        after = {"records": [self.record("same", "a"), self.record("changed", "x"), self.record("added", "d")]}
        result = compare.compare(before, after)
        self.assertEqual(result["counts"], {"added": 1, "removed": 1, "modified": 1, "unchanged": 1})


class BackupTests(unittest.TestCase):
    def test_hash_verified_requires_current_hash_reads(self):
        source = {"records": [{"relative_path": "a.mov", "size": 3, "sha256": "abc", "hash_current_read": True}]}
        backup = {"records": [{"relative_path": "a.mov", "size": 3, "sha256": "abc", "hash_current_read": True}]}
        self.assertEqual(backups.verify(source, backup)["records"][0]["status"], "hash_verified")
        backup["records"][0]["hash_current_read"] = False
        self.assertEqual(backups.verify(source, backup)["records"][0]["status"], "metadata_only")


if __name__ == "__main__":
    unittest.main()
