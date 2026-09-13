"""Version consistency guards.

The scheme: ncrsync/__init__.py holds the only version string. pyproject.toml
derives it, and the CHANGELOG's newest released section must name it. These
tests fail a release that is internally inconsistent.
"""
import re
import tomllib
from pathlib import Path

import ncrsync

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def test_version_is_semver():
    assert SEMVER.match(ncrsync.__version__), ncrsync.__version__


def test_pyproject_takes_version_from_package():
    """No second copy of the version to drift out of sync."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    project = data["project"]
    assert "version" not in project, "version must stay dynamic, not hardcoded"
    assert "version" in project["dynamic"]
    attr = data["tool"]["setuptools"]["dynamic"]["version"]["attr"]
    assert attr == "ncrsync.__version__"


def test_changelog_documents_current_version():
    """The newest released CHANGELOG section matches __version__.

    An '## Unreleased' section above it is allowed and skipped.
    """
    text = (ROOT / "CHANGELOG.md").read_text()
    headings = re.findall(r"^## +(.+?)\s*$", text, re.MULTILINE)
    released = [h for h in headings if not h.lower().startswith("unreleased")]
    assert released, "CHANGELOG has no released section"
    newest = released[0].split()[0].lstrip("v")
    assert newest == ncrsync.__version__, (
        f"CHANGELOG newest release is {newest}, __version__ is {ncrsync.__version__}"
    )
