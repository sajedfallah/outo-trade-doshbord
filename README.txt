
HISTORICAL RELEASE NOTES — CURRENT SETUP IS DOCUMENTED IN README.md
The Telegram token instructions below are obsolete. v0.9.20 loads the rotated
token from NEXUS_TELEGRAM_BOT_TOKEN or an ignored local .env file.

NEXUS v0.9.8 — MANUAL STABLE
============================

WHY THIS BUILD
Vision/OCR has been removed from the critical signal/result path.
You enter the numbers manually, upload the chart, review the flash card,
and publish.

SIGNAL
1) Enter Symbol / BUY-SELL / Timeframe / Entry / TP / SL.
2) Choose Risk % or Fixed Lot.
3) Upload the TradingView chart image.
4) Review RR and flash card.
5) PUBLISH SIGNAL.
6) Optional: enable Direct MT5 execution for that signal.

RESULT
1) Select the NX signal.
2) Choose TP / SL / Breakeven / Extension / Manual Close.
3) Enter Exit Price.
4) R and Return % are pre-calculated but remain editable.
5) Upload result chart.
6) PUBLISH RESULT.
7) The result is sent as a Telegram reply to the original signal post.

FIRST RUN
1) Configure the rotated Telegram token through local environment/.env (v0.9.20).
2) Run INSTALL.cmd once.
3) Run RUN_NEXUS.cmd.

IMPORTANT
- No Tesseract is required.
- No automatic Position Tool detection is used.
- No automatic OCR price extraction is used.
- MT5 execution is optional and disabled by default on the Signal form.
- Keep account_mode=demo during testing.


V0.9.9 — MT5 HISTORY + REPLY CHAIN
==================================
The manual Signal/Result workflow remains unchanged and stable.
MT5 is now the automatic source for trade lifecycle history.

WHEN A TRADE IS OPEN
- Monitor matches the MT5 position to the NX signal through NEXUS NX-XXX.
- Initial and remaining volume are tracked.

PARTIAL CLOSE
Example: initial 0.10 lot, user closes 0.05.
The monitor automatically:
1) detects the MT5 OUT deal,
2) calculates closed and remaining volume,
3) calculates this partial R and total realized R,
4) captures the visible MetaTrader window,
5) creates a Partial Close flash card,
6) replies to the ORIGINAL Telegram signal,
7) stores the Telegram update message_id.

ANOTHER PARTIAL / FINAL CLOSE
- The next update replies to the PREVIOUS update message.
- This creates one Telegram reply chain for the whole trade.

FINAL CLOSE
When remaining volume becomes zero, the monitor calculates:
- full trade P/L from MT5 deals,
- volume-weighted total R across all partial exits,
- weighted average exit,
- TP / SL / Breakeven / Profit / Loss result classification.
It captures MT5 again and sends the FINAL result as a reply to the previous update.

SCREENSHOT
The monitor looks for a visible Windows window whose title contains:
Roco Broker / MetaTrader 5 / MetaTrader.
It restores/foregrounds that window and captures it.
If no matching window is found, config can allow a full-desktop fallback.

RUN
RUN_NEXUS.cmd starts BOTH:
1) MT5_MONITOR.py in a minimized CMD window
2) Streamlit Dashboard

STOP BACKGROUND MONITOR
Run:
STOP_MONITOR.cmd

MANUAL SINGLE SYNC TEST
Run:
MT5_MONITOR_ONCE.cmd

IMPORTANT
- Keep MT5 terminal open while monitoring.
- Telegram bot token must be provided through environment/.env in v0.9.20.
- Direct MT5 execution checkbox must be enabled for signals you want the monitor
  to track automatically.
- Demo mode guard remains enabled.


V0.9.10 — POSITION-BASED MT5 HISTORY FIX
========================================
Live diagnosis confirmed:
- NX-002 stored position/ticket: 2084225
- history_deals_get(datetime range) returned zero deals
- history_deals_get(position=2084225) returned both the opening and closing deal

v0.9.10 therefore uses position-based MT5 history as the authoritative source:

Signal -> mt5_position_id/ticket -> history_deals_get(position=ID)

This path is now used for:
- partial close detection
- final close detection
- remaining volume tracking
- total P/L
- volume-weighted total R
- result classification
- Telegram reply-chain publishing

A fallback also resolves position_id from MT5 order history when a pending order
fills and closes between polling cycles.


V0.9.11 — ADMIN POLISH
======================

1) CHART-ONLY RESULT SCREENSHOT
Automatic MT5 result messages no longer intentionally capture the whole desktop.
Priority is:
  Chart workspace only -> MT5 window fallback
Full desktop fallback is disabled by default.

Default chart crop:
  left   0.18
  top    0.14
  right  0.995
  bottom 0.84

Use Dashboard > SETTINGS > TEST CHART SCREENSHOT to preview exactly what
Telegram will receive. If the user's MT5 panels/layout differ, adjust the four
chart_crop ratios in config.json.

2) PARTIAL CLOSE REPLY CHAIN
MT5 Position ID remains the authoritative lifecycle key.

Example:
Initial volume 0.10
User manually closes 0.05 at TP1
Remaining live volume 0.05

NEXUS automatically publishes:
  original signal
    -> PARTIAL CLOSE reply:
       initial volume / closed volume / remaining volume
       partial R / total realized R
       "position is still open"
         -> FINAL CLOSE reply:
            total P/L / weighted total R / final classification
            chart-only screenshot

Manual MT5 closes are supported even when the closing deal has magic=0 and an
empty comment, because matching is by position_id.

3) RESULT MENU REFACTORED
The old Result tab is now:
  MANUAL OVERRIDE

Normal result publication is automatic from MT5.
Manual Override remains intentionally available for:
- monitor/network interruption
- administrative correction
- manual close outside normal lifecycle
- breakeven/extension or exceptional publication
- emergency resend

4) PROFESSIONAL ADMIN OVERVIEW
Dashboard now shows at a glance:
- live Balance
- live Equity
- Free Margin
- floating P/L
- open positions
- closed NEXUS trades
- win rate
- net P/L
- profit factor
- average R
- best/worst R
- current account drawdown
- NEXUS realized max drawdown
- realized performance curve
- drawdown curve
- performance by symbol
- live MT5 positions
- recent trade lifecycle events

Balance/Equity/Open Positions are read live from MT5.
Performance history uses NEXUS-tracked final trade events, avoiding the MT5
datetime-history issue already confirmed on the target setup.

5) SCREENSHOT CALIBRATION
Dashboard > SETTINGS > TEST CHART SCREENSHOT
shows a real preview of the image that automatic result publication will attach.


V0.9.11.1 — SCREENSHOT HOTFIX
=============================
Confirmed live failure: screenshot capture could not import win32gui.
This build removes the pywin32 dependency from capture completely.
MT5 window discovery/restore now uses Windows user32.dll through ctypes.
Pillow ImageGrab then captures the MT5 window and applies the chart-only crop.
No changes were made to signal execution, MT5 history, partial-close logic,
final-result calculations, Telegram reply-chain logic, or dashboard analytics.


V0.9.11.2 — CAPTURE + PREVIEW FIX
=================================
1) SIGNAL PREVIEW UI
The long Streamlit DeltaGenerator/debug-looking text under Signal Preview was
caused by Streamlit magic rendering a bare conditional expression.
It is now a normal if/else block, so only the intended green/red validation
message is displayed.

2) MT5 WINDOW DETECTION
Window-title matching was not reliable on the target machine.
Capture now finds the actual terminal64.exe process with psutil, enumerates
top-level Windows belonging to that PID, and selects the largest main terminal
window. This avoids picking the smaller Position/order dialog.

3) CHART-ONLY CAPTURE
Capture now grabs the MT5 CLIENT AREA (excluding Windows title/borders) and then
crops to the chart workspace. The default ratios were adjusted for the observed
layout:
  left   0.02
  top    0.055
  right  0.985
  bottom 0.79

Full-desktop fallback remains disabled.

4) TELEGRAM
Historical note: this old test build stored the token in config.json. v0.9.20
removes that unsafe behavior; the previously exposed token must be rotated.


V0.9.11.3 — MT5 MAIN WINDOW DISCOVERY FIX
=========================================
Observed on target machine:
TEST CHART SCREENSHOT -> MT5_MAIN_WINDOW_NOT_FOUND

This build no longer relies on process-name enumeration alone.

Window discovery priority:
1) EnumWindows + native QueryFullProcessImageNameW
2) exact configured terminal executable path
3) executable name terminal64.exe / terminal.exe
4) title keyword fallback
5) PowerShell Get-Process MainWindowHandle fallback

Once the real MT5 main window is found:
- capture uses the MT5 client rectangle
- chart-only crop is applied
- full desktop fallback remains disabled


V0.9.11.4 — METAQUOTES CLASS WINDOW DISCOVERY
=============================================
If process-image/title matching returns zero candidates, NEXUS now also matches
the native Windows class name. MetaTrader/MetaQuotes main windows are selected
by class keywords such as:
  metaquotes
  metatrader

The failure diagnostics now include the 12 largest visible Windows with:
  title
  window class
  PID
  process image path (when readable)
  size

This means a remaining failure will expose the exact real MT5 window identity
instead of returning only candidate_count=0.


V0.9.12 — MT5 DATA RESULT CHARTS
================================
Confirmed target-machine diagnostics showed the visible Windows list contained
Edge, Explorer, Settings and Windows Terminal, but no visible MT5 main window.

Therefore GUI screenshot capture is no longer used for automatic trade results.

New architecture:
MT5 position/history -> MT5 OHLC candle data -> generated chart-only PNG ->
Telegram reply.

Advantages:
- no visible MT5 window required
- no whole-desktop screenshot
- no Windows title/class/PID dependency
- clean chart-only image every time
- Entry / TP / SL / Exit are drawn on the result chart
- Partial Close and Final Close both use the same chart engine
- result image remains linked to the correct NEXUS reply chain

Dashboard Settings now has:
TEST MT5 RESULT CHART

This generates the same kind of chart that Telegram will receive.

The previous Windows screenshot code remains in the package only as a disabled
legacy utility. Automatic result publication does not use it.


V0.9.12.1 — MT5 EXECUTION DEFAULT ON
====================================
Confirmed live database state:
  NX-001
  mt5_enabled = 0
  mt5_status = NOT_REQUESTED
  mt5_ticket = NULL

The signal was published to Telegram, but no MT5 order was requested.

Fix:
- The easy-to-miss MT5 checkbox is removed.
- Signal Execution Mode is explicit.
- Default mode:
    Telegram + MT5 + Auto Tracking
- Optional mode:
    Telegram Only

Telegram Only must be selected intentionally and shows a warning.

Normal default workflow:
Manual values + chart
-> Telegram publish
-> MT5 order_send
-> ticket / position stored
-> automatic Partial Close tracking
-> automatic Final Result
-> MT5-data generated result chart
-> Telegram reply chain

CHECK_LATEST_SIGNAL.cmd shows the newest signal's MT5 execution state.


V0.9.13 — AUTOMATIC DAILY / WEEKLY REPORTS
==========================================
Automated reports are now integrated into the existing MT5 monitor process.

Default schedule (editable in config.json):
  timezone: Asia/Tehran
  daily: Mon-Fri at 23:55
  weekly: Friday at 23:58

Report data source:
NEXUS uses the broker-tested reliable MT5 path:
  history_deals_get(position=POSITION_ID)

It does NOT use MT5 datetime-range history, because that path previously returned
zero rows on the target Roco setup.

Daily / weekly cards include:
- closed trades
- wins / losses / breakeven
- win rate
- net P/L
- total R
- average R
- profit factor
- best / worst trade
- partial-exit count
- current open positions
- live Balance / Equity / current drawdown
- per-symbol performance summary

Duplicate protection:
report_runs table stores each daily/weekly report key, so restarting NEXUS does
not resend the same scheduled report.

Dashboard Settings:
- SEND DAILY REPORT NOW
- SEND WEEKLY REPORT NOW
- report history table

R display:
Result cards now show R rounded to 2 decimals and explicitly state:
  1R = the trade's original risk from Entry to Stop Loss.


V0.9.13.1 — PUBLIC RESULT CARD CLEANUP
======================================
Public Telegram Partial/Final lifecycle cards no longer show realized R.
R analytics remain in Admin Dashboard, History, Daily and Weekly reports.
Signal RR remains unchanged.

Weekly report is explicitly Monday through Friday.


V0.9.14 — COMMAND CENTER
========================
Major admin-dashboard upgrade.

New modules:
- Executive Command Center with separate MT5 Account and NEXUS Strategy KPIs
- Daily P/L calendar
- Risk Center with live SL-based NEXUS open-risk estimation
- Optional Prop-Firm Mode
- MAE/MFE and exit-efficiency metrics from MT5 M1 candles
- Performance by symbol, direction, timeframe, weekday, entry hour, session, setup tag and strategy version
- Consistency, expectancy, payoff, recovery factor and streak analytics
- NEXUS Score (profitability / consistency / risk control / drawdown / execution)
- Trade Journal with grades and mistake tags
- Rule Compliance scoring
- Bootstrap What-if stress simulator
- Trade Explorer filters and CSV/Excel export
- Lifecycle timeline
- Alert Center and monitor heartbeat
- MAE/MFE backfill for old NEXUS trades
- Previous-version DB migration helper

Data integrity:
- MT5 lifecycle/history matching remains position-ID based.
- Public Partial/Final cards remain simplified (realized R hidden publicly).
- R remains available for internal analytics and reports.
- Automatic daily/weekly Telegram reports are preserved.

IMPORTANT WHEN UPGRADING:
Extract this folder next to your previous NEXUS folder. Before first RUN_NEXUS.cmd, run:
  MIGRATE_FROM_PREVIOUS.cmd
Choose the previous live database. The helper backs up the packaged DB and runs the current schema migration.


V0.9.15 — BILINGUAL ADMIN
===========================
The Streamlit admin dashboard now supports Persian and English.

- Language selector is displayed at the top of the dashboard.
- Persian mode uses RTL layout and Persian UI labels.
- English mode uses LTR layout and English UI labels.
- The selected language is saved to config.json under dashboard.language.
- The selected language survives NEXUS / Streamlit restarts.
- Internal MT5 values, database enums, signal IDs and symbols are not mutated.
- Timeframe choices are displayed in English in English mode while the stored
  timeframe value remains parser/card compatible.
- Dataframe headers and common result/status values are localized for Persian.
- Telegram signal/result cards are intentionally unchanged; dashboard language
  is independent from channel-card language.

Default dashboard language: Persian (fa).


V0.9.16 — RISK INTELLIGENCE ENGINE
==================================
New execution-protection layer:
- Pre-Trade Safety Check enforced inside the Direct MT5 executor
- Adaptive Risk Throttle after consecutive losses
  * 2 losses -> 0.75x requested risk
  * 3 losses -> 0.50x
  * 4 losses -> 0.25x
- Kill Switch
  * manual persistent switch from SYSTEM
  * automatic at 5 consecutive losses by default
  * Prop-Firm daily/max-loss limits are enforced when Prop-Firm Mode is enabled
- Maximum open-position slots and total-open-risk limit are enforced
- Telegram publishing continues even when MT5 is blocked; blocked signals are marked BLOCKED and are not lifecycle-monitored

Trade intelligence:
- Local AI-style Trade Review (LOCAL_EXPERT_V1)
- No external API or AI key required
- Reviews MAE/MFE, exit efficiency, planned RR, realized result and risk throttle
- Auto Journal snapshot generated for each final MT5 close
- Backfill button rebuilds reviews/journal for historical NEXUS final trades

Safety philosophy:
- Risk Intelligence only reduces requested risk; it never increases it.
- Fixed-lot requests are reduced by the same throttle multiplier.
- If throttling would put lot below broker minimum, MT5 execution is blocked rather than rounded upward.
- Manual Kill Switch blocks new MT5 orders only. Telegram publishing remains active.

Migration:
Run MIGRATE_FROM_PREVIOUS.cmd once before first RUN_NEXUS.cmd to import the v0.9.15 database.
The v0.9.16 schema migration adds new columns/tables automatically.


V0.9.17 — WORKFLOW MANAGER
==========================
A new bilingual Workflow Manager provides an end-to-end operational audit trail
for every NEXUS signal.

Persistent stages:
  SIGNAL_CREATED
  TELEGRAM_SENT
  PRE_TRADE_GATE
  MT5_ORDER
  POSITION_OPEN
  PARTIAL_CLOSE (optional, repeatable)
  FINAL_CLOSE
  RESULT_SENT
  REPORT_INCLUDED (daily/weekly)

Every transition is stored in storage/NEXUS_DATA.db -> workflow_audit with an
idempotent event_key. The 2-second monitor can therefore record live state
without creating duplicates.

The Workflow tab includes:
- fleet-level workflow registry
- GREEN / YELLOW / RED health
- current stage and elapsed time
- stall detection for orders waiting too long
- stage board for one NX-ID
- complete chronological audit timeline
- Telegram message id, MT5 ticket and MT5 position id traceability
- Partial/Final/Report status
- raw diagnostics
- safe BACKFILL / REPAIR button for older migrated trades

BACKFILL_WORKFLOW.cmd
Reconstructs missing audit events from signals, MT5 lifecycle events, trade
metrics and report_runs. Safe to run more than once.

CHECK_WORKFLOW.cmd
Prints a compact workflow health/status list for troubleshooting.

Important invariants preserved:
- Position-ID based MT5 history remains the canonical close/history path.
- Public Partial/Final Telegram cards still do not display realized R.
- Daily/Weekly reports remain automatic.
- Risk Intelligence / Throttle / Kill Switch / Auto Journal remain enabled.
- Persian/English admin UI remains available.


V0.9.18 — STRATEGY BUILDER + COMPLETE TRADE ARCHIVE
====================================================
New Strategy Builder:
- Create unlimited personal setup names and descriptions.
- Build a separate weighted checklist for every setup.
- Mark checklist items as Required.
- During signal creation, select the setup and tick the exact checklist.
- Live Setup Score (0-100) + grade A+/A/B/C/D.
- Historical checklist snapshot is immutable per signal, even if the template is edited later.
- Optional setup rationale / notes saved with the signal score.

Setup Evolution analytics:
- Performance by setup.
- Performance by score bands (<60, 60-69, 70-79, 80-89, 90-100).
- Per-checklist-item comparison: checked vs unchecked Win Rate / Avg R.
- Avg-R edge helps identify which conditions are associated with stronger historical results.
- Analytics are descriptive, not predictive.

Complete Trade Archive:
- Every NX-ID has one permanent case file.
- Click recent NX-ID buttons or select any historical signal.
- Before-analysis image = original TradingView signal chart.
- After-analysis image = automatic MT5 result chart when available.
- Upload unlimited additional BEFORE / AFTER / EXECUTION / OTHER images.
- Full signal, risk, MT5 order/ticket/position, lifecycle, partial/final events.
- Setup checklist snapshot and setup rationale.
- MAE/MFE, exit efficiency, local trade review, admin note and workflow timeline.

Migration improvement:
MIGRATE_FROM_PREVIOUS.cmd now copies BOTH the live SQLite database and the
previous uploads folder, preserving historical signal/result images for Archive.

Public Telegram cards are unchanged. Realized R remains hidden from public
Partial/Final cards while internal analytics retain it.


V0.9.18.1 — TIMEZONE HOTFIX
===========================
Fixes dashboard refresh crash:
  TypeError: Cannot convert tz-naive timestamps, use tz_localize to localize

Cause:
Older/migrated SQLite timestamps may be timezone-naive while newer records can
contain explicit timezone offsets. The analytics layer now normalizes both
formats to UTC before converting them to the configured dashboard timezone.

This hotfix does not change:
- Strategy Builder / setup checklists
- Trade Archive / image archive
- MT5 execution
- position_id based MT5 history
- Telegram publishing
- Risk Intelligence
- Workflow Manager
- Daily/Weekly reports

V0.9.19 — TRAILING PROFILES & CLIENT POLICIES
===============================================

Core trailing engine (admin/local MT5):
- LADDER mode
  * TP1 can close a configurable percentage of INITIAL or REMAINING volume.
  * Default: TP1 closes 50% of initial volume and moves SL to Entry / Breakeven.
  * TP2 moves SL to TP1.
  * TP3 moves SL to TP2.
  * The sequence continues for all configured intermediate targets.
  * Optional hard final target is placed as the broker TP. This prevents TP1 from
    accidentally closing the whole position and keeps a final broker-side exit.
- R_BASED mode
  * Define arbitrary trigger_r / lock_r stages and optional partial percentages.
- FIXED_R mode
  * Starts after an activation R and continuously ratchets SL by a fixed R distance.
- ATR mode
  * Starts after an activation R and trails behind current price using ATR.
- MANUAL mode
  * No automatic management; original broker SL/TP are preserved.

Safety / idempotency:
- Every partial close and SL move receives a unique action key in trailing_actions.
- A successful TP1 partial close is never repeated on later 2-second monitor polls.
- If the partial close succeeds but the SL modification temporarily fails, the
  engine retries only the missing SL action and does not close another 50%.
- SL is never intentionally moved backward to increase risk.
- Existing NEXUS position-id lifecycle history remains authoritative.

Signal entry:
- Select a Trailing Profile while publishing a signal.
- LADDER profiles expose 2–8 TP levels (profile limit applies).
- The parser-compatible first line remains "🎯 هدف:"; TP2/TP3/... are additive.
- For the default ladder profile, the MT5 order uses the LAST target as broker TP,
  not TP1. TP1 is managed by the local NEXUS trailing engine.

Trade Archive / Workflow:
- Every trade file shows its trailing plan and full trailing action audit.
- Workflow receives TRAILING_MANAGEMENT audit events.
- Normal partial/final Telegram result flow continues to use MT5 deal history.

AutoTrade Client Policies:
- Admin can create AutoTrade client records with subscription expiry.
- Admin can enable/disable trailing for each client.
- Admin assigns the default trailing profile.
- Admin decides whether the customer may customize trailing.
- Admin controls the list of profiles available to that customer.
- Expired clients are automatically rejected by client_trailing_access().

IMPORTANT — REMOTE CLIENT EXECUTION
-----------------------------------
The policy/database layer is implemented in v0.9.19, but there is not yet a
central Signal Server or a customer AutoTrade Client agent in the current NEXUS
package. Therefore the admin/local MT5 trailing engine is executable now, while
remote customer-PC execution will consume these already-defined policies in the
future AutoTrade Client / Signal Server phase. No claim of remote control is made
until that client/server transport exists.

RESULT CHART V2
===============
The MT5 data-generated result image was redesigned:
- Entry = cyan
- TP1/TP2/... = green
- SL = red/pink
- Exit = amber
- High-contrast right-side price badges
- Entry/Exit markers
- Multi-TP ladder levels
- P/L header with readable status
- R was removed from the public result image header; R analytics remain in Admin.
- Historical closed trades prefer copy_rates_range around the actual event time,
  avoiding unrelated recent candles when possible.

DIAGNOSTICS
===========
Run:
  CHECK_TRAILING.cmd

It prints profiles, live signal plans, recent trailing actions, client policies,
and subscription/access status.
