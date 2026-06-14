from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from io import BytesIO
from math import sqrt

from pypdf import PdfReader


@dataclass(frozen=True)
class AtsProxyScore:
    overall_score: int
    parsing_score: int
    keyword_match_score: int
    semantic_match_score: int
    formatting_risk: str
    missing_high_value_terms: tuple[str, ...]


TECHNICAL_TERMS = (
    "access control",
    "agentic ai",
    "ai",
    "api",
    "api integration",
    "ansible",
    "authentication",
    "automation",
    "aws",
    "azure",
    "bash",
    "ci/cd",
    "cloud",
    "cloud infrastructure",
    "compliance",
    "containerization",
    "data pipeline",
    "deepseek",
    "developer tooling",
    "devops",
    "distributed systems",
    "django",
    "docker",
    "elasticsearch",
    "fastapi",
    "filebeat",
    "github actions",
    "graphql",
    "infrastructure as code",
    "java",
    "javascript",
    "jenkins",
    "kafka",
    "kubernetes",
    "linux",
    "llm",
    "logstash",
    "microservices",
    "monitoring",
    "node.js",
    "observability",
    "oci",
    "openrouter",
    "opensearch",
    "postgresql",
    "prompt engineering",
    "python",
    "react",
    "rest api",
    "rbac",
    "reliability",
    "scalability",
    "security",
    "shell",
    "sql",
    "terraform",
    "typescript",
    "cloud native",
)
TERM_ALIASES = {
    "ci/cd": ("ci/cd", "cicd", "continuous integration", "continuous deployment"),
    "cloud native": (
        "cloud native",
        "cloud-native",
        "cloud native platforms",
        "cloud-native platforms",
    ),
    "containerization": ("containerization", "containerized", "dockerized", "container images"),
    "data pipeline": ("data pipeline", "data pipelines"),
    "reliability": ("reliability", "reliable", "resilience", "resilient"),
    "rest api": ("rest api", "rest apis", "restful api", "restful apis"),
    "scalability": ("scalability", "scalable", "horizontally scalable"),
}
NEGATED_TERM_PATTERNS = (
    "not",
    "not a",
    "not an",
    "isn't",
    "is not",
    "isn t",
    "isnt",
    "not just",
    "no",
    "without",
)

SEMANTIC_CLUSTERS = (
    (
        "automation",
        {
            "ansible",
            "automation",
            "ci/cd",
            "github actions",
            "infrastructure as code",
            "jenkins",
            "python",
            "terraform",
        },
    ),
    (
        "cloud platform",
        {
            "aws",
            "azure",
            "cloud",
            "cloud infrastructure",
            "cloud native",
            "containerization",
            "docker",
            "kubernetes",
            "oci",
        },
    ),
    (
        "distributed systems",
        {
            "api",
            "data pipeline",
            "distributed systems",
            "kafka",
            "microservices",
            "reliability",
            "scalability",
        },
    ),
    (
        "observability",
        {
            "elasticsearch",
            "filebeat",
            "logstash",
            "monitoring",
            "observability",
            "opensearch",
        },
    ),
    (
        "security",
        {
            "access control",
            "authentication",
            "compliance",
            "rbac",
            "security",
        },
    ),
    (
        "ai",
        {
            "agentic ai",
            "ai",
            "deepseek",
            "llm",
            "openrouter",
            "prompt engineering",
        },
    ),
)

SECTION_PATTERNS = (
    r"professional\s+summary",
    r"core\s+technical\s+skills",
    r"professional\s+experience",
    r"education",
    r"certifications?",
)
CONTACT_PATTERNS = (
    r"[\w.+-]+@[\w.-]+\.[a-z]{2,}",
    r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b",
    r"linkedin\.com/in/",
)
REQUIRED_LANGUAGE = (
    "required",
    "must have",
    "must-have",
    "minimum",
    "experience with",
    "proficiency",
    "strong experience",
)
STOPWORDS = {
    "about",
    "across",
    "after",
    "also",
    "and",
    "are",
    "based",
    "build",
    "business",
    "can",
    "candidate",
    "candidates",
    "company",
    "customer",
    "customers",
    "design",
    "development",
    "engineering",
    "experience",
    "for",
    "from",
    "have",
    "help",
    "including",
    "into",
    "looking",
    "new",
    "our",
    "platform",
    "product",
    "products",
    "role",
    "services",
    "software",
    "systems",
    "team",
    "that",
    "the",
    "this",
    "with",
    "work",
    "working",
    "you",
}
REPEATED_PHRASE_TECH_ANCHOR_WORDS = {
    word
    for term in TECHNICAL_TERMS
    for word in re.findall(r"[a-z][a-z0-9+#/-]+", term)
    if word not in STOPWORDS
} | {
    "artificial",
    "hardware",
    "intelligence",
    "productivity",
}
REPEATED_PHRASE_BLOCKED_WORDS = {
    "angeles",
    "chance",
    "county",
    "duties",
    "fair",
    "ordinance",
    "posting",
}


def calculate_ats_proxy_score(*, resume_pdf: bytes, job_description: str) -> AtsProxyScore:
    resume_text = extract_pdf_text(resume_pdf)
    resume_normalized = _normalize_text(resume_text)
    job_normalized = _normalize_text(job_description)
    job_terms = _extract_weighted_terms(job_description)
    resume_terms = _matching_terms(resume_normalized, (term for term, _ in job_terms))
    missing_terms = _missing_high_value_terms(
        job_terms=job_terms,
        resume_terms=resume_terms,
    )

    parsing_score = _parsing_score(resume_text, resume_normalized)
    keyword_score = _keyword_score(job_terms, resume_terms)
    semantic_score = _semantic_score(
        resume_normalized=resume_normalized,
        job_normalized=job_normalized,
        job_terms=job_terms,
        resume_terms=resume_terms,
    )
    formatting_risk = _formatting_risk(parsing_score=parsing_score, resume_text=resume_text)
    formatting_score = {"Low": 100, "Medium": 70, "High": 35}[formatting_risk]
    overall = _clamp_score(
        round(
            parsing_score * 0.25
            + keyword_score * 0.35
            + semantic_score * 0.30
            + formatting_score * 0.10
        )
    )
    return AtsProxyScore(
        overall_score=overall,
        parsing_score=parsing_score,
        keyword_match_score=keyword_score,
        semantic_match_score=semantic_score,
        formatting_risk=formatting_risk,
        missing_high_value_terms=missing_terms,
    )


def extract_pdf_text(pdf_content: bytes) -> str:
    if not pdf_content:
        return ""
    try:
        reader = PdfReader(BytesIO(pdf_content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _parsing_score(resume_text: str, resume_normalized: str) -> int:
    if not resume_text.strip():
        return 0
    length_score = min(35, round(len(resume_text) / 1800 * 35))
    section_score = sum(
        7 for pattern in SECTION_PATTERNS if re.search(pattern, resume_normalized)
    )
    contact_score = sum(
        5 for pattern in CONTACT_PATTERNS if re.search(pattern, resume_normalized)
    )
    line_count = len([line for line in resume_text.splitlines() if line.strip()])
    structure_score = 15 if line_count >= 20 else max(0, round(line_count / 20 * 15))
    noisy_text_penalty = 10 if "\ufffd" in resume_text else 0
    return _clamp_score(
        length_score
        + section_score
        + contact_score
        + structure_score
        - noisy_text_penalty
    )


def _keyword_score(
    job_terms: list[tuple[str, float]],
    resume_terms: set[str],
) -> int:
    if not job_terms:
        return 50
    total_weight = sum(weight for _, weight in job_terms)
    matched_weight = sum(weight for term, weight in job_terms if term in resume_terms)
    return _clamp_score(round(matched_weight / total_weight * 100))


def _semantic_score(
    *,
    resume_normalized: str,
    job_normalized: str,
    job_terms: list[tuple[str, float]],
    resume_terms: set[str],
) -> int:
    if not job_terms:
        return 50
    total_weight = 0.0
    matched_weight = 0.0
    for term, weight in job_terms:
        total_weight += weight
        if term in resume_terms:
            matched_weight += weight
            continue
        cluster = _cluster_for_term(term)
        if cluster and any(_contains_term(resume_normalized, related) for related in cluster):
            matched_weight += weight * 0.65

    token_similarity = _token_similarity_score(
        job_normalized=job_normalized,
        resume_normalized=resume_normalized,
    )
    coverage = matched_weight / total_weight
    return _clamp_score(round((coverage * 0.75 + token_similarity * 0.25) * 100))


def _formatting_risk(*, parsing_score: int, resume_text: str) -> str:
    if parsing_score < 55:
        return "High"
    lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
    average_line_length = sum(len(line) for line in lines) / max(len(lines), 1)
    if parsing_score < 75 or average_line_length > 140:
        return "Medium"
    return "Low"


def _missing_high_value_terms(
    *,
    job_terms: list[tuple[str, float]],
    resume_terms: set[str],
    limit: int = 8,
) -> tuple[str, ...]:
    missing_required = [
        term for term, weight in job_terms if term not in resume_terms and weight >= 1.0
    ]
    return tuple(missing_required[:limit])


def _extract_weighted_terms(job_description: str) -> list[tuple[str, float]]:
    normalized = _normalize_text(job_description)
    terms: dict[str, float] = {}
    for term in TECHNICAL_TERMS:
        if _contains_weightable_term(job_description, normalized, term):
            terms[term] = max(terms.get(term, 0.0), _term_weight(job_description, term))
    for phrase in _extract_repeated_phrases(normalized):
        if phrase not in terms:
            terms[phrase] = 0.75
    return sorted(terms.items(), key=lambda item: (-item[1], item[0]))[:40]


def _extract_repeated_phrases(text: str) -> list[str]:
    words = [word for word in re.findall(r"[a-z][a-z0-9.+#/-]+", text) if word not in STOPWORDS]
    phrases: dict[str, int] = {}
    for size in (2, 3):
        for index in range(0, max(len(words) - size + 1, 0)):
            phrase_words = words[index : index + size]
            if any(len(word) < 3 for word in phrase_words):
                continue
            phrase = " ".join(phrase_words)
            phrases[phrase] = phrases.get(phrase, 0) + 1
    return [
        phrase
        for phrase, count in sorted(phrases.items(), key=lambda item: (-item[1], item[0]))
        if count > 1 and _is_relevant_repeated_phrase(phrase)
    ][:12]


def _is_relevant_repeated_phrase(phrase: str) -> bool:
    words = set(phrase.split())
    if words & REPEATED_PHRASE_BLOCKED_WORDS:
        return False
    return bool(words & REPEATED_PHRASE_TECH_ANCHOR_WORDS)


def _term_weight(job_description: str, term: str) -> float:
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", job_description):
        normalized_sentence = _normalize_text(sentence)
        if _contains_term(normalized_sentence, term) and any(
            language in normalized_sentence for language in REQUIRED_LANGUAGE
        ):
            return 1.75
    return 1.0


def _matching_terms(text: str, terms: object) -> set[str]:
    return {term for term in terms if isinstance(term, str) and _contains_term(text, term)}


def _cluster_for_term(term: str) -> set[str] | None:
    for _, cluster_terms in SEMANTIC_CLUSTERS:
        if term in cluster_terms:
            return cluster_terms
    return None


def _keyword_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z][a-z0-9+#/-]+", text)
        if len(token) > 2 and token not in STOPWORDS
    }


def _token_similarity_score(*, job_normalized: str, resume_normalized: str) -> float:
    job_tokens = _keyword_tokens(job_normalized)
    resume_tokens = _keyword_tokens(resume_normalized)
    if not job_tokens:
        return 0.5

    recall = len(job_tokens & resume_tokens) / len(job_tokens)
    cosine = _token_cosine_similarity(
        _keyword_token_counts(job_normalized),
        _keyword_token_counts(resume_normalized),
    )
    return (recall * 0.6) + (cosine * 0.4)


def _keyword_token_counts(text: str) -> Counter[str]:
    return Counter(
        token
        for token in re.findall(r"[a-z][a-z0-9+#/-]+", text)
        if len(token) > 2 and token not in STOPWORDS
    )


def _token_cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = sqrt(sum(value * value for value in left.values()))
    right_norm = sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _contains_term(text: str, term: str) -> bool:
    return any(_contains_normalized_phrase(text, alias) for alias in _term_aliases(term))


def _contains_weightable_term(original_text: str, normalized_text: str, term: str) -> bool:
    if not _contains_term(normalized_text, term):
        return False
    return any(
        _contains_term(normalized_sentence, term)
        and not _has_negated_term_context(normalized_sentence, term)
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", original_text)
        if (normalized_sentence := _normalize_text(sentence))
    )


def _has_negated_term_context(normalized_sentence: str, term: str) -> bool:
    for alias in _term_aliases(term):
        normalized_alias = _normalize_text(alias)
        for negation in NEGATED_TERM_PATTERNS:
            pattern = (
                rf"(?<![a-z0-9]){re.escape(negation)}"
                rf"(?:\s+\w+){{0,3}}\s+{re.escape(normalized_alias)}(?![a-z0-9])"
            )
            if re.search(pattern, normalized_sentence):
                return True
    return False


def _contains_normalized_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = re.escape(_normalize_text(phrase))
    return bool(re.search(rf"(?<![a-z0-9]){normalized_phrase}(?![a-z0-9])", text))


def _term_aliases(term: str) -> tuple[str, ...]:
    normalized = _normalize_text(term)
    aliases = TERM_ALIASES.get(normalized, ())
    return (term, *aliases)


def _normalize_text(text: str) -> str:
    value = text.casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _clamp_score(value: int) -> int:
    return max(0, min(100, value))
