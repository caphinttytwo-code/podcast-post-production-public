# Project index and handoff

The optional `project-index.json` is a sidecar index. It does not replace the module's EDL, batch manifest, revision manifest, audit inventory, raw ASR or approval record. Existing projects may continue directly with their module-specific files.

Run `python scripts/project_index.py --spec project/index-spec.json --output project/project-index.json` relative to the package. Relative file paths in the spec resolve against its directory. Existing outputs are refused, and the destination must be outside this entire package. Each referenced file is read and hashed; missing or changed files stop indexing.

Spec fields:
- `workflow`: audio-edit, video-conform, trailers, locked-revision, or project-audit.
- `module_version`: the specific module revision used for this project.
- `inputs`: records with explicit `role`, `path`, and optional expected `sha256`.
- `artifacts`: the same fields plus an explicit `timebase`: source, reference, final, or non-timed.
- `review_refs`: paths to existing review/approval records. Their hashes identify records; their contents remain authoritative and are not converted to approval by indexing.

Index schema_version is 1.0. The writer adds actual file identities and skill_version; approval_generated is always false. Only index records change; referenced files are untouched. Indexes contain local paths and can reveal content identities, so keep them with private project evidence, not in a release package.

Before a handoff, identify the exact prior delivery and its hash, the role of every source/reference, its controlling timebase, the required mapping, and the next requested operation. Audio to conform uses the approved complete reference; conform to trailers requires the specified master/version and authorized story selection. A master to locked revision requires exact mutable surfaces. Do not create a synthetic mapping from ASR candidates or interpret a previous module's approval as authorization for a new operation.
