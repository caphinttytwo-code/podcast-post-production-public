# Offline validation

Use a separate virtual environment with the root requirements-dev.txt. Keep generated reports, source snapshots and synthetic media outside the entire package. No model key or real programme upload is needed for these checks.

From the package root:

```text
python scripts/check_environment.py --mode audio-edit
python scripts/check_environment.py --mode video-conform
python scripts/check_environment.py --mode trailers
python scripts/check_environment.py --mode locked-revision
python scripts/check_environment.py --mode project-audit
python scripts/run_tests.py --frozen-sources /ABSOLUTE/AUDIT/sources --report-dir /ABSOLUTE/AUDIT/tests
python tests/synthetic_integration.py --work-dir /ABSOLUTE/AUDIT/synthetic --review-ffmpeg /ABSOLUTE/REVIEW/ffmpeg --font /ABSOLUTE/CJK/font.otf
```

The frozen sources are external audit fixtures, not a runtime dependency. The test runner starts each module in a separate process, retains the original 52 tests and adds shared compatibility/safety checks. Shared checks compare cached ASR bytes, subtitle parser/profile results and probe fields/errors with those frozen originals. Mocks reject network and credential access when a complete cache is present.

The synthetic integration creates new deterministic audio and video, executes the five module paths, decodes outputs and compares protected source hashes. It records actual subprocess results. Review explicitly uses the filter-capable binary passed in its configuration; other steps use the active FFmpeg/FFprobe environment. Follow the tested binary profile in dependencies.md. This harness is a test fixture, not a production renderer or approval record.

Also validate the root Skill metadata, UI configuration, relative document links, CLI compatibility, full migration-map target hashes, archived package contents and source/discovery protection. Independent reviewers must review the exact final file hashes. A candidate change invalidates the affected tests and audit evidence.

Technical checks do not establish editorial quality, full human listening/viewing or programme publication approval. This package adds no human review record and grants no installation or switch permission.

The rc.3 harness uses explicit CJK font selection and a real two-line cue. Additional tests cover subtitle PNG integer sizes, glyph rejection, font paths, Review fontsdir, and feature-specific environment failures. Platform differences are reported independently; a macOS pass cannot close Windows permission blockers.

## rc.4 subtitle verification

Run the 88 retained regressions plus 15 migrated subtitle tests and separately listed package protection tests. Run `tests/subtitle_integration.py --work-dir /ABS/NEW` for a synthetic scan → contextual clips → loopback partial save → apply → QA workflow. Its decisions are simulated test inputs, never a real human review. Retain 20 actual host-routing records separately; static reading is not execution.

Old validator options and all old report fields remain available. The conform validator adds profile/limits metadata and rejects invalid minute/second components and non-positive or non-finite media duration; basic shared parsing remains permissive unless explicitly called with strict_components=True. Compare these intended extensions to the fixed new upstream in addition to old-field compatibility.

Additional portable drivers (all evidence directories must be new and outside the package):

```text
python -B -m unittest discover -s tests/package_protection -v
python -B tests/subtitle_integration.py --work-dir /ABS/NEW/subtitle-e2e
python -B tests/product_acceptance.py --work-dir /ABS/NEW/synthetic --report-dir /ABS/NEW/acceptance --font /ABS/CJK/font.otf
python -B tests/production_protection.py --work-dir /ABS/NEW/synthetic --report-dir /ABS/NEW/protection
```

`package_protection` intentionally remains separate from the 103 baseline regressions. Record actual test IDs and platform-specific errors. Windows symlink permission errors are BLOCKED, not evidence of successful rejection. Retain all failed attempts; do not reuse their output directories. The production protection driver covers 18 control/negative checks; it does not replace the remaining environment, cache, font and host-routing requirements in the external plan.
