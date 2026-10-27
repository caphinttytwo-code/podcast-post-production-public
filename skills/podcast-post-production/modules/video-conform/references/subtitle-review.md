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

## Numeric notation and complete numeric review

New options are opt-in; existing review directories without them keep the original
`spoken` notation and `uncertain` review scope. Do not regenerate an old manifest
under saved decisions. The schema-1 defaults preserve its IDs and snapshot hash.

```bash
python3 scripts/subtitle_review.py build \
  --srt /absolute/project/work/baseline.srt \
  --items /absolute/project/work/review-items.json \
  --media-duration 600 --profile compact-clean \
  --numeric-style arabic --numeric-review all \
  --workdir /absolute/project/work/review-v02
```

`arabic` preserves well-formed decimals, percentages and per-mille notation such
as `7.5亿次`, `1%`, `1‰`, `2.0`. It does not convert Chinese quantities, infer a
number, change a unit or authorize a factual correction. `spoken` retains the old
conversion. Dates, signs, ratios, ranges, fractions, currency and ambiguous
punctuation need an explicit reviewed literal or a wording decision. Neither mode
may turn `7.5` into `75` or merge `1、2` into `12`.

`--numeric-review all` adds a separate item for each scanned cue not already
covered by an explicit item. Use protected terms for idioms and proper names;
scanner matches are candidates, not proof that the text is numerical. For ON AIR
news projects choose `arabic` and `all` when following the user's project
preference; this is not a global default for unrelated projects.

Selected numeric items can provide `original_text` (the selected ASR/source
wording), `suggested_text`, `unit_note`, and `group_label`. Without source wording,
the original-text display is only the frozen SRT, not a verbatim ASR claim.
Read the entire number, object, unit, denominator, range and qualifiers such as
大概、多、不到. Keep idioms and official names intact. Suggestions are read-only
until the user actually edits the submitted text. A group label connects cards
visually but never copies a decision between occurrences: use one item per
occurrence when their contexts or meanings differ. Review scope `uncertain`
uses only the explicitly supplied items. The page supports a numeric-only filter and millisecond timestamps. The report lists unconfirmed numeric
cue IDs separately from confirmation of the selected list.

## Exact symbol exceptions

For a proposed single replacement or merge, include the exact `suggested_text`
and its `format_literals`, for example:

```json
{"id":"term","cue_numbers":[12],"suggested_text":"型号C++","format_literals":["C++"]}
```

The page displays these literals. Only an actual `edit` with that exact proposed
text approves the exception. `accept` still keeps the baseline; unselected or
uncertain suggestions never approve it. A changed proposal, invalid wrapping or
ambiguous timing stays pending. Other punctuation continues to fail validation.
For already-confirmed baseline exceptions, pass `build --format-exceptions FILE`.
The file is tied to the decoded UTF-8 SRT text hash (UTF-8 BOM removed), exact cue
number/text, literal and real approval basis:

```json
{"srt_sha256":"SHA256_OF_SRT_TEXT","entries":[{"cue_number":12,"text":"型号C++","literals":["C++"],"approval_basis":"actual prior confirmation reference"}]}
```

Do not fabricate that basis. Applying a review writes a new
`.review/format-exceptions.json` bound to the final SRT, with renumbered targets.
Standalone validation accepts this file with `--format-exceptions` and the same
`--numeric-style`. Never use `--allow-punctuation` as a substitute for narrow
exceptions. In `arabic` mode valid numeric notation is a style rule, rather than
an assertion that every value has received human confirmation.

## Explicit adjacent merge

An item may declare `"operation":"merge"` with at least two contiguous
`cue_numbers` and proposed text. The user must select `edit` and submit exactly
one subtitle block (one or two lines). The helper uses the first original start
and the last original end; it never invents intervening word times. `accept`
does not merge. Uncertain, unselected, overlong or invalid results retain the
baseline and are not reported as an applied merge. Nonadjacent or overlapping
selected operations are refused. Review long gaps or missing speech between
anchors before proposing a merge; the tool cannot decide semantic continuity.

The audit includes `cue-map.json`, original cue texts/times, submitted snapshot,
final text and timing basis. Splitting, new cut points and adjustments beyond
that union remain manual work in a new, reconciled version.

## Source-lineage audit

Use `scripts/audit_subtitle_sources.py --srt FILE --source-map MAP --output NEW`
for a substantive rewrite or when raw ASR contains zero-duration records. This
is an offline audit, not a transcriber or automatic semantic editor. The input
map has:

- `srt_sha256`: decoded UTF-8 SRT text hash, without BOM.
- `records`: all source records in the declared range, each with unique `id`,
  real `start_ms`, `end_ms` and preserved `text`.
- `cues`: each final `cue_number`, its `record_ids`, `before`, `after`, rewrite
  `reason`, `start_anchor_id` and `end_anchor_id`. Positive-duration first/last
  records determine the phrase range. A cue containing zero-duration records
  also needs an explicit `zero_duration_binding_basis`.
- `omissions`: `record_ids`, `reason`, and explicit `status` (`omitted` or
  `pending`). Non-semantic acknowledgments may be omitted only after contextual
  judgment; an unresolved semantic tail is pending, not a deletion.

Every record must be accounted for exactly once, in a cue or an explained
omission. Missing content, missing positive anchors, unresolved omissions and
unsupported phrase binding prevent a passing audit. Never distribute time by
character count or silently drop a zero-duration semantic tail. Retain raw
responses and offsets alongside this map, outside the Skill and delivery.

A passing report proves only observable lineage. The editor still performs two
semantic passes: words/names/numbers first, then continuous meaning, referents,
negation, cause, condition and qualifiers. Keep original/rewritten wording and
reasons; preserve the original phrase range without claiming new word times.
Technical validation, individual decisions and full-duration human listening
remain separate records.
