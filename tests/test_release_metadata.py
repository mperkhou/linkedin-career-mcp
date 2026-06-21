from __future__ import annotations

import re
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_project_version_matches_top_changelog_entry() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = pyproject["project"]["version"]
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## (?P<version>\d+\.\d+\.\d+)\b", changelog, flags=re.MULTILINE)

    assert match is not None
    assert project_version == match.group("version")
