#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from linkedin_career_mcp.application_resume import (
    CORE_SKILLS_PROMPT_JOD_MAX_CHARS,
    DEFAULT_MASTER_RESUME_PATH,
    apply_core_skill_jod_matches,
    build_core_skills_jod_match_prompt,
    initialize_application_resume_object,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run ARO pass one: Core Skills JOD matching."
    )
    parser.add_argument("--master-resume", type=Path, default=DEFAULT_MASTER_RESUME_PATH)
    parser.add_argument("--trimmed-jod", type=Path, required=True)
    parser.add_argument(
        "--core-skill-response",
        type=Path,
        help="JSON response from the Core Technical Skills JOD-match prompt.",
    )
    parser.add_argument(
        "--prompt-output",
        type=Path,
        help="Write the compact Core Technical Skills prompt to this path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the matched ARO YAML to this path. Defaults to stdout when response is set.",
    )
    parser.add_argument("--max-jod-chars", type=int, default=CORE_SKILLS_PROMPT_JOD_MAX_CHARS)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    aro = initialize_application_resume_object(args.master_resume)
    trimmed_jod = args.trimmed_jod.read_text(encoding="utf-8")
    prompt = build_core_skills_jod_match_prompt(
        application_resume=aro,
        trimmed_job_description=trimmed_jod,
        max_jod_chars=args.max_jod_chars,
    )

    if args.prompt_output is not None:
        args.prompt_output.parent.mkdir(parents=True, exist_ok=True)
        args.prompt_output.write_text(f"{prompt}\n", encoding="utf-8")

    if args.core_skill_response is None:
        if args.prompt_output is None:
            sys.stdout.write(f"{prompt}\n")
        return

    response = args.core_skill_response.read_text(encoding="utf-8")
    matched_aro = apply_core_skill_jod_matches(
        application_resume=aro,
        core_skill_response=response,
    )
    output_text = yaml.safe_dump(matched_aro, sort_keys=False, allow_unicode=False)

    if args.output is None:
        sys.stdout.write(output_text)
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output_text, encoding="utf-8")


if __name__ == "__main__":
    main()
