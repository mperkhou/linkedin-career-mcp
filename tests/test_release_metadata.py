from __future__ import annotations

import re
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHANGELOG_VERSION_RE = re.compile(
    r"^## (?P<version>\d+\.\d+\.\d+)\b",
    flags=re.MULTILINE,
)


def _version_tuple(version: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in version.split("."))


def test_project_version_matches_top_changelog_entry() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = pyproject["project"]["version"]
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = CHANGELOG_VERSION_RE.search(changelog)

    assert match is not None
    assert project_version == match.group("version")


def test_changelog_versions_after_3_0_0_have_release_notes() -> None:
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    versions = [match.group("version") for match in CHANGELOG_VERSION_RE.finditer(changelog)]

    missing_release_notes = [
        version
        for version in versions
        if _version_tuple(version) > (3, 0, 0)
        and not (PROJECT_ROOT / "docs" / "release-notes" / f"{version}.md").exists()
    ]

    assert missing_release_notes == []


def test_top_changelog_version_has_release_note() -> None:
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = CHANGELOG_VERSION_RE.search(changelog)

    assert match is not None
    assert (PROJECT_ROOT / "docs" / "release-notes" / f"{match.group('version')}.md").exists()
