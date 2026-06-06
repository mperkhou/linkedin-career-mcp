# LinkedIn Career MCP

Python-centric MCP server for querying public LinkedIn job openings today, with an architecture that can grow into resume matching, tracking, and carefully gated application workflows later.

This project was informed by the MIT-licensed [`administrativetrick/linkedin-mcp`](https://github.com/administrativetrick/linkedin-mcp) TypeScript server, but this implementation is Python-first and does not require LinkedIn credentials for the current public jobs tools.

## What Works Now

- Search public LinkedIn job listings by keywords and location.
- Filter by date posted, job type, workplace type, experience level, distance, sort order, and pagination.
- Fetch public job details by LinkedIn job ID or job URL.
- Run as an MCP stdio server from any compatible client.

## Architecture

```text
MCP client
  -> linkedin_career_mcp.server
  -> linkedin_career_mcp.tools
  -> linkedin_career_mcp.services
  -> linkedin_career_mcp.providers
  -> LinkedIn public jobs pages
```

The package is intentionally split by responsibility:

- `models.py`: stable domain models shared by tools, providers, and future workflows.
- `providers/`: external data adapters. The current provider uses LinkedIn public job pages.
- `services.py`: orchestration and guardrails shared by MCP tools and future CLIs.
- `tools/`: MCP-facing tool registration.
- `workflows/`: placeholders for future multi-step workflows such as application tracking or assisted submissions.

## Install

```bash
cd linkedin-career-mcp
make install
```

`make install` creates `.venv`, installs the package with development requirements, and links
the Codex skill at `~/.codex/skills/linkedin-career-mcp`.

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
      "command": "/Users/mperkhou/Documents/Codex/linkedin-career-mcp/.venv/bin/linkedin-career-mcp"
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

## Configuration

All settings are optional:

- `LINKEDIN_CAREER_MCP_USER_AGENT`: HTTP user agent for public requests.
- `LINKEDIN_CAREER_MCP_TIMEOUT_SECONDS`: request timeout. Default: `12`.
- `LINKEDIN_CAREER_MCP_MAX_RESULTS`: maximum results returned per search. Default: `25`.

## Development

```bash
make lint
make test
```

## Notes And Limits

This server uses public LinkedIn pages. It does not log in, use private member data, or submit applications. Public-page parsing can break when LinkedIn changes markup. Future application automation should be designed with explicit user confirmation, audit logs, and per-site terms review before anything is submitted.
