#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from linkedin_career_mcp.resume_rendering import (
    render_resume_html,
    render_resume_pdf_from_html,
)
from linkedin_career_mcp.webapp import (
    DEFAULT_DATABASE,
    DEFAULT_OUTPUT_DIR,
    store_application_resume_first_draft,
)

DEFAULT_TEMPLATE = Path("templates/resume/master_resume.html.j2")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Store a first-draft ARO, rendered HTML, PDF, and ATS score in SQLite."
    )
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--input", type=Path, required=True, help="First-draft ARO YAML.")
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / DEFAULT_DATABASE,
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output-html", type=Path)
    parser.add_argument("--output-pdf", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    aro_yaml = args.input.read_text(encoding="utf-8")
    resume_html = render_resume_html(yaml_path=args.input, template_path=args.template)
    resume_pdf = render_resume_pdf_from_html(resume_html)

    if args.output_html is not None:
        args.output_html.parent.mkdir(parents=True, exist_ok=True)
        args.output_html.write_text(resume_html, encoding="utf-8")

    if args.output_pdf is not None:
        args.output_pdf.parent.mkdir(parents=True, exist_ok=True)
        args.output_pdf.write_bytes(resume_pdf)

    store_application_resume_first_draft(
        database_path=args.database,
        job_id=args.job_id,
        application_resume_object=aro_yaml,
        resume_html=resume_html,
        resume_pdf=resume_pdf,
        resume_html_path=args.output_html,
        resume_pdf_path=args.output_pdf,
    )
    print(args.job_id)


if __name__ == "__main__":
    main()
