# ADR 0002: Codex Resume Highlighting Workflow

## Status

Accepted.

## Context

The resume generator already produces per-job Application Resume Objects (AROs),
HTML, PDF, and ATS proxy scores. A later manual review pass can improve the
rendered resume by adding selective bolding inside professional-experience
bullets. That polish matters because recruiters and hiring managers scan quickly,
but it is also stylistic: the source wording should not change after the core
JOD-targeted generation step has already produced grounded bullets.

There are two product reasons to keep this as an explicit Codex workflow instead
of folding it into the main draft-generation LLM calls.

First, the project is also a portfolio artifact. A reviewer who follows the
GitHub project from a resume should see more than prompt engineering: the system
launches a bounded agentic workflow, validates the agent output, and applies it
through deterministic application code.

Second, the project intentionally stays cost-aware. Codex plus GPT-class models
can be more expensive by token count than a cheaper draft-generation model, but
the user's Codex subscription includes a monthly budget that would otherwise be
left unused. The highlighting stage spends that already-budgeted capacity only
where it creates visible resume quality.

## Decision

Run resume bullet highlighting as a post-generation Codex workflow.

The Python application owns all writes. Codex receives a read-only prompt with
professional-experience bullets and returns structured JSON patches:

```json
{
  "bullet_updates": [
    {
      "job_order": "1",
      "bullet_order": "1",
      "text": "Original bullet with <strong>selective emphasis</strong>."
    }
  ]
}
```

The validator accepts only `<strong>` tags. It rejects unsupported HTML,
attributes, nested tags, missing bullets, duplicate bullets, extra bullets, too
many spans, and any plain-text change. After validation, the application updates
the stored ARO, re-renders HTML/PDF, and refreshes ATS scoring through the same
database path used by normal draft generation.

The workflow is available in three places:

- `make highlight-draft-resumes JOB_IDS="..."` for direct CLI use.
- The Flask tracker Actions menu for batch highlighting existing draft resumes.
- An optional add-job checkbox that chains highlighting after draft resume
  generation.

## Consequences

This keeps the core resume generator focused on evidence-backed wording while
making the visual polish step demonstrably agentic, inspectable, and safe to
rerun.

The cost tradeoff is explicit. Highlighting is not required for every
development run; it is an optional post-generation polish step that can use
monthly Codex subscription capacity rather than adding another application LLM
call to the default generator.

Failures are contained. If Codex changes content or returns malformed output,
the script exits without writing the highlighted resume. The previous draft
remains available in SQLite.
