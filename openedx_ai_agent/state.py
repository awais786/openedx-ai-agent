"""Campaign state: one JSON file tracking every repo's position in the pipeline.

``campaign/state.json`` is the single source of truth for ``oea status``. Commands
update it as side effects (discover → discovered, draft → ticket_drafted,
upgrade → agent_succeeded / escalated / failed); claim/PR/merge transitions are
recorded by the human coordinator via ``oea status --set``.
"""

import json
from datetime import UTC, datetime

from .config import Config

#: Pipeline order — also the display order in ``oea status``.
STATUSES = [
    "discovered",
    "ticket_drafted",
    "claimed",          # a human maintainer took the ticket
    "agent_succeeded",  # local branch ready for human review
    "escalated",        # agent stopped on a blocker
    "failed",           # agent errored without an escalation summary
    "pr_open",
    "merged",
]


def _state_path(config: Config):
    return config.campaign_dir / "state.json"


def load_state(config: Config) -> dict:
    path = _state_path(config)
    if path.exists():
        return json.loads(path.read_text())
    return {"repos": {}}


def set_status(config: Config, repo: str, status: str, **fields) -> dict:
    """Record a transition. Unknown statuses are rejected to keep the file sane."""
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}; expected one of {STATUSES}")
    state = load_state(config)
    entry = state["repos"].setdefault(repo, {})
    entry["status"] = status
    entry["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    entry.update(fields)
    config.campaign_dir.mkdir(parents=True, exist_ok=True)
    _state_path(config).write_text(json.dumps(state, indent=2) + "\n")
    return state


def summarize(state: dict) -> dict[str, list[str]]:
    """Status → sorted repo names, in pipeline order, skipping empty buckets."""
    buckets: dict[str, list[str]] = {}
    for repo, entry in state["repos"].items():
        buckets.setdefault(entry.get("status", "discovered"), []).append(repo)
    return {s: sorted(buckets[s]) for s in STATUSES if s in buckets}
