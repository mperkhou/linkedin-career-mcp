#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml
from jinja2 import ChainableUndefined, Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

DEFAULT_INPUT = Path("profile/MASTER-RESUME.yml")
DEFAULT_TEMPLATE = Path("templates/resume/master_resume.html.j2")
DEFAULT_OUTPUT = Path("tmp/master_resume_preview.html")
URL_RE = re.compile(r"https?://[^\s<>)]+")


def linkify(value: object) -> Markup:
    text = "" if value is None else str(value)
    parts: list[str | Markup] = []
    cursor = 0
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip(".,")
        trailing = match.group(0)[len(url) :]
        parts.append(escape(text[cursor : match.start()]))
        escaped_url = escape(url)
        parts.append(Markup(f'<a href="{escaped_url}">{escaped_url}</a>'))
        if trailing:
            parts.append(escape(trailing))
        cursor = match.end()
    parts.append(escape(text[cursor:]))
    return Markup("").join(parts)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def render_skill_items(value: object) -> str:
    if not isinstance(value, dict):
        return ""

    items = value.get("items")
    if isinstance(items, dict):
        primary = _string_list(items.get("primary"))
        additional = _string_list(items.get("additional"))
        additional_items = set(additional)
        jod_matched_items = [
            item
            for item in _string_list(value.get("jod_matched_items"))
            if item in additional_items
        ]
        candidates = primary + jod_matched_items
    else:
        candidates = _string_list(items)

    rendered: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if item not in seen:
            rendered.append(item)
            seen.add(item)
    return ", ".join(rendered)


def load_resume(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a YAML mapping at the document root.")
    return value


def render_resume_html(*, yaml_path: Path, template_path: Path) -> str:
    template_dir = template_path.parent
    environment = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(enabled_extensions=("html", "j2")),
        undefined=ChainableUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters["linkify"] = linkify
    environment.filters["render_skill_items"] = render_skill_items
    template = environment.get_template(template_path.name)
    return template.render(data=load_resume(yaml_path))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render the draft master-resume YAML through the Jinja HTML template."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    html = render_resume_html(yaml_path=args.input, template_path=args.template)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
