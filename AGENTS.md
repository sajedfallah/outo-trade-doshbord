# NEXUS contributor instructions

These rules apply to the entire repository.

## Product and safety invariants

- Extend the existing application incrementally. Do not replace working local Admin, MT5, Telegram, lifecycle, analytics, journal, archive, reporting, risk, or trailing behavior without an explicit migration plan.
- Keep Direct MT5 execution demo-guarded. Never run live order or trailing tests merely to validate a code change.
- Never start a Telegram-polling trade bot alongside the direct MT5 executor. Telegram is a publication channel, not the future machine-to-machine signal transport.
- `position_id` plus `history_deals_get(position=...)` is the authoritative MT5 lifecycle join. Do not substitute datetime-range deal history without broker-verified evidence.
- Risk automation may reduce requested risk but must never increase it silently.
- Public Partial/Final Telegram cards must not expose realized R. Internal analytics and reports may retain R.
- Dashboard language and Telegram-card language are independent. Preserve Persian RTL and English LTR behavior.
- Symbol suffixes must remain configurable or discoverable; do not hardcode the current broker.

## Data and migrations

- Treat `storage/NEXUS_DATA.db`, its WAL state, and `uploads/` as production data.
- Before a schema change, inspect the actual schema, create a versioned and restart-safe migration, and test it against a copy/fixture of the previous schema.
- Never overwrite a database from an active WAL-mode installation by copying only the main `.db` file. Use SQLite backup/checkpoint-aware migration and verify the result before replacement.
- Preserve signals, results, lifecycle events, report runs, workflow audit, setup snapshots, journal records, media paths, trailing plans/actions, and client policies.
- Historical setup and trailing snapshots are immutable business records. Template edits must not rewrite them.
- External effects and local state must be designed for crash recovery. Telegram sends and MT5 actions require durable intent, reconciliation, and idempotent retry behavior.
- Preserve the v0.9.20 outbox status contract. `UNKNOWN` effects must not be replayed automatically.

## Secrets and local artifacts

- Never commit or print tokens, credentials, account identifiers, production databases, WAL/SHM files, logs, PID/lock files, or personal uploads.
- Load credentials from environment variables or an ignored local secret file. Keep channel configuration separate from credentials.
- `.env.example` may contain names and placeholders only.
- If a credential is discovered in repository content or output, redact it and advise immediate rotation.

## Change discipline

1. Read `README.md`, `ROADMAP.md`, `docs/architecture.md`, the touched call paths, and the current schema before editing.
2. Keep changes scoped. Avoid broad refactors mixed with behavior fixes.
3. Add regression tests for every defect and migration tests for every schema change.
4. Use `python -m streamlit run Dashboard/app.py`; do not assume a bare `streamlit` command.
5. Keep Windows paths with spaces and `.cmd` launchers working.
6. Update `CHANGELOG.md` and relevant docs with behavior, compatibility, and migration notes.

## Verification levels

- **Static tested:** compilation, imports, lint/static checks, and pure unit tests.
- **Local tested:** temporary SQLite migration, mocked MT5/Telegram integration, Streamlit startup/refresh, and filesystem behavior.
- **MT5 live test required:** broker retcodes, filling modes, stop/freeze constraints, partial closes, SL changes, pending fills, position-history reconciliation, and restart recovery.

Do not describe static compilation as proof of broker execution. Report changed files, tests, limitations, and any required live validation.
