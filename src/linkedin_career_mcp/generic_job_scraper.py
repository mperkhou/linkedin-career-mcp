from __future__ import annotations

import hashlib
import re
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import extruct
import httpx
import trafilatura
from bs4 import BeautifulSoup
from w3lib.html import get_base_url

from linkedin_career_mcp.errors import ProviderError
from linkedin_career_mcp.models import JobDetails

MIN_DESCRIPTION_CHARS = 120
TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "source",
    "trk",
}


async def fetch_generic_job_details(
    *,
    url: str,
    user_agent: str,
    timeout_seconds: float,
) -> JobDetails:
    normalized_url = normalize_job_url(url)
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as client:
            response = await client.get(normalized_url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ProviderError(f"Generic job URL fetch failed: {exc}") from exc

    return extract_generic_job_details_from_html(
        html=response.text,
        url=str(response.url),
    )


def extract_generic_job_details_from_html(*, html: str, url: str) -> JobDetails:
    normalized_url = normalize_job_url(url)
    base_url = get_base_url(html, normalized_url)
    structured_job = _find_structured_job_posting(html=html, base_url=base_url)
    fallback = _fallback_job_fields(html=html, url=normalized_url)

    title = _clean_text(
        _first_value(structured_job, "title", "name")
        or fallback.get("title")
        or "Job Posting"
    )
    description = _clean_description(
        _first_value(structured_job, "description", "responsibilities", "qualifications")
        or fallback.get("description")
    )
    if not description or len(description) < MIN_DESCRIPTION_CHARS:
        raise ProviderError("No usable job description was found at that URL.")

    hiring_organization = _first_mapping(structured_job.get("hiringOrganization"))
    company = _clean_text(
        _first_value(hiring_organization, "name", "legalName")
        or fallback.get("company")
    )
    company_url = _clean_text(_first_value(hiring_organization, "sameAs", "url"))

    return JobDetails(
        job_id=generic_job_id(normalized_url),
        title=title or "Job Posting",
        company=company,
        location=_job_location(structured_job),
        listed_at=_clean_text(_first_value(structured_job, "datePosted")),
        job_url=normalized_url,
        company_url=company_url or None,
        workplace_type=_clean_text(_first_value(structured_job, "jobLocationType")),
        source="generic_url",
        description=description,
        seniority_level=_clean_text(_first_value(structured_job, "experienceRequirements")),
        employment_type=_join_values(structured_job.get("employmentType")),
        job_function=_clean_text(_first_value(structured_job, "occupationalCategory")),
        industries=_clean_text(_first_value(structured_job, "industry")),
    )


def normalize_job_url(url: str) -> str:
    value = str(url or "").strip()
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("Paste a valid http or https job posting URL.")

    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if not _is_tracking_query_key(key)
    ]
    query = urlencode(query_items, doseq=True)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            query,
            "",
        )
    )


def generic_job_id(url: str) -> str:
    digest = hashlib.sha1(normalize_job_url(url).encode("utf-8")).hexdigest()
    return f"url-{digest[:12]}"


def _is_tracking_query_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in TRACKING_QUERY_KEYS or lowered.startswith(TRACKING_QUERY_PREFIXES)


def _find_structured_job_posting(*, html: str, base_url: str) -> dict[str, object]:
    data = extruct.extract(
        html,
        base_url=base_url,
        syntaxes=["json-ld", "microdata", "rdfa"],
        uniform=True,
    )
    for item in _iter_structured_items(data):
        if _is_job_posting(item):
            return item
    return {}


def _iter_structured_items(value: object) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            items.append(node)
            for child in node.values():
                if isinstance(child, list):
                    for entry in child:
                        walk(entry)
                elif isinstance(child, dict):
                    walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return items


def _is_job_posting(item: dict[str, object]) -> bool:
    raw_types = item.get("@type") or item.get("type")
    values = raw_types if isinstance(raw_types, list) else [raw_types]
    for value in values:
        normalized = str(value or "").casefold()
        if normalized.endswith("jobposting") or normalized.endswith("job posting"):
            return True
    return False


def _fallback_job_fields(*, html: str, url: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    page_title = _text(soup.select_one("title"))
    title = _clean_text(
        _meta_content(soup, "og:title")
        or _meta_content(soup, "twitter:title")
        or _text(soup.select_one("h1"))
        or page_title
    )
    company = _clean_text(
        _meta_content(soup, "og:site_name")
        or _meta_content(soup, "application-name")
        or _company_from_page_title(page_title)
        or urlsplit(url).netloc.removeprefix("www.")
    )
    description = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        favor_recall=True,
    )
    if not description:
        description = _main_text_fallback(soup)
    return {
        "title": title,
        "company": company,
        "description": _clean_description(description),
    }


def _company_from_page_title(title: str) -> str:
    match = re.search(r"\bat\s+(.+?)\s*$", title.strip(), flags=re.IGNORECASE)
    if not match:
        return ""
    company = match.group(1).strip(" -|")
    return _clean_text(company)


def _meta_content(soup: BeautifulSoup, name: str) -> str:
    node = soup.find("meta", attrs={"property": name}) or soup.find(
        "meta",
        attrs={"name": name},
    )
    return str(node.get("content") or "") if node else ""


def _main_text_fallback(soup: BeautifulSoup) -> str:
    node = soup.select_one("main, article, [role='main'], body")
    if node is None:
        return ""
    return node.get_text("\n", strip=True)


def _job_location(job: dict[str, object]) -> str | None:
    locations = job.get("jobLocation")
    values = locations if isinstance(locations, list) else [locations]
    parts: list[str] = []
    for location in values:
        location_map = _first_mapping(location)
        if not location_map:
            continue
        address = _first_mapping(location_map.get("address"))
        location_text = _join_values(
            [
                _first_value(address, "streetAddress"),
                _first_value(address, "addressLocality"),
                _first_value(address, "addressRegion"),
                _first_value(address, "postalCode"),
                _first_value(address, "addressCountry"),
            ]
        ) or _clean_text(_first_value(location_map, "name"))
        if location_text:
            parts.append(location_text)
    return _join_values(parts) or None


def _first_value(mapping: object, *keys: str) -> str:
    if not isinstance(mapping, dict):
        return ""
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, dict):
            nested_value = _first_value(value, "@value", "name", "text")
            if nested_value:
                return nested_value
        elif isinstance(value, list):
            joined = _join_values(value)
            if joined:
                return joined
        elif value is not None:
            cleaned = _clean_text(str(value))
            if cleaned:
                return cleaned
    return ""


def _first_mapping(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return {}


def _join_values(value: object) -> str | None:
    values = value if isinstance(value, list) else [value]
    parts: list[str] = []
    for item in values:
        if isinstance(item, dict):
            part = _first_value(item, "@value", "name", "text")
        else:
            part = _clean_text(str(item or ""))
        if part:
            parts.append(part)
    return ", ".join(dict.fromkeys(parts)) or None


def _clean_description(value: object) -> str:
    text = str(value or "").strip()
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text("\n", strip=True)
    return _clean_text(unescape(text))


def _clean_text(value: object) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", str(value or ""))
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _text(node: object | None) -> str:
    if node is None or not hasattr(node, "get_text"):
        return ""
    return str(node.get_text(" ", strip=True))
