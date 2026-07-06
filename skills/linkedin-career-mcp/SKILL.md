---
name: linkedin-career-mcp
description: Use when working with the local LinkedIn Career MCP server, including installing it, running the stdio server, configuring MCP clients, or developing public LinkedIn job-search tools.
metadata:
  short-description: Work with the LinkedIn Career MCP server
---

# LinkedIn Career MCP

This skill supports the local Python MCP server in the repository that contains this skill.

## Setup

- From the repository root, run `make install` to create `.venv`, install development requirements, install Ollama, pull `qwen3:4b`, and link repository skills into `~/.codex/skills`.
- The MCP server executable is `.venv/bin/linkedin-career-mcp` after installation.
- Run tests with `make test` and lint with `make lint`.

## MCP Client Configuration

Use the absolute path to the repository checkout:

```json
{
  "mcpServers": {
    "linkedin-career": {
      "command": "/Users/mperkhou/dev/codex/linkedin-career-mcp/.venv/bin/linkedin-career-mcp"
    }
  }
}
```

## Scope

The current tools search public LinkedIn job listings and fetch public job details. The server does not authenticate to LinkedIn, access private member data, or submit applications.

## Release Versioning

- When starting work that is likely to be committed, create or maintain the
  top `CHANGELOG.md` entry as a major-change candidate by default. Assume the
  work may be breaking until the final diff proves otherwise.
- Before staging or committing, inspect the actual diff and choose the release
  level deliberately:
  - Breaking architecture, default workflow, schema, database, command, or user
    behavior changes bump `MAJOR`, for example `2.0.3` to `3.0.0`.
  - Non-breaking feature or substantial workflow improvements bump `MINOR` and
    reset patch, for example `2.0.3` to `2.1.0`.
  - Bug fixes and narrow repairs bump `PATCH`, for example `2.0.3` to `2.0.4`.
- Keep the package version in `pyproject.toml` and the top `CHANGELOG.md`
  heading aligned. Do not carry patch digits forward when promoting a change to
  a minor or major release.

## ARO Workflow

- Before LinkedIn search planning or resume drafting, use the `master-resume-yaml` skill to create or refine `profile/MASTER-RESUME.yml` from `profile/MP-MASTER-RESUME.txt`.
- The master resume YAML is the Master Resume Object (MRO). It stores header fields, section render flags, core technical skill categories, and professional-experience bullets with category/skill linkages.
- Use `make seed-jobs MAX_JOBS=<n> DATE_POSTED=<window>` for capped
  LinkedIn discovery runs. This plans search terms from the master resume,
  searches public LinkedIn jobs, fetches public job details, trims JOD text,
  and seeds rows into `output/tracking/applications.sqlite3`. The default
  posting-age window is `past_week`; supported windows include `past_24_hours`,
  `past_week`, and `past_month`.
- Use `make regenerate-resumes JOB_IDS=<job_id>` for the main resume workflow. It creates or refreshes the first-draft ARO as `v1`, then runs the GLM 5.2 second-pass refinement and stores `v2`; automatic resume selection prefers manual, then v2, then v1 unless the tracker row has an explicit variant choice.
- Use `make regenerate-draft-resumes JOB_IDS=<job_id>` only when you intentionally want the v1 first-draft ARO artifacts without v2. This deep-copies the MRO, uses the draft-generation model default (`z-ai/glm-5.2`) to match Core Technical Skills to the trimmed JOD, generates compact JOD targets, rewrites rendered experience bullets from ARO source evidence, stores the ARO YAML, renders HTML/PDF, and recalculates ATS fields. V1 generation logs substep progress to stderr and applies `FIRST_DRAFT_LLM_TIMEOUT_SECONDS` as a hard per-LLM-call timeout, defaulting to 300 seconds.
- Use `make refine-draft-resumes JOB_IDS=<job_id>` to create or rerun the v2 refinement for existing v1 drafts.
- V2 refinement is critique-driven and evidence-validated. GLM 5.2 receives
  the v1 ARO, selected JOD text, ATS diagnostics, JOD targets, and MRO/ARO
  evidence; it can recommend supported rewording, ordering, emphasis, or
  aliases, but unsupported skills, tools, metrics, employers, or
  responsibilities are rejected instead of added.
- Resume variants are DB-backed. `v1` is the first draft, `v2` is the GLM
  refinement, and `manual` is the Codex manual pass. Selecting a variant only
  updates the active resume HTML/PDF and ATS columns on the application row; it
  does not delete the other variants, so selection is reversible from the
  tracker review page.
- Use `make regenerate-aro-objects JOB_IDS=<job_id>` when `profile/MASTER-RESUME.yml` changed and stored ARO objects should be recreated from the latest MRO without API calls from existing Core Technical Skills match lists.
- Use `make sync-draft-to-aro JOB_IDS=<job_id>` to render the stored ARO object into the database-backed draft HTML/PDF and refresh ATS scoring without re-querying the LLM.
- Use `make manual-pass-resumes JOB_IDS=<job_id>` after `v1` and `v2` exist to
  store a Codex-reviewed `manual` variant. The command does not select the
  manual variant automatically. Codex manual pass and highlighting runs pin
  `CODEX_REASONING_EFFORT=xhigh` by default; override it or set it empty only
  when intentionally inheriting Codex CLI config.
- Use `make highlight-draft-resumes JOB_IDS=<job_id>` for the guarded Codex
  highlighting workflow. It polishes the currently selected resume variant
  (`v1`, `v2`, or `manual`) and is separate from v2 refinement.
- Cover letters are manual Cover Letter Objects (CLOs) edited in the Flask tracker and rendered to stored PDF blobs on save.
- The Flask tracker is launched with `make launch-website`. Resume,
  cover-letter, description, Add popup, and workflow actions read/write the
  SQLite database directly.
- The tracker Add popup can seed a batch with a job count and posting-age
  window, then chain selected stages for the newly seeded rows: v1 draft
  generation, v2 refinement, Codex manual pass, and Codex highlighting.
- The Add popup's LinkedIn and Other URL forms accept comma- or
  newline-separated URL batches, then run one background workflow for the rows
  that were loaded successfully. They can chain v2 refinement, Codex manual
  pass, and Codex highlighting; manual pass requires v2 refinement. Chained
  highlighting targets `v2` after v2 refinement and `manual` after a chained
  manual pass.
- The Other URL parser reads schema.org `JobPosting` metadata first, then
  embedded app payloads used by Dayforce Next.js pages and Work at a Startup
  Inertia pages, then visible page text.
- The tracker Actions menu runs the same workflow family on selected rows:
  main v1-plus-v2 resume generation, v1-only draft generation, a combined
  v1-plus-v2-plus-manual-pass workflow, v2 create/rerun, manual pass,
  highlighting, ARO regeneration, and draft-to-ARO sync.
- Long-running tracker actions stream progress through the collapsible status panel in the Flask UI.

## Local Conventions

- `profile/MASTER-RESUME.yml` is the canonical Master Resume Object (MRO).
- `output/tracking/applications.sqlite3` is the local application-state database.
- JOD means Job Opening Description: the public text from a posting after parsing and trimming.
- ARO means Application Resume Object: a per-job deep copy of the MRO plus JOD match lists, generated experience bullets, render flags, and edited content.
- CLO means Cover Letter Object: manually edited rich text stored and rendered through the tracker.
- Application tracking columns `applied_to` and `date_applied` are user-managed and are not automatically filled beyond the default `No`.
