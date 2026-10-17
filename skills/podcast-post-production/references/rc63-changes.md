# 0.2-rc6.3beta changes and validation boundaries

Audio source is merged/released v1.7.0 at 46eefcdfa5cc7c4af68da87990850a23593ecf93. Solo remains default. New synchronized-multitrack stays within audio-edit, uses integer sample-frame plans and stops on unequal rates/lengths, offset, drift or inadequate evidence. Paragraph review and source-preserving PCM are separately detected and tested. A cached role transcript remains a projection, never output ASR.

Subtitle numeric scope/style, exact format exceptions, selected adjacent merges, cue map and zero-duration/source audit are pinned to OPEN upstream PR #4 b84c5ed7660721a23bf9abb5f46dbc27984cc144. This source is still pending review. Default subtitle behavior and module-specific trailer/locked rules remain.

Output guards cover whole-package paths, function and CLI entrypoints, hard/symbolic links, caches and derived temporary files. Paragraph review checks actual source content hashes even if size/mtime are preserved. New source provenance and exact original tests are bundled offline; no personal environment values, media, fonts or credentials are bundled.

Minimum standard FFmpeg/FFprobe remains 8.1.1. Explicit Review tools never silently replace standard conform production. Test steps use individual resource/input gates, preserve source hashes on partial execution, stop a batch on changed originals, and distinguish FAIL/BLOCKED/NOT RUN. Reports identify smoke vs evaluated full automatic checks; no synthetic decision represents human listening.

Retained CLI additions are explicitly allowlisted (review-copy, ASR manifest/adoption/role, source-aware audio QA and review records, numeric style/exceptions). New interfaces are separately compared to pinned sources. The old 103 tests are reruns and overlap with the 223 migrated regression cases; do not sum both as unique checks. Three audio source-structure cases are adapted to the single integrated entrypoint/UI without relaxing functional assertions.

This candidate update does not merge a PR, publish a new Release, switch an installed Skill or approve a production project. Roll back by retaining the previous published rc6.2 package and its hash; no live runtime was changed. Untested operating systems/host routing and full human listening/viewing stay NOT RUN.
