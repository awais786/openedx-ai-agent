# Python Upgrade Playbook (stub)

Target-specific knowledge for Python version campaigns across the openedx org. The general
process in [`../campaign-process.md`](../campaign-process.md) applies unchanged — the 2024
Python 3.11/3.12 campaign already proved it: the same per-repo checklist (tox envlist, CI
matrix, classifiers, requirements recompile, version bump, changelog) was applied across
a dozen+ libraries (edx-organizations, edx-submissions, super-csv, edx-search,
edx-celeryutils, edx-val, edx-django-utils, auth-backends, api-doc-tools,
code-annotations, credentials, …).

To fill in (from the 3.11/3.12 campaign and before the next Python campaign):

## 1. Calendar
- Python EOL schedule vs. Open edX release train; which named release raises the floor.
- Coupling with Django: each Django version has a Python floor/ceiling (e.g. Django 6.0
  requires 3.12–3.14) — Python campaigns are often *precursors* to Django campaigns.

## 2. Breaking-change pattern table
- `TODO`: known 3.x→3.y failure patterns from the 2024 campaign (deprecated stdlib
  removals, syntax/typing changes, C-extension wheels lagging).

## 3. Codemod tooling
- Candidates: `pyupgrade` (the python analog of django-upgrade). `TODO`: confirm what the
  2024 campaign used.

## 4. Watchlist
- `TODO`: repos/packages that lagged in the 3.11/3.12 campaign (C-extension dependencies
  are the usual suspects).
