---
name: linkedin-career-mcp
description: Use when working with the local LinkedIn Career MCP server, including installing it, running the stdio server, configuring MCP clients, or developing public LinkedIn job-search tools.
metadata:
  short-description: Work with the LinkedIn Career MCP server
---

# LinkedIn Career MCP

This skill supports the local Python MCP server in the repository that contains this skill.

## Setup

- From the repository root, run `make install` to create `.venv`, install the package with development requirements, install Ollama, pull `qwen3:4b`, and link repository skills into `~/.codex/skills`.
- The MCP server executable is `.venv/bin/linkedin-career-mcp` after installation.
- Run tests with `make test` and lint with `make lint`.
- Run the legacy local matching workflow with `make match-jobs`; it now defaults to
  resume-only artifacts while cover letters are handled manually in the Flask tracker.

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

## Matching Workflow

- Before search planning or artifact tailoring, use the `master-resume-yaml` skill to create
  or refine `profile/MASTER-RESUME.yml` from `profile/MP-MASTER-RESUME.txt`.
- The new resume-generation path starts from an Application Resume Object (ARO), initialized
  as a hard copy of `profile/MASTER-RESUME.yml`, then applies compact JOD-specific Core
  Technical Skills matches before local professional-experience scoring.
- Use `scripts/application_resume_pass_one.py` to manually generate the Core Technical
  Skills prompt, apply a saved JSON response, and write a scored ARO YAML while the broader
  workflow is being redesigned.
- Use `scripts/application_resume_select_bullets.py` after scoring to choose first-draft
  experience bullets by descending positive score buckets while preserving disabled jobs.
- Use `scripts/application_resume_store_first_draft.py` to store the first-draft ARO,
  rendered HTML, generated PDF, and ATS score on the Flask tracker row for a job ID.
- Treat the old full-context resume/cover-letter generation path as legacy during ARO
  refactoring; keep it available for regression tests and tracker workflows until replaced.
- Keep tracked master profile inputs in `profile/`.
- The workflow reads supported profile files, asks local Ollama with `qwen3:4b` to generate LinkedIn search parameters, and searches both remote and hybrid jobs.
- Company patterns in `.blacklist` are matched case-insensitively against company names. `Raytheon*` excludes companies whose names start with `Raytheon`.
- Tailored resumes are written under `output/resumes/[company]/[job_id]_[job_title]/`.
- Cover letters are manual Cover Letter Objects (CLOs) edited from the Flask tracker and
  rendered to stored PDF blobs on save.
- Set `MAX_JOBS` for capped test runs, for example `make match-jobs MAX_JOBS=2`.
- Use `make match-jobs ARTIFACT_MODE=resumes-only` for resume artifacts.
- Use `make regenerate-resumes` for jobs already stored in SQLite. Set `JOB_IDS` to `all`,
  one job ID, space-separated IDs, or a comma-separated list.
- Long-running match/regenerate commands print per-job progress and artifact audit summaries
  to stderr while keeping the final JSON on stdout.
- Application tracking is appended to `output/tracking/read_applications/linkedin_applications.xlsx`.
- Generated tracking columns `applied_to` and `date_applied` are user-managed and are not automatically filled beyond the default `No`.
