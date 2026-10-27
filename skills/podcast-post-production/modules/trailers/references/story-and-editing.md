# Story and editing gates

## Candidate score

Score each candidate 0–2 on every dimension. Reject any candidate with `context` or `payoff` equal to 0.

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| Hook | generic | interesting | immediate concrete tension |
| Context | cannot stand alone | needs small setup | self-contained |
| Escalation | flat | one turn | clear progression/reversal |
| Payoff | trails off | informational close | emotional or conceptual resolution |
| Visual continuity | distracting | repairable | natural speaker/reaction coverage |
| Edit safety | many clipped phrases | a few risky joins | clean breaths and complete clauses |

Prefer candidates scoring at least 9/12.

## Story spec

Record this before cutting:

```text
Candidate:
Source time range:
Cold open:
Setup:
Escalation:
Payoff:
Why it stands alone:
Required context:
Risky cut points:
Title:
Subtitle:
Target duration:
```

Also record purpose, audience, primary platform, core information, cold-viewer promise, transcript coverage, must-keep/remove constraints, and visual/subtitle expectations. If the opening starts with a cold hook, repair who, what, why, and credibility immediately afterward.

For emotional material, retain the cause, quote, or silence that earns the reaction. For book or product stories, establish the person/problem and viewer value before the item or sales close.

## Cut rhythm

- Start 4–12 frames before the first meaningful consonant when room tone or breath is needed.
- End after the sentence, reaction, or resolving beat. Do not cut on the final syllable.
- Keep EDL boundaries as `HH:MM:SS.mmm` strings copied from the transcript. Parse them programmatically; do not calculate minute-to-second conversions by hand.
- Round-trip parsed timestamps back to `HH:MM:SS.mmm` and compare them with the transcript before rendering. A 20-second conversion error can still produce a technically valid but semantically wrong clip.
- Add `first_words` and `last_words` to the cut review record so the boundary can be checked against speech, not only numbers.
- Prefer the longest clean continuous source interval. Merge adjacent selected intervals when the source gap is 0.5 seconds or less unless the gap contains an intentional removal.
- Do not split a continuous example, explanation, and payoff merely to create a faster rhythm. Preserve the original exchange when its accumulated responses create the meaning.
- Use J/L cuts only when they improve comprehension and do not falsify reactions.
- Use 0.20-second video/audio crossfades as a default repair between non-contiguous passages.
- Crossfades consume boundary handles. Keep speech outside the last transition-length portion of the outgoing clip and the first transition-length portion of the incoming clip whenever possible.
- Shorten a crossfade when it smears plosives or overlaps two speakers; lengthen only when ambience needs blending.
- Do not use a dissolve to conceal an incoherent jump. Restore context or reject the join.

## EDL audit before render

For every clip, print and inspect:

```text
index | source in | source out | duration | first words | last words
```

- Reject boundaries whose normalized timestamp differs from the intended transcript time.
- Reject a clip that starts on a meaningful consonant or ends on the final syllable.
- Warn when sequential source intervals are separated by 0.5 seconds or less; merge them by default.
- Count joins. Fewer complete intervals are preferable to many technically smooth micro-cuts.
- For a cold open that reappears later in source order, skip its repeated main-body occurrence cleanly and retain a full clause on both sides.

## Subtitle policy

- Burned source subtitles: keep the entire source image visible; do not cover them with the frame.
- Replacement subtitles: normalize Chinese punctuation, names, numbers, and line breaks; use at most two lines; keep safe margins.
- Never show both source and replacement subtitles simultaneously.
- Subtitle timing follows speech meaning, not merely ASR token boundaries.

## Audio policy

- Preserve stereo when it contains meaningful room or speaker separation; otherwise mono-to-stereo is acceptable.
- Apply loudness treatment once, at final assembly. Avoid repeated normalization across intermediates.
- Listen before and after every join for clicks, doubled words, clipped breaths, and ambience jumps.
- Review at least one second before and after every join at normal speed; replay uncertain joins at reduced speed only as a diagnostic.
- Do not remove pauses that carry emotion or make the speaker sound unnaturally fast.
