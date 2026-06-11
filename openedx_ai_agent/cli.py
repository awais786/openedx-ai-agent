"""``oea`` — the campaign CLI.

Read-only discovery and human-gated drafting. Nothing here pushes, posts,
or merges; outward-facing artifacts land in ``campaign/drafts/`` for review.
"""

import json
import sys
from datetime import date
from pathlib import Path

import click

from .classify import eol_status
from .config import Config
from .discovery import discover as run_discovery
from .drafts import draft_tickets


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


@main.command()
@click.option("--target", default="django", show_default=True, help="Dependency to scan for.")
@click.pass_obj
def discover(config: Config, target: str) -> None:
    """Scan the org for repos declaring TARGET; write campaign/inventory.json."""
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
@click.option("--new-version", required=True, help="Target version being added (e.g. 6.2).")
@click.option("--old-version", required=True, help="Version to keep dual-compat with (e.g. 5.2).")
@click.pass_obj
def draft(config: Config, kind: str, new_version: str, old_version: str) -> None:
    """Draft campaign artifacts (tickets + master issue) for HUMAN review — never posted."""
    inventory = _load_inventory(config)
    drafts_dir = config.campaign_dir / "drafts"
    written = draft_tickets(inventory, drafts_dir, new_version, old_version)
    click.echo(f"{len(written)} drafts written to {drafts_dir}/ — review before posting anything.")


@main.command()
@click.argument("repo")
@click.option("--target", default="django", show_default=True)
@click.option("--new-version", required=True, help="Version to add support for (e.g. 6.0).")
@click.option("--old-version", required=True, help="Version to keep dual-compat with (e.g. 5.2).")
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
    target: str,
    new_version: str,
    old_version: str,
    model: str | None,
    playbook_dir: Path,
) -> None:
    """Run the upgrade agent against a fresh clone of REPO (local-only; never pushes)."""
    from .worker import DEFAULT_MODEL, upgrade_repo  # heavy import — keep CLI startup fast

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


if __name__ == "__main__":
    main()
