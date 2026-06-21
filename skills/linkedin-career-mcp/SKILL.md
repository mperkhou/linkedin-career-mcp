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
- Use `make seed-jobs MAX_JOBS=<n>` for capped LinkedIn discovery runs. This plans search terms from the master resume, searches public LinkedIn jobs, fetches public job details, trims JOD text, and seeds rows into `output/tracking/applications.sqlite3`.
- Use `make regenerate-draft-resumes JOB_IDS=<job_id>` to create first-draft ARO resume artifacts for stored rows. This deep-copies the MRO, asks the configured LLM to match Core Technical Skills to the trimmed JOD, generates compact JOD targets, rewrites rendered experience bullets from ARO source evidence, stores the ARO YAML, renders HTML/PDF, and recalculates ATS fields.
- Use `make regenerate-aro-objects JOB_IDS=<job_id>` when `profile/MASTER-RESUME.yml` changed and stored ARO objects should be recreated from the latest MRO without API calls from existing Core Technical Skills match lists.
- Use `make sync-draft-to-aro JOB_IDS=<job_id>` to render the stored ARO object into the database-backed draft HTML/PDF and refresh ATS scoring without re-querying the LLM.
- Cover letters are manual Cover Letter Objects (CLOs) edited in the Flask tracker and rendered to stored PDF blobs on save.
- The Flask tracker is launched with `make launch-website`. Resume, cover-letter, description, and Add-job workflows read/write the SQLite database directly.
- Long-running tracker actions stream progress through the collapsible status panel in the Flask UI.

## Local Conventions

- `profile/MASTER-RESUME.yml` is the canonical Master Resume Object (MRO).
- `output/tracking/applications.sqlite3` is the local application-state database.
- JOD means Job Opening Description: the public text from a posting after parsing and trimming.
- ARO means Application Resume Object: a per-job deep copy of the MRO plus JOD match lists, generated experience bullets, render flags, and edited content.
- CLO means Cover Letter Object: manually edited rich text stored and rendered through the tracker.
- Application tracking columns `applied_to` and `date_applied` are user-managed and are not automatically filled beyond the default `No`.
