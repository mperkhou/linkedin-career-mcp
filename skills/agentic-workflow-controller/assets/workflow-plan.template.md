# __WORKFLOW_ID__

Release: `__VERSION__`

Objective: __OBJECTIVE__

## Operating Rules

- Follow root `AGENTS.md` before editing, validating, committing, pushing, or
  closing out release work.
- Use runtime state in `tmp/agentic-workflows/__WORKFLOW_ID__/tracker.json` as
  the local cursor.
- Treat P steps as implementation phases and G steps as reassessment gates.
- At each G step, compare completed work against the remaining plan and either
  continue, amend the future steps, or pause for user input.
- Do not mutate live tracker DB rows, generated artifacts, remote branches,
  PRs, tags, scheduled jobs, or external systems unless explicitly authorized by
  the workflow or user.

## Steps

### P01 - Readiness Check

Confirm branch, worktree, release version, and intended scope before editing.

### G01 - Scope Reassessment

Review P01 evidence against the rest of the plan. Continue, amend, or pause.

## Pause Conditions

- The remaining plan no longer matches the implementation evidence.
- The next step would change product behavior beyond the stated objective.
- The next step would mutate live tracker data or generated artifacts without
  explicit approval.
- Validation failure requires a broader refactor than the plan authorized.
