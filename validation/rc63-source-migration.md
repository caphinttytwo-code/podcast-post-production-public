# rc6.3 Beta source integration

Audio: merged/released v1.7.0, commit `46eefcdfa5cc7c4af68da87990850a23593ecf93`.
Subtitles: fixed `b84c5ed7660721a23bf9abb5f46dbc27984cc144`, upstream PR #4 OPEN. Not an approved merged upstream release.
Base: immutable public rc6.2 Beta PR head ddca8f73cc3d343731a1f620dc7fd7096c4fa61a.

Original 29 CLI options remain; explicit additions: audio renderer --review-copy; audio ASR --manifest/--adopt-legacy-cache/--transcript-role; conform validator --numeric-style/--format-exceptions plus existing compact profile options. New review/proxy/multitrack/subtitle-audit entries are separate interfaces. Old solo JSON/EDL and the other three modules stay separate.

The source release contains 130 audio cases; three manifest/UI checks are adapted to the integrated single entrypoint, source version consistency and reference existence. Original source tests remain in the offline frozen archive. The original 103 regression cases rerun against current implementation in a separate fixture; these are overlapping compatibility cases and must not be added as new unique tests.

Adapters add whole-package path protection, cache/temp/link checks, shared StepFun network transport, and unconditional content hash verification before local review decisions. Stateless numeric-style reports omit the default spoken marker to preserve legacy report keys; non-default arabic reports explicitly add numeric_style. No subtitle validation constraints are weakened.

Source CI is retained only as data in the frozen archive; integration workflow remains workflow_dispatch only. Public runtime docs use configurable user budgets and unknown fees rather than personal allowances or expiry snapshots. Public MIT distribution authorization was provided by the owner; inherited notices remain.

No runtime installation, release publishing, upstream subtitle merge or production approval is performed by this update.

Public source-data export: one source-document budget amount is redacted to a configurable user policy. Original Git source commit/hash and the original local archive remain unchanged; source-lock.json and package provenance declare original/distributed document hashes. Adapters replay against the distributed export. Functional code and original source test assertions are not redacted.
