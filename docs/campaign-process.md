# Upgrade Campaign Process (target-agnostic)

This is the general process for running a fleet-wide upgrade campaign across the Open edX
ecosystem — Django, Python, Celery, or any other foundational dependency. It is distilled
from campaigns actually run 2023–2025 (Django 4.2, Python 3.11/3.12, Django 5.2).

Each campaign **target** supplies its own playbook under `playbooks/` providing four things
this process consumes:

1. **Calendar** — the target's release/EOL timeline and how it maps onto the Open edX
   release train.
2. **Breaking-change pattern table** — known failure patterns and their fix recipes.
3. **Codemod tooling** — mechanical rewrite tools to run first (e.g. `django-upgrade`),
   and their known limitations.
4. **Watchlist** — repos and upstream packages that were slow in past campaigns.

---

## Phase 0 — Discovery & classification

- **Study the breaking changes first.** When the new target version releases, read the
  official release notes — breaking-changes and deprecation sections — *before* touching
  any repo. This produces the campaign's expected-failure list: most red CI during the
  campaign traces back to an item on it. Each campaign's list becomes that cycle's refresh
  of the target playbook's pattern table.
  (Agent mapping: at campaign start the PM agent ingests the release notes for the target
  version and emits the pattern table for the Dev/Fixer agents' prompts.)
- **Precursor checks.** Verify floor requirements the new version raises (e.g. a new
  Django major raising the minimum Python) — a precursor campaign may need to finish first.
- Enumerate org repos that declare the dependency (search `setup.py` / `setup.cfg` /
  `pyproject.toml` / `requirements/*.in`).
- Classify each repo:
  - **Library** (`edx-*`, `openedx-*` utility packages) — small, well-tested, low blast
    radius.
  - **Service** (course-discovery, credentials, edx-notes-api, …) — deployed apps.
  - **The platform** (openedx-platform) — last, largest, highest risk.
- Record current supported versions per repo (tox envlist + CI matrix are the source of
  truth, not setup.py classifiers — they drift).

## Phase 0.5 — Campaign launch: announcements, ticketing, community mobilization

**No coding starts before this is done.** The campaign is community-powered; the launch
sequence (reconstructed from the Django 5.2 campaign, March–April 2025):

1. **Master issue** in `openedx/public-engineering` — phases, key dates per phase,
   responsibilities (maintainers / maintainers-at-large / named coordinators).
   (Precedent: openedx/public-engineering#339.)
2. **Per-breaking-change tracking issues** citing the upstream release note and a
   reference fix from another project. (Precedent: #340, #341.)
3. **Per-repo tickets** — one per affected repo, linked under the master issue, so each
   piece of work is individually claimable. (Precedent: "this week — ticket creation and
   documentation", week one of the 5.2 campaign.)
4. **How-to documentation** — a self-serve guide (codemod usage, the per-repo checklist,
   the pattern table) so any maintainer can execute their repo's ticket without the
   coordinator.
5. **Announcement + coordination thread on Discourse** — publish the plan, **ask
   maintainers to come forward and pick their repos' tickets**, direct questions to the
   thread. Maintainers-at-large asked to claim unowned repos.
6. **Ongoing cadence** — periodic progress updates on the thread, deadline reminders,
   public credit to contributors.

**Agent mapping — the agent is the maintainer-at-large of last resort, not a replacement
for the community.** The PM agent runs discovery and *drafts* items 1–5 for the coordinator
to review and post (all outward-facing → human-gated). Tickets then get a **claim window**
for maintainers; the Dev agent picks up only tickets still unclaimed after the window, or
where a maintainer asks for help. This keeps the community engaged (the campaign's real
long-term asset) while guaranteeing nothing stalls.

## Phase 1 — Libraries first (hard gate before anything else)

**ALL libraries get dual-compat (old + new version, e.g. 4.2 + 5.2) before any service
starts.** Services consume these libraries, so an incomplete library tier blocks the whole
fleet — Phase 1 is a gate, not a suggestion. Within the tier, order by the dependency
graph, not alphabet:

1. Shared low-level libs (edx-django-utils, edx-drf-extensions, opaque-keys, …)
2. Mid-tier libs (openedx-events, openedx-filters, edx-celeryutils, …)

Each library must be **released to PyPI** with dual support to count as done.

## Phase 2 — Services: independent, parallel, new-version-only

Once the library gate clears, services (course-discovery, credentials, edx-notes-api, …)
are **independent of each other** — none blocks another, so they can be upgraded in
parallel by different maintainers (or agent runs).

**Services flip directly to the new version — no dual-compat needed.** They are deployed
applications; nobody imports them at a different Django version. Dual-compat is a
*library* obligation (consumers sit at mixed versions during the transition); a service
just upgrades and deploys (5.2-campaign precedent, #339: "upgrade Django services to run
*exclusively* on 5.2").

Cross-phase rules:

- **Ordering rule: smallest packages first, step by step toward the big ones.** Size means
  blast radius, not just lines of code — start where a mistake is cheap and the feedback
  loop is fast, build confidence and a pattern library from the small repos, then take that
  to the critical ones. Each tier's lessons feed the next.
- **Critical-usage dependencies get special care.** django-storages is the canonical
  example: its API sits under file handling across the platform (uploads, certificates,
  exports), so changes there are high-risk regardless of diff size — these are where the
  dual-compat bridge and extra verification matter most.
- Coordinate with repo maintainers / the relevant working group throughout.

## Phase 3 — The platform: the dual-compatibility bridge

openedx-platform goes last — it consumes everything above via constraints.

**Core strategy: never a big-bang switch.** The platform crosses via a bridge period in
three strict stages:

1. **Build dual compatibility.** Make code changes that work on BOTH the old and new
   version. Fix deprecation warnings while still on the old version.
2. **Green on both versions simultaneously.** Run the full test suite against old AND new.
   The new version's run starts non-blocking, then must reach green *while the old version
   stays green*. Do not proceed until both matrices pass.
3. **Drop the old version.** Only after stage 2: remove the old version from the matrix,
   run `make upgrade` (full requirements recompile against the new version only), and land
   full single-version support.

**How dual-compat code is written:** strongly prefer version-agnostic code that runs
identically on both versions. Explicit version conditionals (e.g. gated on
`django.VERSION`) are a **rare last resort**, used only when no single code path can
satisfy both. If an agent finds itself writing version conditionals routinely, that's a
signal it picked the wrong fix, not that the codebase needs branches.

Implication for agents: a change that fixes the new version but breaks the old one during
the bridge period is a **failure**, not progress. Dual-compat shims are removed only in
stage 3, never opportunistically.

### When a repo is "done"
- CI green on the full matrix (old + new target version, all supported Pythons).
- New version released and consumable by dependents.
- Changelog entry + version bump merged.

---

## Per-repo checklist (→ Dev agent instructions)

Canonical file set for a library upgrade (template: openedx/openedx-filters#287):

| File | Change |
|---|---|
| `tox.ini` | Add new env to envlist; add the version spec under `[testenv]` deps |
| `.github/workflows/ci.yml` | Add the new version to the test matrix |
| `setup.py` / `setup.cfg` | Add the new trove classifiers |
| `requirements/*.txt` | Recompile via `make upgrade` / pip-tools — never hand-edit pins |
| `<package>/__init__.py` | Bump `__version__` (breaking support change ⇒ **major** bump) |
| `CHANGELOG.rst` | Entry under the new version: what was added/dropped |
| `Makefile` | Occasionally: add/repair `upgrade` / `compile-requirements` targets |

Rules:
- **Run the target's codemod first** (e.g. `django-upgrade --target-version X.Y`), committed
  separately from judgment-based fixes — keeps mechanical and reasoned changes reviewable
  apart. Codemods cannot detect all breaking changes (anything touching migrations needs
  manual work) — the codemod is the floor, never the whole job.
- **Conventional commits**: `feat!:` for support changes that drop a version,
  `chore:`/`build:` for routine bumps, `fix:` for compat fixes. PR title = commit title.
- Dropping an old version is a separate, explicit decision (`feat!:` + major bump).
  **Policy: drop only after the repo is green on BOTH old and new versions** — the drop PR
  removes the old version from the matrix and runs `make upgrade` so all pins recompile
  against the new version only. See Phase 3.
- Code changes for deprecations go in the **same PR for libraries**, **separate prep PRs
  for the platform**.
- Never touch unrelated formatting/refactors in an upgrade PR.

---

## Failure taxonomy (→ Fixer agent brain)

When CI goes red after the bump, classify before fixing.

### A. Known breaking-change patterns
See the target playbook's pattern table (e.g. `playbooks/django.md`).

**General fix-shape rule** (reference: openedx/edx-val#580, historical): when a removed API
has several copy-pasted call sites, **consolidate them into one dual-compat helper with its
own dedicated tests**, rather than patching each call site in place. That helper is also
where a rare, justified version conditional may live (Phase 3).

### B. Third-party dependency lag
The most common real blocker: a dependency doesn't support the new version yet.
Identify the offender from the resolver error or import failure, then follow the
**upstream ladder**:

1. **Check support first.** Does any released version of the package support the version
   being targeted? (Check classifiers, setup.py/pyproject, CI matrix, changelog —
   classifiers can lag reality, so the CI matrix/changelog is the better signal.)
2. **Supported** → bump the pin to that version.
3. **Not supported yet** → ask upstream: open an issue requesting support.
4. **Owner doesn't act** → do the work for them: clone/fork, make the support PR ourselves,
   and hand it to the maintainer to merge. (Standard practice, not a last resort — we
   contribute the fix rather than wait.)
   **The upstream PR is the same per-repo checklist, applied to their repo** — update their
   tox envlist, their CI matrix, add the code changes. Two adaptations: follow *their*
   conventions (commit style, changelog format, requirements tooling), and keep the diff
   minimal — support for the new version only, no opinions about their project.
   (Agent mapping: the Dev agent reuses its checklist on external repos, with a "match the
   host repo's conventions" override; human reviews before anything is posted.)
5. **While waiting for the merge/release** → pin a git hash temporarily, replaced with a
   real version pin once released. (Precedent: edx-proctoring-proctortrack during the
   Django 4.2 campaign.)
6. **Upstream is openedx-owned** → it's simply an earlier item in our own campaign
   ordering, not an external ask.
7. **Unmaintained / maintainer unreachable and PR unmerged** → stop and escalate to human:
   fork-and-own vs. replace is a strategic decision, not an agent call.

Agent note: steps 3–4 (issues and upstream PRs) are **outward-facing actions** — draft
them, but a human reviews and sends. Never post to external repos autonomously.

### C. Flaky vs. real failures
- `TODO(awais)`: heuristics — which suites/shards in openedx-platform are known flaky,
  what to rerun vs. investigate, how many reruns before suspecting the upgrade.

### D. Infra / CI failures
Unrelated to the change (runner images, pip resolver timeouts, codecov).
- `TODO(awais)`: known infra failure signatures.

### Escalation rule (for the agent)
If a failure doesn't match A–D after one diagnosis pass, or the fix would touch business
logic beyond mechanical compatibility: **stop, summarize findings, escalate to human.**
Never force-fix by deleting/skipping tests.

---

## Definition of done (→ Reviewer agent rubric)

Per repo, a PR is mergeable when:
- [ ] CI green on the **full matrix** (all supported version combos — old versions must
      still pass, not just the new one)
- [ ] tox envlist, CI matrix, and setup.py classifiers **agree** with each other
- [ ] Requirements recompiled (no hand-edited pins; diff shows compiler output)
- [ ] Version bumped per semver (major if support dropped/added with `feat!:`)
- [ ] CHANGELOG entry present and accurate
- [ ] Conventional-commit PR title; description states what's added/dropped and links the
      campaign tracking issue
- [ ] Diff contains **only** upgrade-related changes
- [ ] No tests deleted, skipped, or weakened to get to green

Campaign-level done: all tier repos released; openedx-platform on the new version as
default; tracking issues closed.

---

## Agent mapping

| Process section | Agent | Role |
|---|---|---|
| Phases 0–0.5 | PM | Scan org, classify repos, draft master issue / tickets / announcement / how-to doc (human posts) |
| Phase 1–2 + per-repo checklist | Dev | Branch, run codemod, apply checklist, fix known patterns, open draft PR |
| Failure taxonomy | Fixer | Read CI results, classify, apply fix pattern or escalate |
| Definition of done | Reviewer | Gate the PR against the rubric before requesting human review |

Invariants: agents only open **draft** PRs; a human merges. All outward-facing actions
(announcements, tickets, upstream issues/PRs) are human-gated. Escalation is success,
not failure.
