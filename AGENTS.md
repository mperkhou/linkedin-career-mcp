# Agent Guidance

This file is the canonical operating guide for agents working in this
repository. Keep product explanation in `README.md`, workflow-specific command
details in `skills/`, and shared repo guardrails here.

## Scope

- Apply these rules when editing, testing, reviewing, releasing, or diagnosing
  this checkout.
- Prefer the existing Python-first architecture and local workflow conventions.
- Use `skills/linkedin-career-mcp/SKILL.md` for command-level workflow details.
- Use `skills/manual-resume-passthrough/SKILL.md` for manual resume pass work.

## Canonical State

- `profile/MASTER-RESUME.yml` is the canonical Master Resume Object (MRO).
- `output/tracking/applications.sqlite3` is the tracker database and source of
  truth for application rows, generated artifacts, selected resume variants,
  cover-letter content, and workflow status.
- JOD means Job Opening Description: parsed and trimmed posting text.
- ARO means Application Resume Object: the per-job resume object derived from
  the MRO and stored with the application.
- CLO means Cover Letter Object: manually edited cover-letter content stored in
  the tracker and rendered to PDF.
- Resume variants are distinct DB-backed records: `v1`, `v2`, `manual`, and any
  highlighted output written back to the intended variant.

## Editing Safety

- Inspect the worktree before editing. Do not revert user changes unless the
  user explicitly asks.
- Use `rg` or `rg --files` first for searches.
- Use `apply_patch` for manual file edits.
- Avoid destructive commands such as `git reset --hard` or `git checkout --`
  unless explicitly requested.
- Do not mutate tracker DB data, generated resume artifacts, profile files, or
  application rows unless the task requires it.
- Keep edits scoped to the requested release or fix. Split unrelated concerns
  into separate commits or follow-up work.

## Resume And Cover Letter Evidence

- Ground resume, cover-letter, and application-answer claims in local evidence:
  the tracker row, JOD, generated variants, MRO, ARO, and known user context.
- Do not inflate AWS depth, vendor-specific ownership, leadership scope,
  certifications, metrics, tools, employers, or regulated-environment claims.
- Preserve candid transferability language when the user has analogous
  experience but not direct production experience with a requested tool.
- Treat ATS and Jack & Jill feedback as signals, not permission to invent
  unsupported experience.

## Tracker Workflow Invariants

- Preserve explicit Review-page resume selections. Automatic selection should
  not overwrite a user-selected variant.
- The normal automatic preference is `manual > v2 > v1` when no explicit
  selection is set.
- `v1` is the first draft, `v2` is the evidence-validated second-pass
  refinement, and `manual` is the Codex-reviewed manual pass.
- Manual pass work requires existing `v1` and `v2` context where the workflow
  depends on second-pass evidence.
- Chained highlighting must target the intended variant: selected variant by
  default, `v2` after v2 refinement, and `manual` after a chained manual pass.
- Do not delete or overwrite other variants when selecting, highlighting, or
  rendering one variant.

## Release Workflow

- For committed work, keep `pyproject.toml` version and the top `CHANGELOG.md`
  entry aligned.
- Every PR that changes committed repository state must update the matching
  release-note file under `docs/release-notes/<version>.md`. For version bumps,
  `pyproject.toml`, the top `CHANGELOG.md` heading, and the release-note
  filename must all use the same version.
- Release notes should summarize why the release exists, what changed, and any
  validation or migration notes that future agents and operators would need.
- Choose SemVer deliberately from the final diff:
  - `MAJOR` for breaking architecture, workflow, schema, command, or user
    behavior changes.
  - `MINOR` for non-breaking features or substantial workflow improvements.
  - `PATCH` for bug fixes and narrow repairs.
- Run appropriate validation before PR. At minimum, consider:
  - `git diff --check`
  - focused `.venv/bin/python -m pytest ...`
  - `make lint`
  - `make test`
- Do not open or merge a release PR while its matching release-note file is
  missing.
- Release closeout is incomplete after a PR merge until the matching remote tag
  exists. After CI passes and the PR is merged:
  - checkout synced `main`
  - pull latest `main`
  - create an annotated tag named `vX.Y.Z` on the merged `main` commit
  - use tag subject `Release vX.Y.Z`
  - include a short tag body matching the top changelog heading
  - push tag `vX.Y.Z` to `origin`
  - verify the remote tag with
    `git ls-remote --tags origin refs/tags/vX.Y.Z`

## Long-Running Work

- Keep long-running workflows visible through logs, status files, or tracker
  status output.
- Do not leave required command sessions running silently at the end of a turn.
- For detached or overnight work, record the command, log path, status path, and
  how to resume or stop the run.

## Validation Notes

- Prefer `.venv/bin/python -m pytest` for focused pytest runs.
- Use `make lint` and `make test` for release validation unless the user
  explicitly asks for a narrower check.
- Restart or smoke-test the Flask tracker when changing templates, static
  assets, JavaScript, web routes, or background action behavior.
