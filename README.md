# LinkedIn Career MCP

LinkedIn Career MCP is a local, database-backed job-search and resume-tailoring workflow. It searches public LinkedIn postings, trims noisy job-opening descriptions, builds per-job Application Resume Objects (AROs) from a structured master resume, renders first-draft resume HTML/PDF, and keeps the human review loop in a Flask tracker.

The project is intentionally local-first. It does not authenticate to LinkedIn, read private member data, submit applications, or auto-generate cover letters.

## What Changed

The workflow now centers on explicit objects instead of large freeform context bundles. `profile/MASTER-RESUME.yml` is the canonical Master Resume Object (MRO); each job gets an Application Resume Object (ARO) deep-copied from that master; cover letters are manual Cover Letter Objects (CLOs); and the Flask database stores the ARO, rendered HTML, rendered PDF, ATS fields, and user edits.

That object-oriented design is more straightforward than the previous artifact pipeline: each step has a clear input and output, local algorithms handle deterministic scoring and bullet selection, and expensive LLM calls are limited to the parts that need semantic matching. The result is easier to modify, easier to debug, and more reproducible across runs.

## Terms

- **JOD**: Job Opening Description. This is the parsed posting text after trimming low-signal boilerplate such as benefits, compensation, legal notices, and generic company copy.
- **MRO**: Master Resume Object. This is the canonical `MASTER-RESUME.yml` resume source with neutral render flags, skill categories, and experience bullet linkages.
- **ARO**: Application Resume Object. This is a per-job deep copy of the MRO with JOD match lists, bullet scores, render flags, and manual edits.
- **CLO**: Cover Letter Object. This is a manually pasted/edited rich-text cover letter stored in the database and rendered to PDF.
- **ATS score**: A local proxy score that combines parsing, keyword, semantic, and formatting signals from the rendered resume and the selected JOD.

## Master Resume Setup

The master resume build is a separate initialization workflow. It happens before LinkedIn search and before per-job tailoring.

![Master resume object build](docs/assets/master-resume-object-build.svg)

The source text in `profile/MP-MASTER-RESUME.txt` is converted into `profile/MASTER-RESUME.yml` with Codex skills and project guidelines. The important part is the linkage work: professional-experience bullets are mapped to Core Technical Skills categories and terms, using both direct skill matches and broader category matches. Those links become the deterministic scoring surface later.

## Application Workflow

Once the master resume exists, the job workflow is:

![ARO application workflow](docs/assets/aro-application-workflow.svg)

1. Plan optimized LinkedIn search terms from the master resume.
2. Search public LinkedIn postings and fetch job details.
3. Parse and trim each JOD with the multi-pass ML cleaner.
4. Seed the Flask SQLite database with raw JOD and prompt JOD.
5. Deep-copy the MRO into an ARO for the job.
6. Ask the configured LLM through OpenRouter to match Core Technical Skills to the JOD.
7. Locally count JOD matches for every linked job bullet.
8. Locally select renderable bullets by score, min/max limits, and tie buckets.
9. Store the ARO in SQLite, render resume HTML through Jinja2, render PDF, and calculate ATS score.
10. Review, edit, sync, download, and rescore from the Flask UI.

User edits update the ARO as the workflow basis. The rendered draft resume is derived from the ARO, and the tracker shows when the stored ARO and rendered resume are out of sync.

## Flask Tracker

The tracker is the daily operating surface. The main page shows job status, ATS score, JOD links, resume links, ARO/resume sync state, and manual cover-letter actions.

![Annotated main tracker](docs/assets/tracker-main-annotated.png)

The JOD editor keeps the source text and prompt text visible side by side. Saving this view updates the JOD fields and recalculates ATS values from the current resume.

![Annotated JOD editor](docs/assets/job-description-editor-annotated.png)

The resume editor exposes ARO-backed fields and rich-text controls. Saving re-renders HTML/PDF and refreshes ATS scoring.

![Annotated resume editor](docs/assets/resume-editor-annotated.png)

Cover letters are manual for now. The edit page provides a rich-text area for pasted content, then renders the emerald-style PDF on save.

![Annotated cover letter editor](docs/assets/cover-letter-editor-annotated.png)

Long-running actions stream into a collapsible progress panel so draft regeneration does not block the tracker UI.

![Annotated progress panel](docs/assets/background-progress-annotated.png)

## Commands

Install the local environment:

```bash
make install
```

Launch the Flask tracker:

```bash
make launch-website
```

Seed new LinkedIn rows into the database:

```bash
make seed-jobs MAX_JOBS=5
```

Generate or regenerate first-draft ARO resumes for stored jobs:

```bash
make regenerate-draft-resumes JOB_IDS="4424184336"
```

Recreate stored ARO objects from the latest master resume without API calls:

```bash
make regenerate-aro-objects JOB_IDS="4424184336"
```

Render the current stored ARO into resume HTML/PDF and refresh ATS scoring without an LLM call:

```bash
make sync-draft-to-aro JOB_IDS="4424184336"
```

Run validation:

```bash
make lint
make test
```

## MCP Tools

The server executable is created at `.venv/bin/linkedin-career-mcp`.

```json
{
  "mcpServers": {
    "linkedin-career": {
      "command": "/Users/mperkhou/dev/codex/linkedin-career-mcp/.venv/bin/linkedin-career-mcp"
    }
  }
}
```

Available MCP capabilities include public LinkedIn search, public job-detail retrieval, raw payload inspection, and the database-seeding matching workflow. The matching workflow no longer creates file-system resume or cover-letter artifacts; it seeds application/JOD rows for later ARO generation.

## Configuration

The default LLM provider is the API/OpenRouter path:

- `LINKEDIN_CAREER_MCP_LLM_PROVIDER`: `api` or `ollama`
- `LINKEDIN_CAREER_MCP_LLM_API_KEY`: API key for OpenRouter-compatible calls
- `LINKEDIN_CAREER_MCP_LLM_API_MODEL`: model for ARO draft skill matching
- `LINKEDIN_CAREER_MCP_LLM_PLANNER_API_MODEL`: cheaper planner model for search-query generation
- `LINKEDIN_CAREER_MCP_OLLAMA_MODEL`: local fallback model when provider is `ollama`

The important local files are:

- `profile/MP-MASTER-RESUME.txt`
- `profile/MASTER-RESUME.yml`
- `output/tracking/applications.sqlite3`
- `templates/resume/master_resume.html.j2`

## Development

The active workflow modules are intentionally smaller than the retired artifact pipeline:

- `src/linkedin_career_mcp/workflows/matching.py`: LinkedIn search planning, filtering, JOD trimming, and DB seeding.
- `src/linkedin_career_mcp/application_resume.py`: ARO initialization, Core Technical Skills matching prompt, scoring, and bullet selection.
- `src/linkedin_career_mcp/jod.py`: JOD cleaning and prompt trimming.
- `src/linkedin_career_mcp/resume_rendering.py`: HTML/PDF rendering.
- `src/linkedin_career_mcp/webapp.py`: database-backed review, edit, download, rescore, and background actions.

Keep the MRO neutral: empty `jod_matched_items`, zero match counts, and no job-specific pruning. Job-specific decisions belong in the ARO stored on the application row.
