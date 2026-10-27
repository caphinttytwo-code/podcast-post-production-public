# Multitrack Join QA

- Enumerate every source audio stream and preserve stream order, channel layout, sample rate, language metadata, and default disposition unless explicitly unlocked.
- Use frame-aligned picture boundaries. Give speech enough handle to keep complete consonants, vowels, breaths, and room tone.
- Apply identical fade timing to every retained audio track. A common localized treatment is a short non-overlapping fade-out/fade-in; use a true crossfade only when overlapping source context is authorized.
- Do not hide an uncertain boundary with a longer fade. Recheck the transcript, waveform, audio, and neighboring frames.
- Validate every join on every track for clipped words, clicks, silence gaps, duplicated ambience, and channel changes.
- Compare source and output decoded audio outside the authorized join when the codec and render path make that comparison meaningful.
- Technical waveform and decode checks do not replace listening. Record the human full-length gate separately.
