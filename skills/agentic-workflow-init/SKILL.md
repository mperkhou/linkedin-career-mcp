---
name: agentic-workflow-init
description: Use when Codex should bootstrap a new committed agentic workflow plan before implementation work begins, including repo readiness checks, branch creation, SemVer confirmation, docs/agentic-workflows plan creation, bootstrap CHANGELOG entry, bootstrap commit, ignored runtime tracker initialization, plan digest binding, and kickoff prompt generation for agentic-workflow-controller. Do not use for executing implementation steps after the workflow is initialized.
---

# Agentic Workflow Init

## Overview

Use this skill to scaffold a new workflow. It creates the committed canonical
plan and the ignored runtime tracker binding that
`agentic-workflow-controller` will later execute or resume.

Follow root `AGENTS.md` first. The init skill must not implement the feature,
run the executor, mutate tracker DB data, push, open PRs, merge, tag, or create
a second runtime plan.

## Bootstrap Sequence

1. Verify repository root, safe worktree state, synced `main`, and existing
   `AGENTS.md`.
2. Create the feature branch.
3. Derive or confirm one target SemVer for the whole workflow.
4. Create one committed canonical plan:
   `docs/agentic-workflows/<version>-<feature-slug>.md`.
5. Add the matching top `CHANGELOG.md` heading and an initial bootstrap bullet.
6. Commit the plan and changelog before implementation work starts.
7. Initialize ignored runtime tracker state only after the bootstrap commit.
8. Bind tracker state to workflow ID, target version, branch, canonical plan
   path, plan revision, plan digest, bootstrap commit, and timestamps.
9. Render a kickoff prompt for a fresh/local session to run or resume with
   `$agentic-workflow-controller`.

Use `skills/agentic-workflow-controller/assets/workflow-plan.template.md` as
the starting point for the committed plan. Keep the plan concise but specific:
P steps for work phases, optional G gates for reassessment, explicit validation,
pause conditions, and any evidence routes that should be collected.

## Runtime Tracker

After the bootstrap commit exists, initialize runtime state with the shared
helper:

```bash
.venv/bin/python skills/agentic-workflow-controller/scripts/workflow_state.py \
  init <workflow_id> \
  --version <X.Y.Z> \
  --objective "<workflow objective>" \
  --current-step P01 \
  --branch <branch-name> \
  --plan-path docs/agentic-workflows/<X.Y.Z>-<feature-slug>.md \
  --plan-revision 1 \
  --bootstrap-commit <commit-sha>
```

The helper writes ignored state under `tmp/agentic-workflows/<workflow_id>/`.
The runtime `plan.md`, if created, is only a pointer to the committed plan. Do
not edit it as a competing plan.

## Kickoff Prompt

End initialization by giving the user a prompt like:

```text
Use $agentic-workflow-controller in /Users/mperkhou/dev/codex/linkedin-career-mcp
to resume workflow <workflow_id>.

Read AGENTS.md, docs/agentic-workflows/<X.Y.Z>-<feature-slug>.md, and
tmp/agentic-workflows/<workflow_id>/tracker.json. Validate the tracker, start at
P01, record attempted/completed steps, use evidence routes where the plan calls
for them, and pause at G gates or release-closeout actions that require user
approval.
```

## Boundaries

- Do not implement P steps during bootstrap.
- Do not mutate `output/tracking/applications.sqlite3`, generated resumes,
  cover-letter artifacts, remote branches, PRs, tags, scheduled jobs, or
  external systems.
- Do not store heavy or sensitive evidence in repo-local runtime state.
- Do not treat runtime JSON as permission to bypass user approval.
