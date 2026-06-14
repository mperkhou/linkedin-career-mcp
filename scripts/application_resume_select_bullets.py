#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from linkedin_career_mcp.application_resume import select_first_draft_experience_bullets


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Select scored ARO experience bullets for first-draft rendering."
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Scored Application Resume Object YAML.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the selected first-draft ARO YAML to this path. Defaults to stdout.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    aro = _load_yaml_mapping(args.input)
    selected = select_first_draft_experience_bullets(aro)
    output_text = yaml.safe_dump(selected, sort_keys=False, allow_unicode=False)

    if args.output is None:
        sys.stdout.write(output_text)
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output_text, encoding="utf-8")


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a YAML mapping at the document root.")
    return value


if __name__ == "__main__":
    main()
