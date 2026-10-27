# Non-executable planning format 1.0

Use only when deterministic duration/dependency checks help the requested plan. Prose maps and summaries do not require conversion to JSON. This format is separate from, and cannot be rendered as, existing EDLs or multitrack plans.

```json
{
  "schema_version": "1.0",
  "revision": "proposal-01",
  "sources": [{"id": "main", "sample_rate": 48000, "frames": 4800000}],
  "base": {"source_id": "main", "start_frame": 0, "end_frame": 4800000},
  "runtime": {"kind": "hard", "target_seconds": 60, "tolerance_seconds": 0},
  "items": [{"id": "S01", "action": "remove", "start_frame": 480000,
    "end_frame": 2400000, "reason": "Synthetic proposed digression removal; unique example would be omitted."}],
  "recommended_ids": ["S01"],
  "choices": {},
  "protected_ranges": [{"start_frame": 0, "end_frame": 480000}],
  "units": []
}
```

The example declares 100 seconds, recommends removing 40 seconds, and reports a 60-second proposal. With no user choices the recorded-choice estimate is still 100 seconds. Both are estimates from declared frames; neither grants execution.

Sources have unique IDs, positive integer sample rates/frame counts and optional `path` + `sha256`. Supply both to read and match actual bytes. Without them the checker explicitly records `declared_metadata_only`; it never decodes metadata or proves synchronization. Paths resolve against the plan file; actual source/review files must stay outside the Skill. All ranges are half-open integer frames on their source clock; consumed ranges and anchors use the selected base clock.

Actions:
- `keep` / `remove`: `start_frame` and `end_frame` inside the selected base.
- `replace`: that same consumed range plus recorded `segments`.
- `insert`: `at_frame` on the base plus recorded `segments`.
- `move`: one segment on the base clock, consumed there and inserted at `at_frame` outside itself. A rerecord outside a shortened base is an `insert`, not a move from inside that base.

Each segment has `source_id`, `start_frame`, `end_frame`. Insert/replace/move defaults to `block_mode: whole` with exactly one contiguous segment. Fine mode records `block_mode: fine` and an exact-scope `fine_review_ref` (path/hash); without it the checker reports a scope conflict. A whole grouped block gets `buffer_frames` before and after once, on the base clock. No default buffer is added.

`fixed_extra_frames` counts only content not already in the selected base or insertions. `transition_overlap_frames` subtracts a separately justified total of actual overlapping samples, not sequential fades. Durations across source sample rates use rational arithmetic; this does not authorize resampling or multitrack clock repair.

`recommended_ids` names one proposed option set, not all mutually exclusive alternatives. Supply separate plans for meaningful alternatives. `choices` maps IDs to `choice: apply|keep|pending|custom`. Apply/keep binds both `item_sha256` and `source_context_sha256` returned by an initial check: one identifies the exact item and the other its source metadata and selected base. Apply also links `review_ref: {path, sha256}` to the real decision record. Hashes establish current bytes, not human authorship. The agent must read the record. Keep overrides a recommendation and protects its original consumed range; custom choices remain unresolved until their exact revised ranges are confirmed. Comments may be retained as `note` and are not approval.

`protected_ranges` protect original base content. Selected keep actions protect their range. A selected item may have `requires: [other-item-id]`; missing selected conditions are reported rather than automatically applied. Optional `units` have unique IDs, source-frame ranges and `depends_on: [unit-id]` for known content dependencies. If a retained unit refers to a fully removed prerequisite, the checker reports a dangling reference. It does not infer semantic dependencies or certify partially edited units; inspect those in the actual plan/audition.

Overlapping remove-only proposals are unioned for arithmetic. Overlapping replacements/moves and insertions inside consumed interiors are conflicts requiring a combined decision. Hard-target overrun and unresolved recommendations stay `NEEDS_REVIEW`. Soft targets report their upper-target relationship without silently changing a choice.

Run with the package's selected Python:

```
python modules/editorial-plan/scripts/check_plan.py /project/plan.json --report /project/check-01.json
```

The report must be fresh, outside the package and distinct from all referenced source/review files. Exit 0 = checked arithmetic/constraints only, 2 = needs review or hard-target tradeoff, 1 = invalid inputs or evidence. Reports always have `approval_generated: false`, `executable: false` and `audio_modified: false`. No network, ASR, audition renderer or editor is called.
