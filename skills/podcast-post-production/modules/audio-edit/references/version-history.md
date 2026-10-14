# Version history

## Version

- Skill release: `v1.5.1`.
- Editorial branches: `casual-non-rigorous` and `rigorous-explainer`.
- Both branches use the shared staged-transcript, editorial-decision, pause-shaping, and post-edit QA workflow. Keep their content tolerance and pacing profiles distinct.
- v1.4 adds ChatCut-aware reference roles, bidirectional source alignment, complete project-local difference memory, and a local acoustic fallback when a rendered reference has no usable transcript.
- v1.4.1 standardizes every StepFun endpoint on the `https://api.stepfun.com/step_plan/v1` API base.
- v1.5 adds an explicit reference-author approval state and a guarded path for promoting repeated, non-sensitive qualitative patterns into a named branch's personal defaults.
- v1.5.1 hardens local rendered-reference comparison with direct baseline-to-reference alignment, EDL-backed source mapping, staged-transcript support, safe source-tail exhaustion, 0.1-second micro-edit retention, and duration reconciliation.
