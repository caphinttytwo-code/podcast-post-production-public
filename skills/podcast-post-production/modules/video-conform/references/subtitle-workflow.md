# Subtitle workflow

Use this workflow after the approved final timeline is locked, including continuation from a user-designated audio exported on that same timeline. Audio duration alone does not prove timeline identity. For a locked video, use its timebase and requested same-basename SRT; for standalone continuation, keep the approved source and deliver a new version.

## 1. Inspect and prepare

- Search the project and final-video directory for SRT, VTT, ASS, transcripts, timecoded ASR JSON, terminology and listening decisions before transcribing. Record the baseline hash, locked timebase, already-proofread range, editable range and chosen style. Reuse complete compatible caches and approved wording. Do not retranscribe a complete recording solely because proofreading resumes; obtain new results only for missing/unreliable material, or the range explicitly requested for renewed cross-validation.
- Probe the selected final media's exact duration and audio stream. Extract the format required by the selected ASR only if a new call is needed. Preserve the original audio.
- Keep raw text, provider responses, chunks, alignment data, and QA logs under `work/subtitles-vNN/`; keep them out of `delivery/`.
- Use `https://api.stepfun.com/step_plan/v1` as the single StepFun API base. Derive synchronous and asynchronous ASR paths from it and override only through `STEPFUN_API_BASE_URL`.
- Resolve credentials in this order: macOS Keychain service `STEPFUN_API_KEY`, environment `STEPFUN_API_KEY`, then `STEP_API_KEY`. Never print or persist a raw key.
- If the preferred provider is unavailable, stop before switching to a local or different cloud ASR. Obtain user approval for the fallback and disclose its resource/privacy impact.

## 2. Obtain text and timestamps

For Chinese, use `stepaudio-2.5-asr` for the main text with language `zh` and ITN enabled. Treat its HTTP/SSE text as text only when returned timestamps are all zero or incomplete.

Use a timestamp source that returns real utterance or word boundaries:

1. Prefer StepFun asynchronous file ASR with `step-asr-1.1` and `show_utterances=true`.
2. Supply 16 kHz mono MP3/WAV under the provider's size limit through a private or temporary HTTPS URL. Expose only the intended audio. Keep the URL alive until the ASR task reaches a terminal state; an initial GET does not prove the provider will not download again after queueing.
3. Close the tunnel immediately after all tasks finish. Delete any explicitly created provider file object when authorized.
4. Treat `PENDING`, `QUEUED`, `SUBMITTED`, and `RUNNING` as non-terminal. Treat a response with results as success. Preserve the exact error stage and message on failure.
5. Back off on HTTP 429 rather than resubmitting successful tasks.

Do not deliver an SRT from zero timestamps, missing continuous-speech timestamps, or character-proportional timing.

## 3. Recover blocked or failed long audio

- First submit the whole file when safe and supported.
- If the whole file is risk-blocked, download-blocked, or lacks complete timestamps, split the locked-final audio into approximately three-minute windows with about 1.5 seconds of overlap on each side.
- Keep only words whose midpoint falls inside the window's non-overlap core. This removes duplicates without discarding boundary speech.
- If an individual three-minute window fails, split only that core into approximately one-minute windows with the same overlap/core rule.
- Save task IDs and results per window so the job can resume without retranscribing completed windows.
- If the shorter online windows still fail, report the exact final-video time ranges. Ask before using local Whisper or another provider.

## 4. Build and proofread cues

- Create a glossary before proofreading: canonical people and pronouns, programs, works, products, venues, organizations, dates, numbers, technical terms, aliases, and known ASR confusions.
- Align the StepAudio text to provider word timestamps. If asynchronous text and StepAudio text are materially identical, the timestamped words may be used directly after proofreading; otherwise use character/word sequence alignment while retaining real word boundaries.
- Make each cue a complete sentence or independently understandable meaning. Use real pauses and word/phrase boundaries, then natural wrapping under the chosen length limits. Do not separate a condition from its result, a modifier from its head, or a verb from its object simply to fit a limit. The existing house style targets about 16 characters per line and roughly 0.35–5 seconds per cue; `compact-clean` is an explicitly selected alternative below.
- Remove non-semantic `啊`, `嗯`, `呃`, repeated starts, and obvious stutters. Preserve meaningful repetition, emotion, jokes, names, numbers, and claims.
- Correct names, programs, venues, locations, brands, dates, and technical terms from authoritative sources when factual verification is needed. Distinguish checking what was said from independently fact-checking a speaker's claim; do not silently rewrite a recorded or user-confirmed claim. Keep a timecoded uncertainty list for anything not safely inferable and ask the user instead of guessing.
- Avoid ordinary Chinese sentence-final punctuation for the cleaned house style. Do not split a person name, fixed term, or Latin brand such as `HALF Coffee` across cues.
- Keep cue times strictly increasing and non-overlapping. When a provider returns equal or zero-length word boundaries, extend only enough to create a valid cue without moving the next cue earlier.

## Semantic review, dialogue and numbers

Use two distinct passes when doing substantive proofreading. First correct words, names and terms; then read continuous surrounding text for pronouns and their referents, subjects, qualifiers, conditions/results, chronology and complete meanings. Scan corrected page boundaries again. Structural checks cannot certify semantic completeness or absence of typos.

- Compare cached or newly authorized StepFun/Qwen text for missing/extra words, homophones, numbers, units and names. Agreement is evidence, not a verdict; disputes are resolved against audio and context, never by majority vote. When calling a Bailian model, follow the available `bailian-gen`/`bailian-protocol` Skills and `bl speech recognize`, checking version, authentication, costs, model capabilities and parameters. Never silently fall back to a native API or another provider. Do not upload complete audio when only a short disputed segment is needed and authorized.
- Remove non-semantic agreement such as repeated 对对对 only when it adds no answer, distinction or emotional meaning. Keep meaningful affirmation/negation and emphasis. In ordinary turn-taking use separate cues without names. Two prefixed lines are reserved for a substantive rapid exchange or reliably established simultaneous speech; diarization IDs alone do not establish overlap. Keep uncertain speaker boundaries for listening.
- A request to clean filler does not authorize paraphrasing. Only when the user allows oral translation/rephrasing may you simplify syntax; preserve facts, numbers, logical relationships and qualifiers such as 大概/可能. Log before/after wording and its basis. When only wording changes and the spoken span is unchanged, retain its original phrase boundaries; do not present old word times as exact times for new words.
- Scan Arabic and Chinese quantities, dates, decades, fractions, percentages, approximate ranges and units throughout the authorized text. Protect fixed names, idioms, titles and quoted verse with a project glossary; number scanning generates candidates, not automatic corrections. Compare the number AND the object, unit, denominator, population/stage and qualifiers. Do not average ranges or recompute a speaker's statement into a new claim.
- Put unresolved words, numerical scope and speaker boundaries in a timecoded list with surrounding text and a context clip. After an initial human review, a targeted second list may cover remaining dialogue/semantic/numeric issues. Use [review tools](subtitle-review.md) to collect and apply actual decisions. A submitted partial list does not confirm every unselected item.

## Optional profile: compact-clean

Enable only when selected for the task. Keep the existing default and user-specified styles available; record the selected profile and any explicit overrides.

- Maximum 16 visible Unicode characters per line, 28 across the whole cue, and two lines. Count internal spaces, Latin letters, digits and leading `-`; do not count the line break. Long expressions wrap at a natural semantic boundary; over-capacity expressions split at independently meaningful clauses using real timing anchors. Flag indivisible verified terms or unresolved splits instead of silently breaking them.
- No punctuation or decorative symbols. Only leading `-` on BOTH lines of a verified two-person cue is exempt. An ordinary single speaker has no name, colon or prefix. Omit empty agreement rather than producing a two-person page for it.
- Convert meaningful numeric notation before punctuation removal: `1.8米` → `1点8米`, `10%` → `百分之10`, `2/3` → `3分之2`. A clearly identified ratio can become `2比1`; ambiguous time/date/range, negative values, currency/unit symbols and punctuation inside a protected term require review or a documented style exception. Never remove a decimal point to produce `18米`, collapse `1、2` into `12`, or silently drop a unit symbol.
- Format limits do not authorize meaning changes, filler deletion or guessed timing. The editor performs semantic decisions; the validator only checks observable constraints.

## 5. Validate and deliver

Require all of the following:

- UTF-8 SRT with sequential one-based cue numbers.
- Parseable `HH:MM:SS,mmm --> HH:MM:SS,mmm` timestamps.
- Positive durations, no overlaps, no empty cues, and final cue end at or before final-video duration.
- No unintended lines beyond the chosen visible-length limit; allow a documented exception for an indivisible verified term.
- Spot checks at opening, early section, midpoint, ending, all conform joins, provider-window boundaries, and every drift-correction region.
- A manual scan for names, homophones, pronouns, repeated phrases, numbers, and ASR hallucinations.

Run:

```bash
python3 scripts/validate_srt.py work/subtitles-v01/draft.srt \
  --video versions/videos/locked-final.mp4 \
  --bad-term 何菜头=和菜头 \
  --json-out work/subtitles-v01/qa/subtitle-qa.json
```

Use `--allow-punctuation` only when the user explicitly chooses a punctuation-preserving subtitle style. Write to a partial filename, validate it, hash it, then atomically rename it beside the video. Refuse an existing destination. Record text model, timestamp model, coverage, cue count, unresolved terms, QA results, and delivery hash in a subtitle QA summary outside `delivery/`.

For the optional compact profile:

```bash
python3 scripts/validate_srt.py /absolute/project/work/draft.srt \
  --media-duration 00:20:00.000 --profile compact-clean \
  --json-out /absolute/project/work/subtitle-qa.json
```

`--max-chars`, `--max-lines` and `--max-screen-chars` override profile limits; `--allow-punctuation` explicitly overrides punctuation enforcement. Without `--profile`, existing validation defaults remain unchanged. Record any overrides as the chosen style. Review confirmed dialogue separately: syntactically valid hyphens do not prove actual overlapping speech.

The delivery record separates structural/format QA, cache/model comparisons, text semantic review, individual human decisions and full-duration human listening. Keep original/version hashes, selected scope, word/phrase anchors, glossary, raw response locations, omissions, rewrites, saved decisions, pending items and output hashes in the work directory. Unselected items remain unconfirmed even when retained unchanged. Never infer full listening or release readiness from model agreement, a successful page save or passing validation.
