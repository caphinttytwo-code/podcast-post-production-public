# Shared Editorial Decision Rules

Read this reference before either branch creates mechanical or semantic EDL entries. Keep decisions on the source timeline and use the refreshed mechanical-stage transcript for semantic editing.

## Pass Order

1. Mark deterministic mechanical defects.
2. Generate and read the mechanical-stage transcript.
3. Make semantic and structural decisions from that refreshed transcript.
4. Shape pauses after retained content is stable.
5. Render from the original source, transcribe the actual candidate, and run the four editorial checks.
6. Run a residual mechanical scan on the post-edit transcript before release review.

Do not merge these passes merely because one EDL stores their approved source-time intervals.

## Mechanical Decisions

Treat a region as mechanical only when its removal does not require interpreting the speaker's intended meaning.

- Allow standalone, purely hesitant `呃` or `额` only after audio confirms that no unique word, breath, emphasis, or emotional beat overlaps it.
- Allow explicit countdowns, edit instructions, equipment interruptions, clearly abandoned fragments, immediate acoustic stutters, and work pauses around a failed take.
- Never batch-delete `嗯`, `啊`, `那个`, `就是`, `然后`, `所以`, `但是`, `对`, or similar words. Retain them whenever they provide sequence, contrast, response, reference, emphasis, emotion, or natural connection.
- Keep a filler when removing it would clip a consonant, collapse a breath, expose a room-tone jump, or make the delivery implausibly continuous.

## Residual Mechanical Scan

Run the scan once on the refreshed mechanical-stage transcript and again on the rendered candidate transcript.

- Group adjacent takes that share a stable core word sequence and progressively expand toward one complete version.
- Inspect lists, names, abstract long sentences, transitions, summaries, previews, and sign-offs more closely; repeated attempts are frequently distributed across ASR cue boundaries.
- Inspect short repeated subjects, predicates, conjunction fragments, and self-corrections beside the retained take. Do not let their brevity or a clean first render exempt them from the second scan.
- Treat a cluster as mechanical only when the retained take covers the discarded take's complete meaning and program function.
- Put newly found items through the confirmation gate. Never add them to an approved EDL silently.

## Rerecord Selection

Compare takes in this order:

1. completeness of the intended expression;
2. factual and semantic accuracy;
3. natural delivery and emotional truth;
4. continuity with the retained context;
5. later take, only when the first four are equal.

Preserve an earlier take's unique setup, subject, object, qualification, transition, evaluation, or emotional lead-in when the later take does not replace it. Never join two incomplete takes into a sentence the speaker never recorded.

## Semantic-Unit Gate

Delete a complete region only when all four dimensions remain intact:

- grammar: the retained speech is syntactically complete;
- meaning: no unique claim, qualification, example, joke, or emotional turn is lost;
- logic: references, cause and effect, comparisons, and callbacks retain their dependencies;
- program function: setup, transition, pacing, companionship, personality, emphasis, and conclusion still work.

Use whole semantic units instead of ASR fragments or isolated repeated words. A grammatical sentence may still be redundant; an imperfect sentence may still carry essential personality or emotional function.

Before accepting a semantic difference, flag changes to numbers, names, negations, qualifications, cause and effect, transitions, references, conclusions, persona, and section navigation. A high-confidence alignment does not override this sensitive-field gate.

Treat a broad statement followed by a concrete mechanism as redundant only when the concrete version fully covers the same claim and deletion preserves emphasis, contrast, and listening orientation.

## Uncertainty Contract

- Put a certain, approved removal in `cuts[]`.
- Put likely but consequential redundancy in `review_candidates[]` with `status: pending`.
- Keep passages that may carry emotion, connection, or necessary setup unless a human approves the cut.
- Record a rejected suggestion in `review_candidates[]` with `status: rejected` when the audit trail is useful.
- Never render `review_candidates[]`. Move an approved candidate into `cuts[]` and remove it from the candidate list.

## Post-edit Four Checks

Judge the rendered candidate rather than trusting the EDL:

1. Sentence integrity: no fragment, missing subject, broken causal phrase, doubled syllable, or clipped onset.
2. Logic integrity: every reference, number, example, callback, qualification, and conclusion retains its setup.
3. Pacing integrity: the pause hierarchy remains audible and no stretch becomes mechanically dense or unexpectedly slow.
4. Persona integrity: hesitation, laughter, emotion, emphasis, and speaker character remain natural.

Any failed or unresolved check keeps the episode out of release-ready state.

## Synthetic Decision Examples

- Keep `然后` in “我先核对数据，然后解释结论” because it carries sequence.
- Keep the earlier of two takes when the later take loses a qualification, even though the later take appears last.
- Keep a short setup sentence when a later pronoun, joke, or conclusion depends on it.
- Remove or compress dead air attached to an abandoned take, while retaining a deliberate pause before a conclusion.
- Put a repeated explanation with a different emotional beat in `review_candidates[]` instead of deciding automatically.
