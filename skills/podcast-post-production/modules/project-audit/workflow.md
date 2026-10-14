# Media Project Audit Cleanup

Produce a verifiable cleanup plan while keeping every mutation behind an explicit approval gate.

## Operating contract

- Start read-only. Require one or more exact project roots; do not infer a home directory, workspace root, mounted volume, or wildcard target.
- Use `scripts/inventory_project.py` to write a current inventory outside the scanned roots when possible. Unmatched files default to `pending`, never to deletion.
- Distinguish a current file read and hash from a historical manifest, and distinguish a user statement that a backup exists from a backup that was actually read and matched.
- Read [references/safety-gates.md](references/safety-gates.md) before proposing quarantine, movement, or deletion.
- This skill has no deletion script. Any move or permanent deletion requires a new explicit authorization naming the resolved targets.

## Workflow

1. Inventory exact roots, recording size, modification time, classification, SHA-256 when requested, and media stream metadata where available.
2. Explain classification rules and output separate retain, quarantine-candidate, and pending lists. Retain rules override all other matches.
3. Use `scripts/verify_backups.py` only when both source and backup inventories were produced from files actually read.
4. Present the plan and stop for approval before moving anything. Prefer a recoverable quarantine with a versioned manifest.
5. After an approved move, create a fresh inventory and compare it with `scripts/compare_manifests.py`.
6. Permanent deletion requires a second explicit approval and a final record of resolved paths, prior hashes, deletion time, and measured free-space change.

## Status language

- `hash_verified`: both files were read and their current hashes match.
- `user_confirmed`: the user says a backup is usable; this is not technical verification.
- `historical_record_only`: a prior hash or manifest exists but was not refreshed.
- `pending`: no cleanup rule or proof supports a stronger classification.

## Resources

- [references/safety-gates.md](references/safety-gates.md): authorization and deletion boundaries.
- [references/manifest-schema.md](references/manifest-schema.md): inventory and comparison fields.
- `scripts/inventory_project.py`: read-only filesystem/media inventory and classification.
- `scripts/compare_manifests.py`: before/after member-set and hash comparison.
- `scripts/verify_backups.py`: current source/backup manifest matching.
