#!/usr/bin/env python3
"""Retest a macOS host binding using only its pinned tools and synthetic data."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

RESOURCES = ("python", "standard_ffmpeg", "standard_ffprobe", "review_ffmpeg",
             "review_ffprobe", "font")


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def fingerprint(profile, compact=False):
    return hashlib.sha256(json.dumps({k: v for k, v in profile.items() if k != "fingerprint"},
                                     sort_keys=True, separators=(",", ":") if compact else None).encode()).hexdigest()


def profile_errors(profile, verify):
    errors = []
    if profile.get("version") != 1 or profile.get("fingerprint") not in {fingerprint(profile), fingerprint(profile, compact=True)}:
        errors.append("profile version or fingerprint differs")
    if str(Path(sys.executable).absolute()) != profile["python"] or sys.version != profile["python_version"]:
        errors.append("bound Python identity differs")
    package = Path(profile["installed_package"])
    try:
        if package.is_symlink() or verify(package) != profile["identity"]:
            errors.append("installed package identity differs")
    except (OSError, ValueError) as exc:
        errors.append("installed package: " + str(exc))
    files = {item["path"]: item for item in profile["bound_files"]}
    for key in RESOURCES:
        if profile[key] not in files:
            errors.append("missing bound resource: " + key)
    for name, item in files.items():
        path = Path(name)
        try:
            if str(path.resolve(strict=True)) != item["resolved"] or sha(path) != item["sha256"]:
                errors.append("bound file changed: " + name)
        except OSError:
            errors.append("bound file unavailable: " + name)
    return errors


def atomic_replace(path, contents):
    descriptor, temporary = tempfile.mkstemp(prefix=".runtime-profile-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def capture(command, work, label, env):
    result = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True, timeout=300)
    (work / (label + ".stdout")).write_text(result.stdout, encoding="utf-8")
    (work / (label + ".stderr")).write_text(result.stderr, encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.runtime_root.resolve(strict=True)
    path = root / "runtime-profile.json"
    work = args.work_dir.expanduser().absolute()
    if path.is_symlink() or any(item.is_symlink() for item in (work, *work.parents)):
        parser.error("profile and evidence must use direct paths")
    original = path.read_bytes()
    profile = json.loads(original)
    package = Path(profile["installed_package"]).resolve(strict=True)
    if work == package or package in work.parents or work in package.parents or work == root or work in root.parents:
        parser.error("use a new evidence directory outside the installed package")
    work.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.chmod(work, 0o700)
    current = platform.mac_ver()[0]
    report = {"status": "BLOCKED", "old_macos": profile["macos"], "current_macos": current,
              "old_fingerprint": profile["fingerprint"], "new_fingerprint": None,
              "package_identity": profile["identity"], "changes": [],
              "tools": {key: profile[key] for key in RESOURCES},
              "recorded_at": datetime.now(timezone.utc).isoformat(),
              "human_review": "NOT RUN", "model_calls": 0, "uploads": 0}

    def verify_package(location):
        # Verify using the recorded manifest digest before loading any package code.
        manifest = location / "package-manifest.json"
        if manifest.is_symlink() or manifest.stat().st_nlink != 1 or sha(manifest) != profile["identity"]["manifest_sha256"]:
            raise ValueError("manifest hash differs")
        files = {}
        for file in location.rglob("*"):
            relative = file.relative_to(location)
            if file.is_symlink() or file.suffix in (".pyc", ".pyo"):
                raise ValueError("unexpected link or bytecode: " + str(relative))
            if any(part in (".git", "__pycache__", ".DS_Store") for part in relative.parts) or file == manifest:
                continue
            if file.is_file():
                if file.stat().st_nlink != 1:
                    raise ValueError("unexpected hard link: " + str(relative))
                files[relative.as_posix()] = sha(file)
        data = json.loads(manifest.read_bytes())
        tree = hashlib.sha256("".join(f"{files[k]}  {k}\n" for k in sorted(files)).encode()).hexdigest()
        if files != data["files"] or tree != data["tree_sha256"]:
            changed = set(files) ^ set(data["files"])
            changed.update(key for key in files.keys() & data["files"].keys() if files[key] != data["files"][key])
            raise ValueError("files differ: " + ", ".join(sorted(changed)))
        return {"version": data["version"], "tree_sha256": tree, "files": len(files),
                "manifest_sha256": sha(manifest)}

    try:
        if not current:
            raise ValueError("a macOS host is required")
        report["changes"] = (["macOS " + profile["macos"] + " -> " + current]
                             if current != profile["macos"] else [])
        errors = profile_errors(profile, verify_package)
        if errors:
            report["changes"].extend(errors)
            raise ValueError("non-OS binding drift; review changes before retesting")
        env = {**os.environ, "PATH": os.pathsep.join([str(Path(profile["standard_ffmpeg"]).parent),
               str(Path(profile["python"]).parent), "/usr/bin", "/bin"]),
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}
        for key in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE", "PP_RUNTIME_PROFILE"):
            env.pop(key, None)
        command = [profile["python"], "-B", "-s", package / "scripts/setup_skill.py", "test",
                   "--test", "quick", "--work-dir", work / "quick", "--features", "all",
                   "--ffmpeg", profile["standard_ffmpeg"], "--ffprobe", profile["standard_ffprobe"],
                   "--review-ffmpeg", profile["review_ffmpeg"], "--font", profile["font"]]
        result = capture(command, work, "quick", env)
        report["quick_exit_code"] = result.returncode
        if result.returncode:
            raise RuntimeError("synthetic quick test failed")
        checked = json.loads((work / "quick/installation-report.json").read_text())
        if (not checked["ok"] or checked["identity"] != profile["identity"]
                or not checked["capabilities"] or any(row["status"] != "PASS" for row in checked["capabilities"])):
            raise RuntimeError("quick test evidence does not verify all capabilities")
        report["capabilities"] = {row["id"]: row["status"] for row in checked["capabilities"]}
        review_video = work / "quick/quick-probes/trailers-review/smoke.mp4"
        review = capture([profile["review_ffprobe"], "-v", "error", "-show_streams", "-of", "json",
                          review_video], work, "review-probe", env)
        if review.returncode or not {"audio", "video"} <= {x["codec_type"] for x in json.loads(review.stdout)["streams"]}:
            raise RuntimeError("bound Review ffprobe could not verify the synthetic Review export")
        updated = {**profile, "macos": current}
        if current != profile["macos"]:
            updated["fingerprint"] = fingerprint(updated)
        contents = (json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode()
        with (root / ".runtime-profile.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if path.is_symlink() or path.read_bytes() != original:
                raise ValueError("profile changed concurrently")
            errors = profile_errors(profile, verify_package)
            if errors or platform.mac_ver()[0] != current:
                report["changes"].extend(errors)
                raise ValueError("binding changed during retest")
            backup = work / "runtime-profile.before.json"
            backup.write_bytes(original)
            os.chmod(backup, 0o600)
            if current != profile["macos"]:
                atomic_replace(path, contents)
            try:
                check = capture([root / "bin/pp-python", "--check"], work, "runtime-check", env)
                expected = updated["fingerprint"]
                if check.returncode or json.loads(check.stdout).get("fingerprint") != expected:
                    raise RuntimeError("post-update runtime check failed")
            except Exception:
                if current != profile["macos"] and path.read_bytes() == contents:
                    atomic_replace(path, original)
                    report["rollback"] = "RESTORED"
                raise
        report.update(status="PASS", new_fingerprint=updated["fingerprint"],
                      profile_updated=current != profile["macos"])
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as exc:
        report["error"] = str(exc)
    (work / "revalidation-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
