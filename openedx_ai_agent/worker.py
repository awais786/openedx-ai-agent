"""Per-repo upgrade worker: a Claude Agent SDK session driven by the playbook.

Flow (campaign process, Phase 2): clone → branch → codemod-first → checklist →
test loop → LOCAL result. Pushing the branch and opening a draft PR are gated
behind ``--push`` and are the only outward-facing actions; they never happen in
a dry run. Escalations land in ``campaign/escalations/<repo>.md``.
"""

import asyncio
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from .config import Config
from .state import set_status

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TURNS = 60

WORKER_TOOLS = ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]

PROMPT_TEMPLATE = """\
Apply the per-repo upgrade checklist to this repository: add {target} {new_version} \
support while KEEPING {target} {old_version} support (dual-compatibility — a change \
that breaks {old_version} is a failure).

Steps, in order:
1. If the target playbook's "Codemod tooling" section names a codemod for {target}, \
install it (pip install) and run it exactly as the playbook shows, then commit the \
result separately with message "chore: apply {target} codemod". If the playbook names \
no codemod for this target, skip this step — do not invent one.
2. Apply the per-repo checklist from the playbook (tox envlist, CI matrix, trove \
classifiers, requirements recompile via `make upgrade` if available, version bump, \
changelog entry).
3. Run the test suite (prefer `tox -e <new env>` if tox is configured, else pytest). \
Fix failures using the failure taxonomy in the playbook. Never delete, skip, or \
weaken a test to get green.
4. Commit the checklist + fixes with a conventional-commit message \
(`feat: add {target} {new_version} support`).

Constraints:
- Do NOT push, do NOT open PRs, do NOT touch anything outside this repository.
- Only upgrade-related changes — no drive-by refactors or formatting.
- If you hit a blocker outside the playbook's failure taxonomy (e.g. an incompatible \
third-party dependency, a failure you cannot classify, or a fix that would require \
changing business logic), STOP and write a clear escalation summary as your final \
message starting with the line "ESCALATE:".

Finish with a short summary: what changed, test results on both versions, and \
anything a human reviewer should look at closely.
"""


@dataclass
class WorkerResult:
    repo: str
    succeeded: bool
    escalated: bool
    summary: str
    cost_usd: float | None
    num_turns: int | None
    checkout: Path
    branch: str


def _git(checkout: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(checkout), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def _clone(config: Config, repo: str, workdir: Path) -> Path:
    url = f"https://github.com/{config.org}/{repo}.git"
    checkout = workdir / repo
    subprocess.run(
        ["git", "clone", "--depth", "50", url, str(checkout)],
        capture_output=True, text=True, check=True,
    )
    return checkout


def build_system_prompt(playbook_dir: Path, target: str) -> str:
    """The agent's instructions ARE the playbook: process doc + target playbook."""
    process = (playbook_dir / "campaign-process.md").read_text()
    target_playbook_path = playbook_dir / "playbooks" / f"{target}.md"
    target_playbook = (
        target_playbook_path.read_text() if target_playbook_path.exists() else ""
    )
    return (
        "You are the Dev agent in an Open edX upgrade campaign. Follow the campaign "
        "process and target playbook below EXACTLY — they encode hard-won judgment "
        "from previous hand-run campaigns and override your own preferences.\n\n"
        f"=== CAMPAIGN PROCESS ===\n{process}\n\n"
        f"=== TARGET PLAYBOOK ({target}) ===\n{target_playbook}"
    )


async def _run_agent(
    checkout: Path, system_prompt: str, prompt: str, model: str
) -> ResultMessage | None:
    result: ResultMessage | None = None
    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            cwd=str(checkout),
            system_prompt=system_prompt,
            allowed_tools=WORKER_TOOLS,
            permission_mode="acceptEdits",
            max_turns=MAX_TURNS,
            model=model,
        ),
    ):
        if isinstance(message, ResultMessage):
            result = message
    return result


def upgrade_repo(
    config: Config,
    repo: str,
    target: str,
    new_version: str,
    old_version: str,
    playbook_dir: Path,
    model: str = DEFAULT_MODEL,
    workdir: Path | None = None,
) -> WorkerResult:
    """Run the upgrade agent against a fresh clone. Local-only — see cli for --push."""
    workdir = workdir or Path(tempfile.mkdtemp(prefix="oea-"))
    checkout = _clone(config, repo, workdir)
    branch = f"upgrade/{target}{new_version.replace('.', '')}"
    _git(checkout, "checkout", "-b", branch)

    system_prompt = build_system_prompt(playbook_dir, target)
    prompt = PROMPT_TEMPLATE.format(
        target=target, new_version=new_version, old_version=old_version
    )

    result = asyncio.run(_run_agent(checkout, system_prompt, prompt, model))

    summary = (result.result or "") if result else "agent produced no result message"
    escalated = summary.lstrip().startswith("ESCALATE:")
    succeeded = bool(result) and not result.is_error and not escalated

    worker_result = WorkerResult(
        repo=repo,
        succeeded=succeeded,
        escalated=escalated,
        summary=summary,
        cost_usd=result.total_cost_usd if result else None,
        num_turns=result.num_turns if result else None,
        checkout=checkout,
        branch=branch,
    )
    _write_report(config, worker_result)
    set_status(
        config,
        repo,
        "agent_succeeded" if succeeded else "escalated" if escalated else "failed",
        branch=branch,
        checkout=str(checkout),
        cost_usd=worker_result.cost_usd,
    )
    return worker_result


def _write_report(config: Config, result: WorkerResult) -> None:
    """Run report (always) + escalation file (when the agent stopped on a blocker)."""
    runs_dir = config.campaign_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    try:
        commits = _git(result.checkout, "log", "--oneline", "origin/HEAD..HEAD")
        diffstat = _git(result.checkout, "diff", "--stat", "origin/HEAD...HEAD")
    except subprocess.CalledProcessError:
        commits, diffstat = "(unavailable)", "(unavailable)"

    cost = f"${result.cost_usd:.2f}" if result.cost_usd is not None else "n/a"
    outcome = "✅ succeeded" if result.succeeded else "🛑 escalated" if result.escalated else "❌ failed"
    report = (
        f"# Upgrade run: {result.repo}\n\n"
        f"- Branch: `{result.branch}` (local checkout: `{result.checkout}`)\n"
        f"- Outcome: {outcome}\n"
        f"- Cost: {cost} | Turns: {result.num_turns}\n\n"
        f"## Commits\n\n```\n{commits}\n```\n\n"
        f"## Diffstat\n\n```\n{diffstat}\n```\n\n"
        f"## Agent summary\n\n{result.summary}\n"
    )
    (runs_dir / f"{result.repo}.md").write_text(report)

    if result.escalated:
        esc_dir = config.campaign_dir / "escalations"
        esc_dir.mkdir(parents=True, exist_ok=True)
        (esc_dir / f"{result.repo}.md").write_text(
            f"# Escalation: {result.repo}\n\n{result.summary}\n"
        )
