# Contextual subtitle review tools

Read when a subtitle job needs a human uncertainty list, a numerical second pass, or application of submitted decisions. The tools use standard-library Python 3.10+ and local `ffmpeg`/`ffprobe` for optional clips. They do not call models, upload audio, paraphrase text, infer speakers or generate new timing boundaries.

## Prepare the list

Select the frozen baseline and allowed proofreading scope first. Generate numeric candidates if useful:

```bash
python3 scripts/subtitle_review.py scan-numbers \
  --srt /absolute/project/work/baseline.srt \
  --protected-term 示例机构 --protected-term 三星堆 \
  --output /absolute/project/work/numeric-candidates.json
```

Scanning includes broad Chinese numeral candidates; it can flag nonnumeric words. Review candidates against the glossary and cached ASR, group related numerical claims, mark actual priority disputes, and keep selected targets explicit. Do not convert fixed names or call all candidates errors. Preserve evidence sources and offset mappings separately.

The input is a JSON list. Each item requires `cue_numbers` (one or more exact, one-based cue numbers). Optional fields are `id` (unique ASCII letters/digits/underscore/hyphen), `question`, `kind`, `priority`, `evidence` (provider → selected plain transcript text) and `prior_confirmation` (a genuine previous human conclusion with its basis). Do not insert a full provider response, credentials, cloud file metadata or signed URLs. URLs in selected evidence text are redacted automatically.

```json
[
  {
    "id": "depth",
    "cue_numbers": [12],
    "kind": "numeric",
    "priority": true,
    "question": "核对深度的数值和单位",
    "evidence": {"模型A": "一米八", "模型B": "一米八十厘米"}
  }
]
```

Build into a NEW work directory:

```bash
python3 scripts/subtitle_review.py build \
  --srt /absolute/project/work/baseline.srt \
  --items /absolute/project/work/review-items.json \
  --audio /absolute/project/locked-audio.mp3 \
  --profile compact-clean --context-seconds 5 \
  --workdir /absolute/project/work/review-v01
```

Without clips, omit `--audio` and supply `--media-duration SECONDS`. `--max-chars`, `--max-lines`, `--max-screen-chars` and `--allow-punctuation` explicitly override the chosen profile and are recorded in the manifest. A new build captures the baseline bytes/hash, exact cue text and times, context, manifest hash and optional clips. Prior confirmations require an explicit basis and are counted separately. Do not replace an existing review directory or regenerate IDs underneath saved decisions; create a new version and explicitly reconcile changes.

## Review and save

```bash
python3 scripts/subtitle_review.py serve \
  --workdir /absolute/project/work/review-v01
```

Open the printed loopback URL. The page supports all/priority/unselected/uncertain/completed filters, audio/context, evidence, edited text, notes, undo and autosave. Keep a blank line BETWEEN multiple targeted cues and a single newline WITHIN a two-line cue. The bulk button expressly confirms ALL unselected items and requires confirmation; filtering to priority does not limit that bulk action.

The server binds only to `127.0.0.1`, serves the declared clips rather than the whole project, checks POST origin, and rejects stale revisions from another page. A save error means the conclusion is not saved: refresh/reconcile before continuing. Stop the server when no longer needed.

## Apply the actual submitted snapshot

```bash
python3 scripts/subtitle_review.py apply \
  --workdir /absolute/project/work/review-v01 \
  --output /absolute/project/delivery/subtitles-v02.srt
```

The recorded source must still match the frozen baseline. `--source` can identify an identical baseline moved to a new path; it does not waive hash verification. The tool rejects duplicate/unknown IDs, changed manifest/targets, overlapping selected targets and existing output/audit paths.

- **accept** retains current text, regardless of any unused textarea content.
- **edit** changes ONLY the explicitly selected cues, preserves their times, and checks their format. Under compact-clean, unambiguous numeric symbols are converted before punctuation removal. An ambiguous numeric symbol, extra page, overlong phrase or change requiring timing work remains pending; the original targeted text is retained in a review draft. Do not silently truncate it or divide time by character count.
- **uncertain** remains a listening question and keeps its original text.
- **unselected** retains original text and is never counted as human confirmation.

The output's `.review` directory stores the exact submitted JSON, manifest, per-item ledger, changes, pending items and validation/hash report. A pending result is labeled `review_draft`. Even a technically valid result with no pending edits can contain unselected items: report that count accurately, as separate from human confirmation. `human_full_audio_review` remains false; record any actual full listening separately with its scope and evidence.

For pending reflow/timing work, edit in a new version using real phrase/word anchors, validate it, and reconcile the item explicitly. Do not claim the helper completed semantic checking or generated new ASR word times. Keep raw model responses and prior listening records outside delivery and outside the Skill repository.
