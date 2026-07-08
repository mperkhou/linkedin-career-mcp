---
name: agentic-workflow-controller
description: Use when Codex should run or continue a staged implementation workflow with P-step execution prompts, G-step reassessment gates, a local JSON tracker, pause conditions, validation evidence, and release closeout state. Trigger for agentic workflow controller requests, living implementation plans, P01/G01 style plans, workflow tracker JSON, or requests to resume a gated multi-step repo workflow.
---

# Agentic Workflow Controller

## Overview

Use this skill to execute a living plan that has implementation phases such as
`P01`, `P02`, and reassessment gates such as `G01`, `G02`. The controller keeps
the plan explicit, records local workflow state, and pauses when the next action
requires user judgment or external approval.

Follow the repository root `AGENTS.md` before using this skill. This skill does
not replace repo safety rules, release closeout, tracker database caution,
resume-evidence discipline, or explicit user authorization.

## State Model

Keep two kinds of state:

- **Tracked templates and finalized plans**: stable files committed to the repo.
- **Runtime state**: ignored files under `tmp/agentic-workflows/<workflow_id>/`.

The runtime state is a resumable cursor, not a release artifact. It records the
current step, completed steps, reassessment gates, validation evidence, branch
or PR references, artifacts, and pause conditions.

## Templates

- `assets/workflow-tracker.template.json`: copied to runtime `tracker.json` when
  a workflow starts.
- `assets/workflow-tracker.schema.json`: lightweight JSON contract for the
  tracker structure.
- `assets/workflow-plan.template.md`: copied to runtime `plan.md` for the
  in-progress execution plan.

If a workflow plan becomes part of the release history, commit a stable copy
under a docs path chosen for that release. Do not commit progress-only runtime
state from `tmp/agentic-workflows/`.

## Helper Script

Use `scripts/workflow_state.py` for deterministic state updates:

```bash
.venv/bin/python skills/agentic-workflow-controller/scripts/workflow_state.py \
  init v4-8-0-render-stamats-vida \
  --version 4.8.0 \
  --objective "Render Stamats and VIDA as older resume experience" \
  --current-step P01
```

Common commands:

- `init`: copy tracked templates into a new runtime workflow directory.
- `status`: print the current workflow cursor.
- `set-current`: set the current P or G step.
- `complete`: record a completed P step with optional evidence.
- `gate`: record a G-step reassessment, decision, and optional amended next
  steps.
- `pause`: record a condition that requires user input or an external change.
- `validate`: check that a runtime `tracker.json` follows the required shape.

## Execution Rules

When continuing a workflow:

1. Read `AGENTS.md`, the workflow plan, and the runtime `tracker.json`.
2. Identify the current P step or G gate.
3. Execute only the current step unless the plan explicitly authorizes a range.
4. Record evidence before marking a step complete.
5. At a G gate, compare completed work against the remaining plan. Continue,
   amend future steps, or pause.
6. Keep machine-readable workflow output and committed release artifacts stable.
7. Do not mutate live tracker DB rows, generated artifacts, remote branches,
   PRs, tags, scheduled jobs, or external systems unless the workflow plan or
   user explicitly authorizes that action.

## Pause Conditions

Pause and ask the user before continuing when:

- The next step changes confirmed product semantics or release scope.
- A workflow would mutate live tracker database rows or generated application
  artifacts outside the stated task.
- A reassessment gate finds the remaining plan is materially wrong.
- Validation fails in a way that requires a broader refactor than the plan
  authorized.
- A remote push, PR merge, release tag, or destructive operation is not already
  authorized.
- External credentials, secrets, production data, or user-owned accounts are
  required.

## Autonomy Boundary

This controller is procedural guidance for Codex sessions. It is not a daemon,
scheduler, permission system, or substitute for user approval. It helps Codex
carry out an already authorized staged workflow while keeping pause points,
evidence, and release hygiene visible.
