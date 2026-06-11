"""Discovery against a fully mocked GitHub API — no network."""

import json

import respx
from httpx import Response

from openedx_ai_agent.config import Config
from openedx_ai_agent.discovery import GITHUB_API, discover

ORG_REPOS = [
    {"name": "openedx-filters", "archived": False, "fork": False,
     "default_branch": "main", "pushed_at": "2026-06-01T00:00:00Z"},
    {"name": "old-archived-thing", "archived": True, "fork": False,
     "default_branch": "master", "pushed_at": "2020-01-01T00:00:00Z"},
    {"name": "frontend-app-learning", "archived": False, "fork": False,
     "default_branch": "main", "pushed_at": "2026-06-01T00:00:00Z"},
]

FILTERS_TOX = (
    "[tox]\nenvlist = py{311,312}-django{42,52}\n"
    "[testenv]\ndeps =\n    django52: Django>=5.2,<5.3\n"
)


@respx.mock
def test_discover_writes_inventory(tmp_path):
    respx.get(f"{GITHUB_API}/orgs/testorg/repos").mock(
        side_effect=lambda request: Response(
            200, json=ORG_REPOS if request.url.params["page"] == "1" else []
        )
    )
    # openedx-filters declares django in tox.ini; everything else 404s.
    respx.get(f"{GITHUB_API}/repos/testorg/openedx-filters/contents/tox.ini").mock(
        return_value=Response(200, text=FILTERS_TOX)
    )
    respx.get(url__regex=rf"{GITHUB_API}/repos/testorg/.+/contents/.+").mock(
        return_value=Response(404)
    )

    config = Config(org="testorg", campaign_dir=tmp_path / "campaign")
    inventory = discover(config, target="django")

    assert inventory["repos_scanned"] == 2  # archived repo excluded
    assert [r["repo"] for r in inventory["repos"]] == ["openedx-filters"]
    entry = inventory["repos"][0]
    assert entry["classification"] == "library"
    assert entry["versions"]["tox"] == ["4.2", "5.2"]
    assert entry["declares_in"] == ["tox.ini"]

    on_disk = json.loads((tmp_path / "campaign" / "inventory.json").read_text())
    assert on_disk == inventory
