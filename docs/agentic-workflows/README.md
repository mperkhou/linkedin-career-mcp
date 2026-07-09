# Agentic Workflows

Agentic workflows are a lightweight orchestration pattern for larger repo
changes. They reduce repeated prompt/response management while keeping
automation guided, reviewable, and anchored in committed release artifacts.

## Lifecycle

1. Use `$agentic-workflow-init` to bootstrap the workflow.
2. Commit one canonical plan under `docs/agentic-workflows/<version>-<slug>.md`.
3. Initialize ignored runtime state under `tmp/agentic-workflows/<workflow_id>/`.
4. Hand a kickoff prompt to `$agentic-workflow-controller`.
5. Use the controller to execute P steps, run evidence routes, reassess at G
   gates, validate, pause, and close out the release when authorized.

## Bootstrap Skill Vs Controller Skill

`agentic-workflow-init` scaffolds. It verifies readiness, creates the branch,
confirms one SemVer target, writes the committed plan, adds the bootstrap
changelog entry, commits those files, initializes the tracker, records plan
digest/revision binding, and produces the kickoff prompt.

`agentic-workflow-controller` executes or resumes. It reads `AGENTS.md`, the
committed plan, and the runtime tracker; records attempted and completed steps;
collects read-only evidence routes; pauses or amends at gates; and preserves
release hygiene.

## Canonical Plan And Tracker Binding

The committed plan is the source of truth. Runtime tracker state is only a
cursor and evidence log. The tracker records the plan path, plan revision,
SHA-256 digest, target version, branch, and bootstrap commit. If the plan file
changes without a rebind, validation fails so the session does not accidentally
execute stale instructions.

When a G gate amends future work, update the committed plan, add a same-version
`CHANGELOG.md` bullet, commit both changes, then run `workflow_state.py
rebind-plan` to update the tracker digest and revision.

## Evidence Routes

Evidence routes are read-only investigations attached to a P step. They can run
as subagents when available or as `local_fallback` in the main thread. Routes
collect facts and recommendations; the main agent remains responsible for
edits, gates, tracker updates, commits, PRs, merges, and tags.

## Artifact Storage

Repository-local state may contain only small control files, route prompts,
route assessments, sanitized summaries, hashes/references, and artifact
manifests under `tmp/agentic-workflows/<workflow_id>/`.

Heavy or sensitive evidence belongs outside the repository tree:

```text
$TMPDIR/linkedin-career-mcp-agentic/<workflow_id>/<step_id>/<run_id>/
```

Do not put raw SQLite databases, generated PDFs, raw logs, token stores,
cookies, credentials, runtime homes, repo clones, or other sensitive/heavy
evidence in repo-local runtime state.

## Troubleshooting

- If `validate` reports a plan digest mismatch, inspect the committed plan
  changes and rebind only after confirming the amendment was intentional.
- If a tracker lock exists, check whether another process is writing the
  tracker before removing stale lock files.
- If a route needs sensitive or heavy evidence, store the raw evidence under
  `$TMPDIR/linkedin-career-mcp-agentic/...` and commit only a sanitized manifest
  or summary.
