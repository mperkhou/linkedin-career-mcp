#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from linkedin_career_mcp.resume_rendering import render_resume_html

DEFAULT_INPUT = Path("profile/MASTER-RESUME.yml")
DEFAULT_TEMPLATE = Path("templates/resume/master_resume.html.j2")
DEFAULT_OUTPUT = Path("tmp/master_resume_preview.html")


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
