# Testing

Install dependencies and run:

```powershell
python -m pip install -r requirements.txt
python -m pytest -q -p no:cacheprovider
```

Normal tests use temporary SQLite databases and `FakeMT5Gateway`; they do not require a terminal, broker login, Telegram token, or network.

Coverage includes NX-ID uniqueness, durable creation, outbox idempotency/retry/unknown handling, Partial/Final linkage, report keys, mixed timestamps, position-ID history, ladder stage idempotency/restart reconciliation, disconnect/reconnect, order rejection, volume stepping, WAL backup, schema migration, risk controls, checklist snapshots, config secret hygiene, and MT5 connection ownership.

Live MT5 validation is a separate release gate. Never describe fake/static results as live broker verification.
