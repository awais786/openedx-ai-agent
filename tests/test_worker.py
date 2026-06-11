"""Worker prompt assembly and reporting — offline (no SDK session, no git clone)."""

from pathlib import Path

from openedx_ai_agent.config import Config
from openedx_ai_agent.worker import WorkerResult, _write_report, build_system_prompt

REPO_ROOT = Path(__file__).parent.parent


def test_system_prompt_embeds_playbooks():
    prompt = build_system_prompt(REPO_ROOT / "docs", "django")
    # The process doc and the django pattern table must both reach the agent.
    assert "dual-compatibility bridge" in prompt.lower() or "dual compatibility" in prompt.lower()
    assert "get_storage_class" in prompt
    assert "Never touch unrelated formatting" in prompt


def test_system_prompt_missing_target_playbook(tmp_path):
    (tmp_path / "campaign-process.md").write_text("PROCESS")
    (tmp_path / "playbooks").mkdir()
    prompt = build_system_prompt(tmp_path, "celery-unknown")
    assert "PROCESS" in prompt


def test_escalation_report_written(tmp_path):
    config = Config(campaign_dir=tmp_path / "campaign")
    result = WorkerResult(
        repo="edx-fake",
        succeeded=False,
        escalated=True,
        summary="ESCALATE: third-party dep X has no 6.0-compatible release.",
        cost_usd=1.23,
        num_turns=7,
        checkout=tmp_path / "edx-fake",  # not a git repo → diff sections degrade gracefully
        branch="upgrade/django60",
    )
    _write_report(config, result)

    run_report = (tmp_path / "campaign" / "runs" / "edx-fake.md").read_text()
    assert "🛑 escalated" in run_report
    assert "$1.23" in run_report
    assert "(unavailable)" in run_report  # git data degrades, doesn't crash

    escalation = (tmp_path / "campaign" / "escalations" / "edx-fake.md").read_text()
    assert "third-party dep X" in escalation
