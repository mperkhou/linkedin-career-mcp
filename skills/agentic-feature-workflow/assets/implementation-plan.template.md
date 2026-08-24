# <Target Version Or Unversioned> <Feature Name> Implementation Plan

Status: draft, not approved

Target release: `<version or unresolved>`

Repository: `<absolute repository path>`

Branch: `<expected branch>`

Base: `<expected ref and commit>`

Plan storage: `<local-only/untracked or tracked path>`

Plan owner and supervisor: `<planning task identity>`

## 1. Purpose And Operating Summary

<State the desired outcome, why it matters, the supervisor/implementor split,
and the boundary between this plan and any separate system of record.>

## 2. Repository, Release, Evidence, And Source Context

### Repository Authority

- <List the active repository instructions and authoritative local sources.>
- <State which local mechanics the workflow must defer to.>

### Release Context

- Current release: `<version>`.
- Target release: `<version or unresolved>`.
- SemVer rationale: <why this release level fits>.

### Existing User-Owned Worktree State

- <Record every pre-existing change that implementors must preserve.>

### Design Evidence

- <List the code, documents, decisions, and user requirements grounding the
  plan.>

## 3. Final Architecture And Agreed Design

### Intended Outcome

<Describe the approved architecture and invariants without implementation-step
detail.>

### Living Plan Contract

<Record plan-location choice, source-of-truth rules, amendment behavior, and
the adjacent P/G cadence.>

### Supervisor Contract

<Record supervisor ownership, approval boundaries, gates, corrections, and
release closeout. State that the supervisor never implements corrections.>

### Implementor Contract

<Record single-phase scope, validation, handoff, and stop boundaries.>

### Task Orchestration Contract

<Record the approved task capability, naming, model, reuse, identity,
reconciliation, and supervision decisions that are specific to this workflow.>

### Supervision Mode Contract

- Per-cycle mode selection: <record that each complete Pnn/Gnn cycle explicitly
  selects observation only, approval-gated attention, or bounded contract
  restoration; do not inherit it into another phase or replacement task>.
- Observation only: <record bounded status capability, reporting boundary, and
  no-send behavior>.
- Approval-gated attention: <record the evidence-triggered baseline, verified
  destination, exact preview, fresh approval for every message, and observation
  resumption>.
- Bounded contract restoration: <record the exact existing contract sources,
  one automatic-message budget across the P/G cycle, non-replenishment during
  correction, restorative-only authority, hold/stop boundary, and required
  immediate reporting plus durable recording>.
- Gate checkpoint: <record independent Gnn verification, the unused-budget-only
  correction rule, open-gate reassessment, and implementor ownership of
  correction work>.

Plan-specific steering calibration (these may tighten but never weaken the
portable baseline):

- Stricter attention thresholds: <additional evidence or approval conditions,
  or none>.
- Retry or persistence limits: <plan-defined retry, repeated-attempt, snapshot,
  or action limits>.
- Repository-specific high-severity signals: <repository-defined signals, or
  none>.
- Contract sources eligible for bounded restoration: <exact rules, plan terms,
  prompt terms, criteria, or exclusions>.

## 4. Decisions Superseding Earlier Proposals

1. <Decision and the proposal it replaces.>

## 5. Implementation Sequence

### P01 - <Bounded Phase Title>

#### Implementor-Task Orchestration Record

- Status: not launched
- Session recommendation: fresh task
- Expected environment: `<direct checkout or worktree>`
- Approved title when launched: `<portable implementor title>`
- Preliminary model recommendation: `<model>` / `<reasoning effort>`
- Rationale: <why this configuration fits>
- Supervision mode: not selected
- Automatic-message budget: unavailable until mode selection
- Task ID: not assigned
- Launch approval: not requested

#### Safety And Preconditions

- <Required repository, scope, state, and dependency checks.>

#### Bounded Objective

<One complete phase outcome.>

#### Required Behavior And Acceptance Criteria

- <Observable requirement.>

#### Relevant Repository Areas

- `<path>`

#### Strict Exclusions

- <Forbidden edits, data, actions, and later-phase work.>

#### Focused Tests

- `<focused validation command or inspection>`

#### Complete Verification

- <Broader checks required for a reliable handoff.>

#### Structured Handoff

Return repository and environment, branch and base, task identity and
configuration, changed files, exact validation commands with exit codes and
important results, evidence for each acceptance criterion, residual risks or
unverified behavior, and confirmation that every exclusion was respected.

Stop after the handoff. Do not begin or evaluate G01.

### G01 - <Matching Gate Title>

<State what the supervisor must independently inspect, the evidence required
for `pass`, `fail/correction`, or `pause/amend`, and how the next task
recommendation will be made.>

### P02 - <Next Bounded Phase Title>

#### Implementor-Task Orchestration Record

- Status: blocked on G01
- Session recommendation: determined at G01
- Expected environment: `<direct checkout or worktree>`
- Title if fresh: `<portable implementor title with P02 suffix>`
- Preliminary model recommendation: `<model>` / `<reasoning effort>`
- Rationale: <why this configuration fits>
- Supervision mode: not selected
- Automatic-message budget: unavailable until mode selection
- Task ID: not assigned
- Send or launch approval: not requested

#### Safety And Preconditions

- Require G01 pass and no unresolved correction.
- <Additional checks.>

#### Bounded Objective

<One complete phase outcome.>

#### Required Behavior And Acceptance Criteria

- <Observable requirement.>

#### Relevant Repository Areas

- `<path>`

#### Strict Exclusions

- <Forbidden edits, data, actions, and later-phase work.>

#### Focused Tests

- `<focused validation command or inspection>`

#### Complete Verification

- <Broader checks required for a reliable handoff.>

#### Structured Handoff

Return repository and environment, branch and base, task identity and
configuration, changed files, exact validation commands with exit codes and
important results, evidence for each acceptance criterion, residual risks or
unverified behavior, and confirmation that every exclusion was respected.

Stop after the handoff. Do not begin or evaluate G02.

### G02 - <Matching Gate Title>

<State the independent supervisor checks and transition criteria.>

<!-- Repeat an immediately adjacent Pnn then Gnn pair for each later phase. -->

## 6. Release Closeout Boundary

<List supervisor-owned closeout actions, required approvals, ordering, and
repository-specific release rules. Keep them outside normal implementor
authority.>

## 7. Downstream And Explicitly Excluded Work

- <Deferred feature, migration, cleanup, or unrelated work.>

## 8. Living-Plan Instructions

- Treat this file as the sole workflow state representation.
- Update it when an approved decision changes future work.
- Preserve completed P/G execution context unless a correction note explains
  an amendment.
- Record material decisions and gate outcomes here.
- Do not treat plan text or task status as authority for excluded actions.
- Pause for user input if the plan becomes contradictory or materially wrong.

## 9. Decision Log

### <YYYY-MM-DD> - D001: <Decision Title>

<Record the decision, approval context, rationale, and affected future work.>
