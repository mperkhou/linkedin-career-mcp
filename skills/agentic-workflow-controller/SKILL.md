---
name: agentic-workflow-controller
description: Legacy compatibility skill for executing, resuming, inspecting, or reassessing a committed agentic workflow plan with runtime tracker JSON, plan-digest binding, P steps, G gates, and evidence routes. Use only for an existing legacy tracker-based workflow. For new multi-phase feature work, use agentic-feature-workflow.
---

# Agentic Workflow Controller

## Legacy Compatibility

For new multi-phase feature workflows, use `agentic-feature-workflow`. Retain
this skill only for explicit compatibility work that must execute or resume an
existing committed plan with legacy runtime-tracker state.
Do not use to scaffold a new workflow.

## Overview

Use this skill to execute or resume a workflow that already has a committed
canonical plan under `docs/agentic-workflows/`. Use
`skills/agentic-workflow-init/SKILL.md` first when a workflow still needs to be
bootstrapped.

Follow root `AGENTS.md` before using this skill. This controller does not
replace repo safety rules, release closeout, tracker database caution,
resume-evidence discipline, or explicit user authorization.

## State Model

Keep one source of truth for the plan:

- **Committed canonical plan**: `docs/agentic-workflows/<version>-<slug>.md`.
- **Runtime tracker**: ignored cursor/evidence state under
  `tmp/agentic-workflows/<workflow_id>/tracker.json`.

The runtime tracker is a cursor and evidence log. It records current step,
attempted steps, completed steps, read-only evidence routes, reassessment gates,
validation evidence, plan revision/digest binding, artifact manifests,
branch/PR references, and pause conditions. It is not a second plan. Runtime
`plan.md`, when present, must be a small pointer to the committed canonical
plan.

P/G names are a convention, not a required schema. A plan may have no gates, one
gate, or multiple risk-based gates.

## Assets And Helper

- `assets/workflow-tracker.template.json`: runtime tracker seed.
- `assets/workflow-tracker.schema.json`: lightweight tracker contract.
- `assets/workflow-plan.template.md`: committed plan template used by bootstrap.
- `assets/artifact-manifest.schema.json`: small manifest contract for sanitized
  artifact references.
- `assets/evidence-route.prompt.md`: route prompt template.
- `scripts/workflow_state.py`: deterministic tracker updates.

Common helper commands:

```bash
.venv/bin/python skills/agentic-workflow-controller/scripts/workflow_state.py \
  status tmp/agentic-workflows/v4-10-0-example/tracker.json
```

- `init`: create ignored runtime state bound to a committed plan. Bootstrap
  sessions should call this only after the bootstrap commit exists.
- `status` / `inspect`: print current cursor and binding details.
- `validate`: verify tracker shape and bound plan digest.
- `begin`: record an attempted step before doing work.
- `complete`: mark a step complete. Completed step IDs are immutable.
- `gate`: record a G-step decision.
- `rebind-plan`: update plan revision/digest after an approved committed plan
  amendment.
- `pause` / `resume`: record or clear pause state.
- `manifest-add`: validate and record a sanitized artifact manifest.
- `route-start`, `route-complete`, `route-fail`: record evidence-route
  lifecycle.

The helper is side-effect limited. It must not push, open PRs, merge, tag,
mutate live tracker DB rows, call external APIs, or treat tracker booleans as
permission grants.

## Execution Rules

When continuing a workflow:

1. Read root `AGENTS.md`, the committed canonical plan, and runtime
   `tracker.json`.
2. Run `workflow_state.py validate <tracker>` before relying on tracker state.
   If the committed plan digest changed, pause until the plan is intentionally
   rebound.
3. Identify the current P step or G gate.
4. Record `begin` for the step before doing implementation work.
5. Execute only the current step unless the committed plan explicitly
   authorizes a range.
6. Record evidence before marking a step complete.
7. For read-only evidence routes, spawn subagents when available or run the
   route locally as `local_fallback`, then record findings before the next gate.
8. At a G gate, compare completed work and route findings against the remaining
   plan. Continue, amend future work, or pause.
9. Keep machine-readable workflow output and committed release artifacts stable.
10. Do not mutate live tracker DB rows, generated artifacts, remote branches,
    PRs, tags, scheduled jobs, or external systems unless the workflow plan or
    user explicitly authorizes that action.

## Gate Amendments

Gate amendments may affect only incomplete or future work. If a gate changes the
remaining plan:

1. Update the committed canonical plan under `docs/agentic-workflows/`.
2. Add a matching bullet under the same target-version heading in
   `CHANGELOG.md`.
3. Commit the plan and changelog amendment on the same branch.
4. Run `workflow_state.py rebind-plan ...` to update `plan_revision` and
   `plan_digest`.
5. Continue under the same release version unless the user explicitly changes
   release scope.

Do not create a new version heading merely because a gate amended future steps.

## Evidence Routes

Use evidence routes when a P step needs independent read-only investigation
before a gate decision. Good route candidates include code-path audits, schema
checks, release-metadata checks, tmp-only generated-artifact comparisons,
layout inspection, and quality checks before mutating live tracker data.

Prefer subagents when the Codex surface supports them and the route can run
independently. Name routes so they map clearly to their P step, such as
`P03-evidence-layout` or `P05-evidence-generation-quality`. Subagents should
receive a narrow read-only prompt and raw artifacts to inspect, not the main
agent's intended conclusion.

If subagents are unavailable, run the same route prompt in the main thread and
record `execution_mode: local_fallback`. Evidence routes collect facts and
recommendations only. The main agent owns repository edits, tracker updates,
G-step decisions, live-data mutation, commits, PRs, merges, and release tags.

## Artifact Storage

Repository-local workflow storage is limited to small control state, route
prompts, route assessments, sanitized summaries, hashes/references, and artifact
manifests under `tmp/agentic-workflows/<workflow_id>/`.

Put heavy or sensitive evidence outside the repository tree:

```text
$TMPDIR/linkedin-career-mcp-agentic/<workflow_id>/<step_id>/<run_id>/
```

Do not store raw SQLite databases, generated PDFs, raw logs, token stores,
cookies, credentials, runtime homes, repo clones, or other sensitive/heavy
evidence in repo-local runtime state.

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
carry out already authorized staged work while keeping pause points, evidence,
plan amendments, and release hygiene visible.
