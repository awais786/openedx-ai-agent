# Django Upgrade Playbook

Target-specific knowledge for Django upgrade campaigns. The general process lives in
[`../campaign-process.md`](../campaign-process.md); this file supplies the four things the
process consumes for Django: calendar, pattern table, codemod tooling, watchlist.

Seeded from the Django 4.2 (2023) and Django 5.2 (2025) campaigns — sources:
[openedx/public-engineering#339](https://github.com/openedx/public-engineering/issues/339)
(master issue), #340/#341 (breaking-change tickets), the
[5.2 coordination thread](https://discuss.openedx.org/t/django-5-2-upgrade-plan/15397),
and ~822 merged PRs across the openedx org.

---

## 1. Calendar (checked June 2026 — re-verify at kickoff)

- Open edX is on **Django 5.2 LTS** (platform flip Oct 2025; extended support → April 2028).
- Latest Django: 6.0.x. Non-LTS 6.0/6.1 are skipped per policy.
- **Next campaign target: Django 6.2 LTS, releasing April 2027.** Replaying the 5.2
  cadence: kickoff ≈ April–May 2027 → libraries dual-compat (5.2 + 6.2) by mid-2027 →
  services by late summer → platform flip ≈ Oct 2027 → ships in the **December 2027 named
  release**, ~4 months ahead of 5.2's April 2028 EOL. Aligns with the edX release train;
  no off-cycle pressure.
- Precursor: per endoflife.date, Django 5.2 supports Python 3.10–3.14 but 6.0 requires
  **3.12–3.14**. Confirm fleet Python versions before kickoff.
- Hygiene audit (June 2026): **Django 4.2 security support ended April 7, 2026** — any
  straggler repo still pinned to 4.2 is running an unsupported Django today. Worth a fleet
  scan now, independent of the next campaign.
- Head start: 6.0/6.1 release notes are already published; most of 6.2's breaking-changes
  list is knowable early (deprecations warn one version ahead). Small-repo rehearsals
  against 6.0/6.1 can seed the §2 pattern table before the campaign opens.

### Past campaign timeline (5.2, for cadence reference)
Announced March 31, 2025 → libraries dual-compat by May 14 → services 5.2-only by Aug 4 →
Tutor updates by Sep 4 → platform flip Oct 2025 → shipped in Ulmo.

---

## 2. Breaking-change pattern table

Known Django breaking-change patterns and fix recipes, each backed by a real campaign PR:

| Pattern | Symptom | Fix (with precedent) |
|---|---|---|
| `get_storage_class` removed (5.2) | `ImportError`/deprecation in storage code & tests | Migrate to `STORAGES` / `django.core.files.storage.storages`; dual-compat shim if repo must support both ("feat!: upgrade code and fix get_storage_class (compatibility django42 and django52)") |
| `STORAGES` replaces `DEFAULT_FILE_STORAGE` (4.2→5.x) | Settings errors | "feat!: Upgrading storages with new STORAGES" (course-discovery) |
| `SHA1PasswordHasher` removed (5.x) | Test failures referencing the hasher | Remove from tests / switch hasher ("fix: removing deprecated SHA1PasswordHasher from tests") |
| Signal receiver return shape changed (5.2) | Tuple-unpacking errors in signal handling | Update unpacking ("fix: Updated tuple unpacking of signal receivers") |
| Delete ordering / signal consistency tightened (5.2) | Order-dependent test failures around deletes | Adjust expectations/code ("fix: django52 tightened consistency around delete ordering and signals") |
| Unsaved instances rejected in related filters (5.x) | `ValueError` passing unsaved model to filter | Save first / restructure ("fix: Passing unsaved model instances to related filters…", "fix: ensure _get_user returns saved user (with id)") |
| Lazy translation objects | Str-comparison/serialization failures | Force `str()` where needed ("fix: Correctly handle Django lazy translation objects") |
| `CSRF_TRUSTED_ORIGINS` requires schemes (4.x) | CSRF failures in deployment/tests | Add `https://` schemes ("feat!: Django 4.0 and above, CSRF_TRUSTED_ORIGINS must include schemes") |
| `Meta.index_together` removed (5.2) | System check errors / `makemigrations` failures | Convert to `Meta.indexes` and **generate new migrations** — flagged in the 5.2 thread as requiring manual intervention; django-upgrade does not handle it |

`TODO`: extend with 5.2→6.x patterns as the next campaign reveals them (seed from the
published 6.0/6.1 release notes).

---

## 3. Codemod tooling

- **[`django-upgrade`](https://pypi.org/project/django-upgrade/)** — run
  `django-upgrade --target-version X.Y` as the first action on every repo, committed
  separately from judgment-based fixes.
- **Known limitation (from the 5.2 campaign thread):** it cannot detect all breaking
  changes — anything touching migrations (e.g. `index_together`) needs manual work.

---

## 4. Watchlist

**Laggards from the 5.2 campaign** (the last 4 repos incomplete as of May 16, 2025, per the
coordination thread): `django-multi-email-field`, `edx-sga`, `edx-enterprise`,
`enterprise-integrated-channels`. Expect the same repos (especially the large enterprise
pair) to need early attention and active shepherding in the next campaign.

**Critical-usage dependency:** `django-storages` — sits under file handling platform-wide
(uploads, certificates, exports). Storage changes are high-risk regardless of diff size.

**Slow third parties needing version bumps in past campaigns:** django-storages,
django-simple-history, django-pipeline; git-hash pin precedent: edx-proctoring-proctortrack.

`TODO`: confirm/extend — any other third-party packages that were slow?
