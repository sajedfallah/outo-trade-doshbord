# Reliability model

NEXUS v0.9.20 makes local intent durable before contacting Telegram or MT5.

## Safety boundaries

- A signal row, checklist snapshot, trailing plan, and Telegram outbox intent are persisted before publication/execution.
- Duplicate NX-IDs raise an explicit error; existing dossiers are never replaced.
- Telegram operations use deterministic outbox keys and bounded exponential retry.
- Network failures with an uncertain Telegram outcome become `UNKNOWN` and are not replayed automatically. This avoids uncontrolled duplicates and requires Admin review.
- The monitor owns its MT5 connection. Result-chart helpers only shut down sessions they initialized themselves.
- Trailing actions distinguish `EXECUTING`, `CONFIRMED`, `FAILED`, `WAITING`, and `UNKNOWN`; uncertain partial closes are reconciled against position-ID history before any retry.
- A disabled global monitor or trailing setting is now honored.

The System tab shows MT5 state, queue/attention counts, heartbeat context, trailing errors, last Telegram success, and database schema version without exposing secrets.

## Crash boundaries

Telegram cannot provide a client idempotency key. If the process dies after Telegram accepts a message but before SQLite records the response, v0.9.20 fails closed: the outbox item is marked `UNKNOWN` at startup. An Admin must compare the channel and workflow before deciding whether to resend.

MT5 partial-close recovery uses baseline exit tickets and `history_deals_get(position=POSITION_ID)`. When a new exit deal exists, the action is confirmed without another order. If the result remains unknowable, the engine stops that action for manual reconciliation.
