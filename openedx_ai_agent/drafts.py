"""Draft generation: per-repo tickets + the master campaign issue.

Everything here writes markdown to ``<campaign_dir>/drafts/`` for HUMAN review
and posting — agents never post outward-facing content themselves (campaign
process, Phase 0.5). Tickets are deliberately formulaic (matching the hand-run
5.2 campaign's templated tickets), so generation is deterministic — no LLM call.
"""

import json
from pathlib import Path

from .classify import supported_versions

TICKET_TEMPLATE = """\
# [{repo}] Add {target} {new_version} support

Part of the org-wide {target} {new_version} upgrade campaign (see master issue).

## Current state

- Classification: {classification}
- Supported {target} versions (tox/CI): {supported}

## What to do

Follow the per-repo checklist in the campaign how-to guide:

1. Run the codemod first, committed separately (e.g. `django-upgrade --target-version {new_version}`).
2. Add `{target}{compact_version}` to the tox envlist and the CI matrix.
3. Add the trove classifier for {target} {new_version}.
4. Recompile requirements (`make upgrade`) — never hand-edit pins.
5. Fix deprecations so tests pass on BOTH {old_version} and {new_version}
   (dual-compat — do not drop {old_version} in this PR).
6. Version bump + changelog entry; conventional-commit PR title (`feat!:` if support changes).

## Definition of done

- CI green on the full matrix (old AND new versions).
- New version released to PyPI so dependents can bump constraints.

---
*This ticket is part of a coordinated campaign. Claim it by commenting here.
Unclaimed tickets will be picked up by the campaign's agent-assisted process
after the claim window.*
"""

MASTER_TEMPLATE = """\
# {target_title} {new_version} Upgrade

## Overview

The {target_title} upgrade will be performed on all repositories that use
{target_title}, starting with the libraries and working our way up to the
services and the platform. The effort relies on repository maintainers to
shepherd the upgrade process.

## Approach

- ⭐ First phase: update all libraries to support {target_title} {new_version}
  while maintaining {old_version} compatibility ({library_count} libraries identified).
- ✨ Second phase: upgrade services to run exclusively on {new_version}
  ({service_count} services identified).
- 🏁 Final phase: openedx-platform dual-compat bridge, then flip.

## Affected repositories

{repo_table}

## Responsibilities

- 👩‍💻 Maintainers: update your repositories (claim your repo's ticket).
- 🦸 Maintainers-at-large: handle repositories without assigned maintainers.
- 🧭 Coordination: campaign coordinators will track progress and help unblock.

Unclaimed tickets after the claim window are handled by the agent-assisted
campaign process (draft PRs, human-reviewed).
"""


def _repo_table(repos: list[dict]) -> str:
    lines = ["| Repo | Type | Current versions |", "|---|---|---|"]
    for entry in repos:
        supported = ", ".join(supported_versions(entry)) or "—"
        lines.append(f"| {entry['repo']} | {entry['classification']} | {supported} |")
    return "\n".join(lines)


def draft_tickets(
    inventory: dict,
    drafts_dir: Path,
    new_version: str,
    old_version: str,
) -> list[Path]:
    """Write one ticket per affected repo + the master issue draft. Returns paths."""
    drafts_dir.mkdir(parents=True, exist_ok=True)
    target = inventory["target"]
    written: list[Path] = []

    for entry in inventory["repos"]:
        ticket = TICKET_TEMPLATE.format(
            repo=entry["repo"],
            target=target,
            new_version=new_version,
            old_version=old_version,
            compact_version=new_version.replace(".", ""),
            classification=entry["classification"],
            supported=", ".join(supported_versions(entry)) or "unknown — verify manually",
        )
        path = drafts_dir / f"ticket-{entry['repo']}.md"
        path.write_text(ticket)
        written.append(path)

    repos = inventory["repos"]
    master = MASTER_TEMPLATE.format(
        target_title=target.title(),
        new_version=new_version,
        old_version=old_version,
        library_count=sum(1 for r in repos if r["classification"] == "library"),
        service_count=sum(1 for r in repos if r["classification"] == "service"),
        repo_table=_repo_table(repos),
    )
    master_path = drafts_dir / "master-issue.md"
    master_path.write_text(master)
    written.append(master_path)

    manifest = drafts_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {"target": target, "new_version": new_version, "tickets": [p.name for p in written]},
            indent=2,
        )
        + "\n"
    )
    return written
