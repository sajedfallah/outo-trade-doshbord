# Changelog

All notable changes should be recorded here. The historical v0.9.8–v0.9.19 narrative is retained in `README.txt` and can be normalized into this file incrementally.

## Unreleased

- Stabilization / end-to-end Windows + MT5 demo acceptance is the active release gate.
- See `docs/NEXT_VALIDATION_WORKFLOW_FA.md` and `ROADMAP.md`.

## 0.9.39.1 — Readability & Typography Final

### Added / Changed

- Added one shared readability layer (`NEXUS-TYPE-1.0`) for Admin + Client.
- Raised desktop root typography to a readable 17px baseline with responsive tablet/mobile scaling.
- Improved Persian/English fallback stack: Vazirmatn / IRANYekanX / Segoe UI / Tahoma without bundling font binaries.
- Centered internal section/page/panel titles consistently.
- Prevented legacy compact/mobile CSS from shrinking important labels, cards, tables and navigation to unreadable sizes.

### Validation

- `python -m compileall -q .` — PASS.
- `pytest -q` — 135 passed.
- Admin runtime smoke matrix — PASS across FA/EN and DARK/LIGHT combinations.
- Client runtime smoke matrix — PASS across FA/EN and DARK/LIGHT combinations.

## 0.9.39 — Responsive Premium Platform

### Added

- Unified Admin customer, subscription and license management.
- One-flow Quick Create for Client + User + Subscription + License.
- Shared responsive NEXUS design system across Admin and Client.
- Admin DARK/LIGHT theme toggle with persisted preference.
- Responsive Client Portal with Dashboard, Signals, Trades, Performance, AutoTrade, Subscription/License and Profile views.
- Authenticated client-scoped overview API for safe subscription/license metadata and execution reports.
- Platform roles and permissions for `ADMIN`, `AUTO_TRADE_USER`, `DASHBOARD_USER` and `PRO_USER`.
- Product/subscription/entitlement and license binding management.
- Local Client API and License Server startup flows.

### Compatibility / Safety

- Existing signal/risk/MT5/Telegram execution semantics remain the safety baseline.
- Client data remains client-scoped.
- Raw license secrets/device hashes are not exposed by the read-only client overview surface.
- Hosted production deployment and funded-account approval remain outside this release acceptance.

## 0.9.25 — ICT Scoring + UI Reliability

- Added built-in deterministic ICT scoring models, grading and No-Trade gates.
- Improved LIGHT dashboard contrast, typography and theme-aware charts.
- Hardened trailing range reconstruction and unresolved-position diagnostics.
- Added ATR anti-chatter threshold support.

## 0.9.24 — Scalping Performance + Exact Chart Overlay

- Added dashboard caching/performance improvements and warm MT5 session ownership.
- Added exact single-axis Entry/SL/TP rendering and publication timing metrics.
- Preserved Telegram-confirmation-before-MT5 execution and fail-closed `UNKNOWN` delivery behavior.

## 0.9.23 — Dual Theme Approved Signal Renderer

- Added persisted LIGHT/DARK Dashboard and Signal Card themes.
- Bundled approved NEXUS/Nexu visual assets.
- Unified Preview and Telegram Publish through the same renderer.

## 0.9.22 — Pro Command Center & Data-Driven Signal Charts

- Replaced normal signal publication screen capture with MT5 OHLC-based rendering.
- Added premium Command Center layout and optional analysis-image input.

## 0.9.21 — Command Center & Mentor Analytics

- Added category-based Admin navigation, performance-first overview and deterministic Mentor analytics.
- Added dedicated operational pages for trailing, workflow, risk and client policy.

## 0.9.20 — Stabilization & Reliability

### Added

- Environment/`.env` Telegram secret loading, public example, ignore rules, and configuration audit.
- Versioned schema ledger and durable Telegram outbox with bounded retry and fail-closed unknown delivery state.
- Durable signal creation before Telegram/MT5 side effects and explicit duplicate NX-ID errors.
- SQLite Backup API migration with timestamped backup for in-place/ZIP upgrades, WAL inclusion, integrity validation, schema lock and active-monitor guard.
- Incremental real/fake MT5 gateway for broker-free tests.
- Trailing executing/confirmed/reconciliation states, position-history partial recovery, historical target checks and freeze-level validation.
- Broker-independent pytest reliability foundation.

### Fixed

- Result-chart generation no longer shuts down a monitor-owned MT5 session.
- Monitor/trailing global enable flags are enforced.
- Signals without an actionable MT5 status no longer enter lifecycle polling.
- Checklist grades use configured thresholds and required-item publication policy is enforced.

### Security

- Removed the exposed Telegram bot token from public configuration. Historical credentials still require operator-side rotation if previously exposed.

## 0.9.19 — Trailing Profiles & Client Policies

- Added persisted trailing profiles, per-signal trailing plan snapshots and action audit records.
- Added ladder, R-based, fixed-R, ATR and manual modes.
- Added Admin-side AutoTrade client/trailing policy records and resolution.
- Added multi-target signal entry and Result Chart V2.
- Preserved position-ID lifecycle history and public-card R suppression.
