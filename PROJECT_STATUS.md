# NEXUS Project Status

## Current baseline

**Version:** v0.9.39.1  
**Release:** Responsive Premium Platform · Readability Final  
**Phase:** Stabilization + End-to-End Demo Validation  
**Next target:** v0.9.40 STABLE BETA

---

## What is implemented

### Admin

- Responsive NEXUS Command Center.
- DARK/LIGHT theme system.
- Persian/English UI.
- Shared readability/typography layer.
- MT5 account/status, trade status, daily performance, system health and Market Pulse.
- Signal creation, risk controls, journal/archive/analytics/mentor/workflow pages.
- Customer + Subscription + License management.
- Quick Create workflow.

### Client

- Responsive authenticated Client Portal.
- Dashboard, Signals, Trades, Performance, AutoTrade, Subscription/License and Profile views.
- Shared Admin/Client design language.
- Client-scoped role/permission/entitlement access.
- Local MT5 connection and license activation surface.

### Platform services

- Client API (`127.0.0.1:8790`).
- License Server.
- Platform users and roles.
- Products/subscriptions/entitlements.
- License ownership and binding model.
- Client-scoped execution reporting.

### Trading core

- MT5 gateway/execution.
- MT5 lifecycle monitor.
- Position-ID history association.
- Risk Engine / kill switch / prop-firm controls.
- Partial / break-even / trailing infrastructure.
- Telegram durable publication flow.
- Result/report/analytics infrastructure.

---

## Current Windows workstation evidence

Observed in the current manual validation cycle:

- Admin dashboard starts on port 8501.
- Client Portal starts on port 8502.
- Client API starts successfully on port 8790.
- Customer/User creation succeeds.
- Subscription creation succeeds.
- License creation/assignment succeeds.
- Client login succeeds when the Client API service is running.
- Client Subscription/License page loads assigned metadata.
- Client currently exposes `MT5 OFFLINE` until the next demo-terminal activation test is completed.

---

## Automated evidence for v0.9.39.1

- Compile check: PASS.
- Pytest: **135 passed**.
- Admin runtime smoke matrix: PASS.
- Client runtime smoke matrix: PASS.
- Secret-shaped Telegram token scan: PASS in the packaged release validation.

Automated checks are not a substitute for live Windows + MetaTrader demo acceptance.

---

## Current release gate

The project is intentionally frozen against broad feature expansion until this path passes:

```text
Customer / User
      ↓
Subscription
      ↓
License
      ↓
Client Login
      ↓
MT5 Demo Connection
      ↓
License Binding
      ↓
Assigned Signal
      ↓
AutoTrade
      ↓
MT5 Position
      ↓
Trailing / Partial / BE
      ↓
Final Close
      ↓
Reverse Sync
      ↓
Performance / Reports
```

Detailed procedures: `docs/NEXT_VALIDATION_WORKFLOW_FA.md`.

---

## Required evidence before v0.9.40 STABLE BETA

1. Client + MT5 demo connection evidence.
2. License activation and binding persistence evidence.
3. Cross-client isolation negative test.
4. One BUY and one SELL assigned-signal E2E test.
5. Duplicate-execution/restart safety test.
6. Partial / BE / trailing lifecycle test.
7. Manual close + reverse-sync test.
8. Performance/report reconciliation against MT5 history.
9. FA/EN × DARK/LIGHT UI acceptance.
10. Desktop/tablet/mobile acceptance.
11. Clean public-source secret/runtime-data scan.

---

## Release artifact reference

Canonical local package at this checkpoint:

```text
NEXUS_v0.9.39.1_READABILITY_FINAL.zip
SHA-256: 319d47d138a1ca07fa9c1f83e97c777d237fa7460edec2fea0ec0ff7719004b7
```

See `RELEASE_ARTIFACTS.md` before publishing binary packages to this public repository.
