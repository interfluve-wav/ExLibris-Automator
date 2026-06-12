# Documentation Index

Canonical map of every document in this repository, grouped by audience.

**Working branch:** `v7` · **Quick start:** [`GETTING_STARTED.md`](GETTING_STARTED.md)

---

## Start here

| Document | Audience | What it covers |
|---|---|---|
| [`../README.md`](../README.md) | Everyone | Overview, tech stack, quick start, API summary |
| [`QUICKSTART.md`](QUICKSTART.md) | Everyone | Copy-paste setup, run, health, recovery commands |
| [`GETTING_STARTED.md`](GETTING_STARTED.md) | New operators | Step-by-step install, configure, first citation |
| [`AUDIT.md`](AUDIT.md) | Maintainers | Latest repository health audit |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Developers | Stack, process model, module map, dataflow |
| [`SMART_BATCH_GUIDE.md`](SMART_BATCH_GUIDE.md) | Operators | Daily Discord batch workflow |

---

## Operating the system

| Document | What it covers |
|---|---|
| [`OPERATIONS_RUNBOOK.md`](OPERATIONS_RUNBOOK.md) | Startup, health checks, recovery, shutdown |
| [`COMMANDS_REFERENCE.md`](COMMANDS_REFERENCE.md) | Discord, Flask API, shell launchers |
| [`ALL_FEATURES_GUIDE.md`](ALL_FEATURES_GUIDE.md) | End-to-end feature reference |
| [`FEATURES_OVERVIEW.md`](FEATURES_OVERVIEW.md) | Feature catalog by subsystem |
| [`IPC_PROTOCOL.md`](IPC_PROTOCOL.md) | File-based IPC contracts |

---

## Setup & configuration

| Document | What it covers |
|---|---|
| [`ENV_EXAMPLE.md`](ENV_EXAMPLE.md) | `.env` template and variable reference |
| [`DISCORD_SETUP.md`](DISCORD_SETUP.md) | Create and configure the Discord bot |
| [`../deployment/DEPLOYMENT.md`](../deployment/DEPLOYMENT.md) | systemd / production deployment |

---

## Contributing & governance

| Document | What it covers |
|---|---|
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Branching, commits, PR checklist, coding standards |
| [`../SECURITY.md`](../SECURITY.md) | Secrets, CI scanning, vulnerability reporting |
| [`../CHANGELOG.md`](../CHANGELOG.md) | Version history |

---

## Architecture deep dives

| Document | Status | What it covers |
|---|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | **Current** | Authoritative system reference |
| [`OPTIMIZATION_SUMMARY.md`](OPTIMIZATION_SUMMARY.md) | Reference | Performance work history |
| [`TECHNICAL_DOCUMENTATION_FIX.md`](TECHNICAL_DOCUMENTATION_FIX.md) | Reference | Tech-doc parser notes |
| [`Web App & Discord Bot Integration Steps.md`](Web%20App%20%26%20Discord%20Bot%20Integration%20Steps.md) | Reference | GUI/bot integration notes |
| [`Asset Type Integration Future.md`](Asset%20Type%20Integration%20Future.md) | Roadmap | Future asset-type ideas |

---

## Root-level reference (legacy / supplementary)

| Document | Notes |
|---|---|
| [`../PRODUCTION.md`](../PRODUCTION.md) | Production notes |
| [`../replit.md`](../replit.md) | Replit deployment (legacy) |
| [`../OPTIMIZATIONS_2026-02.md`](../OPTIMIZATIONS_2026-02.md) | Feb 2026 optimization log |
| [`../BEFORE_AFTER.md`](../BEFORE_AFTER.md) | Before/after comparison |
| [`../ANALYSIS_SUMMARY.md`](../ANALYSIS_SUMMARY.md) | Analysis summary |

---

## Tests & benchmarks

```bash
.venv/bin/python test_citations.py
.venv/bin/python tests/performance_tests.py
```
