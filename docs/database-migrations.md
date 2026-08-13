# Database migrations

Schema version 2 introduces `schema_migrations`, the durable `outbox`, signal publication state, and reliability indexes. Migrations use `CREATE IF NOT EXISTS`, guarded additive columns, and unique keys, so they can run repeatedly.

On the first repository access to an existing pre-v0.9.20 database, NEXUS acquires a cross-process schema lock and creates a timestamped SQLite online backup before applying version 2. This also protects in-place upgrades, not only ZIP-to-ZIP migration.

## Upgrade procedure

1. Stop the NEXUS monitor and dashboard cleanly. Migration refuses to continue when the current monitor PID is active.
2. Keep the old release folder unchanged next to the new release.
3. Run `MIGRATE_FROM_PREVIOUS.cmd` from v0.9.20.
4. Select the source release.
5. The tool creates a timestamped online SQLite backup of the destination, uses SQLite Backup API to stage the source including committed WAL pages, validates integrity, replaces only the new release database, copies uploads, applies incremental migrations, and prints row counts/schema version.
6. Review the report before starting `RUN_NEXUS.cmd`.

The old installation is never deleted. Backups are placed under `storage/backups/` and are excluded from Git.

## Schema history

| Version | Name | Main additions |
|---|---|---|
| 1 | v0.9.19 baseline | Existing signals, lifecycle, strategy, archive, journal, risk, trailing, and client-policy tables. |
| 2 | v0.9.20 reliability outbox | `schema_migrations`, `outbox`, signal publication fields, operational indexes. |

Production databases, WAL/SHM files, and backups must never be committed.
