---
name: podcast-post-production
description: Beta testing version. Edit solo or synchronized equal-length multitrack podcast audio, conform full videos to edited audio, produce video trailers, revise approved video masters, or audit media projects. Use for 播客精剪、视频对版、片花、锁版精修 媒体项目审计、字幕续校、数字复听 and 字幕校对.
metadata:
  version: "0.2.0-rc.6.3-beta"
---

# 播客音视频后期 — Beta

This is **0.2.0-rc.6.3-beta Beta**, a public MIT-licensed Beta testing release. It is not a stable release.

Choose the workflow for the user's actual requested output. This is a standalone five-module package; it does not require the former individual Skills to be installed.

For transcription, follow [ASR redirect and cache safety](references/asr-security.md). A redirect failure does not authorize a changed endpoint or retry upload.

## Beta first use and environment changes

Before production in a new installation, read [Beta setup](references/alpha-installation.md). Run the bundled setup entrypoint in `inspect` mode in a fresh directory outside this package. Show what the present resources can do, missing resources and their purpose, external API/upload/possible fees, and conditions software cannot solve. Offer quick tests (recommended), full tests, or skip; record the user's choice. Do not treat dependency presence as a passed production test or a configured key as account entitlement.

Use [the bundled test plan](references/alpha-testing.md) and [host execution instructions](references/executor-prompt.md); do not ask for separately delivered test documents or fetch old private repositories. A direct third-party installation has no proven pre-install test: disclose it and offer the same tests after copying. After installation, show the generated installation/capability report. Reuse an existing report only after matching this package identity and current environment fingerprint; resource changes require affected checks again. Use the report's Python interpreter and selected tool paths for production. Installing this Beta does not authorize replacing old Skills.

## Select the workflow

| Mode | Trigger and controlling input | Read next |
|---|---|---|
| `audio-edit` | Audio-only solo editing (default), paragraph review, preserve-source PCM edits, or synchronized-multitrack editing/rerecord assembly. Different lengths/rates, offset or drift require external alignment first. | [Audio workflow](modules/audio-edit/workflow.md) |
| `video-conform` | A complete edited audio reference determines the full video's content and duration; includes locked-final or proven same-timebase subtitle continuation and contextual proofreading. | [Conform workflow](modules/video-conform/workflow.md) |
| `trailers` | Story selection, video clips, vertical packaging, covers, PIP, or a visual-only change. A selected talking-head excerpt does not require fresh story discovery. | [Trailer workflow](modules/trailers/workflow.md) |
| `locked-revision` | Exact removals or localized timing/audio/subtitle fixes to an approved video master. The rest stays locked. | [Locked workflow](modules/locked-revision/workflow.md) |
| `project-audit` | Explicit inventory, backup verification, quarantine or cleanup request for named project roots. | [Audit workflow](modules/project-audit/workflow.md) |

Read only the selected module and its step-specific references. For a mixed request, identify the required modules and their handoff before execution. If source/reference versions or requested surfaces are ambiguous, inspect available records and clarify the unresolved choice.

## Shared boundaries

- Preserve originals, approved versions, raw ASR and caches. Put project media, manifests, reports and generated evidence outside this entire Skill directory.
- Follow the selected module's authorization gates, source roles, editorial branches and technical criteria. The common index is not permission to edit, upload, clean up or publish.
- Use source ASR timestamps for candidate location; determine real edit boundaries from complete events, waveform, listening and frames as applicable.
- A cover-only request changes only the cover. Subtitle-only work uses the specified locked-final timebase. Do not reopen story selection or render unrequested video.
- Technical QA, sampled inspection, full human listening/viewing and publication status are distinct records. A new package, an index or a passed structural test cannot imply human approval or release readiness.
- Cloud ASR requires the module's upload/model authorization; reuse valid caches. StepFun follows the user-selected valid Plan or authorized billing route; do not assume an account entitlement or expiry. For Bailian, follow the user's CLI-first routing and installed Bailian instructions; do not silently change providers or use native APIs.
- Cleanup is a separate requested workflow, never automatic after delivery. Inventory exact targets and obey approval gates for movement and permanent deletion.

## Resources and handoff

Resolve scripts relative to this package or the selected module; existing script arguments and module-specific JSON formats are retained. Shared code is internal infrastructure, not a new universal EDL or renderer.

- Before executing a module, read [minimum environment and installation requirements](references/dependencies.md), then run the task-specific check. Missing packages/fonts/codecs block only dependent steps; never auto-install global tools. Use a small synthetic smoke for a new environment; keep environment evidence outside the package. A version check alone does not certify production or human review.
- For cross-module continuation or a unified evidence index, read [project index and handoff](references/project-index.md).
- For this update, read [rc6.3 changes](references/rc63-changes.md) when reviewing compatibility or rollback.
- For migration lineage and retained license notices, read [provenance](references/provenance.json) and [NOTICE](NOTICE.md).

This is an Beta candidate. Users may explicitly choose the bundled installer and tests. Development or a technical pass does not authorize switching existing installations, editing media, uploading, cleanup or publishing. Full human listening/viewing remains a separate project record.
