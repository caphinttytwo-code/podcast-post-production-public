#!/usr/bin/env python3
"""Calibrate every source-video input seek in an EDL manifest."""

from __future__ import annotations

from pathlib import Path as _PPPath
import sys as _ppsys
_ppsys.path.insert(0, str(_PPPath(__file__).resolve().parents[3]))
from shared.files import protect_output_args


from pathlib import Path as _PackagePath
import sys as _package_sys
_PACKAGE_ROOT = _PackagePath(__file__).resolve().parents[3]
if str(_PACKAGE_ROOT) not in _package_sys.path:
    _package_sys.path.insert(0, str(_PACKAGE_ROOT))
from shared.files import sha256 as digest


import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from calibrate_fast_seek import calibrate




def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("source_pcm", type=Path, nargs="?")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--minimum-correlation", type=float, default=0.80)
    parser.add_argument("--maximum-residual", type=float, default=0.005)
    args = parser.parse_args()
    protect_output_args(args)
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite seek calibration: {args.output}")
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    source = Path(payload["source_video"])
    pcm_path = args.source_pcm or Path(payload.get("analysis_cache", {}).get("source_pcm", ""))
    if not pcm_path.is_file():
        raise FileNotFoundError("Source PCM is missing; pass it explicitly or rebuild the EDL cache")
    full_pcm = np.memmap(pcm_path, dtype="<i2", mode="r")
    pcm_start = float(payload.get("source_audio_start_seconds", 0.0))
    rows, unsafe = [], []
    for number, segment in enumerate(payload["segments"], 1):
        desired = float(segment["source_media_in_seconds"])
        result = calibrate(source, full_pcm, desired, pcm_start)
        row = {"segment_index": int(segment["index"]), **result}
        rows.append(row)
        if (result["verified_correlation"] < args.minimum_correlation or
                abs(result["residual_error_seconds"]) > args.maximum_residual):
            unsafe.append(row)
        if number % 10 == 0 or number == len(payload["segments"]):
            print(f"calibrated {number}/{len(payload['segments'])}", flush=True)
    report = {
        "schema_version": "1.0",
        "job_id": payload["job_id"],
        "manifest_sha256": digest(args.manifest),
        "source_video": str(source),
        "source_pcm": str(pcm_path.resolve()),
        "thresholds": {"minimum_correlation": args.minimum_correlation,
                       "maximum_residual_seconds": args.maximum_residual},
        "segment_count": len(rows),
        "maximum_uncorrected_error_seconds": max(abs(row["uncorrected_error_seconds"]) for row in rows),
        "maximum_residual_error_seconds": max(abs(row["residual_error_seconds"]) for row in rows),
        "minimum_verified_correlation": min(row["verified_correlation"] for row in rows),
        "unsafe_count": len(unsafe),
        "unsafe_segment_indices": [row["segment_index"] for row in unsafe],
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "segment_count", "maximum_uncorrected_error_seconds",
        "maximum_residual_error_seconds", "minimum_verified_correlation", "unsafe_count",
    )}, ensure_ascii=False, indent=2))
    if unsafe:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
