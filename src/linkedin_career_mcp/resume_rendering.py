from __future__ import annotations

import html as html_lib
import re
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

import yaml
from bs4 import BeautifulSoup
from jinja2 import ChainableUndefined, Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

_RESUME_RICH_TAG_RE = re.compile(
    r"</?\s*(a|b|br|div|em|i|p|span|strong)\b",
    re.IGNORECASE,
)
_RESUME_LINK_RE = re.compile(r"https?://[^\s<>)]*")
MAX_RENDERED_JOD_MATCHED_SKILLS_PER_CATEGORY = 8


def linkify(value: object) -> Markup:
    text = "" if value is None else str(value)
    parts: list[str | Markup] = []
    cursor = 0
    for match in _RESUME_LINK_RE.finditer(text):
        label = match.group(0)
        url = label.rstrip(".,")
        trailing = label[len(label.rstrip(".,")) :]
        parts.append(escape(text[cursor : match.start()]))
        escaped_url = escape(url)
        escaped_label = escape(label.rstrip(".,"))
        parts.append(Markup(f'<a href="{escaped_url}">{escaped_label}</a>'))
        if trailing:
            parts.append(escape(trailing))
        cursor = match.end()
    parts.append(escape(text[cursor:]))
    return Markup("").join(parts)


def rich_text(value: object) -> Markup:
    return Markup(sanitize_resume_rich_text(value))


def sanitize_resume_rich_text(value: object) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    text = html_lib.unescape(text)
    if not _RESUME_RICH_TAG_RE.search(text):
        return str(linkify(text))

    soup = BeautifulSoup(text, "html.parser")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    return "".join(_resume_rich_node_markup(child) for child in soup.contents).strip()


def _resume_rich_node_markup(node: object) -> str:
    from bs4 import NavigableString, Tag

    if isinstance(node, NavigableString):
        return str(linkify(str(node)))
    if not isinstance(node, Tag):
        return ""

    name = (node.name or "").lower()
    if name == "br":
        return "<br/>"

    inner = "".join(_resume_rich_node_markup(child) for child in node.children)
    if name in {"b", "strong"}:
        return f"<b>{inner}</b>"
    if name == "span" and _span_is_semantic_strong(node):
        return f"<b>{inner}</b>"
    if name in {"i", "em"}:
        return f"<i>{inner}</i>"
    if name == "a":
        href = str(node.get("href") or "").strip()
        if href.startswith(("http://", "https://", "mailto:")):
            safe_href = escape(href)
            return f'<a href="{safe_href}">{inner}</a>'
        return inner
    return inner


def _span_is_semantic_strong(node: object) -> bool:
    from bs4 import Tag

    if not isinstance(node, Tag):
        return False
    if str(node.get("data-streamdown") or "").lower() == "strong":
        return True
    classes = node.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    return "font-semibold" in classes or "font-bold" in classes


def render_skill_items(value: object) -> str:
    return ", ".join(_rendered_skill_items(value, seen=set()))


def render_core_skill_rows(value: object) -> list[dict[str, str]]:
    if not isinstance(value, dict):
        return []

    raw_bullets = value.get("bullet_points")
    if not isinstance(raw_bullets, list):
        return []

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for bullet in raw_bullets:
        if isinstance(bullet, str):
            text = bullet.strip()
            if text:
                rows.append({"category": "", "text": text})
            continue
        if not isinstance(bullet, dict):
            continue
        items = _rendered_skill_items(bullet, seen=seen)
        if not items:
            continue
        rows.append(
            {
                "category": str(bullet.get("category") or "").strip(),
                "text": ", ".join(items),
            }
        )
    return rows


def _rendered_skill_items(value: object, *, seen: set[str]) -> list[str]:
    if not isinstance(value, dict):
        return []

    items = value.get("items")
    if isinstance(items, dict):
        primary = _string_list(items.get("primary"))
        additional = _string_list(items.get("additional"))
        display_items = primary + additional
        display_by_key = {
            _skill_key(item): item
            for item in display_items
        }
        alias_by_key = _skill_aliases(items, display_by_key)
        additional_items = set(additional)
        jod_matched_items: list[str] = []
        matched_keys: set[str] = set()
        for item in _string_list(value.get("jod_matched_items")):
            canonical = alias_by_key.get(_skill_key(item), item)
            if canonical in additional_items:
                key = _skill_key(canonical)
                if key in matched_keys:
                    continue
                matched_keys.add(key)
                jod_matched_items.append(canonical)
                if len(jod_matched_items) >= MAX_RENDERED_JOD_MATCHED_SKILLS_PER_CATEGORY:
                    break
        candidates = primary + jod_matched_items
    else:
        candidates = _string_list(items)

    rendered: list[str] = []
    for item in candidates:
        key = _skill_key(item)
        if key and key not in seen:
            rendered.append(item)
            seen.add(key)
    return rendered


def _skill_aliases(
    items: dict[str, object],
    display_by_key: dict[str, str],
) -> dict[str, str]:
    aliases: dict[str, str] = {}
    raw_match_terms = items.get("match_terms")
    if not isinstance(raw_match_terms, dict):
        return aliases
    for raw_skill, raw_terms in raw_match_terms.items():
        skill = display_by_key.get(_skill_key(raw_skill))
        if skill is None:
            continue
        for term in _string_list(raw_terms):
            aliases[_skill_key(term)] = skill
    return aliases


def _skill_key(value: object) -> str:
    text = str(value or "").strip().lower()
    replacements = {
        "python 3": "python",
        "rest api": "restful api",
        "rest apis": "restful apis",
        "managed postgresql": "postgresql",
        "linux environments": "linux",
        "cloud monitoring": "observability",
    }
    text = replacements.get(text, text)
    return "".join(character for character in text if character.isalnum())


def load_resume(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a YAML mapping at the document root.")
    return value


def render_resume_html(*, yaml_path: Path, template_path: Path) -> str:
    return render_resume_html_from_mapping(
        resume=load_resume(yaml_path),
        template_path=template_path,
    )


def render_resume_html_from_mapping(
    *,
    resume: dict[str, Any],
    template_path: Path,
) -> str:
    template_dir = template_path.parent
    environment = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(enabled_extensions=("html", "j2")),
        undefined=ChainableUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters["linkify"] = linkify
    environment.filters["rich_text"] = rich_text
    environment.filters["render_core_skill_rows"] = render_core_skill_rows
    environment.filters["render_skill_items"] = render_skill_items
    template = environment.get_template(template_path.name)
    return template.render(data=resume)


def render_resume_pdf_from_html(html: str) -> bytes:
    try:
        return _render_pdf_with_playwright(html)
    except Exception as exc:
        print(
            "HTML-to-PDF rendering fell back to plain-text ReportLab output: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return _render_text_pdf_from_html(html)


def _render_pdf_with_playwright(html: str) -> bytes:
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as tmp_dir:
        html_path = Path(tmp_dir) / "resume.html"
        html_path.write_text(html, encoding="utf-8")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
                return page.pdf(format="Letter", print_background=True)
            finally:
                browser.close()


def _render_text_pdf_from_html(html: str) -> bytes:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style"]):
        node.decompose()
    lines = [
        line.strip()
        for line in soup.get_text("\n").splitlines()
        if line.strip()
    ]

    buffer = BytesIO()
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "ResumeHtmlFallbackBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.4,
        leading=11.2,
        spaceAfter=2,
    )
    story: list[Any] = []
    for line in lines:
        story.append(Paragraph(html_lib.escape(line), body))
        story.append(Spacer(1, 1))

    if not story:
        story.append(Paragraph("Resume HTML was empty.", body))

    document = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        rightMargin=54,
        leftMargin=54,
        topMargin=58,
        bottomMargin=52,
    )
    document.build(story)
    return buffer.getvalue()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]
