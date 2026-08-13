# NEXUS incremental roadmap

The current baseline is v0.9.19. Work proceeds in small, migration-safe milestones; local Admin operation remains available throughout server evolution.

## Milestone 0 — v0.9.20 stabilization and safety (implemented; live validation pending)

This is the next implementation milestone.

### 0A. Repository and secret hygiene

- Rotate the exposed Telegram token.
- Load the token from an environment variable or ignored local secret file while keeping channel ID/config separate.
- Add `.env.example` and `.gitignore`; remove secrets, production DB/WAL/SHM, logs, locks, PIDs, and personal uploads from distributable source.
- Add a redacted configuration validator and prevent secret values from entering diagnostics.

Acceptance: a clean checkout starts after documented local configuration, no real secret is present in repository files, and Telegram tests redact credential-bearing URLs/responses.

### 0B. Test foundation

- Add `tests/` with pure unit tests for event R/classification, risk throttle, target validation, volume stepping, checklist scoring, mixed timestamps, workflow state, and client policy precedence.
- Add fake-MT5 integration tests for market/pending planning, position-ID history, partial/final lifecycle, trailing stages, broker rejects, and restart recovery.
- Add temporary-SQLite migration tests from representative prior schemas and verify idempotency/data preservation.
- Add mocked Telegram tests for reply chaining, retry, timeout, and crash recovery.

Acceptance: tests run without a broker or real Telegram token and cover every P0/P1 defect fixed below.

### 0C. Durable external-effects workflow

- Persist signal intent and immutable setup/trailing snapshots before Telegram/MT5 side effects.
- Replace `INSERT OR REPLACE` signal behavior with explicit create/update semantics and reject duplicate NX-IDs.
- Add outbox/delivery states for signal, partial, final, and report publication; retry failed deliveries without duplicating successful sends.
- Reconcile MT5 action intent against live position/deal history after crashes before retrying a partial close or SL move.

Acceptance: injected crashes at each boundary recover without lost lifecycle messages, duplicate Telegram posts, duplicate partial closes, or overwritten signal dossiers.

### 0D. MT5 monitor stabilization

- Make MT5 session ownership explicit; chart generation must reuse the active session or avoid shutting it down.
- Stop polling/log flooding for `NOT_REQUESTED`, invalid, canceled, or permanently unresolvable records; surface one durable workflow diagnostic with controlled retry/backoff.
- Resolve pending fill/cancel/expiry transitions through order history and persist a terminal state.
- Make trailing restart-aware by reconstructing target crossings since the last durable stage, not only from the current M1 candle.
- Validate freeze level and stop distance explicitly and preserve raw request/retcode diagnostics.
- Enforce `monitor.enabled`, `trailing.enabled`, and other operational flags consistently.

Acceptance: a mocked restart across TP1/TP2/TP3 produces exactly one partial and the expected SL stages; canceled pending orders terminate cleanly; scheduled reports still work after result-chart publication.

### 0E. Versioned, WAL-safe migrations

- Introduce ordered schema versions and a migration ledger.
- Make repository connection ownership explicit and close connections deterministically; do not rely on `sqlite3.Connection` context management to close file handles.
- Use SQLite online backup/checkpoint-aware copying; never copy only an active main DB file.
- Validate integrity, schema version, row counts, and upload paths before switching installations.
- Keep and document rollback backups; make the Windows migration launcher non-interactive-capable while retaining guided mode.
- Add foreign keys/indexes where safe through tested rebuild migrations.

Acceptance: migration tests preserve all audited entities from prior fixtures, work twice idempotently, and fail closed without replacing the destination when validation fails.

## Milestone 1 — Result Chart V3

- Premium dark NEXUS composition with collision-aware ENTRY/EXIT/TP/SL labels.
- Plot all partial exits and the final exit from persisted lifecycle events.
- Use configured display timezone and broker digits; keep public realized R hidden.
- Add golden-image/layout tests across BUY/SELL, 1–8 targets, dense candles, and long symbols.

## Milestone 2 — trailing broker validation

- Demo-account validation matrix for TP1 partial + BE, TP2 -> TP1, TP3 -> TP2.
- Validate min/max/step, stop/freeze levels, spread, filling modes, partial-deal timing, and restart recovery on Roco demo.
- Document static/local results separately from MT5 live evidence.

## Milestone 3 — Strategy Builder and archive polish

- Enforce configurable grade thresholds and required-checklist publication rules.
- Make setup/trailing snapshots database-immutable.
- Complete trade dossier fields, media categories, path portability, and gallery UX.
- Add sample-size labels and uncertainty warnings to descriptive checklist analytics; never imply causation.

## Milestone 4 — central signal server foundation

- Write API, authentication, authorization, signal revision, policy, heartbeat, acknowledgement, and audit specifications first.
- Add a minimal FastAPI/PostgreSQL service beside the local Admin; use a durable local outbox/sync adapter.
- Preserve offline local Admin operation during migration.
- Telegram remains a publication channel, not client transport.

## Milestone 5 — authenticated investor dashboard

- Separate read-only application and server-side role authorization.
- Admin-controlled publication of open trades and archives.
- No execution controls, credentials, internal notes, or operational diagnostics.

## Milestone 6 — Windows AutoTrade client

- Authenticated central-server transport, local-only MT5 credentials, heartbeat/reconnect, signal deduplication, acknowledgements, and restart-safe local trailing.
- Apply authority in this order: signal override > Admin client policy > permitted user preference > default profile.

## Milestone 7 — subscription and expiry

- Plans, start/expiry, suspension, features, risk/trailing ranges, symbols, client limits, and optional account/broker/device bindings.
- Define and test safe management of already-open positions after expiry before enforcing it.
