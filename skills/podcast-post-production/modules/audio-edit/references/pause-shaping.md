# Pause Shaping

Use this reference in both editorial branches after mechanical cleanup, refreshed-transcript semantic editing, and stable content selection. Pause shaping improves pacing without treating silence as automatically defective.

## Privacy Contract

- Keep source audio, transcripts, excerpts, file names, absolute paths, real timecodes, project statistics, and delivery artifacts out of the Skill repository and public Git history.
- Use generated audio and fictional transcripts for committed examples and tests.
- Produce aggregate metrics by default. Do not serialize transcript text or source identifiers in pause-profile reports.
- Keep analysis outputs in the episode workspace or a temporary directory, never beside this Skill unless the data is synthetic and intentionally committed.

## Evidence

1. Use ASR timing to identify language structure and candidate gaps.
2. Use waveform, VAD, or short-window energy to refine acoustic boundaries.
3. Check transcript context before shortening a pause that follows a number, source, condition, contrast, or conclusion.
4. Listen across every accepted join. Widen or reject it when a breath, consonant, room tone, or rhetorical beat sounds damaged.

Treat numeric thresholds only as candidate-discovery signals. Never accept or reject a pause edit from duration alone.

ASR can miss quiet speech and waveform energy can mistake breaths for silence. Require both semantic and acoustic evidence for automatic recommendations.

## Pause Roles

- `intra-clause`: a brief hesitation inside one grammatical unit. Preserve by default unless it is clearly accidental.
- `clause`: a separation between related clauses. Shorten only when the relationship remains easy to follow.
- `sentence`: a completed idea before the next sentence. Preserve more space than an intra-clause pause.
- `section`: a topic or argument transition. Keep enough time for the listener to register the change.
- `rhetorical`: deliberate emphasis, suspense, emotion, or reflection. Keep and document when unusually long.
- `work`: recording operation, searching for a take, or dead air attached to an abandoned rerecord. Remove with the failed take or compress aggressively; do not confuse it with an intentional rhetorical pause. Record the resulting approved EDL entry using the nearest retained semantic role rather than adding `work` to the public pause-role enum.

Preserve the general hierarchy `section/rhetorical > sentence > clause > intra-clause`. Do not force all roles to one target duration.

## Editing Pass

1. Measure the distribution of inter-phrase gaps by role, including gaps shorter than two seconds.
2. Flag outliers relative to their role and local delivery; do not delete from duration alone.
3. For a pure timing edit, use `pause-compression` and record the original and retained gap.
4. For a content removal that also trims surrounding silence, use `content-with-pause-trim` and record the retained boundary words without storing private excerpts in public repositories.
5. Retain short room-tone handles and natural breaths. Reject joins that clip consonants or create implausibly continuous speech.
6. Keep reference-derived numeric ranges provisional until repeated approved episodes show the same pattern.

When comparing a human or agent reference, separate content-bearing removals, independent pause compression between retained words, and unresolved duration residual. Silence carried inside a discarded take belongs to the content removal. Never use the total low-energy-duration difference as the independent pause-compression amount.

When a tool such as ChatCut can reset every pause on a track, record the tool and setting when known. Treat a uniform reference distribution as tool-induced evidence until the user confirms it as an intentional preference. Do not flatten the branch's semantic pause hierarchy to match a global control.

For `casual-non-rigorous`, favor breathing room, comedy, companionship, and emotional hesitation. For `rigorous-explainer`, preserve extra space around numbers, sources, conditions, contrasts, evidence, and conclusions. Do not transfer one branch's pacing profile to the other.

When a human reference author confirms pacing and explicitly selects it as a `rigorous-explainer` personal default, review non-semantic gaps more actively after content selection. Learn the relative tendency, not the episode's durations: shorten work-like or redundant space first, retain semantic and rhetorical separation, and reject any join that weakens comprehension or natural delivery.

## Aggregate QA

Report without transcript excerpts or source identifiers:

- duration change and normalized retained-text rate;
- gap count and percentile distribution for each pause role;
- counts above one and two seconds;
- normalized low-energy duration using a documented threshold range;
- whether any numbers, sources, qualifications, transitions, or conclusions require human review.

Technical metrics never replace a full-length human listen.
