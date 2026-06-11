"""Ticket and master-issue drafting — deterministic, offline."""

from openedx_ai_agent.drafts import draft_tickets

INVENTORY = {
    "org": "testorg",
    "target": "django",
    "repos": [
        {"repo": "openedx-filters", "classification": "library",
         "versions": {"tox": ["4.2", "5.2"], "ci": [], "classifiers": []}},
        {"repo": "course-discovery", "classification": "service",
         "versions": {"tox": ["5.2"], "ci": [], "classifiers": []}},
    ],
}


def test_draft_tickets_and_master(tmp_path):
    written = draft_tickets(INVENTORY, tmp_path, new_version="6.2", old_version="5.2")
    names = {p.name for p in written}
    assert names == {"ticket-openedx-filters.md", "ticket-course-discovery.md", "master-issue.md"}

    ticket = (tmp_path / "ticket-openedx-filters.md").read_text()
    assert "django62" in ticket                      # tox factor for the new version
    assert "BOTH 5.2 and 6.2" in ticket              # dual-compat instruction
    assert "Claim it by commenting" in ticket        # community claim window

    master = (tmp_path / "master-issue.md").read_text()
    assert "1 libraries identified" in master
    assert "1 services identified" in master
    assert "| openedx-filters | library | 4.2, 5.2 |" in master
