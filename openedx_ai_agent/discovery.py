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


async def _fetch_org_repos(client: httpx.AsyncClient, config: Config) -> list[dict[str, Any]]:
    """All non-archived, non-fork repos in the org (paginated)."""
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
        repos.extend(r for r in batch if not r["archived"] and not r["fork"])
        page += 1
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


async def _discover(config: Config, target: str) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=30) as client:
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


def discover(config: Config, target: str = "django") -> dict[str, Any]:
    """Scan the org and write ``<campaign_dir>/inventory.json``. Returns the inventory."""
    from .state import load_state, set_status  # local import to avoid cycle at module load

    inventory = asyncio.run(_discover(config, target))
    config.campaign_dir.mkdir(parents=True, exist_ok=True)
    out = config.campaign_dir / "inventory.json"
    out.write_text(json.dumps(inventory, indent=2) + "\n")

    known = load_state(config)["repos"]
    for entry in inventory["repos"]:
        if entry["repo"] not in known:  # don't regress repos already further along
            set_status(config, entry["repo"], "discovered")
    return inventory
