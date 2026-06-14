from __future__ import annotations

import math
import re
from collections import Counter

from linkedin_career_mcp.models import JobDetails

NO_PUBLIC_JOB_DESCRIPTION = "No public job description was available."
JOB_DESCRIPTION_PROMPT_MAX_CHARS = 12_000

ROLE_RELEVANT_START_HEADINGS = (
    "Job Summary",
    "Position Summary",
    "Role Summary",
    "The Role",
    "About the Role",
    "About this Role",
    "About the Job",
    "The Opportunity",
    "What You’ll Do",
    "What You'll Do",
    "What You Will Do",
    "What You’ll Be Doing",
    "What You'll Be Doing",
    "What You Will Be Doing",
    "What We Need To See",
    "Key Responsibilities",
    "Responsibilities",
    "What You’ll Bring",
    "What You'll Bring",
    "What You Bring",
    "What We’re Looking For",
    "What We're Looking For",
    "Required Qualifications",
    "Minimum Qualifications",
    "Basic Qualifications",
    "Qualifications",
    "Requirements",
    "Skills and Experience",
    "Who You Are",
    "You might thrive",
    "You could be",
)
LOW_SIGNAL_PREAMBLE_HEADINGS = (
    "Our Mission",
    "Our Mission & Values",
    "Mission & Values",
    "Our Values",
    "Our Culture",
    "Our Culture & Work Style",
    "Culture & Work Style",
    "Life at",
    "Why Join",
    "Why Join Us",
    "Why Join The",
)
TRAILING_BOILERPLATE_HEADINGS = (
    "How We Support You",
    "Why Join",
    "Why Join Us",
    "Why You’ll Love Working Here",
    "Why You'll Love Working Here",
    "Benefits & Perks",
    "Pay & Benefits",
    "Our Benefits",
    "Perks & Benefits",
    "Health & Wellness",
    "Financial Well-being",
    "Family Support",
    "Growth & Development",
    "Time Off & Flexibility",
    "What We Offer",
    "Compensation",
    "Compensation Range",
    "Equal Opportunity",
    "Equal opportunity employer",
    "Diversity, Equity",
    "How we feel about Diversity",
    "Accommodations",
    "For US Applicants",
    "Benefits Offering",
    "Privacy Statement",
    "Privacy Notice",
    "Applicant Privacy Notice",
    "Applicant Notice",
    "By providing your information",
    "Your base salary",
    "US base salary range",
    "US Salary Range",
    "The base salary range",
    "Base salary range",
    "Salary range",
    "Applications for this job",
    "This posting is for",
    "NVIDIA uses AI tools",
    "About The Team",
)
ROLE_RELEVANT_PREFIX_MARKERS = (
    "you will",
    "you'll",
    "responsibil",
    "build",
    "design",
    "develop",
    "automate",
    "platform",
    "infrastructure",
    "cloud",
    "api",
    "monitor",
    "observability",
    "terraform",
    "kubernetes",
    "aws",
    "python",
    "ci/cd",
    "sagemaker",
    "snowflake",
    "splunk",
    "software engineering expectations",
    "developer productivity",
)
JOD_HARD_DROP_MARKERS = (
    "base salary",
    "salary range",
    "compensation",
    "competitive compensation",
    "target incentive compensation",
    "on-target-earnings",
    "internal pay equity",
    "benefits",
    "wellness benefits",
    "pay transparency",
    "medical, dental",
    "401(k)",
    "parental leave",
    "equal opportunity",
    "equal employment opportunity",
    "affirmative action",
    "reasonable accommodation",
    "accommodation requests",
    "privacy policy",
    "applicant privacy",
    "personal information",
    "e-verify",
    "recruiter will share",
    "hiring process",
    "interview process",
    "application process",
    "starting pay",
    "we may use artificial intelligence",
    "we may use ai tools",
    "401k",
    "paid company holidays",
)
JOD_HARD_KEEP_MARKERS = (
    "responsibil",
    "what you'll do",
    "what you will do",
    "key responsibilities",
    "job summary",
    "role summary",
    "required qualifications",
    "minimum qualifications",
    "basic qualifications",
    "skills and experience",
)
JOD_CHUNK_KEEP_THRESHOLD = -0.75
JOD_CHUNK_MIN_MEANINGFUL_LENGTH = 24
INLINE_TRAILING_BOILERPLATE_BOUNDARY_RE = re.compile(
    r"\s+(?=(?:"
    r"Benefits\s+Compensation|"
    r"Benefits\b|"
    r"Salary\s+Ranges?|"
    r"Salary\s+&\s+Benefits|"
    r"Pay\s+Disclai\\s*mer|"
    r"Pay\s+Range|"
    r"In\s+the\s+spirit\s+of\s+pay\s+transparency|"
    r"Actual\s+placement\s+in\s+range|"
    r"What\s+[A-Z][A-Za-z0-9]+\s+Offers\s+You|"
    r"Competitive\s+compensation|"
    r"To\s+determine\s+a\s+successful\s+candidate|"
    r"It\s+is\s+the\s+policy\s+of|"
    r"Accommodation\s+requests|"
    r"Disclai\s*me\s*r|"
    r"EE\s*O\b|"
    r"We\s+offer\s+a\s+401k|"
    r"Additional\s+factors\s+considered|"
    r"Actual\s+compensation|"
    r"Individual\s+total\s+compensation|"
    r"The\s+base\s+compensation\s+range|"
    r"Compensation\s+(?:The\s+salary\s+range|for|of|&\s+Benefits|\$)|"
    r"Compensation\b"
    r")\b)",
)
JOD_BOILERPLATE_START_RE = re.compile(
    r"^(?:"
    r"actual compensation|"
    r"actual placement in range|"
    r"benefits\b|"
    r"competitive compensation|"
    r"compensation\b|"
    r"in the spirit of pay transparency|"
    r"individual total compensation|"
    r"it is the policy of .{0,80}?equal employment opportunity|"
    r"to determine a successful candidate|"
    r"we offer a 401k|"
    r"the base compensation range|"
    r"the opportunity to work alongside .{0,160}?compensation|"
    r"what [a-z0-9]+ offers you|"
    r"[a-z0-9 .,'&-]{0,80}? is an equal opportunity employer"
    r")",
    re.IGNORECASE,
)
JOD_CHUNK_TRAINING_EXAMPLES = (
    (
        "keep",
        "Job Summary Build scalable platform services, APIs, automation, observability, "
        "and infrastructure used by engineering teams.",
    ),
    (
        "keep",
        "Responsibilities Design and develop cloud automation, CI/CD pipelines, monitoring, "
        "and distributed systems for production workloads.",
    ),
    (
        "keep",
        "Required Qualifications Experience with Python, Terraform, AWS, Kubernetes, Linux, "
        "security, APIs, and operational troubleshooting.",
    ),
    (
        "keep",
        "What You'll Do Own developer tooling, reliability, data pipelines, integrations, "
        "and automation frameworks across teams.",
    ),
    (
        "keep",
        "Preferred Qualifications Experience with LLM workflows, AI tooling, platform "
        "engineering, observability, and infrastructure as code.",
    ),
    (
        "drop",
        "Benefits include comprehensive medical dental and vision coverage, wellness "
        "stipends, parental leave, paid time off, and retirement savings.",
    ),
    (
        "drop",
        "The base salary range for this role depends on location, market data, equity, "
        "bonus eligibility, and other compensation factors.",
    ),
    (
        "drop",
        "We are an equal opportunity employer and provide reasonable accommodation during "
        "the application and interview process.",
    ),
    (
        "drop",
        "Applicant privacy notice explains how personal information is processed, retained, "
        "and shared under our privacy policy.",
    ),
    (
        "drop",
        "A recruiter will share more details about hiring process logistics, interview "
        "steps, application review, and employment eligibility.",
    ),
)


def usable_job_description(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if is_placeholder_job_description(text):
        return None
    return text


def is_placeholder_job_description(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value).strip().casefold().rstrip(".")
    placeholder = NO_PUBLIC_JOB_DESCRIPTION.casefold().rstrip(".")
    return normalized == placeholder


def job_description_context(job: JobDetails) -> str:
    description = clean_job_description_for_prompt(
        job.description or NO_PUBLIC_JOB_DESCRIPTION
    )
    return limit_context(description, max_chars=JOB_DESCRIPTION_PROMPT_MAX_CHARS)


def clean_job_description_for_prompt(description: str) -> str:
    original = _normalize_job_description_text(description)
    if not original:
        return NO_PUBLIC_JOB_DESCRIPTION

    cleaned = _trim_low_signal_preamble(original)
    cleaned = _trim_trailing_boilerplate(cleaned)
    cleaned = _select_relevant_job_description_chunks(cleaned)
    return cleaned.strip() or original


def limit_context(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars].rsplit("\n", 1)[0].strip()
    return truncated or text[:max_chars].strip()


def _trim_low_signal_preamble(description: str) -> str:
    role_start = _first_heading_match(description, ROLE_RELEVANT_START_HEADINGS)
    if role_start is None or role_start.start() == 0:
        return description

    prefix = description[: role_start.start()]
    has_low_signal_prefix = _first_heading_match(prefix, LOW_SIGNAL_PREAMBLE_HEADINGS) is not None
    if has_low_signal_prefix:
        return description[role_start.start() :].lstrip(" :-\n")
    if len(prefix) > 3_000 and _role_relevant_marker_count(prefix) < 3:
        return description[role_start.start() :].lstrip(" :-\n")
    return description


def _trim_trailing_boilerplate(description: str) -> str:
    last_role_start = max(
        (match.start() for match in _heading_matches(description, ROLE_RELEVANT_START_HEADINGS)),
        default=-1,
    )
    boilerplate = _first_heading_match(
        description,
        TRAILING_BOILERPLATE_HEADINGS,
        start=max(1, min(len(description), 300)),
        skip_before=last_role_start,
        strict_single_word=True,
    )
    if boilerplate is None:
        return description
    return description[: boilerplate.start()].rstrip(" :-\n")


def _select_relevant_job_description_chunks(description: str) -> str:
    if not _contains_any_casefolded(description, JOD_HARD_DROP_MARKERS):
        return description

    chunks = _job_description_chunks(description)
    if len(chunks) <= 1:
        return description

    kept_chunks: list[str] = []
    dropped_count = 0
    seen_role_chunk = False
    for chunk in chunks:
        contains_role_heading = _contains_role_relevant_heading(chunk)
        if _keep_job_description_chunk(
            chunk,
            preserve_company_context=not seen_role_chunk,
        ):
            kept_chunks.append(chunk)
        else:
            dropped_count += 1
        seen_role_chunk = seen_role_chunk or contains_role_heading

    selected = "\n".join(kept_chunks).strip()
    if dropped_count == 0 or not selected:
        return description
    if len(selected) < min(900, len(description) * 0.35):
        return description
    return selected


def _job_description_chunks(description: str) -> list[str]:
    boundary_headings = (
        *ROLE_RELEVANT_START_HEADINGS,
        *LOW_SIGNAL_PREAMBLE_HEADINGS,
        *TRAILING_BOILERPLATE_HEADINGS,
    )
    boundaries = {0, len(description)}
    for match in _heading_matches(description, boundary_headings):
        boundaries.add(match.start())

    chunks: list[str] = []
    sorted_boundaries = sorted(boundaries)
    for index, start in enumerate(sorted_boundaries[:-1]):
        end = sorted_boundaries[index + 1]
        segment = description[start:end].strip(" :-\n")
        if segment:
            chunks.extend(_split_job_description_segment(segment))
    return chunks


def _split_job_description_segment(segment: str) -> list[str]:
    segments = INLINE_TRAILING_BOILERPLATE_BOUNDARY_RE.split(segment)
    pieces = []
    for subsegment in segments:
        pieces.extend(
            piece.strip(" :-\n")
            for piece in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", subsegment)
        )
    chunks: list[str] = []
    for piece in pieces:
        if not piece:
            continue
        chunks.extend(_split_oversized_job_description_piece(piece))
    return chunks


def _split_oversized_job_description_piece(piece: str) -> list[str]:
    if len(piece) <= 900:
        return [piece]
    parts = [part.strip(" :-\n") for part in re.split(r";\s+", piece) if part.strip()]
    if len(parts) > 1:
        return parts
    return [piece]


def _keep_job_description_chunk(
    chunk: str,
    *,
    preserve_company_context: bool = False,
) -> bool:
    text = " ".join(chunk.split())
    if len(text) < JOD_CHUNK_MIN_MEANINGFUL_LENGTH:
        return False

    hard_drop = _contains_any_casefolded(text, JOD_HARD_DROP_MARKERS) or (
        _first_heading_match(text, TRAILING_BOILERPLATE_HEADINGS, strict_single_word=True)
        is not None
    )
    hard_keep = (
        _contains_role_relevant_heading(text)
        or _contains_any_casefolded(text, JOD_HARD_KEEP_MARKERS)
    )
    role_marker_count = _role_relevant_marker_count(text)
    if hard_drop and JOD_BOILERPLATE_START_RE.search(text):
        return False
    if preserve_company_context and not hard_drop:
        return True
    if hard_drop and not hard_keep and role_marker_count < 2:
        return False
    if hard_keep or role_marker_count >= 2:
        return True
    return _JOD_CHUNK_CLASSIFIER.keep_log_odds(text) >= JOD_CHUNK_KEEP_THRESHOLD


def _contains_role_relevant_heading(text: str) -> bool:
    return _first_heading_match(text, ROLE_RELEVANT_START_HEADINGS) is not None


def _role_relevant_marker_count(text: str) -> int:
    normalized = text.casefold()
    return sum(1 for marker in ROLE_RELEVANT_PREFIX_MARKERS if marker in normalized)


def _contains_any_casefolded(text: str, markers: tuple[str, ...]) -> bool:
    normalized = text.casefold()
    return any(marker.casefold() in normalized for marker in markers)


def _jod_chunk_feature_tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z][a-z0-9.+#/-]+", text.casefold())
        if len(token) > 2
    ]


class _JodChunkClassifier:
    def __init__(
        self,
        *,
        class_counts: Counter[str],
        token_counts: dict[str, Counter[str]],
    ) -> None:
        self.class_counts = class_counts
        self.token_counts = token_counts
        self.vocabulary = {
            token for counts in token_counts.values() for token in counts
        }
        self.token_totals = {
            label: sum(counts.values()) for label, counts in token_counts.items()
        }

    @classmethod
    def train(cls, examples: tuple[tuple[str, str], ...]) -> _JodChunkClassifier:
        class_counts: Counter[str] = Counter()
        token_counts: dict[str, Counter[str]] = {"keep": Counter(), "drop": Counter()}
        for label, text in examples:
            class_counts[label] += 1
            token_counts.setdefault(label, Counter()).update(_jod_chunk_feature_tokens(text))
        return cls(class_counts=class_counts, token_counts=token_counts)

    def keep_log_odds(self, text: str) -> float:
        tokens = _jod_chunk_feature_tokens(text)
        keep_log = self._label_log_probability(label="keep", tokens=tokens)
        drop_log = self._label_log_probability(label="drop", tokens=tokens)
        return keep_log - drop_log

    def _label_log_probability(self, *, label: str, tokens: list[str]) -> float:
        label_count = self.class_counts.get(label, 0)
        total_classes = sum(self.class_counts.values())
        class_prior = (label_count + 1) / (total_classes + max(len(self.class_counts), 1))
        token_counts = self.token_counts.get(label, Counter())
        denominator = self.token_totals.get(label, 0) + max(len(self.vocabulary), 1)
        score = math.log(class_prior)
        for token in tokens:
            score += math.log((token_counts.get(token, 0) + 1) / denominator)
        return score


_JOD_CHUNK_CLASSIFIER = _JodChunkClassifier.train(JOD_CHUNK_TRAINING_EXAMPLES)


def _first_heading_match(
    text: str,
    headings: tuple[str, ...],
    *,
    start: int = 0,
    skip_before: int = -1,
    strict_single_word: bool = False,
) -> re.Match[str] | None:
    matches = _heading_matches(
        text,
        headings,
        start=start,
        skip_before=skip_before,
        strict_single_word=strict_single_word,
    )
    if not matches:
        return None
    return min(matches, key=lambda match: match.start())


def _heading_matches(
    text: str,
    headings: tuple[str, ...],
    *,
    start: int = 0,
    skip_before: int = -1,
    strict_single_word: bool = False,
) -> list[re.Match[str]]:
    matches: list[re.Match[str]] = []
    for heading in headings:
        for match in _heading_pattern(heading).finditer(text, pos=start):
            if match.start() < skip_before:
                continue
            if _is_heading_like_match(
                text,
                match,
                heading=heading,
                strict_single_word=strict_single_word,
            ):
                matches.append(match)
    return sorted(matches, key=lambda match: match.start())


def _heading_pattern(heading: str) -> re.Pattern[str]:
    parts = [re.escape(part) for part in heading.split()]
    pattern = r"\s+".join(parts)
    return re.compile(rf"(?<![\w/]){pattern}(?=\s|[:?!.,;()\-/–—]|$)", re.IGNORECASE)


def _is_heading_like_match(
    text: str,
    match: re.Match[str],
    *,
    heading: str,
    strict_single_word: bool,
) -> bool:
    matched_text = match.group(0)
    first_alpha = next((char for char in matched_text if char.isalpha()), "")
    if first_alpha and not first_alpha.isupper():
        return False

    heading_word_count = len(heading.split())
    previous_index = match.start() - 1
    while previous_index >= 0 and text[previous_index].isspace():
        previous_index -= 1
    if (
        previous_index >= 0
        and text[previous_index] not in ".!?:;\n\r"
        and heading_word_count == 1
    ):
        return False

    if strict_single_word and heading_word_count == 1:
        suffix = text[match.end() :].lstrip()
        if suffix and suffix[0] not in ":-–—\n\r":
            return False
    return True


def _normalize_job_description_text(description: str) -> str:
    lines = [" ".join(line.split()) for line in description.splitlines()]
    normalized_lines = [line for line in lines if line]
    if len(normalized_lines) > 1:
        return "\n".join(normalized_lines)
    return " ".join(description.split())
