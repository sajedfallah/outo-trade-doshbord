# NEXUS

NEXUS v0.9.20 — Stabilization & Reliability is a Windows-first trading signal and trade-management system. The current release is a local bilingual Streamlit Admin Command Center connected directly to the administrator's MetaTrader 5 terminal, Telegram channel, and SQLite data store.

This repository is an existing production-oriented codebase, not a clean-room rewrite. Stabilization code and broker-free tests are in place; controlled demo-account validation is the next release gate before new product surfaces are added.

## What exists now

- Manual signal creation with raw MT5 chart capture, BUY/SELL geometry checks, risk or fixed-lot sizing, setup/checklist snapshot, and multi-target trailing plan.
- Raw MT5 chart-panel screenshots for initial signal and final result publication; no generated chart overlays are applied to those Telegram images.
- Telegram signal publication and reply-chain lifecycle updates.
- Direct MT5 market/pending execution with demo-account guard, configurable/discoverable symbol mapping, filling fallbacks, and risk controls.
- Position-ID-based lifecycle monitoring for partial and final closes.
- Result Chart V3 cards with a readable price-action panel plus a complete risk/reward map for entry, stop, every target, and persisted exits.
- Ladder, R-based, fixed-R, ATR, and manual trailing profiles with persisted plans/actions.
- Account and NEXUS-only performance analytics, workflow audit, reports, strategy analytics, archive, journal, and local deterministic trade review.
- AutoTrade client/trailing policy data models. There is no central server or remote subscriber client yet.

Planned but not implemented: the central signal server, authenticated investor dashboard, remote AutoTrade client, and complete subscription/licensing system.

## Runtime layout

- `Dashboard/app.py` — streamlined, page-based Admin UI for account overview, signal issuance, setup checklists, and trade dossiers.
- `Dashboard/advanced_app.py` — the original full Command Center, loaded only when Advanced tools is selected.
- `MT5_MONITOR.py` / `monitor/mt5_monitor.py` — continuous MT5 lifecycle, trailing, reporting, and workflow monitor.
- `mt5trade/executor.py` — direct MT5 order planning and submission.
- `storage/repo.py` — SQLite schema and repository functions.
- `telegram/publisher.py` — Telegram Bot API publication.
- `trailing/engine.py` — local trailing state machine.
- `risk/risk_engine.py` — pre-trade safety, throttle, and kill switch.
- `strategy/setup_engine.py` — checklist scoring and descriptive setup analysis.
- `monitor/` — lifecycle logic, reports, charts, metrics, reviews, and workflow audit.

See [the architecture audit](docs/architecture.md) for dependencies, data schema, flow maps, and known risks.

## Run locally

Requirements: Windows, Python 3.14, an installed MT5 terminal, and the packages in `requirements.txt`.

```powershell
python -m pip install -r requirements.txt
python -m streamlit run Dashboard/app.py
```

For the normal two-process workflow, run `RUN_NEXUS.cmd`; it starts the monitor and then the dashboard. `MT5_MONITOR_ONCE.cmd` performs a single lifecycle synchronization. Do not run more than one continuous monitor.

The default Admin UI evaluates only the selected page, so ordinary clicks no longer rebuild every analytics and operations panel. The Home page contains essential account cards and balance/equity charts. Signal setup selection immediately loads that setup's checklist; the scored checklist snapshot is stored with the signal for future reporting. Trade Archive starts as a compact trade menu and opens one detailed dossier at a time. The former all-in-one interface remains available through **Advanced tools**.

## Raw MT5 chart publication

For signal issuance and final-close cards, NEXUS captures the currently visible chart panel from the configured MT5 terminal. It does not add labels, redraw candles, or edit the screenshot. Before publishing a signal, open the intended symbol/timeframe chart in MT5 and keep its drawings visible. The crop is configured in `monitor.screenshot.chart_crop`; it excludes terminal panels while retaining the chart's own drawings and indicators. Partial exits remain text-card replies to the original signal; only the final close sends the raw chart image.

The configured MT5 account mode is guarded as demo by default. Do not change it to real without a deliberate live-trading release process.

## Critical lifecycle invariant

On the target broker, datetime-range deal history has returned zero rows for known trades. NEXUS therefore uses:

```text
signal -> MT5 ticket/position ID -> history_deals_get(position=POSITION_ID)
```

Manual close deals with `magic = 0` and empty comments still belong to a NEXUS trade when their `position_id` matches.

## Secret configuration

The token exposed by the historical package must be rotated manually in BotFather. v0.9.20 removes it from `config.json`. Copy `.env.example` to ignored `.env` and set the rotated value:

```text
NEXUS_TELEGRAM_BOT_TOKEN=...
```

Never include `config.json` with credentials, `.env`, production SQLite files, WAL/SHM files, logs, PID/lock files, or personal uploads in a public repository.

## Current quality status

Audit performed 2026-08-13:

- Python compilation: passed.
- SQLite integrity check: passed; database is in WAL mode.
- Temporary legacy-schema migration smoke test: preserved sample data and created current tables.
- Existing diagnostic scripts: environment, trailing, and workflow checks ran.
- Automated pytest reliability suite: 32 tests passed locally and remains broker-independent.
- MT5 package/terminal availability: detected locally, but no order, partial-close, SL-change, or live broker test was performed by this audit.

High-priority defects and the next acceptance criteria are tracked in `ROADMAP.md`. The historical release narrative remains in `README.txt` until it is curated into the changelog.

## Documentation

- `docs/architecture.md` — current architecture, schema, flows, audit findings.
- `docs/reliability.md`, `docs/outbox.md`, and `docs/trailing-recovery.md` — crash/retry behavior.
- `docs/database-migrations.md` and `docs/testing.md` — upgrade and verification procedures.
- `ROADMAP.md` — incremental implementation plan.
- `CHANGELOG.md` — release and audit notes.
- `TRAILING_PROFILES_GUIDE.txt` — current operator quick guide.
- `AGENTS.md` — repository invariants for contributors and coding agents.
