# LinkedIn Career MCP

Python-centric MCP server for querying public LinkedIn job openings today, with an architecture that can grow into resume matching, tracking, and carefully gated application workflows later.

This project was informed by the MIT-licensed [`administrativetrick/linkedin-mcp`](https://github.com/administrativetrick/linkedin-mcp) TypeScript server, but this implementation is Python-first and does not require LinkedIn credentials for the current public jobs tools.

## What Works Now

- Search public LinkedIn job listings by keywords and location.
- Filter by date posted, job type, workplace type, experience level, distance, sort order, and pagination.
- Fetch public job details by LinkedIn job ID or job URL.
- Use local Ollama with `qwen3:4b` to generate profile-aware LinkedIn search parameters.
- Use local Ollama with `qwen3:4b` to tailor a resume PDF for each matching job.
- Track generated resume artifacts and LinkedIn links in a local spreadsheet.
- Run as an MCP stdio server from any compatible client.

## Architecture

```text
MCP client
  -> linkedin_career_mcp.server
  -> linkedin_career_mcp.tools
  -> direct search path:
       linkedin_career_mcp.services
       -> linkedin_career_mcp.providers
       -> LinkedIn public jobs pages
  -> matching workflow path:
       profile/* + .blacklist
       -> Ollama qwen3:4b search planner
       -> linkedin_career_mcp.services
       -> LinkedIn public jobs pages
       -> Ollama qwen3:4b resume tailor
       -> output/resumes/* + output/tracking/*
```

The package is intentionally split by responsibility:

- `models.py`: stable domain models shared by tools, providers, and future workflows.
- `providers/`: external data adapters. The current provider uses LinkedIn public job pages.
- `services.py`: orchestration and guardrails shared by MCP tools and future CLIs.
- `tools/`: MCP-facing tool registration.
- `ollama.py`: local Ollama API client used for Qwen3 generation.
- `workflows/`: multi-step workflows such as profile-aware job matching and resume tailoring.

## Install

```bash
cd linkedin-career-mcp
make install
```

`make install` creates `.venv`, installs the package with development requirements, installs
Ollama with `curl -fsSL https://ollama.com/install.sh | sh`, pulls `qwen3:4b`, and links the
Codex skill at `~/.codex/skills/linkedin-career-mcp`.

## Run

```bash
.venv/bin/linkedin-career-mcp
```

The command starts an MCP stdio server, so it is meant to be launched by an MCP client.

## MCP Client Config

Use the absolute path for your local checkout:

```json
{
  "mcpServers": {
    "linkedin-career": {
      "command": "/Users/mperkhou/dev/codex/linkedin-career-mcp/.venv/bin/linkedin-career-mcp"
    }
  }
}
```

If you install globally or with `uvx`, adjust `command` accordingly.

## Tools

### `search_linkedin_jobs`

Search public LinkedIn listings.

Required:

- `keywords`: job title or search terms.
- `location`: city, state, country, or `remote`.

Optional:

- `date_posted`: `any_time`, `past_24_hours`, `past_week`, `past_month`
- `job_type`: `full_time`, `part_time`, `contract`, `temporary`, `volunteer`, `internship`, `other`
- `workplace_type`: `on_site`, `remote`, `hybrid`
- `experience_level`: `internship`, `entry_level`, `associate`, `mid_senior`, `director`, `executive`
- `sort_by`: `relevance`, `recent`
- `distance`: miles from the provided location.
- `limit`: result count, capped by server settings.
- `page`: zero-based page number.

### `get_linkedin_job_details`

Fetch a public LinkedIn job detail page by `job_id` or `job_url`.

### `find_matching_linkedin_jobs`

Run a local Ollama-assisted workflow that reads files from `profile/`, generates multiple
LinkedIn search queries with `qwen3:4b`, forces remote and hybrid workplace filters, filters
blacklisted companies, fetches matching job details, and writes a tailored resume PDF for each
job.

The workflow has two Qwen3 passes:

1. Search planning: profile files are extracted to text and sent to local Ollama with `qwen3:4b`.
   Qwen3 returns JSON search-query objects containing LinkedIn parameters such as `keywords`,
   `location`, `date_posted`, `job_type`, `experience_level`, `sort_by`, `limit`, and `page`.
   The workflow validates those parameters, then expands each query into remote and hybrid
   `workplace_type` variants before calling the existing LinkedIn search service.
2. Resume tailoring: for each non-blacklisted matching job, the workflow fetches the public job
   details from LinkedIn and sends the job description plus the same `profile/` context back to
   local Ollama with `qwen3:4b`. Qwen3 returns final resume text tailored to that job. The workflow
   renders that text to a PDF and records the artifact in the tracking workbook.

Default local inputs:

- `profile/`: put `MP-RESUME-AGENTIC.pdf`, current job descriptions, and other profile files here.
  Supported file types are `.pdf`, `.docx`, `.txt`, `.md`, `.rst`, `.json`, and `.csv`.
- `.blacklist`: company-name glob patterns, matched case-insensitively. For example, `Raytheon*`
  excludes companies whose names start with `Raytheon`.

Default local outputs:

- `output/resumes/[company]/[job_id]_[job_title]/mp_resume_[job_title].pdf`: customized resumes.
- `output/tracking/read_applications/linkedin_applications.xlsx`: tracking workbook with LinkedIn
  and resume links, plus user-editable `applied_to` and `date_applied` columns.

You can run the same workflow from the command line:

```bash
make match-jobs
```

## Configuration

All settings are optional:

- `LINKEDIN_CAREER_MCP_USER_AGENT`: HTTP user agent for public requests.
- `LINKEDIN_CAREER_MCP_TIMEOUT_SECONDS`: request timeout. Default: `12`.
- `LINKEDIN_CAREER_MCP_MAX_RESULTS`: maximum results returned per search. Default: `25`.
- `LINKEDIN_CAREER_MCP_OLLAMA_BASE_URL`: Ollama API URL. Default: `http://127.0.0.1:11434`.
- `LINKEDIN_CAREER_MCP_OLLAMA_MODEL`: local model used for matching and resume tailoring.
  Default: `qwen3:4b`.
- `LINKEDIN_CAREER_MCP_OLLAMA_TIMEOUT_SECONDS`: local generation timeout. Default: `180`.

## Development

```bash
make lint
make test
```

## Notes And Limits

This server uses public LinkedIn pages. It does not log in, use private member data, or submit applications. Public-page parsing can break when LinkedIn changes markup. Future application automation should be designed with explicit user confirmation, audit logs, and per-site terms review before anything is submitted.
