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

### Django 6.x patterns (seeded June 2026 from the official release notes — not yet campaign-verified)

A 5.2 → 6.x campaign crosses everything removed in 6.0 AND 6.1. Curated for Open edX
relevance from `django/django` `docs/releases/6.0.txt` and `docs/internals/deprecation.txt`:

**Precursor (hard gate):** Django 6.0 supports **Python 3.12–3.14 only** — 5.2 is the last
series with 3.10/3.11. The Python-floor campaign must finish first. Also `asgiref >= 3.9.1`.
Django officially suggests third-party apps drop Django < 5.2 after 6.0 ships — matching our
drop policy.

**Removed in 6.0:**

| Pattern | Symptom | Fix |
|---|---|---|
| `DEFAULT_AUTO_FIELD` now defaults to `BigAutoField` | Unintended `makemigrations` diffs (PK type change!) in repos that never set it (long-standing `models.W042` warning) | Set `DEFAULT_AUTO_FIELD = "django.db.models.AutoField"` explicitly (or per-app `default_auto_field`) to preserve current PKs — do NOT accept an auto-generated PK-type migration |
| `Model.save()` / `asave()` positional args removed | `TypeError` on `save(True)`-style calls | Keyword-only: `save(force_insert=True)` |
| `format_html()` without args/kwargs removed | `TypeError`/error on bare `format_html(s)` calls | Pass args, or use `mark_safe` where genuinely static |
| `CheckConstraint(check=...)` kwarg removed | `TypeError` in models/migrations | Rename to `condition=` |
| `forms.URLField` default scheme is now `https` | Test failures asserting `http://` normalization | Set expectations / explicit `assume_scheme` |
| `BaseConstraint` positional args removed | `TypeError` in custom constraints | Keyword args |
| `ModelAdmin.lookup_allowed()` requires `request` | `TypeError` in admin subclasses | Add `request` to the signature |
| `django.urls.register_converter()` override disallowed | Error registering an existing converter name | Rename or dedupe converters |
| `ModelAdmin.log_deletion()` / `LogEntryManager.log_action()` removed | `AttributeError` in admin auditing code | Use `log_deletions()` / `log_actions()` plural replacements |
| Custom lookups/expressions: `as_sql()` params must be a tuple | Param-merge errors in custom ORM expressions | Return tuples; unpack as `(*lhs_params, *rhs_params)` |
| Email internals overhauled (`SafeMIMEText`/`SafeMIMEMultipart`/`BadHeaderError` deprecated; undocumented `EmailMessage` internals changed) | Breakage in code subclassing email internals (e.g. ACE/email pipelines) | Audit subclasses; move to documented API / `email.message.MIMEPart` |
| `Field.pre_save()` may be called more than once per save | Duplicated side effects (counters, timestamps) | Make `pre_save` idempotent |
| JSON serializer always emits trailing newline | Golden-file/snapshot test diffs | Update fixtures |
| `cx_Oracle` support removed | Oracle backends fail | N/A for openedx (long dropped) |

**Removed in 6.1 (also crossed by a 6.2 campaign):**

| Pattern | Symptom | Fix |
|---|---|---|
| `staticfiles.finders.find(all=...)` kwarg removed | `TypeError` in static-asset tooling | Use `find_all=` |
| `auth.login()` / `alogin()` no longer fall back to `request.user` when `user=None` | Auth flows silently relying on the fallback break | Pass the user explicitly |
| Postgres aggregates `ordering` kwarg removed (`ArrayAgg`, `JSONBAgg`, `StringAgg`) | `TypeError` in annotated queries | Use `order_by=` |
| `RemoteUserMiddleware` subclasses overriding only `process_request` | Deprecation → breakage | Also override `aprocess_request()` |

**Deprecated in 6.0 (fix the warnings during the campaign; removal in 7.0):** keyword-only
params in `django.core.mail` APIs; `ADMINS`/`MANAGERS` as (name, address) tuples → plain
address strings; postgres `StringAgg` → generally-available `django.db.models.StringAgg`;
`urlize` default protocol flips to HTTPS in 7.0 (`URLIZE_ASSUME_HTTPS` transitional).

`TODO`: re-verify against the 6.2 release notes at campaign kickoff and promote
campaign-verified patterns (with PR references) into the table above.

---

## 2b. Reference PRs (what "done right" looks like)

| PR | What it demonstrates |
|---|---|
| [openedx/django-user-tasks#412](https://github.com/openedx/django-user-tasks/pull/412) | **The canonical first library PR** — the complete flow end to end: claimed per-repo ticket (#413) → `django-upgrade` codemod → checklist files (`tox.ini`, CI matrix, classifier, `test_settings`, version bump, CHANGELOG) → targeted code fixes (`conf.py` storage, `schema/urls.py`) → PR description linking the campaign Discourse thread and resolving the ticket. ~30 changed lines total. This is the shape the Dev agent's output is graded against. |
| [openedx/openedx-filters#287](https://github.com/openedx/openedx-filters/pull/287) | The minimal config-only variant (no code fixes needed) — the seven-file checklist in its purest form. |

**PR description conventions** (from #412): state that the codemod was run, link the
campaign coordination thread, reference the per-repo ticket ("Created PR to resolve #N"),
and note the version bump + changelog.

## 3. Codemod tooling

- **[`django-upgrade`](https://github.com/adamchainz/django-upgrade)** (adamchainz) — the
  campaign's standard **syntax-compatibility** codemod: mechanically rewrites code for the
  target Django version (settings renames, deprecated call forms, etc.). Run it as the
  FIRST action on every repo, committed separately from judgment-based fixes:

  ```bash
  pip install django-upgrade          # or: uvx django-upgrade
  git ls-files -z -- '*.py' | xargs -0 django-upgrade --target-version 5.2
  ```

- **Known limitation (from the 5.2 campaign thread):** it cannot detect all breaking
  changes — anything touching migrations (e.g. `index_together`) needs manual work, and
  behavioral changes (storage APIs, signal semantics) are out of its scope entirely.
  The codemod is the floor, never the whole job.

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
