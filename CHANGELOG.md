# Changelog

## Unreleased — Admin dashboard simplification

- Fixed the new-checklist-item form: its submit button no longer remains disabled while editing inside a Streamlit form, and blank/zero-weight input now receives an explicit validation message.
- Replaced fragment-scoped operational reruns with compatible full reruns, preventing Streamlit API errors after checklist saves, archive selection, and image uploads.
- Upgraded MT5 result images to `NEXUS_RESULT_V3`: readable price-action scaling, compact execution markers, collision-aware labels, all persisted partial/final exits, and a separate complete risk/reward trade map for ENTRY/SL/all TP levels.
- Replaced the 14-tab default view with a five-item, page-based Persian navigation shell that evaluates only the selected page.
- Reduced Home to essential account cards, balance/equity history, open positions, and recent activity.
- Made setup selection immediately render its active checklist and live weighted grade during signal issuance; the immutable checklist snapshot remains attached to the durable signal record.
- Changed Trade Archive to a compact trade menu with a separate visual dossier for the selected trade.
- Preserved the previous full Command Center as an on-demand Advanced tools view.
- Removed the signal-page `st.stop()` branch after queued Telegram delivery so recoverable delivery states render normally instead of presenting as an application stop.
- Added pure dashboard view-model regression tests and isolated secret tests from the operator's local `.env` file.

All notable changes should be recorded here. The historical v0.9.8–v0.9.19 narrative is retained in `README.txt` and can be normalized into this file incrementally.

## Unreleased

## 0.9.20 — Stabilization & Reliability

### Added

- Environment/`.env` Telegram secret loading, public example, ignore rules, and configuration audit.
- Versioned schema ledger and durable Telegram outbox with bounded retry and fail-closed unknown delivery state.
- Durable signal creation before Telegram/MT5 side effects and explicit duplicate NX-ID errors.
- SQLite Backup API migration with timestamped backup for both in-place and ZIP-to-ZIP upgrades, WAL inclusion, integrity validation, row-count report, schema lock, and active-monitor guard.
- Incremental real/fake MT5 gateway for broker-free tests.
- Trailing executing/confirmed/reconciliation states, position-history partial recovery, historical target checks, and freeze-level validation.
- Compact Admin reliability status and failed/unknown outbox visibility.
- Pytest suite and reliability/migration/outbox/trailing/testing documentation.

### Fixed

- Result-chart generation no longer shuts down a monitor-owned MT5 session.
- Monitor/trailing global enable flags are enforced.
- Signals without an actionable MT5 status no longer enter the lifecycle polling set.
- Checklist grades use configured thresholds and required-item publication policy is enforced.

### Security

- Removed the exposed Telegram bot token from public configuration. The historical token still requires manual rotation.

### Documentation

- Added repository-wide contributor and safety rules in `AGENTS.md`.
- Added a current `README.md` with runtime orientation, security warning, and verified quality status.
- Added `docs/architecture.md` with architecture/dependency maps, database schema, operational flows, and audit findings.
- Added `ROADMAP.md` with stabilization-first milestones and acceptance criteria.

### Resolved audit findings

- Removed the plaintext Telegram credential from `config.json`; manual rotation of the historically exposed token remains required.
- Replaced print-only diagnostics as the sole verification with a broker-independent pytest suite.
- Confirmed SQLite integrity is OK, WAL mode is active, and `PRAGMA user_version` is still `0`.
- Confirmed position-ID-based MT5 deal history remains the lifecycle source.
- Added durable outbox/recovery behavior for Telegram lifecycle and report publication.
- Fixed nested MT5 initialization/shutdown ownership in result-chart generation.
- Replaced unsafe main-file migration copying with validated SQLite online backup.
- Removed non-actionable signals from monitor polling and enforced key runtime configuration contracts.
- Made repository SQLite connection closure deterministic.

## 0.9.19 — Trailing Profiles & Client Policies

- Added persisted trailing profiles, per-signal trailing plan snapshots, and action audit records.
- Added ladder, R-based, fixed-R, ATR, and manual modes.
- Added Admin-side AutoTrade client and trailing policy records/resolution.
- Added multi-target signal entry and Result Chart V2.
- Preserved position-ID lifecycle history and public-card R suppression.

Remote client execution, the central signal server, full licensing, and the investor dashboard are not part of this version.
