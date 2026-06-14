# Architecture

`linkedin-career-mcp` is Python-centric by default. MCP is the integration boundary, but career-specific behavior lives in plain Python modules that can be reused by tests, CLIs, scheduled jobs, and future browser automation.

## Layers

```text
server.py
  Creates the FastMCP server and wires dependencies.

tools/
  Registers MCP tools. Tool functions should stay thin and return serializable models.

services/
  Coordinates providers, applies caps and defaults, and owns tool-friendly errors.

providers/
  Encapsulates external systems. Providers return domain models, not MCP payloads.

workflows/
  Reserved for multi-step career tasks such as application preparation, tracking,
  and user-confirmed submission flows.
```

## Design Rules

- Keep LinkedIn public scraping isolated in `providers/linkedin_public.py`.
- Do not put credentials in provider constructors unless a future authenticated provider needs them.
- Prefer domain models in `models/` over loose dictionaries between layers.
- Future application submission workflows must require explicit user approval before any external submit action.
- Add new job boards as providers, not as separate MCP servers, unless their auth/runtime needs diverge.

## Future Workflow Sketch

```text
search jobs -> normalize -> rank against profile -> create resume and cover-letter drafts
  -> user reviews each field -> submit only after explicit approval -> record audit event
```
