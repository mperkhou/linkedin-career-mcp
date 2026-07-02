# ADR 0003: Store Resume Refinements as DB-Backed Variants

## Status

Accepted.

## Date

2026-07-01

## Context

The JOD-target ARO workflow produces useful first-draft resumes, but refinement
is not a purely mechanical overwrite. A second model pass can improve structure,
wording, and role alignment, yet it can also introduce unsupported claims,
overfit to noisy ATS missing terms, or make a weaker editorial choice than the
first draft.

The earlier manual passthrough workflow also showed that human or Codex review
can produce a valuable third draft, but overwriting the first draft makes it
hard to compare outcomes, debug evidence decisions, or reverse a selection
after inspecting the rendered HTML/PDF.

The system therefore needs resume refinement to:

- preserve the original first draft for every job
- store second-pass critique, validation, and ATS evidence next to the output
- let the user compare v1, v2, and manual drafts before choosing one
- make selected resume links reversible without deleting alternatives
- keep generated artifacts in SQLite instead of sidecar audit files
- avoid automatically promoting an LLM refinement over the first draft

## Decision

Store resume refinements in `application_resume_variants` as versioned,
job-scoped variants.

The production variant keys are:

- `v1`: the first-draft ARO, rendered HTML, rendered PDF, and ATS fields
- `v2`: the GLM second-pass refinement and its critique/validation metadata
- `manual`: a Codex manual pass that reviews v1, v2, the v2 critique trail, ATS
  diagnostics, JOD text, prompt JOD text, and master-resume evidence

Each variant stores the ARO YAML, HTML, PDF bytes, filenames, MIME metadata,
ATS scores, ATS missing terms, ATS diagnostics, evidence packet, critique
prompt/response, parsed critique, validation report, accepted and rejected
patches, external critique metadata, model metadata, source label, parent
variant, and timestamps when available.

The `applications` row keeps the active resume fields used by normal tracker
links. It also stores `selected_resume_variant`. Selecting `v1`, `v2`, or
`manual` copies that variant's ARO, rendered artifacts, and ATS fields into the
active columns and updates `selected_resume_variant`. It does not delete or
mutate the other variants.

The main resume workflow creates or refreshes v1, then stores v2 without
selecting it. The v1-only workflow remains available for deliberate first-draft
runs. The v2 refinement workflow can create v2 if it is missing or replace the
existing v2 when rerun. The manual pass stores a manual variant and also leaves
selection unchanged until the user explicitly chooses it.

## Consequences

Positive:

- The first draft remains available as a stable baseline.
- The user can compare v1, v2, and manual variants before changing active resume
  links.
- Variant selection is reversible because selection copies from stored variants
  into active columns instead of destroying prior drafts.
- ATS diagnostics, critique output, accepted changes, rejected changes, and
  unsupported claims stay tied to the exact variant they explain.
- Manual review and Codex review use the same storage model as automated v2
  refinement.
- The tracker can expose variant-specific HTML/PDF downloads while preserving
  one active resume link for normal use.

Tradeoffs:

- SQLite stores more duplicated HTML/PDF/ARO data per job.
- Schema migrations and backfills are more complex than a single active resume
  column set.
- The UI must clearly distinguish stored variants from the selected active
  variant.
- Rerunning v2 or manual generation needs explicit replacement semantics for
  that variant key.
- Tests need to cover both variant storage and active-column synchronization.

## Alternatives Considered

### Overwrite the First Draft

Rejected. Overwriting v1 made it difficult to diagnose whether the second pass
helped, compare ATS deltas, or return to a stronger first draft.

### Store Refinement Audits as Sidecar Files

Rejected. Sidecars are useful for development traces, but the tracker database
is the operating source of truth. Storing critique and validation details in
SQLite keeps review, downloads, comparisons, and reruns DB-derived.

### Automatically Select v2 After Generation

Rejected. The second pass is valuable, but it is still model output that may
overreach or make editorial tradeoffs the user does not want. The tracker should
show v2, not silently promote it.

### Treat Manual Pass as a Special Overwrite

Rejected. Manual pass output needs the same reversibility and comparison
behavior as v2. Storing it as `manual` keeps all resume drafts under one model.

## References

- [Architecture](../architecture.md)
- [4.0.0 release notes](../release-notes/4.0.0.md)
- [ADR 0001: Adopt JOD-Target ARO Rewrite Workflow](0001-adopt-jod-target-aro-rewrite-workflow.md)
