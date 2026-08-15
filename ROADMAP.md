# NEXUS incremental roadmap

## Current baseline

**NEXUS v0.9.39.1 — Responsive Premium Platform / Readability Final**

The project has reached the point where platform surfaces, local client services, roles, subscriptions, licensing and the responsive Admin/Client experience exist. The next priority is **stabilization and end-to-end validation**, not broad feature expansion.

The release principle from this point forward is:

```text
STABILITY
  ↓
CLIENT FLOW
  ↓
MT5 DEMO VALIDATION
  ↓
END-TO-END EXECUTION
  ↓
REVERSE SYNC / REPORTING
  ↓
SECURITY / PACKAGING
  ↓
CLOUD / COMMERCIAL RELEASE
```

---

## Milestone A — v0.9.39.1 baseline freeze

**Status: current**

Completed baseline capabilities:

- Responsive Admin Command Center.
- Responsive Client Trading Portal.
- Shared DARK/LIGHT visual system.
- Persian/English UI surfaces.
- `NEXUS-TYPE-1.0` readability layer and centered internal titles.
- Platform users, roles and permissions.
- Customer/Client ID management.
- Products, subscriptions and entitlements.
- License generation, ownership and MT5/device binding model.
- Authenticated Client API.
- License Server.
- Unified Customer + Subscription + License Quick Create flow.
- Existing MT5 execution, monitor, risk, trailing, Telegram, reports and analytics infrastructure.

Automated release evidence:

- `python -m compileall -q .` — PASS.
- `pytest -q` — 135 passed.
- Admin runtime smoke matrix — PASS.
- Client runtime smoke matrix — PASS.

Acceptance to close this milestone:

- Repository/documentation reflects the v0.9.39.1 baseline.
- No known critical UI/runtime regression blocks the next demo validation.
- A backup branch exists before repository synchronization.

---

## Milestone B — Client + MT5 demo activation

**Priority: NEXT**

Goal: prove that an authenticated client can connect a real demo MT5 terminal and activate the assigned license without weakening the existing security boundary.

Required sequence:

1. Start Client API on `127.0.0.1:8790`.
2. Start Admin on `localhost:8501`.
3. Start Client on `localhost:8502`.
4. Create a dedicated demo client through Quick Create.
5. Confirm role, subscription and active license.
6. Connect the Client Portal to a demo `terminal64.exe`.
7. Verify MT5 login/server detection.
8. Activate license.
9. Verify first binding to the expected Client ID + MT5 Login + device fingerprint.
10. Restart Client/API and verify binding persists.
11. Verify another MT5 login/device is rejected until Admin Reset Binding is used.

Acceptance:

- Client status changes from `MT5 OFFLINE` to connected.
- License remains ACTIVE and bound to the correct demo account/device.
- No Admin-only information is exposed to the client.
- Restart/reconnect does not create a duplicate binding.

---

## Milestone C — First assigned signal end-to-end

Goal: validate the complete signal path without relying on assumptions from isolated tests.

```text
Admin Signal
  ↓
Signal Distribution
  ↓
Client Assignment
  ↓
Client API
  ↓
Client Portal
  ↓
Permission / Entitlement / License checks
  ↓
AutoTrade
  ↓
MT5 Demo
```

Test cases:

- One BUY signal.
- One SELL signal.
- Signal assigned to Client A is invisible to Client B.
- Expired/suspended subscription cannot execute.
- Invalid/unbound license cannot execute.
- MT5 offline prevents execution cleanly.
- Risk/kill-switch block prevents new execution while the signal remains visible where appropriate.

Acceptance:

- Exactly one MT5 order is produced for one accepted signal.
- No duplicate execution after refresh/restart.
- Rejected executions return a clear reason.
- Execution report is persisted client-scoped.

---

## Milestone D — Position lifecycle and trade management

Goal: validate the demo position after entry.

Required evidence:

- Entry captured correctly.
- SL/TP geometry matches the signal.
- Partial close behavior is correct.
- Break-even stage is correct.
- Trailing stages are correct.
- Restart during an open trade reconstructs state safely.
- Manual broker-side close is associated through `position_id`.
- Final close is stored exactly once.

Acceptance:

- No duplicate partial closes.
- No duplicate SL moves.
- No orphaned lifecycle after restart.
- Position-ID history remains the authoritative lifecycle source.

---

## Milestone E — Reverse sync and multi-surface consistency

Goal: Admin, Client and MT5 must agree on the same trade state.

Validate:

- MT5 open position -> Admin active trade.
- MT5 open position -> Client trade view.
- Pending -> filled transition.
- Manual close -> final closed state.
- Client execution report -> Admin/client reporting.
- Unknown externally opened demo position import behavior.

Acceptance:

- No cross-client leakage.
- No stale active position after final close.
- No duplicate import after restart.

---

## Milestone F — Performance and reporting acceptance

Validate after completed demo trades:

- Balance / Equity.
- Daily P/L.
- Win/Loss/BE classification.
- R multiple.
- Duration.
- MAE/MFE where available.
- Daily report.
- Weekly report.
- Client personal report scope.
- Admin account-wide/NEXUS analytics.

Acceptance:

- Closed-trade metrics match the broker history used by NEXUS.
- Client sees only its own entitled reporting surface.
- Daily/weekly summaries do not double count canceled/active trades.

---

## Milestone G — Responsive / theme / language UAT

Before the next stable beta, test every important page in:

```text
FA + DARK
FA + LIGHT
EN + DARK
EN + LIGHT
```

Viewport matrix:

- 1920×1080 desktop.
- 1366×768 laptop.
- 1024px tablet landscape.
- 768px tablet.
- ~390×844 mobile.

Acceptance:

- No horizontal overflow in primary workflows.
- No unreadably small typography.
- Internal titles remain centered.
- Forms remain touch-friendly.
- Customer/license and client pages remain usable on mobile.

---

## Milestone H — Stable Beta v0.9.40

The next version should be named **v0.9.40 STABLE BETA** only after Milestones B–G have documented evidence.

v0.9.40 should prioritize bug fixes, reliability and acceptance results over new feature breadth.

Release requirements:

- Demo E2E signal/trade pass.
- Restart/recovery pass.
- Reverse-sync pass.
- Client isolation pass.
- Role/entitlement/license negative tests pass.
- Responsive/theme/language UAT pass.
- Clean public-source secret scan.
- Updated operator documentation.

---

## Milestone I — Production hardening

After stable beta:

- HTTPS/TLS for hosted services.
- Hardened authentication/session policy.
- Rate limiting.
- Audit logs for sensitive Admin operations.
- Central observability and error monitoring.
- Backup/restore drills.
- License abuse/replay controls.
- Remote heartbeat/reconnect behavior.
- Windows client/agent packaging and update mechanism.

---

## Milestone J — Cloud SaaS architecture

Target architecture:

```text
                    NEXUS CLOUD
                         │
      ┌──────────────────┼──────────────────┐
      │                  │                  │
   Database          API Server       License Service
      │                  │                  │
      └──────────────────┼──────────────────┘
                         │
                Signal Distribution
                         │
          ┌──────────────┼──────────────┐
          │              │              │
       Client A       Client B       Client C
          │              │              │
       MT5 Agent      MT5 Agent      MT5 Agent
```

Commercial infrastructure such as OTP, payment gateway, billing, invoices, automatic renewal, SMS/email verification and support automation belongs after the trading/client core is stable.

---

## Current rule

**Do not approve funded/live-account use based only on compile, pytest or UI smoke results.**

The immediate release gate is the controlled Windows + MT5 demo workflow documented in `docs/NEXT_VALIDATION_WORKFLOW_FA.md`.
