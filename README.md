# NEXUS

## Current release: v0.9.39.1

NEXUS v0.9.39.1 is the current **Responsive Premium Platform / Readability Final** baseline. It keeps the trading, risk, monitoring, Telegram, storage, role, subscription and licensing architecture while advancing NEXUS into a local Admin + Client trading platform with a shared visual system.

> ⚠️ NEXUS can execute trades through MetaTrader 5. The current release must remain on controlled demo validation until the end-to-end acceptance workflow in `docs/NEXT_VALIDATION_WORKFLOW_FA.md` is completed.

## What exists now

### Admin Command Center

- Responsive Streamlit Admin dashboard.
- Shared DARK/LIGHT NEXUS design system.
- Persian/English presentation.
- Readability system `NEXUS-TYPE-1.0` with larger typography and centered internal titles.
- MT5 account/status surfaces, trading status, daily performance, system health and Market Pulse.
- Manual signal creation, setup/checklist snapshots, risk/fixed-lot sizing and multi-target plans.
- Risk Center, workflow audit, journal, archive, mentor analytics and performance analytics.
- Unified customer / subscription / license management.
- Quick Create workflow for Customer + User + Subscription + License.

### Client Trading Portal

- Authenticated Streamlit Client Portal.
- Shared visual language with the Admin Command Center.
- Responsive Dashboard, Signals, Trades, Performance, AutoTrade, Subscription/License and Profile pages.
- Role/permission and entitlement-aware access.
- Client-scoped signal, execution-report and account information.
- Local MT5 connection and license activation flow.

### Platform services

- `client_api/` authenticated client API.
- `licensing/` local license server.
- Platform users and roles: `ADMIN`, `AUTO_TRADE_USER`, `DASHBOARD_USER`, `PRO_USER`.
- Products, subscriptions, entitlements and license/client ownership.
- MT5-login/device binding with Admin reset controls.
- SQLite repositories and migration-safe schema evolution.

### Trading / lifecycle engine

- Telegram publication and reply-chain lifecycle updates.
- Direct MT5 market/pending execution with demo-account safety guard.
- Position-ID-based MT5 lifecycle synchronization.
- Break-even / partial / trailing management.
- Risk throttle, prop-firm limits and kill-switch controls.
- Result cards, daily/weekly reports and trading analytics.
- Market/account reverse observation and controlled MT5 import support.

## Runtime layout

- `Dashboard/app.py` — Admin Command Center and platform administration.
- `Dashboard/components/ui_tokens.py` — shared NEXUS design tokens, typography, DARK/LIGHT palettes and responsive CSS.
- `Dashboard/components/customer_license_center.py` — customer/license management presentation.
- `Client/app.py` — NEXUS Client Portal.
- `client_api/server.py` / `client_api/routes.py` — authenticated client-scoped HTTP API.
- `licensing/server.py` — license activation/verification service.
- `storage/repo.py` / `storage/platform_repo.py` — trading and platform persistence.
- `MT5_MONITOR.py` / `monitor/mt5_monitor.py` — MT5 lifecycle, trailing, reporting and workflow monitor.
- `mt5trade/` — MT5 gateway/execution services.
- `risk/` — risk intelligence and safety gates.
- `telegram/` — Telegram publication/outbox.
- `strategy/` — deterministic strategy/checklist models.

## Correct local startup order

Install dependencies first:

```powershell
python -m pip install -r requirements.txt
```

Start the platform services in this order:

```powershell
RUN_CLIENT_API_SERVER.cmd
RUN_NEXUS.cmd
RUN_CLIENT_PANEL.cmd
```

Expected endpoints:

```text
Admin:      http://localhost:8501
Client:     http://localhost:8502
Client API: http://127.0.0.1:8790
```

`RUN_PLATFORM_SERVICES.cmd` can be used for the supported grouped service startup path where appropriate.

## Current manual workstation validation

The following local flow has been observed on the Windows workstation during v0.9.39.x validation:

- Admin dashboard starts on port 8501.
- Client Portal starts on port 8502.
- Client API starts successfully on port 8790.
- Platform user creation works.
- Customer/Client ID creation works.
- Subscription creation works.
- License creation/assignment works.
- Client authentication succeeds once Client API is running.
- Subscription/license metadata is visible in the Client Portal.
- MT5 remains the next controlled validation gate when the Client shows `MT5 = OFFLINE`.

## Immediate next release gate

No large feature expansion should be started before the current platform flow is validated end to end.

The required order is:

```text
Customer
  ↓
Subscription
  ↓
License
  ↓
Client Login
  ↓
MT5 Demo Connection
  ↓
License Activation / Binding
  ↓
Assigned Signal
  ↓
AutoTrade Execution
  ↓
MT5 Position Lifecycle
  ↓
Result / Reverse Sync
  ↓
Performance / Reporting
```

Detailed acceptance steps and evidence requirements are documented in:

- `docs/NEXT_VALIDATION_WORKFLOW_FA.md`
- `PROJECT_STATUS.md`
- `ROADMAP.md`

## Automated quality status

Validation recorded for the v0.9.39.1 package:

- `python -m compileall -q .` — PASS.
- `pytest -q` — **135 passed**.
- Admin runtime smoke matrix — PASS across FA/EN and DARK/LIGHT combinations.
- Client runtime smoke matrix — PASS across FA/EN and DARK/LIGHT combinations.
- Client API / License Server health paths — validated in the packaged release workflow.
- Telegram token-shaped secret scan — PASS.

These checks do **not** replace controlled real Windows/MT5 demo acceptance. No funded-account usage is approved by these automated results.

## Security / repository hygiene

This repository is public. Never commit:

- `.env`
- real Telegram bot tokens or API credentials
- production SQLite/WAL/SHM files
- runtime logs/PID/lock files
- private client data
- device fingerprints
- personal uploads or broker/account screenshots that should not be public

`config.json` must remain free of secrets; operator-specific configuration should be reviewed before public release packaging.

## Release artifact

The current local release artifact is:

```text
NEXUS_v0.9.39.1_READABILITY_FINAL.zip
SHA-256: 319d47d138a1ca07fa9c1f83e97c777d237fa7460edec2fea0ec0ff7719004b7
```

See `RELEASE_ARTIFACTS.md` for artifact policy and repository-safety notes.

## Documentation

- `PROJECT_STATUS.md` — current platform state and release gate.
- `docs/NEXT_VALIDATION_WORKFLOW_FA.md` — next end-to-end validation workflow in Persian.
- `docs/architecture.md` — architecture, schema and operational flows.
- `docs/testing.md` — automated/local testing guidance.
- `docs/reliability.md` — reliability rules.
- `docs/outbox.md` — Telegram/external-effect durability.
- `docs/trailing-recovery.md` — trailing/restart behavior.
- `ROADMAP.md` — incremental delivery roadmap.
- `CHANGELOG.md` — release history.
- `AGENTS.md` — repository invariants for contributors and coding agents.
