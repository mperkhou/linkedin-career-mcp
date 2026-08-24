# ADR 0007: Split Agentic Workflow Bootstrap and Execution

## Status

Superseded for new workflows by
[ADR 0008: Supervisor-Managed Living Plans](0008-supervisor-managed-living-plans.md).
Retained as historical evidence for compatible machine-tracked workflows.

## Context

The 4.7.0 and 4.9.0 workflow controller made larger Codex-led repo changes more
repeatable by combining P-step execution, G-step reassessment, runtime tracker
state, and read-only evidence routes. In practice, one ambiguity remained: the
same skill both initialized new workflows and executed existing ones.

That made it easier for a session to start implementation before a committed
plan existed, or to treat ignored runtime files as if they were the release
plan. The work-repo pattern suggested a cleaner split: a bootstrap layer creates
the canonical plan and binds runtime state to it, while an executor layer only
runs or resumes that already-authorized plan.

## Decision

Add `agentic-workflow-init` as a thin bootstrap skill and keep
`agentic-workflow-controller` as the executor/resumer skill.

The bootstrap skill creates one committed plan under `docs/agentic-workflows/`,
adds the initial same-version changelog bullet, commits those bootstrap
artifacts, initializes ignored runtime tracker state, binds that state to the
plan path, digest, revision, branch, target version, and bootstrap commit, then
hands off a kickoff prompt to the controller.

The controller executes existing plans. Runtime state is a cursor and evidence
log, not a second plan. Gate amendments may change only incomplete/future work;
they must update the committed plan, add a same-version changelog bullet, commit
those changes, and rebind the tracker digest/revision.

Workflow state is hardened with attempted-step tracking, immutable completed
step IDs, plan digest validation, atomic JSON writes, lock files, path
confinement, recursive secret rejection, and sanitized artifact manifests.

## Consequences

- Larger repo changes require one extra bootstrap step, but the result is more
  reproducible and easier to resume in a fresh Codex session.
- The committed plan becomes auditable release history; ignored runtime state
  stays small and disposable.
- Tracker JSON cannot grant permission to push, merge, tag, mutate live tracker
  DB rows, or touch external systems. Those actions still require user/workflow
  authorization.
- Heavy or sensitive evidence moves outside the repository tree, while
  repo-local runtime state stores only sanitized summaries, hashes, route
  prompts, and manifests.

## Related Links

- [Agentic workflow docs](../agentic-workflows/README.md)
- [Agentic workflow init skill](../../skills/agentic-workflow-init/SKILL.md)
- [Agentic workflow controller skill](../../skills/agentic-workflow-controller/SKILL.md)
- [ADR 0006: Agentic workflow evidence routes](0006-agentic-workflow-evidence-routes.md)
- [ADR 0008: Supervisor-Managed Living Plans](0008-supervisor-managed-living-plans.md)
