# ADR 0004: Orchestrate Local Workflows from the Flask Tracker

## Status

Accepted.

## Date

2026-07-01

## Context

The project started with MCP tools and CLI commands as the main automation
surface. As the tracker became the daily operating UI, more of the useful work
moved next to the data the user is reviewing: seeded application rows, cleaned
JODs, generated resume variants, ATS diagnostics, cover letters, notes, and
application status.

The local workflows also became longer running. Seeding may fetch multiple
public postings, v1 generation calls the draft-generation LLM, v2 refinement
calls GLM 5.2, Codex manual pass builds and evaluates a review bundle, and Codex
highlighting can run across selected resumes. Running those synchronously inside
normal Flask requests would make the tracker feel blocked and would hide the
progress needed for debugging.

The system needs tracker-triggered workflows to:

- start from the user's current review context
- preserve explicit user choice over which expensive steps run
- make v1 plus v2 the main resume path
- keep v1-only generation available as an intentional alternate path
- allow v2 to be created or rerun from the UI
- stream progress for long-running local commands
- avoid turning the local tracker into a remote job runner or submission system

## Decision

Use the Flask tracker as a local orchestration surface for trusted local
workflows.

Tracker actions create background action runs and stream command output into the
tracker status panel. The background action model is intentionally small:
actions run in local background threads, keep a bounded in-memory message log,
and report status through `/actions/status`. This is sufficient for a local
single-user app and avoids introducing a queue service or public deployment
assumptions.

The tracker exposes two orchestration surfaces.

The Add popup can seed public job postings and optionally continue the workflow
for the newly seeded rows. The user chooses a job count, posting-age window, and
which follow-up stages to run: v1 draft generation, v2 refinement, Codex manual
pass, and Codex highlighting. The seed command output is parsed for newly seeded
job IDs, and follow-up commands run only for that seeded batch.

The main tracker Actions menu operates on selected rows. It exposes explicit
resume actions, including:

- main v1 plus v2 resume workflow
- v1-only draft generation
- v2 refinement or rerun
- Codex manual pass variant generation
- Codex highlighting
- ARO regeneration and draft-to-ARO sync

The main operator path is v1 plus v2. The v1-only action remains available for
debugging, low-cost iteration, and deliberate first-draft-only runs. V2
refinement is also available as a standalone action so an existing v1 draft can
receive a first v2 or rerun and replace an existing v2.

## Consequences

Positive:

- The user can start workflows from the tracker state they are already
  reviewing.
- Expensive stages are explicit toggles or selected actions instead of hidden
  side effects.
- Seeded-batch workflows can run only against newly inserted rows instead of
  accidentally processing all active rows.
- Long-running actions remain observable through the tracker status panel.
- The Make/CLI targets remain the stable automation contract while the tracker
  provides a more ergonomic local control surface.
- V1-only, v2 rerun, manual pass, and highlighting workflows remain independently
  callable for debugging and review.

Tradeoffs:

- The Flask app now owns more orchestration state and validation rules.
- Background action state is in memory, so it is intentionally not durable
  across tracker restarts.
- The tracker must keep UI labels, Make targets, and background command
  construction aligned.
- Workflow dependency rules must be explicit, for example v2 and manual pass
  require a v1 draft context.
- This design is suitable for a local single-user app, not a public multi-user
  job execution service.

## Alternatives Considered

### Keep Workflows CLI-Only

Rejected. CLI-only workflows are useful for automation, but they force the user
to switch away from the tracker context where job rows, variants, ATS deltas,
notes, and review decisions are visible.

### Run Long Workflows Synchronously in Flask Requests

Rejected. Synchronous requests would block the UI, make progress hard to inspect,
and obscure failures during LLM-backed or Codex-backed workflows.

### Always Run Every Stage After Seeding

Rejected. Manual pass and highlighting are useful but expensive and sometimes
unnecessary. The tracker should make them deliberate choices.

### Overload the V1 Draft Action to Mean V1 Plus V2

Rejected. The main workflow should be explicit, and v1-only generation should
remain available for focused debugging and lower-cost runs. Separate actions
make the operator intent visible.

## References

- [Architecture](../architecture.md)
- [ADR 0003: Store Resume Refinements as DB-Backed Variants](0003-db-backed-resume-variants.md)
- [4.0.0 release notes](../release-notes/4.0.0.md)
