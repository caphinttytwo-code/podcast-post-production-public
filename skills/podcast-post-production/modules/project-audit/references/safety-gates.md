# Safety Gates

## Gate 1: inventory only

Resolve each root to an absolute path, reject broad or missing targets, and write the proposed retain, quarantine-candidate, and pending sets. No project file moves or deletions are allowed at this gate.

## Gate 2: recoverable quarantine

Proceed only after the user approves the exact candidate set. Recheck that every source still matches its inventory size and hash. Move into a uniquely named quarantine on the same volume when practical, preserve relative paths, and write a post-move manifest. Never treat quarantine as deletion approval.

## Gate 3: permanent deletion

Proceed only after a separate explicit instruction to permanently delete the resolved quarantine or named files. Reconfirm that the target is not a root, home directory, workspace root, source directory, or unresolved variable/glob. Record every deleted path and its last verified hash, then measure actual free-space change.

If backup evidence is only `user_confirmed` or `historical_record_only`, say so. Do not relabel it as `hash_verified`.
