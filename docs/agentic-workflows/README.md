# Agentic Workflows

For new multi-phase repository changes, use
`$agentic-feature-workflow`. The active approach is a supervisor-managed,
living Markdown plan: the supervisor controls planning, task selection, exact
approval previews, gates, corrections, and release closeout, while a separate
user-owned implementor task receives exactly one bounded P phase.

Every P phase is immediately followed by an independent G gate. The plan is
the sole workflow source of truth; the active workflow does not require a
machine tracker, JSON state, plan digest, rebind operation, or workflow
runtime. See [ADR 0008](../adr/0008-supervisor-managed-living-plans.md) for the
architecture decision and the
[`agentic-feature-workflow` skill](../../skills/agentic-feature-workflow/SKILL.md)
for the operating contract.

## Active Workflow

1. Draft one bounded living plan conversationally, resolve contradictions, and
   obtain explicit approval of its content.
2. Choose whether the approved plan is local-only or tracked in Git; do not
   infer that storage choice.
3. The supervisor dispatches one complete P phase to a separate implementor
   task only after showing the exact task action and receiving approval.
4. The implementor returns its structured handoff and stops before the matching
   G gate.
5. The supervisor independently evaluates the G gate, records its decision in
   the living plan, and only then prepares a correction or the next phase.

## Supervision Modes

Each complete P/G cycle selects one mode:

| Mode | Architectural boundary |
| --- | --- |
| **Observation only** | Bounded read-only observation with no implementor message. |
| **Approval-gated attention** | Every message has a verified destination, exact preview, and fresh approval. |
| **Bounded contract restoration** | One non-replenishing message may restore an existing approved contract; it cannot become general autonomous authority. |

The detailed evidence thresholds, scenarios, message budget, and correction
rules are canonical in the
[implementor-task orchestration reference](../../skills/agentic-feature-workflow/references/implementor-task-orchestration.md).

## Legacy Compatibility And Historical Evidence

`agentic-workflow-init` and `agentic-workflow-controller` remain available
for historical, machine-tracked workflow compatibility. Do not use them to
scaffold a new workflow. Their tracker-based bootstrap, evidence-route, and
plan-binding model remains documented as history in
[ADR 0006](../adr/0006-agentic-workflow-evidence-routes.md) and
[ADR 0007](../adr/0007-agentic-workflow-bootstrap-and-plan-binding.md), both
superseded for new workflows by ADR 0008.

Historical release notes and the committed
[4.8.0 workflow example](4.8.0-render-stamats-vida.md) remain preserved.

## Planned Public Rebuild

- These user-owned planning records are not current implementation authority.
  Their execution cadence is reconciled with the active living-plan workflow,
  but each future release still requires its own approved living plan and exact
  task-action approvals before work begins.
- [5.0.0 workspace separation](5.0.0-public-rebuild-workspace-separation.md) is
  the detailed private-migration plan. Work is developed in a parallel copy,
  merged through the existing private project repository, and accepted only
  after clean-main cutover and live use of the original operational checkout
  against an external workspace. One implementor receives one bounded P step at
  a time, every G gate remains with the supervisor, and PR, merge, cutover,
  soak, acceptance, and tagging remain supervisor-owned closeout decisions.
- [5.1.0 Review-page comparison
  stub](5.1.0-review-resume-variant-comparison.md) reserves the next minor
  release for two explicit resume-version selectors and pair-driven diff
  rendering without changing the stored selected resume variant.
- [5.2.0 rolling roadmap](5.2.0-public-rebuild-roadmap.md) preserves the
  remaining public-rebuild phases as planning input. It is not implementation
  authority; after 5.1.0, its selected scope becomes the detailed 5.2.0 plan
  and its deferred remainder starts the fledgling 5.3.0 roadmap. Each private
  5.x release repeats the one-P/one-gate cadence plus the implementation-copy,
  PR, operational cutover, user-soak, and acceptance-before-tag cycle.
