---
name: podcast-post-production
description: 剪辑导演（Beta）：为长播客、访谈和圆桌制定内容筛选、目标时长与补录放置方案；也执行已确认的音频精剪、同步多轨装配、视频对版、片花包装、字幕局部修订及项目审计。只出方案、只修字幕/封面/接点或只清理时按对应分支处理，不自动扩大为整片重剪。
metadata:
  version: "0.5.0-beta"
---

# 剪辑导演 — Beta

This is **0.5.0-beta**, a locally prepared, unpublished Beta upgrade candidate under the inherited MIT license. It is not a stable release; actual installation and activation status come from host-side reports. The technical Skill ID remains `podcast-post-production`; “播客音视频后期” is the prior display name.

Choose the workflow for the user's actual requested output. This is a standalone six-module package; it does not require the former individual Skills to be installed. Existing project schemas, EDLs and module commands are retained. A local runtime profile remains bound to its exact package identity and requires revalidation before any future switch. For candidate lineage and handoff, read [local upgrade status](references/local-050-upgrade.md).

For transcription, follow [ASR redirect and cache safety](references/asr-security.md). A redirect failure does not authorize a changed endpoint or retry upload.

## Beta first use and environment changes

Before production in a new installation, read [Beta setup](references/alpha-installation.md). Run the bundled setup entrypoint in `inspect` mode in a fresh directory outside this package. Show what the present resources can do, missing resources and their purpose, external API/upload/possible fees, and conditions software cannot solve. Offer quick tests (recommended), full tests, or skip; record the user's choice. Do not treat dependency presence as a passed production test or a configured key as account entitlement.

Use [the bundled test plan](references/alpha-testing.md) and [host execution instructions](references/executor-prompt.md); do not ask for separately delivered test documents or fetch old private repositories. A direct third-party installation has no proven pre-install test: disclose it and offer the same tests after copying. After installation, show the generated installation/capability report. Reuse an existing report only after matching this package identity and current environment fingerprint; resource changes require affected checks again. Use the report's Python interpreter and selected tool paths for production. Installing this Beta does not authorize replacing old Skills.

## Select the workflow

| Mode | Trigger and controlling input | Read next |
|---|---|---|
| `editorial-plan` | Long-program material maps, target-runtime selection, episode structure, rerecord placement or a summary of proposed choices. Plan-only by default; auditions require the requested/approved scope. | [Content planning](modules/editorial-plan/workflow.md) |
| `audio-edit` | Audio-only solo editing (default), paragraph review, preserve-source PCM edits, or synchronized-multitrack editing/rerecord assembly. Different lengths/rates, offset or drift require external alignment first. | [Audio workflow](modules/audio-edit/workflow.md) |
| `video-conform` | A complete edited audio reference determines the full video's content and duration; includes locked-final or proven same-timebase subtitle continuation and contextual proofreading. | [Conform workflow](modules/video-conform/workflow.md) |
| `trailers` | Story selection, video clips, vertical packaging, covers, PIP, or a visual-only change. A selected talking-head excerpt does not require fresh story discovery. | [Trailer workflow](modules/trailers/workflow.md) |
| `locked-revision` | Exact removals or localized timing/audio/subtitle fixes to an approved video master. The rest stays locked. | [Locked workflow](modules/locked-revision/workflow.md) |
| `project-audit` | Explicit inventory, backup verification, quarantine or cleanup request for named project roots. | [Audit workflow](modules/project-audit/workflow.md) |

Read only the selected module and its step-specific references. For a mixed request, identify the required modules and their handoff before execution. If source/reference versions or requested surfaces are ambiguous, inspect available records and clarify the unresolved choice.

“剪辑导演” is an entrypoint, not authorization for a whole production. A plan may stop at text; a local fix may enter an existing execution module directly. Shared project indexes point to each module's authoritative evidence, not a replacement universal EDL.

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
- For the inherited baseline, read [rc6.3 changes](references/rc63-changes.md); current local changes and handoff are in [local upgrade status](references/local-050-upgrade.md).
- For migration lineage and retained license notices, read [provenance](references/provenance.json) and [NOTICE](NOTICE.md).

This is a Beta candidate. Users may explicitly choose the bundled installer and tests. Development or a technical pass does not authorize switching existing installations, editing media, uploading, cleanup or publishing. Full human listening/viewing remains a separate project record.
