# Telegram outbox

The `outbox` table is the durable boundary for Telegram signal, Partial, Final, and report delivery.

Each item stores a unique idempotency key, operation type, optional signal ID, JSON payload/reference, status, attempt count, error, next retry time, timestamps, and Telegram message ID.

## States

- `PENDING` — durable intent not yet claimed.
- `SENDING` — one process owns the current attempt.
- `SENT` — Telegram returned a message ID and local linkage was updated.
- `FAILED` — definite failure; eligible for bounded exponential retry.
- `DEAD` — retry limit reached.
- `UNKNOWN` — delivery may have succeeded; never auto-replayed.

Deterministic keys include `NX-ID:TELEGRAM:SIGNAL`, lifecycle `event_key:TELEGRAM`, and `REPORT:report_key:TELEGRAM`. `INSERT OR IGNORE` returns the existing item for repeat calls.

The monitor processes due items every pass. Dead/unknown items are shown in the Admin System reliability area. Payloads contain message text and local media references, never the bot token.
