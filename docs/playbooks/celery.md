# Celery Upgrade Playbook (stub)

Target-specific knowledge for Celery (and broker stack) upgrade campaigns. The general
process in [`../campaign-process.md`](../campaign-process.md) applies; Celery adds its own
wrinkles to capture here before the first agent-assisted campaign:

## 1. Calendar
- `TODO`: Celery/kombu/billiard release and support timeline vs. Open edX release train.

## 2. Breaking-change pattern table
- `TODO`: known patterns — settings renames (`CELERY_*` namespacing), task serialization
  defaults, broker transport options, kombu/billiard lockstep version coupling.

## 3. Codemod tooling
- `TODO`: no django-upgrade equivalent known — likely grep-driven checklists instead.

## 4. Watchlist
- `TODO`: repos with deep Celery coupling (edx-celeryutils, openedx-platform workers,
  enterprise tasks).
