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
