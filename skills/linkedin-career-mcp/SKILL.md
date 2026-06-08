---
name: linkedin-career-mcp
description: Use when working with the local LinkedIn Career MCP server, including installing it, running the stdio server, configuring MCP clients, or developing public LinkedIn job-search tools.
metadata:
  short-description: Work with the LinkedIn Career MCP server
---

# LinkedIn Career MCP

This skill supports the local Python MCP server in the repository that contains this skill.

## Setup

- From the repository root, run `make install` to create `.venv`, install the package with development requirements, install Ollama, pull `qwen3:4b`, and link this skill into `~/.codex/skills`.
- The MCP server executable is `.venv/bin/linkedin-career-mcp` after installation.
- Run tests with `make test` and lint with `make lint`.
- Run the local matching workflow with `make match-jobs`; it generates both resumes and
  cover letters by default.

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

- Put private profile inputs in `profile/`; this directory is intentionally ignored by Git.
- The workflow reads supported profile files, asks local Ollama with `qwen3:4b` to generate LinkedIn search parameters, and searches both remote and hybrid jobs.
- Company patterns in `.blacklist` are matched case-insensitively against company names. `Raytheon*` excludes companies whose names start with `Raytheon`.
- Tailored resumes are written under `output/resumes/[company]/[job_id]_[job_title]/`.
- Cover letters are written under `output/cover_letters/[company]/[job_id]_[job_title]/`.
- Use `make match-jobs ARTIFACT_MODE=resumes-only` or
  `make match-jobs ARTIFACT_MODE=cover-letters-only` for one artifact type.
- Use `make regenerate-resumes`, `make regenerate-cover-letters`, or `make regenerate-all`
  for jobs already stored in SQLite. Set `JOB_IDS` to `all`, one job ID, space-separated
  IDs, or a comma-separated list.
- Long-running match/regenerate commands print per-job progress and artifact audit summaries
  to stderr while keeping the final JSON on stdout. Set `COVER_LETTER_RETRIES=0` to disable
  the default one-pass retry for jobs still missing cover letters after generation.
- Application tracking is appended to `output/tracking/read_applications/linkedin_applications.xlsx`.
- Generated tracking columns `applied_to` and `date_applied` are user-managed and are not automatically filled beyond the default `No`.
