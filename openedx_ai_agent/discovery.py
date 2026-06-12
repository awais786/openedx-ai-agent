"""Org-wide repository discovery: which repos declare the campaign target?

Produces ``campaign/inventory.json`` — the input for classification, auditing,
and ticket drafting. Read-only against the GitHub API.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import httpx

from .classify import classify_repo, extract_versions
from .config import Config

GITHUB_API = "https://api.github.com"

#: Files that reveal a repo's dependency-version support. tox.ini and the CI
#: workflow are the source of truth (per the campaign process doc); setup.py
#: classifiers drift but are still worth recording.
FILES_TO_CHECK = (
    "tox.ini",
    ".github/workflows/ci.yml",
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
)

CONCURRENCY = 10


#: Primary languages worth inspecting for Python dependency targets. ``None``
#: covers repos GitHub couldn't classify (docs-heavy repos can still ship Python).
_PYTHON_LANGUAGES = {"Python", None}


async def _fetch_org_repos(client: httpx.AsyncClient, config: Config) -> list[dict[str, Any]]:
    """Non-archived, non-fork, Python-language repos in the org (paginated).

    The language filter is free (it's in the listing response) and roughly halves
    the scan — frontend-* JavaScript repos never get file fetches.
    """
    repos: list[dict[str, Any]] = []
    page = 1
    while True:
        resp = await client.get(
            f"{GITHUB_API}/orgs/{config.org}/repos",
            params={"per_page": 100, "page": page, "type": "public"},
            headers=config.github_headers,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        repos.extend(
            r
            for r in batch
            if not r["archived"] and not r["fork"] and r.get("language") in _PYTHON_LANGUAGES
        )
        page += 1
    return repos


async def _fetch_named_repos(
    client: httpx.AsyncClient, config: Config, names: list[str]
) -> list[dict[str, Any]]:
    """Metadata for an explicit repo list — skips the org walk entirely."""
    repos: list[dict[str, Any]] = []
    for name in names:
        resp = await client.get(
            f"{GITHUB_API}/repos/{config.org}/{name}", headers=config.github_headers
        )
        resp.raise_for_status()
        repos.append(resp.json())
    return repos


async def _fetch_file(
    client: httpx.AsyncClient, config: Config, repo: str, path: str
) -> str | None:
    """Raw contents of one file from the repo's default branch, or None if absent."""
    resp = await client.get(
        f"{GITHUB_API}/repos/{config.org}/{repo}/contents/{path}",
        headers={**config.github_headers, "Accept": "application/vnd.github.raw+json"},
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text


async def _inspect_repo(
    client: httpx.AsyncClient,
    config: Config,
    repo: dict[str, Any],
    target: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any] | None:
    """Fetch the version-declaring files; return an inventory entry if the repo
    mentions the target dependency, else None."""
    async with semaphore:
        files = {path: await _fetch_file(client, config, repo["name"], path) for path in FILES_TO_CHECK}
    relevant = {p: c for p, c in files.items() if c and target.lower() in c.lower()}
    if not relevant:
        return None
    versions = extract_versions(target, files)
    return {
        "repo": repo["name"],
        "default_branch": repo["default_branch"],
        "pushed_at": repo["pushed_at"],
        "classification": classify_repo(repo["name"]),
        "declares_in": sorted(relevant),
        "versions": versions,
    }


async def _discover(config: Config, target: str, repos_filter: list[str] | None) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=30) as client:
        if repos_filter:
            repos = await _fetch_named_repos(client, config, repos_filter)
        else:
            repos = await _fetch_org_repos(client, config)
        entries = await asyncio.gather(
            *(_inspect_repo(client, config, repo, target, semaphore) for repo in repos)
        )
    return {
        "org": config.org,
        "target": target,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "repos_scanned": len(repos),
        "repos": sorted((e for e in entries if e), key=lambda e: e["repo"]),
    }


def discover(
    config: Config, target: str = "django", repos_filter: list[str] | None = None
) -> dict[str, Any]:
    """Scan the org (or an explicit repo list) and write ``<campaign_dir>/inventory.json``."""
    from .state import load_state, set_status  # local import to avoid cycle at module load

    inventory = asyncio.run(_discover(config, target, repos_filter))
    config.campaign_dir.mkdir(parents=True, exist_ok=True)
    out = config.campaign_dir / "inventory.json"
    out.write_text(json.dumps(inventory, indent=2) + "\n")

    known = load_state(config)["repos"]
    for entry in inventory["repos"]:
        if entry["repo"] not in known:  # don't regress repos already further along
            set_status(config, entry["repo"], "discovered")
    return inventory
