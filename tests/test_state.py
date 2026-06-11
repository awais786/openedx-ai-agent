"""Campaign state transitions — offline."""

import pytest

from openedx_ai_agent.config import Config
from openedx_ai_agent.state import load_state, set_status, summarize


def test_set_and_summarize(tmp_path):
    config = Config(campaign_dir=tmp_path / "campaign")
    set_status(config, "openedx-filters", "discovered")
    set_status(config, "edx-val", "discovered")
    set_status(config, "edx-val", "agent_succeeded", branch="upgrade/django62", cost_usd=2.5)

    state = load_state(config)
    assert state["repos"]["edx-val"]["status"] == "agent_succeeded"
    assert state["repos"]["edx-val"]["branch"] == "upgrade/django62"
    assert "updated_at" in state["repos"]["edx-val"]

    buckets = summarize(state)
    assert list(buckets) == ["discovered", "agent_succeeded"]  # pipeline order
    assert buckets["discovered"] == ["openedx-filters"]


def test_unknown_status_rejected(tmp_path):
    config = Config(campaign_dir=tmp_path / "campaign")
    with pytest.raises(ValueError, match="unknown status"):
        set_status(config, "edx-val", "donezo")
