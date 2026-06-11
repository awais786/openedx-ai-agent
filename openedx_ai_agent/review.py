"""Reviewer: mechanical definition-of-done checks over an upgrade branch.

These are the deterministic rows of the campaign-process DoD rubric — the ones a
machine can verify from the diff and the working tree. Judgment calls (is every
change upgrade-related? are the fixes correct?) stay with the human reviewer;
this gate just guarantees the boring invariants before a human spends time.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .classify import extract_versions

#: Files inspected for version signals, mirroring discovery.
_SIGNAL_FILES = ("tox.ini", ".github/workflows/ci.yml", "setup.py", "setup.cfg", "pyproject.toml")


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def _git(checkout: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(checkout), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout


def _read_signals(checkout: Path) -> dict[str, str | None]:
    files: dict[str, str | None] = {}
    for name in _SIGNAL_FILES:
        path = checkout / name
        files[name] = path.read_text() if path.exists() else None
    return files


def review_checkout(
    checkout: Path,
    target: str,
    new_version: str,
    old_version: str,
    base: str = "origin/HEAD",
) -> list[Check]:
    """Run the mechanical DoD checks on ``checkout``'s HEAD vs ``base``."""
    name_status = _git(checkout, "diff", "--name-status", f"{base}...HEAD")
    changed = [line.split("\t", 1) for line in name_status.splitlines() if line.strip()]
    diff_text = _git(checkout, "diff", f"{base}...HEAD")
    checks: list[Check] = []

    changelog_files = [p for _, p in changed if "changelog" in p.lower()]
    checks.append(
        Check(
            "changelog_updated",
            bool(changelog_files),
            ", ".join(changelog_files) or "no CHANGELOG change in diff",
        )
    )

    version_lines = [
        line for line in diff_text.splitlines()
        if line.startswith("+") and re.search(r"__version__|^[+]\s*version\s*=", line)
    ]
    checks.append(
        Check(
            "version_bumped",
            bool(version_lines),
            version_lines[0].lstrip("+ ") if version_lines else "no version change in diff",
        )
    )

    versions = extract_versions(target, _read_signals(checkout))
    for signal in ("tox", "ci", "classifiers"):
        present = new_version in versions[signal]
        checks.append(
            Check(
                f"new_version_in_{signal}",
                present,
                f"{signal} declares: {', '.join(versions[signal]) or 'nothing'}",
            )
        )

    old_retained = old_version in (versions["tox"] or versions["ci"])
    checks.append(
        Check(
            "old_version_retained",
            old_retained,
            f"dual-compat bridge: {old_version} must stay until the drop PR",
        )
    )

    deleted_tests = [p for status, p in changed if status.startswith("D") and "test" in p.lower()]
    checks.append(
        Check(
            "no_tests_deleted",
            not deleted_tests,
            ", ".join(deleted_tests) or "no test files deleted",
        )
    )

    return checks


def render_report(repo: str, checks: list[Check]) -> str:
    passed = sum(1 for c in checks if c.passed)
    lines = [
        f"# Review: {repo}",
        "",
        f"Mechanical definition-of-done: **{passed}/{len(checks)} checks passed**",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    lines += [f"| {c.name} | {'✅' if c.passed else '❌'} | {c.detail} |" for c in checks]
    lines += [
        "",
        "_Mechanical checks only — a human still reviews diff correctness, scope,",
        "and CI results on the full matrix before the PR leaves draft._",
    ]
    return "\n".join(lines) + "\n"
