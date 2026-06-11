"""Version extraction and EOL audit logic — all offline."""

from openedx_ai_agent.classify import (
    classify_repo,
    eol_status,
    extract_versions,
    supported_versions,
)

# Shaped like openedx-filters after the 5.2 campaign (tox factors + CI matrix).
TOX_INI = """
[tox]
envlist = py{311,312}-django{42,52}, quality

[testenv]
deps =
    django42: Django>=4.2,<4.3
    django52: Django>=5.2,<5.3
"""

CI_YML = """
jobs:
  tests:
    strategy:
      matrix:
        python-version: ['3.11', '3.12']
        django-version: ['4.2', '5.2']
"""

SETUP_PY = """
classifiers=[
    'Framework :: Django',
    'Framework :: Django :: 4.2',
    'Framework :: Django :: 5.2',
],
"""


def _entry(tox=None, ci=None, setup=None, repo="openedx-filters"):
    files = {"tox.ini": tox, ".github/workflows/ci.yml": ci, "setup.py": setup}
    return {
        "repo": repo,
        "classification": classify_repo(repo),
        "versions": extract_versions("django", files),
    }


def test_extract_from_tox_factors():
    versions = extract_versions("django", {"tox.ini": TOX_INI})
    assert versions["tox"] == ["4.2", "5.2"]


def test_extract_from_ci_matrix():
    versions = extract_versions("django", {".github/workflows/ci.yml": CI_YML})
    assert versions["ci"] == ["4.2", "5.2"]


def test_extract_from_classifiers():
    versions = extract_versions("django", {"setup.py": SETUP_PY})
    assert versions["classifiers"] == ["4.2", "5.2"]


def test_tox_beats_classifiers_as_signal():
    # Classifiers drift; tox is the source of truth.
    entry = _entry(tox=TOX_INI.replace("52", "42"), setup=SETUP_PY)
    assert supported_versions(entry) == ["4.2"]


def test_classify():
    assert classify_repo("openedx-platform") == "platform"
    assert classify_repo("course-discovery") == "service"
    assert classify_repo("openedx-filters") == "library"


def test_eol_repo_flagged():
    entry = _entry(tox="[tox]\nenvlist = py311-django42\n")
    finding = eol_status(entry, today="2026-06-12")
    assert finding is not None
    assert finding["supported"] == ["4.2"]
    assert finding["latest_eol_date"] == "2026-04-07"


def test_current_repo_not_flagged():
    entry = _entry(tox=TOX_INI)  # supports 5.2 → in support until 2028
    assert eol_status(entry, today="2026-06-12") is None


def test_no_signal_returns_none():
    entry = _entry()
    assert eol_status(entry, today="2026-06-12") is None
