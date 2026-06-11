"""Repo classification and supported-version extraction.

Version extraction reads three signals, most-trustworthy first (per the campaign
process doc: "tox envlist + CI matrix are the source of truth, not setup.py
classifiers — they drift"):

1. tox.ini envlist factors (``django42``, ``django52`` …)
2. CI workflow matrix entries (``django-version: ["4.2", "5.2"]`` …)
3. Trove classifiers (``Framework :: Django :: 5.2``)
"""

import re

#: The platform crosses last (campaign process, Phase 3).
PLATFORM_REPOS = {"edx-platform", "openedx-platform"}

#: Deployed applications — Phase 2 of a campaign, after libraries.
SERVICE_REPOS = {
    "course-discovery",
    "credentials",
    "ecommerce",
    "edx-analytics-dashboard",
    "edx-exams",
    "edx-notes-api",
    "enterprise-access",
    "enterprise-catalog",
    "enterprise-subsidy",
    "license-manager",
    "registrar",
    "xqueue",
}

#: Django versions with their security-support end date (ISO), per endoflife.date.
#: Re-verify at campaign kickoff.
DJANGO_EOL = {
    "3.2": "2024-04-01",
    "4.2": "2026-04-07",
    "5.2": "2028-04-30",
    "6.0": "2027-04-30",
}

_TOX_FACTOR = re.compile(r"django(\d)(\d+)", re.IGNORECASE)
_TOX_FACTOR_BRACE = re.compile(r"django\{([\d,\s]+)\}", re.IGNORECASE)
_CI_MATRIX = re.compile(r"django[-_]version[^\n]*?:\s*\[([^\]]*)\]", re.IGNORECASE)
_CLASSIFIER = re.compile(r"Framework :: Django :: (\d+\.\d+)")
_VERSION_LITERAL = re.compile(r"['\"]?(\d+\.\d+)['\"]?")


def classify_repo(name: str) -> str:
    """library / service / platform — drives campaign ordering (small → big)."""
    if name in PLATFORM_REPOS:
        return "platform"
    if name in SERVICE_REPOS:
        return "service"
    return "library"


def extract_versions(target: str, files: dict[str, str | None]) -> dict[str, list[str]]:
    """Supported target versions per signal source. Only Django is implemented;
    other targets return empty signals (the inventory still records where the
    target is declared)."""
    if target.lower() != "django":
        return {"tox": [], "ci": [], "classifiers": []}

    tox = files.get("tox.ini") or ""
    ci = files.get(".github/workflows/ci.yml") or ""
    meta = (files.get("setup.py") or "") + (files.get("setup.cfg") or "") + (
        files.get("pyproject.toml") or ""
    )

    tox_set = {f"{m.group(1)}.{m.group(2)}" for m in _TOX_FACTOR.finditer(tox)}
    # Brace factor form: envlist = py{311,312}-django{42,52}
    for brace in _TOX_FACTOR_BRACE.finditer(tox):
        for token in brace.group(1).replace(" ", "").split(","):
            if len(token) >= 2:
                tox_set.add(f"{token[0]}.{token[1:]}")
    tox_versions = sorted(tox_set)

    ci_versions: set[str] = set()
    for matrix in _CI_MATRIX.finditer(ci):
        ci_versions.update(m.group(1) for m in _VERSION_LITERAL.finditer(matrix.group(1)))
    # CI matrices sometimes use tox-style factors instead of dotted versions.
    ci_versions.update(f"{m.group(1)}.{m.group(2)}" for m in _TOX_FACTOR.finditer(ci))

    classifier_versions = sorted(set(_CLASSIFIER.findall(meta)))

    return {
        "tox": tox_versions,
        "ci": sorted(ci_versions),
        "classifiers": classifier_versions,
    }


def supported_versions(entry: dict) -> list[str]:
    """Best-signal supported versions for an inventory entry: tox, else CI,
    else classifiers."""
    versions = entry.get("versions", {})
    return versions.get("tox") or versions.get("ci") or versions.get("classifiers") or []


def eol_status(entry: dict, today: str) -> dict | None:
    """If the repo supports ONLY end-of-life Django versions, return the audit
    finding; None when at least one supported version is still in support
    (or when no version signal exists — those are reported separately)."""
    versions = supported_versions(entry)
    if not versions:
        return None
    live = [v for v in versions if DJANGO_EOL.get(v, "9999-12-31") > today]
    if live:
        return None
    return {
        "repo": entry["repo"],
        "classification": entry["classification"],
        "supported": versions,
        "latest_eol_date": max(DJANGO_EOL.get(v, "unknown") for v in versions),
    }
