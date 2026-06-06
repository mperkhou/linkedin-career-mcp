from __future__ import annotations

import json
from pathlib import Path

from linkedin_career_mcp.models import JobDetails

FIXTURES_DIR = Path(__file__).parent / "fixtures"
LINKEDIN_JOBS_DIR = FIXTURES_DIR / "linkedin_jobs"


def load_linkedin_job_fixture(job_id: str) -> JobDetails:
    path = LINKEDIN_JOBS_DIR / f"{job_id}.json"
    return JobDetails(**json.loads(path.read_text(encoding="utf-8")))
