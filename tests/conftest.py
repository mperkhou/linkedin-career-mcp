import pytest

from linkedin_career_mcp.models import JobSearchQuery


@pytest.fixture
def sample_query() -> JobSearchQuery:
    return JobSearchQuery(
        keywords="software engineer",
        location="Chicago, IL",
        date_posted="past_week",
        workplace_type="remote",
        limit=5,
    )
