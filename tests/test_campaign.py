"""Campaign init: the (package, old, new) triple + release-notes fetch — offline."""

import respx
from click.testing import CliRunner
from httpx import Response

from openedx_ai_agent.campaign import init_campaign, load_campaign
from openedx_ai_agent.cli import main
from openedx_ai_agent.config import Config

NOTES_URL = "https://api.github.com/repos/django/django/contents/docs/releases/6.0.txt"
DEPRECATION_URL = "https://api.github.com/repos/django/django/contents/docs/internals/deprecation.txt"


@respx.mock
def test_init_writes_campaign_and_fetches_notes(tmp_path):
    respx.get(NOTES_URL).mock(return_value=Response(200, text="Backwards incompatible changes"))
    respx.get(DEPRECATION_URL).mock(return_value=Response(200, text="6.1 removals"))

    config = Config(campaign_dir=tmp_path / "campaign")
    campaign, fetched = init_campaign(config, "django", "5.2", "6.0")

    assert load_campaign(config) == campaign
    assert campaign["new_version"] == "6.0"
    assert len(fetched) == 2
    notes = (tmp_path / "campaign" / "release-notes" / "docs-releases-6.0.txt").read_text()
    assert "Backwards incompatible" in notes


@respx.mock
def test_init_unreleased_version_404_tolerated(tmp_path):
    respx.get(url__regex=r"https://api\.github\.com/.*").mock(return_value=Response(404))
    config = Config(campaign_dir=tmp_path / "campaign")
    _, fetched = init_campaign(config, "django", "5.2", "6.2")
    assert fetched == []  # nothing published yet — campaign still initialized
    assert load_campaign(config)["new_version"] == "6.2"


def test_init_unknown_target_skips_notes(tmp_path):
    config = Config(campaign_dir=tmp_path / "campaign")
    _, fetched = init_campaign(config, "celery", "5.3", "5.5")
    assert fetched == []
    assert load_campaign(config)["target"] == "celery"


def test_commands_default_from_campaign_json(tmp_path):
    """draft falls back to campaign.json instead of demanding flags."""
    runner = CliRunner()
    campaign_dir = tmp_path / "campaign"
    config = Config(campaign_dir=campaign_dir)
    init_campaign(config, "celery", "5.3", "5.5")  # no notes source — fine
    # No inventory yet → the version resolution must succeed and THEN fail on inventory.
    result = runner.invoke(
        main, ["--campaign-dir", str(campaign_dir), "draft", "tickets"]
    )
    assert "inventory.json not found" in result.output


def test_commands_error_without_campaign_or_flags(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["--campaign-dir", str(tmp_path / "campaign"), "draft", "tickets"]
    )
    assert result.exit_code != 0
    assert "oea init" in result.output
