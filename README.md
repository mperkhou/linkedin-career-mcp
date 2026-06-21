# LinkedIn Career MCP

LinkedIn Career MCP is a local, database-backed job-search and resume-tailoring workflow. It searches public LinkedIn postings, trims noisy job-opening descriptions, builds per-job Application Resume Objects (AROs) from a structured master resume, renders first-draft resume HTML/PDF, and keeps the human review loop in a Flask tracker.

The project is intentionally local-first. It does not authenticate to LinkedIn, read private member data, submit applications, or auto-generate cover letters.

## What Changed

The workflow now centers on explicit objects instead of large freeform context bundles. `profile/MASTER-RESUME.yml` is the canonical Master Resume Object (MRO); each job gets an Application Resume Object (ARO) deep-copied from that master; cover letters are manual Cover Letter Objects (CLOs); and the Flask database stores the ARO, rendered HTML, rendered PDF, ATS fields, and user edits.

That object-oriented design is more straightforward than the previous artifact pipeline: each step has a clear input and output, the master resume carries structured source evidence, and expensive LLM calls are limited to the parts that need semantic matching. The result is easier to modify, easier to debug, and more reproducible across runs.

The v3.0.0 redesign is documented in the [release notes](docs/release-notes/3.0.0.md), [experiment log](docs/experiments/2026-06-21-jod-target-aro-redesign.md), and [architecture decision record](docs/adr/0001-adopt-jod-target-aro-rewrite-workflow.md). The guiding lesson was to keep source evidence bounded and truthful, then let the LLM generate role-specific bullets instead of asking local scoring code to pick from a fixed bullet inventory.

## Terms

- **JOD**: Job Opening Description. This is the parsed posting text after trimming low-signal boilerplate such as benefits, compensation, legal notices, and generic company copy.
- **MRO**: Master Resume Object. This is the canonical `MASTER-RESUME.yml` resume source with neutral render flags, skill categories, and experience evidence linkages.
- **ARO**: Application Resume Object. This is a per-job deep copy of the MRO with JOD match lists, generated experience bullets, render flags, and manual edits.
- **CLO**: Cover Letter Object. This is a manually pasted/edited rich-text cover letter stored in the database and rendered to PDF.
- **ATS score**: A local proxy score that combines parsing, keyword, semantic, and formatting signals from the rendered resume and the selected JOD.

## Master Resume Setup

The master resume build is a separate initialization workflow. It happens before LinkedIn search and before per-job tailoring.

![Master resume object build](docs/assets/master-resume-object-build.svg)

The source text in `profile/MP-MASTER-RESUME.txt` is converted into `profile/MASTER-RESUME.yml` with Codex skills and project guidelines. The important part is the linkage work: professional-experience source evidence is mapped to Core Technical Skills categories and terms, using both direct skill matches and broader category matches. The current role stores paragraph-level source evidence in the MRO so per-job ARO generation can tailor final bullets without reading a separate `tmp/master-paragraphs.md` file.

## Application Workflow

Once the master resume exists, the job workflow is:

![ARO application workflow](docs/assets/aro-application-workflow.svg)

1. Plan optimized LinkedIn search terms from the master resume.
2. Search public LinkedIn postings and fetch job details.
3. Parse and trim each JOD with the multi-pass ML cleaner.
4. Seed the Flask SQLite database with raw JOD and prompt JOD.
5. Deep-copy the MRO into an ARO for the job.
6. Ask the configured LLM through OpenRouter to match Core Technical Skills to the JOD.
7. Ask the JOD-target model to distill the JOD into compact requirement targets.
8. Rewrite the rendered experience jobs from their ARO source evidence, including current-role paragraph evidence stored in the MRO.
9. Store the ARO in SQLite, render resume HTML through Jinja2, render PDF, and calculate ATS score.
10. Review, edit, sync, download, and rescore from the Flask UI.

User edits update the ARO as the workflow basis. The rendered draft resume is derived from the ARO, and the tracker shows when the stored ARO and rendered resume are out of sync.

### JOD Target Rewrite Example

The draft generator reads the tracker row, preferring `prompt_job_description` and
falling back to `job_description`, then writes the generated ARO and rendered artifacts
back to the same row. In code, the candidate read is effectively:

```sql
SELECT job_id, company, job_title, prompt_job_description, job_description,
       application_resume_object
FROM applications
ORDER BY rowid;
```

The stored first draft updates fields such as `application_resume_object`,
`resume_html_content`, `resume_content`, `resume_filename`, `source_resume_path`,
`ats_score`, `ats_keyword_score`, and `ats_semantic_score`. The `source_*_path`
fields are populated for explicit artifact-cache runs; normal Flask/Make runs can
store the rendered HTML/PDF blobs in SQLite with blank source paths.

A cached smoke run for `url-9823c4455364` used this row:

```text
company: Coinbase
job_title: Staff Site Reliability Engineer, Core AI Infrastructure
prompt_job_description: 3342 chars
cache: tmp/final_jod_workflow_smoke_20260621T043327Z/artifacts
ATS after generation: 90 overall, 90 keyword, 77 semantic
```

The first GLM 5.2 call turns the trimmed JOD into compact targets. The complete
cached response is in `url-9823c4455364_jod_targets_response.json`:

```json
{
  "job_opening_description": {
    "requirements_targets": [
      "8+ years of experience automating and supporting AWS cloud infrastructure and network environments.",
      "Hands-on experience with infrastructure-as-code tools such as Terraform, Ansible, Chef, Puppet, or Salt.",
      "Production experience deploying, managing, and troubleshooting containerized workloads using Docker and Kubernetes.",
      "Proficiency in scripting or programming with Python, Bash, Ruby, or Go, including developing full-stack internal applications.",
      "Experience with Git-based CI/CD pipelines, including extending frameworks for IT services and enterprise network platforms.",
      "Track record of leading incident response under strict SLAs, including on-call support, root cause analysis, and blameless retrospectives.",
      "Experience building automation and tooling to streamline IT workflows, eliminate manual tasks, and improve deployment velocity.",
      "Experience strengthening observability by defining metrics, implementing monitoring solutions, and managing log aggregation.",
      "Experience partnering with Security and Compliance to integrate surveillance tooling into deployment pipelines.",
      "Experience utilizing generative AI responsibly to drive measurable improvements in workflow efficiency, cost, and quality.",
      "Strong network security fundamentals and experience working in highly regulated, fast-paced, remote-first IT environments.",
      "Expertise with Linux administration and automating EC2 or container deployments with Terraform."
    ]
  }
}
```

The ARO stores that as `job_opening_description.schema_version:
job_opening_description.v1` with ordered `requirements_targets`. The next GLM 5.2
calls rewrite each rendered job from only that job's ARO source evidence. For a
prior-role example, job order `2` used the cached prompt
`url-9823c4455364_job_2_rewrite_prompt.txt`. This prompt excerpt preserves the
full target list and full raw experience block:

```text
Target Job Requirements:
- 8+ years of experience automating and supporting AWS cloud infrastructure and network environments.
- Hands-on experience with infrastructure-as-code tools such as Terraform, Ansible, Chef, Puppet, or Salt.
- Production experience deploying, managing, and troubleshooting containerized workloads using Docker and Kubernetes.
- Proficiency in scripting or programming with Python, Bash, Ruby, or Go, including developing full-stack internal applications.
- Experience with Git-based CI/CD pipelines, including extending frameworks for IT services and enterprise network platforms.
- Track record of leading incident response under strict SLAs, including on-call support, root cause analysis, and blameless retrospectives.
- Experience building automation and tooling to streamline IT workflows, eliminate manual tasks, and improve deployment velocity.
- Experience strengthening observability by defining metrics, implementing monitoring solutions, and managing log aggregation.
- Experience partnering with Security and Compliance to integrate surveillance tooling into deployment pipelines.
- Experience utilizing generative AI responsibly to drive measurable improvements in workflow efficiency, cost, and quality.
- Strong network security fundamentals and experience working in highly regulated, fast-paced, remote-first IT environments.
- Expertise with Linux administration and automating EC2 or container deployments with Terraform.

Raw Experience (University of Iowa Hospitals and Clinics | Iowa City, IA | Engineering Support Specialist | Jan 2020 - May 2021):
- Adhered to strict software development lifecycles to build custom Python and AutoIT automation scripts, streamlining system upgrades across hundreds of mission-critical platform nodes as full-cycle software engineering work.
- Collaborated on the structural design and implementation of a DICOM anonymization server utilizing a modern React.js frontend interface as web application development.
- Conducted performance troubleshooting, defect handling, and remote patch deployments on highly regulated medical platform surfaces through deep debugging and patching.
- Administered IT and HIS systems for the department of radiology, including Philips Vue PACS and interconnected applications/software used by regulated clinical teams as radiology systems administration.
- Provided technical support for HCIS radiology servers and computer systems across mission-critical hospital environments across the support scope.
- Wrote Python and AutoIT scripts for remote software/update deployment and performed mass patch rollouts across hundreds of systems as automation detail.
- Helped implement a DICOM anonymization server over IPv4 with a React.js frontend as DICOM detail.

CRITICAL RULES:
1. Strictly use the exact numerical metrics and outcomes provided in the Raw Experience.
2. Do NOT hallucinate new tools, soft skills, software competencies, or outcomes.
3. Rephrase verbs and phrase structures to align with the Target Job Requirements.
4. If a target cannot be supported by the Raw Experience, ignore that target.
5. Format the final output as between 2 and 5 punchy bullet points utilizing the Google XYZ framework.
6. Output ONLY the raw string of each bullet point, one per line. No introductions, markdown, numbering, or chat text.
```

The cached response replaced that job's source evidence with generated rendered bullets:

```text
Accomplished streamlined system upgrades and eliminated manual IT workflows, as measured by mass patch rollouts across hundreds of mission-critical platform nodes, by writing custom Python and AutoIT automation scripts for remote software and update deployment.
Accomplished the development of full-stack internal applications for highly regulated clinical teams, as measured by the successful implementation of a DICOM anonymization server over IPv4, by collaborating on the structural design and implementation utilizing a modern React.js frontend interface.
Accomplished sustained operational stability in mission-critical hospital environments, as measured by effective performance troubleshooting and defect handling across HCIS radiology servers and computer systems, by administering IT and HIS systems and conducting remote patch deployments on regulated medical platform surfaces.
```

The stored ARO keeps those generated bullets as the rendered experience content
for that role. The current-role rewrite follows the same source-evidence pattern,
but starts from paragraph-level evidence stored directly in `profile/MASTER-RESUME.yml`.

## Flask Tracker

The tracker is the daily operating surface. The main page shows job status, ATS score, JOD links, resume links, ARO/resume sync state, and manual cover-letter actions.

![Annotated main tracker](docs/assets/tracker-main-annotated.png)

The JOD editor keeps the source text and prompt text visible side by side. Saving
this view updates the JOD fields and recalculates ATS values from the current
resume. The second image is the same page scrolled below the raw text panes,
where the tracker shows removed text and a line-level diff.

![Annotated JOD editor](docs/assets/job-description-editor-annotated.png)

![Annotated JOD diff view](docs/assets/job-description-diff-annotated.png)

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
- `LINKEDIN_CAREER_MCP_LLM_API_MODEL`: default API model for non-draft-generation API calls
- `LINKEDIN_CAREER_MCP_LLM_PLANNER_API_MODEL`: cheaper planner model for search-query generation
- `LINKEDIN_CAREER_MCP_OLLAMA_MODEL`: local fallback model when provider is `ollama`

Draft generation uses the JOD-target rewrite framework by default. Core Technical
Skills matching, JOD target generation, and experience-bullet rewrite calls default
to OpenRouter model `z-ai/glm-5.2`; override with:

```bash
JOD_MODEL=<model-id> make regenerate-draft-resumes JOB_IDS="4424184336"
```

Use `CORE_SKILL_MODEL=<model-id>` only when Core Technical Skills matching should
use a different model from the JOD target and bullet rewrite calls.

Use `MASTER_RESUME=<path>` to run the same ARO workflow against
an alternate master resume object without replacing the canonical MRO.

The important local files are:

- `profile/MP-MASTER-RESUME.txt`
- `profile/MASTER-RESUME.yml`
- `output/tracking/applications.sqlite3`
- `templates/resume/master_resume.html.j2`

## Development

The active workflow modules are intentionally smaller than the retired artifact pipeline:

- `src/linkedin_career_mcp/workflows/matching.py`: LinkedIn search planning, filtering, JOD trimming, and DB seeding.
- `src/linkedin_career_mcp/application_resume.py`: ARO initialization, Core Technical Skills matching prompt, JOD target creation, and evidence-backed bullet rewriting.
- `src/linkedin_career_mcp/jod.py`: JOD cleaning and prompt trimming.
- `src/linkedin_career_mcp/resume_rendering.py`: HTML/PDF rendering.
- `src/linkedin_career_mcp/webapp.py`: database-backed review, edit, download, rescore, and background actions.

Keep the MRO neutral: empty `jod_matched_items`, zero match counts, source-evidence bullets, and no job-specific pruning. Job-specific generated bullets belong in the ARO stored on the application row.

The resume template treats Education, Certifications, and Portfolio as supporting sections
after Professional Experience. By default, they are grouped together so senior-engineer
resumes can use page 1 for high-signal experience and flow supporting sections onto page 2
without a forced break that could create a third page. Set
`resume_layout.supporting_sections_start_on_page_2: true` in an ARO/MRO only when an
explicit page break before supporting sections is desired.
