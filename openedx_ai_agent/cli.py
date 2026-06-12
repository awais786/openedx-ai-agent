"""``oea`` — the campaign CLI.

Read-only discovery and human-gated drafting. Nothing here pushes, posts,
or merges; outward-facing artifacts land in ``campaign/drafts/`` for review.
"""

import json
import sys
from datetime import date
from pathlib import Path

import click

from .campaign import init_campaign, load_campaign
from .classify import eol_status
from .config import Config
from .discovery import discover as run_discovery
from .drafts import draft_tickets
from .review import render_report, review_checkout
from .state import STATUSES, load_state, set_status, summarize


@click.group()
@click.option("--org", default=None, help="GitHub org to scan (default: openedx).")
@click.option("--campaign-dir", default=None, help="Campaign state directory (default: ./campaign).")
@click.pass_context
def main(ctx: click.Context, org: str | None, campaign_dir: str | None) -> None:
    """AI-assisted upgrade campaigns for the Open edX ecosystem."""
    ctx.obj = Config.from_env(org=org, campaign_dir=campaign_dir)


def _load_inventory(config: Config) -> dict:
    path = config.campaign_dir / "inventory.json"
    if not path.exists():
        raise click.ClickException(f"{path} not found — run `oea discover` first.")
    return json.loads(path.read_text())


def _resolve_versions(
    config: Config,
    target: str | None,
    new_version: str | None,
    old_version: str | None,
    require_target: bool = True,
) -> tuple[str | None, str, str]:
    """Flags win; otherwise fall back to campaign.json (written by `oea init`)."""
    campaign = load_campaign(config) or {}
    target = target or campaign.get("target")
    new_version = new_version or campaign.get("new_version")
    old_version = old_version or campaign.get("old_version")
    required = [("--new-version", new_version), ("--old-version", old_version)]
    if require_target:
        required.insert(0, ("--target", target))
    missing = [name for name, value in required if not value]
    if missing:
        raise click.ClickException(
            f"missing {', '.join(missing)} — pass the flag(s) or run `oea init` first."
        )
    return target, new_version, old_version


@main.command()
@click.option("--target", prompt="Which package (e.g. django)", help="Dependency to upgrade.")
@click.option("--old-version", prompt="Existing version (e.g. 5.2)", help="Version currently supported.")
@click.option("--new-version", prompt="Target version (e.g. 6.0)", help="Version to upgrade to.")
@click.pass_obj
def init(config: Config, target: str, old_version: str, new_version: str) -> None:
    """Start a campaign: capture (package, existing, target) and fetch release notes."""
    campaign, fetched = init_campaign(config, target, old_version, new_version)
    click.echo(f"\nCampaign initialized: {target} {old_version} → {new_version} (org: {campaign['org']})")
    if fetched:
        click.echo("Release notes fetched (the breaking-changes source for Phase 0):")
        for path in fetched:
            click.echo(f"  {path}")
    else:
        click.echo(
            f"No release-notes source configured for {target!r} — supply breaking-changes "
            f"knowledge via docs/playbooks/{target}.md instead."
        )
    click.echo(
        "\nNext: review the notes, update the playbook pattern table, then `oea discover`."
    )


@main.command()
@click.option("--target", default=None, help="Dependency to scan for (default: campaign.json, else django).")
@click.pass_obj
def discover(config: Config, target: str | None) -> None:
    """Scan the org for repos declaring TARGET; write campaign/inventory.json."""
    target = target or (load_campaign(config) or {}).get("target") or "django"
    if not config.github_token:
        click.echo("warning: GITHUB_TOKEN not set — unauthenticated API limits are low.", err=True)
    inventory = run_discovery(config, target)
    click.echo(
        f"Scanned {inventory['repos_scanned']} repos in {inventory['org']}: "
        f"{len(inventory['repos'])} declare {target}."
    )
    click.echo(f"Inventory written to {config.campaign_dir / 'inventory.json'}")


@main.command()
@click.option("--eol", "eol_only", is_flag=True, help="Report repos supporting only EOL versions.")
@click.pass_obj
def audit(config: Config, eol_only: bool) -> None:
    """Audit the inventory for version hygiene."""
    inventory = _load_inventory(config)
    today = date.today().isoformat()
    findings = [f for f in (eol_status(e, today) for e in inventory["repos"]) if f]
    no_signal = [e["repo"] for e in inventory["repos"] if not any(e["versions"].values())]

    del eol_only  # --eol is the only audit mode so far; flag kept for CLI stability
    if findings:
        click.echo(f"{len(findings)} repos support ONLY end-of-life Django versions:\n")
        click.echo(f"{'repo':40} {'type':10} {'supported':16} eol date")
        for f in findings:
            click.echo(
                f"{f['repo']:40} {f['classification']:10} "
                f"{', '.join(f['supported']):16} {f['latest_eol_date']}"
            )
    else:
        click.echo("No repos on EOL-only Django versions. ✔")
    if no_signal:
        click.echo(
            f"\n{len(no_signal)} repos declare Django but expose no version signal "
            f"(no tox/CI/classifier match) — verify manually:"
        )
        click.echo("  " + ", ".join(sorted(no_signal)))

    report = config.campaign_dir / "audit-eol.json"
    payload = {"date": today, "findings": findings, "no_signal": no_signal}
    report.write_text(json.dumps(payload, indent=2) + "\n")
    click.echo(f"\nReport written to {report}")
    if findings:
        sys.exit(1)


@main.command()
@click.argument("kind", type=click.Choice(["tickets"]))
@click.option("--new-version", default=None, help="Target version being added (default: campaign.json).")
@click.option("--old-version", default=None, help="Dual-compat version (default: campaign.json).")
@click.pass_obj
def draft(config: Config, kind: str, new_version: str | None, old_version: str | None) -> None:
    """Draft campaign artifacts (tickets + master issue) for HUMAN review — never posted."""
    _, new_version, old_version = _resolve_versions(
        config, None, new_version, old_version, require_target=False
    )
    inventory = _load_inventory(config)
    drafts_dir = config.campaign_dir / "drafts"
    written = draft_tickets(inventory, drafts_dir, new_version, old_version)
    known = load_state(config)["repos"]
    for entry in inventory["repos"]:
        if known.get(entry["repo"], {}).get("status") in (None, "discovered"):
            set_status(config, entry["repo"], "ticket_drafted")
    click.echo(f"{len(written)} drafts written to {drafts_dir}/ — review before posting anything.")


@main.command()
@click.argument("repo")
@click.option("--target", default=None, help="Dependency (default: campaign.json).")
@click.option("--new-version", default=None, help="Version to add support for (default: campaign.json).")
@click.option("--old-version", default=None, help="Dual-compat version (default: campaign.json).")
@click.option("--model", default=None, help="Model for the worker session (default: claude-sonnet-4-6).")
@click.option(
    "--playbook-dir",
    default="docs",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Directory containing campaign-process.md and playbooks/.",
)
@click.pass_obj
def upgrade(
    config: Config,
    repo: str,
    target: str | None,
    new_version: str | None,
    old_version: str | None,
    model: str | None,
    playbook_dir: Path,
) -> None:
    """Run the upgrade agent against a fresh clone of REPO (local-only; never pushes)."""
    from .worker import DEFAULT_MODEL, upgrade_repo  # heavy import — keep CLI startup fast

    target, new_version, old_version = _resolve_versions(config, target, new_version, old_version)

    click.echo(f"Cloning {config.org}/{repo} and starting the upgrade agent…")
    result = upgrade_repo(
        config,
        repo,
        target=target,
        new_version=new_version,
        old_version=old_version,
        playbook_dir=playbook_dir,
        model=model or DEFAULT_MODEL,
    )
    outcome = "succeeded" if result.succeeded else "ESCALATED" if result.escalated else "FAILED"
    cost = f"${result.cost_usd:.2f}" if result.cost_usd is not None else "n/a"
    click.echo(f"\n{outcome} — branch {result.branch} in {result.checkout} (cost {cost})")
    click.echo(f"Report: {config.campaign_dir / 'runs' / (repo + '.md')}")
    click.echo("Review the diff, then push the branch and open a draft PR yourself.")
    if not result.succeeded:
        sys.exit(1)


@main.command()
@click.argument("checkout", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--repo", default=None, help="Repo name for the report (default: directory name).")
@click.option("--target", default=None, help="Dependency (default: campaign.json).")
@click.option("--new-version", default=None, help="(default: campaign.json)")
@click.option("--old-version", default=None, help="(default: campaign.json)")
@click.option("--base", default="origin/HEAD", show_default=True, help="Ref to diff against.")
@click.pass_obj
def review(
    config: Config,
    checkout: Path,
    repo: str | None,
    target: str | None,
    new_version: str | None,
    old_version: str | None,
    base: str,
) -> None:
    """Run the mechanical definition-of-done checks on an upgrade CHECKOUT."""
    target, new_version, old_version = _resolve_versions(config, target, new_version, old_version)
    repo = repo or checkout.name
    checks = review_checkout(checkout, target, new_version, old_version, base=base)
    report = render_report(repo, checks)

    reviews_dir = config.campaign_dir / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    (reviews_dir / f"{repo}.md").write_text(report)

    for check in checks:
        click.echo(f"{'✅' if check.passed else '❌'} {check.name}: {check.detail}")
    failed = [c for c in checks if not c.passed]
    click.echo(f"\nReport: {reviews_dir / (repo + '.md')}")
    if failed:
        click.echo(f"{len(failed)} check(s) failed — fix before the PR leaves draft.")
        sys.exit(1)


@main.command()
@click.option(
    "--set", "transition", default=None, metavar="REPO=STATUS",
    help=f"Record a human transition, e.g. edx-val=claimed. Statuses: {', '.join(STATUSES)}",
)
@click.pass_obj
def status(config: Config, transition: str | None) -> None:
    """Campaign dashboard from campaign/state.json."""
    if transition:
        repo, _, new_status = transition.partition("=")
        if not new_status:
            raise click.ClickException("expected REPO=STATUS")
        try:
            set_status(config, repo, new_status)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"{repo} → {new_status}")
        return

    state = load_state(config)
    if not state["repos"]:
        click.echo("No campaign state yet — run `oea discover`, `oea upgrade`, or `--set`.")
        return
    for bucket, repos in summarize(state).items():
        click.echo(f"{bucket} ({len(repos)})")
        for repo in repos:
            click.echo(f"  {repo}")


if __name__ == "__main__":
    main()
