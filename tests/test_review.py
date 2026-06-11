"""Reviewer checks against a real (temporary) git repository."""

import subprocess

import pytest

from openedx_ai_agent.review import render_report, review_checkout

BASE_TOX = "[tox]\nenvlist = py{311,312}-django{52}\n"
UPGRADED_TOX = "[tox]\nenvlist = py{311,312}-django{52,62}\n"
BASE_CI = "matrix:\n  django-version: ['5.2']\n"
UPGRADED_CI = "matrix:\n  django-version: ['5.2', '6.2']\n"
BASE_SETUP = "classifiers=['Framework :: Django :: 5.2']\nversion='1.0.0'\n"
UPGRADED_SETUP = (
    "classifiers=['Framework :: Django :: 5.2', 'Framework :: Django :: 6.2']\nversion='2.0.0'\n"
)


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """A base commit on main, with HEAD on an upgrade branch."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "tox.ini").write_text(BASE_TOX)
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(BASE_CI)
    (tmp_path / "setup.py").write_text(BASE_SETUP)
    (tmp_path / "CHANGELOG.rst").write_text("History\n")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text('__version__ = "1.0.0"\n')
    (tmp_path / "tests_dir").mkdir()
    (tmp_path / "tests_dir" / "test_x.py").write_text("def test_x(): pass\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    _git(tmp_path, "checkout", "-qb", "upgrade/django62")
    return tmp_path


def _commit_all(repo):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "feat: add django 6.2 support")


def test_good_upgrade_passes(repo):
    (repo / "tox.ini").write_text(UPGRADED_TOX)
    (repo / ".github" / "workflows" / "ci.yml").write_text(UPGRADED_CI)
    (repo / "setup.py").write_text(UPGRADED_SETUP)
    (repo / "CHANGELOG.rst").write_text("History\n2.0.0 — django 6.2 support\n")
    (repo / "pkg" / "__init__.py").write_text('__version__ = "2.0.0"\n')
    _commit_all(repo)

    checks = review_checkout(repo, "django", "6.2", "5.2", base="main")
    assert all(c.passed for c in checks), [c for c in checks if not c.passed]


def test_dropped_old_version_fails(repo):
    # Agent jumped to 6.2-only — violates the dual-compat bridge.
    (repo / "tox.ini").write_text("[tox]\nenvlist = py{311,312}-django{62}\n")
    _commit_all(repo)
    checks = {c.name: c for c in review_checkout(repo, "django", "6.2", "5.2", base="main")}
    assert not checks["old_version_retained"].passed


def test_deleted_test_flagged(repo):
    (repo / "tox.ini").write_text(UPGRADED_TOX)
    (repo / "tests_dir" / "test_x.py").unlink()
    _commit_all(repo)
    checks = {c.name: c for c in review_checkout(repo, "django", "6.2", "5.2", base="main")}
    assert not checks["no_tests_deleted"].passed
    assert "tests_dir/test_x.py" in checks["no_tests_deleted"].detail


def test_missing_changelog_and_version_fail(repo):
    (repo / "tox.ini").write_text(UPGRADED_TOX)
    _commit_all(repo)
    checks = {c.name: c for c in review_checkout(repo, "django", "6.2", "5.2", base="main")}
    assert not checks["changelog_updated"].passed
    assert not checks["version_bumped"].passed


def test_render_report(repo):
    (repo / "tox.ini").write_text(UPGRADED_TOX)
    _commit_all(repo)
    checks = review_checkout(repo, "django", "6.2", "5.2", base="main")
    report = render_report("some-repo", checks)
    assert "# Review: some-repo" in report
    assert "checks passed" in report
