"""Campaign initialization: the (package, existing version, target version) triple.

``oea init`` captures the triple once into ``campaign/campaign.json``; every other
command defaults from it. Init also performs the first Phase 0 step automatically:
fetching the target's official release notes (the breaking-changes source) into
``campaign/release-notes/`` for the coordinator and the agents to consume.
"""

import json

import httpx

from .config import Config

#: Where official release notes live, per target. Fetched via the GitHub
#: contents API (works where docs sites are unreachable / rate-limited).
RELEASE_NOTES_SOURCES = {
    "django": {
        "repo": "django/django",
        "paths": [
            "docs/releases/{version}.txt",
            "docs/internals/deprecation.txt",
        ],
    },
}


def load_campaign(config: Config) -> dict | None:
    path = config.campaign_dir / "campaign.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def init_campaign(
    config: Config, target: str, old_version: str, new_version: str
) -> tuple[dict, list[str]]:
    """Write campaign.json and fetch release notes. Returns (campaign, fetched paths)."""
    campaign = {
        "target": target,
        "old_version": old_version,
        "new_version": new_version,
        "org": config.org,
    }
    config.campaign_dir.mkdir(parents=True, exist_ok=True)
    (config.campaign_dir / "campaign.json").write_text(json.dumps(campaign, indent=2) + "\n")
    fetched = fetch_release_notes(config, target, new_version)
    return campaign, fetched


def fetch_release_notes(config: Config, target: str, version: str) -> list[str]:
    """Download the target's release notes into campaign/release-notes/.

    Targets without a configured source are skipped (the campaign still works —
    the coordinator supplies breaking-changes knowledge via the playbook instead).
    """
    source = RELEASE_NOTES_SOURCES.get(target.lower())
    if not source:
        return []

    notes_dir = config.campaign_dir / "release-notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    fetched: list[str] = []
    with httpx.Client(timeout=30) as client:
        for path_tpl in source["paths"]:
            path = path_tpl.format(version=version)
            resp = client.get(
                f"https://api.github.com/repos/{source['repo']}/contents/{path}",
                headers={**config.github_headers, "Accept": "application/vnd.github.raw+json"},
            )
            if resp.status_code == 404:
                continue  # e.g. release notes for an unreleased version
            resp.raise_for_status()
            dest = notes_dir / path.replace("/", "-")
            dest.write_text(resp.text)
            fetched.append(str(dest))
    return fetched
