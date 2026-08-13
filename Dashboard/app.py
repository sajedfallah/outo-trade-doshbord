"""Streamlined NEXUS Admin UI.

Only the selected page is evaluated.  The previous full command centre remains
available under Advanced tools for operators who need low-level diagnostics.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_loader import load_config
from Dashboard.cards import signal_card, valid_geometry, rr_value
from Dashboard.analytics import performance
from Dashboard.trade_archive import collect_trade_images, safe_filename
from Dashboard.view_models import account_history_frame, checklist_snapshot_rows, trade_menu_rows, validate_checklist_item_input
from monitor.workflow import audit
from monitor.window_capture import capture_current_chart
from mt5trade.service import execute_persisted_signal
from storage.repo import (
    DuplicateSignalError, add_archive_file, add_setup_item, create_setup,
    create_signal_durable, ensure_default_trailing_profiles, ensure_setup_names,
    get_signal, get_signal_setup_score, get_signal_trailing_plan, get_state,
    list_account_snapshots, list_archive_files, list_results, list_setup_items,
    list_setups, list_signals, list_trade_events, list_trailing_actions,
    list_trailing_profiles, outbox_status, schema_version, update_setup,
    update_setup_item,
)
from strategy.setup_engine import score_checklist
from telegram.outbox import deliver_item
from trailing.engine import build_signal_plan, validate_targets


CFG = load_config()
SIGNAL_DIR = ROOT / "uploads" / "signals"
ARCHIVE_DIR = ROOT / "uploads" / "archive"
for folder in (SIGNAL_DIR, ARCHIVE_DIR):
    folder.mkdir(parents=True, exist_ok=True)
ensure_setup_names(CFG.get("analytics", {}).get("setup_tags", ["SCALP"]))
ensure_default_trailing_profiles()

st.set_page_config(page_title="NEXUS v0.9.20", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
.stApp{background:radial-gradient(circle at 84% 4%,#192342 0,#0a101d 30%,#080d17 75%);direction:rtl}.block-container{max-width:1540px;padding:1.25rem 1.5rem 2.4rem}
[data-testid="stSidebar"]{border-left:1px solid #202c43;background:linear-gradient(180deg,#0c1220,#080d17)}
[data-testid="stMetric"]{background:linear-gradient(145deg,rgba(31,42,67,.92),rgba(15,23,38,.92));border:1px solid rgba(126,145,184,.19);padding:15px 16px;border-radius:18px;box-shadow:0 11px 30px rgba(0,0,0,.17)}
.nx-head{padding:21px 24px;border:1px solid rgba(126,145,184,.20);border-radius:23px;background:linear-gradient(130deg,rgba(31,44,73,.94),rgba(13,20,35,.80));box-shadow:0 16px 42px rgba(0,0,0,.19);margin-bottom:18px}.nx-head h2{margin:0}.nx-head small{opacity:.68}
.nx-card{padding:15px 16px;border:1px solid rgba(126,145,184,.17);border-radius:17px;background:linear-gradient(145deg,rgba(24,34,56,.88),rgba(12,18,31,.88));margin-bottom:9px;box-shadow:0 10px 22px rgba(0,0,0,.12)}
.nx-panel{padding:18px;border:1px solid rgba(126,145,184,.17);border-radius:20px;background:rgba(13,20,34,.72);box-shadow:0 12px 30px rgba(0,0,0,.13)}.muted{opacity:.68}.ltr{direction:ltr;text-align:left}.stCodeBlock,code,pre{direction:ltr;text-align:left}
.donut{width:142px;height:142px;border-radius:50%;display:grid;place-items:center;margin:8px auto;background:conic-gradient(#44d59b calc(var(--win)*1%),#f05b72 0 100%)}.donut::after{content:'';width:104px;height:104px;border-radius:50%;background:#101827;box-shadow:inset 0 0 20px rgba(0,0,0,.3)}.donut-label{position:relative;top:-95px;text-align:center;font-weight:750;font-size:20px;direction:ltr;height:0}.donut-sub{position:relative;top:-65px;text-align:center;color:#93a4c2;font-size:11px;height:0}
</style>
""", unsafe_allow_html=True)


def _fmt(value, digits=2):
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


with st.sidebar:
    st.markdown("## ⚡ NEXUS")
    st.caption("پنل مدیریت ساده و سریع")
    page = st.radio(
        "منوی اصلی",
        ["خانه", "صدور سیگنال", "ستاپ‌ها و چک‌لیست", "بایگانی معاملات", "ابزارهای پیشرفته"],
        label_visibility="collapsed",
    )
    st.divider()
    delivery = outbox_status()
    heartbeat = get_state("monitor_heartbeat")
    monitor_live = False
    if heartbeat:
        try:
            updated = datetime.fromisoformat(str(heartbeat["updated_at"]))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            monitor_live = (datetime.now(timezone.utc) - updated).total_seconds() < 30
        except Exception:
            pass
    st.caption(f"مانیتور: {'فعال 🟢' if monitor_live else 'غیرفعال 🔴'}")
    st.caption(f"صف ارسال: {delivery.get('pending', 0)}")
    st.caption(f"پایگاه داده: v{schema_version()}")

st.markdown(f'<div class="nx-head"><h2>{page}</h2><small>NEXUS v0.9.20 · Stabilization & Reliability</small></div>', unsafe_allow_html=True)


def render_home():
    signals = list_signals()
    events = list_trade_events()
    snapshots = list_account_snapshots(2000)
    snap = snapshots[0] if snapshots else {}
    finals = [e for e in events if str(e.get("event_type") or "").upper() == "FINAL_CLOSE"]
    net_profit = sum(float(e.get("total_profit") or 0) for e in finals)
    wins = sum(float(e.get("total_profit") or 0) > 0 for e in finals)
    win_rate = wins / len(finals) * 100 if finals else 0
    perf = performance(signals, events, cfg=CFG)
    balance = float(snap.get("balance") or 0)
    equity = float(snap.get("equity") or 0)
    drawdown = ((balance - equity) / balance * 100) if balance > 0 and equity < balance else 0

    if not monitor_live:
        st.warning("مانیتور MT5 فعال نیست؛ اطلاعات حساب از آخرین Snapshot ذخیره‌شده نمایش داده می‌شود.")
    cards = st.columns(6)
    cards[0].metric("بالانس", _fmt(balance))
    cards[1].metric("اکوئیتی", _fmt(equity), f"{float(snap.get('floating_pl') or 0):+,.2f}")
    cards[2].metric("معاملات باز", int(snap.get("open_positions") or 0))
    cards[3].metric("سود خالص NEXUS", f"{net_profit:+,.2f}")
    cards[4].metric("نرخ برد", f"{win_rate:.1f}%")
    cards[5].metric("افت فعلی حساب", f"{drawdown:.2f}%")

    st.subheader("نمای حساب")
    history = account_history_frame(snapshots)
    chart_col, health_col = st.columns([2.2, .85], gap="large")
    with chart_col:
        st.markdown('<div class="nx-panel">', unsafe_allow_html=True)
        if history.empty:
            st.info("پس از ثبت Snapshotهای حساب، نمودار بالانس و اکوئیتی در این قسمت نمایش داده می‌شود.")
        else:
            st.line_chart(history.set_index("زمان")[["بالانس", "اکوئیتی"]], height=330, width="stretch")
        st.markdown('</div>', unsafe_allow_html=True)
    with health_col:
        st.markdown('<div class="nx-panel">', unsafe_allow_html=True)
        st.caption("خلاصه عملکرد NEXUS")
        st.markdown(f'<div class="donut" style="--win:{win_rate:.2f}"></div><div class="donut-label">{win_rate:.0f}%</div><div class="donut-sub">نرخ برد</div>', unsafe_allow_html=True)
        st.metric("معاملات بسته", perf["total_trades"])
        st.metric("Profit Factor", "∞" if perf["profit_factor"] == float("inf") else f"{perf['profit_factor']:.2f}")
        st.metric("میانگین R", f"{perf['avg_r']:+.2f}R")
        st.markdown('</div>', unsafe_allow_html=True)

    if not perf["daily"].empty:
        st.subheader("عملکرد روزانه")
        st.bar_chart(perf["daily"].set_index("date")[["P/L"]], height=180, width="stretch")

    left, right = st.columns([1.6, 1], gap="large")
    with left:
        st.subheader("سیگنال‌های در حال پیگیری")
        active = [s for s in signals if str(s.get("monitor_state") or "").upper() not in ("CLOSED", "CANCELED", "BLOCKED") and int(s.get("mt5_enabled") or 0)]
        if active:
            fields = ["signal_id", "symbol", "direction", "setup_tag", "mt5_status", "monitor_state"]
            st.dataframe(pd.DataFrame(active)[fields], hide_index=True, width="stretch")
        else:
            st.caption("سیگنال فعالی برای پیگیری وجود ندارد.")
    with right:
        st.subheader("آخرین فعالیت‌ها")
        for event in events[:6]:
            st.markdown(
                f'<div class="nx-card"><b>{event.get("signal_id")}</b> · {event.get("event_type") or "—"}'
                f'<br><span class="muted">{event.get("event_time") or ""}</span></div>',
                unsafe_allow_html=True,
            )
        if not events:
            st.caption("هنوز رویدادی ثبت نشده است.")


@st.fragment
def render_signal():
    active_setups = list_setups(active_only=True)
    if not active_setups:
        st.error("ابتدا در صفحه «ستاپ‌ها و چک‌لیست» حداقل یک ستاپ فعال بسازید.")
        return

    top = st.columns([1.2, 1, 1, 1])
    signal_id = top[0].text_input("شناسه سیگنال", value=_next_signal_id()).strip().upper()
    symbol = top[1].selectbox("نماد", CFG.get("symbols", ["XAUUSD"]))
    direction = top[2].radio("جهت", ["BUY", "SELL"], horizontal=True)
    timeframe = top[3].selectbox("تایم‌فریم", CFG.get("timeframes", ["H1"]))

    setup_names = [s["name"] for s in active_setups]
    selected_name = st.selectbox("نوع ستاپ", setup_names, key="signal_setup_selector")
    setup = next(s for s in active_setups if s["name"] == selected_name)
    if setup.get("description"):
        st.caption(setup["description"])

    items = list_setup_items(setup["id"], active_only=True)
    answers = {}
    st.subheader("چک‌لیست همین ستاپ")
    if not items:
        st.warning("برای این ستاپ هنوز چک‌لیستی تعریف نشده است.")
    else:
        cols = st.columns(2)
        for index, item in enumerate(items):
            required = " · اجباری ⭐" if item.get("required") else ""
            label = f"{item['item_text']} · {float(item.get('weight') or 0):g} امتیاز{required}"
            answers[str(item["id"])] = cols[index % 2].checkbox(label, key=f"check_{setup['id']}_{item['id']}")
    rationale = st.text_area("دلیل انتخاب ستاپ / یادداشت", height=75)
    score = score_checklist(setup, items, answers, rationale, CFG.get("strategy_builder", {}).get("score_grades"))
    score_cols = st.columns(4)
    score_cols[0].metric("امتیاز", "—" if score["score_percent"] is None else f"{score['score_percent']:.0f}%")
    score_cols[1].metric("رتبه", score["grade"])
    score_cols[2].metric("امتیاز کسب‌شده", f"{score['score_points']:g} از {score['max_points']:g}")
    score_cols[3].metric("موارد اجباری ناقص", score["required_missed"])

    p1, p2, p3 = st.columns(3)
    entry = p1.number_input("ورود", value=0.0, format="%.8f")
    stop_loss = p2.number_input("حد ضرر", value=0.0, format="%.8f")
    take_profit = p3.number_input("حد سود", value=0.0, format="%.8f")
    tp_levels = [take_profit]
    profiles = list_trailing_profiles(active_only=True)
    default_profile = CFG.get("trailing", {}).get("default_profile_name")
    profile_names = [p["name"] for p in profiles]
    profile_index = profile_names.index(default_profile) if default_profile in profile_names else 0
    profile = profiles[profile_index] if profiles else {"id": None, "name": "Manual", "mode": "MANUAL", "params": {}}
    risk = float(CFG["risk_management"]["default_risk_percent"])
    lot = None
    trailing_enabled = bool(CFG.get("trailing", {}).get("default_enabled", True))
    with st.expander("تنظیمات پیشرفته حجم و مدیریت معامله"):
        sizing = st.radio("روش تعیین حجم", ["ریسک درصدی", "حجم ثابت"], horizontal=True)
        if sizing == "ریسک درصدی":
            risk = st.number_input("ریسک (%)", min_value=0.01, max_value=10.0, value=risk, step=0.1)
        else:
            risk = None
            lot = st.number_input("حجم ثابت", min_value=0.001, value=0.01, step=0.01, format="%.3f")
        if profiles:
            trailing_enabled = st.checkbox("فعال‌سازی مدیریت Trailing", value=trailing_enabled)
            selected_profile = st.selectbox("پروفایل Trailing", profile_names, index=profile_index)
            profile = next(p for p in profiles if p["name"] == selected_profile)
            if trailing_enabled and str(profile.get("mode") or "").upper() == "LADDER":
                target_count = st.number_input("تعداد اهداف", min_value=1, max_value=8, value=3, step=1)
                for target_number in range(2, int(target_count) + 1):
                    tp_levels.append(st.number_input(f"TP{target_number}", value=0.0, format="%.8f", key=f"compact_tp_{target_number}"))
    st.info("تصویر سیگنال هنگام صدور، مستقیماً و بدون طراحی مجدد از پنل چارتِ بازِ MetaTrader 5 گرفته می‌شود. پیش از ارسال، همان چارت را روی نماد و تایم‌فریم این سیگنال قرار دهید.")
    default_mt5 = bool(CFG.get("execution", {}).get("execute_by_default", True)) and not bool(CFG.get("execution", {}).get("telegram_only_default", False))
    execution = st.radio("نحوه ارسال", ["تلگرام + اجرای MT5", "تلگرام فقط"], index=0 if default_mt5 else 1, horizontal=True)

    complete = entry > 0 and stop_loss > 0 and bool(tp_levels) and all(float(target) > 0 for target in tp_levels)
    targets_ok, target_reason = validate_targets(direction, entry, tp_levels) if complete else (False, "INCOMPLETE")
    valid = complete and targets_ok and valid_geometry(direction, entry, take_profit, stop_loss)
    rr = rr_value(entry, take_profit, stop_loss) if complete else 0
    if complete and not valid:
        st.error(f"چیدمان قیمت‌ها معتبر نیست: {target_reason}")
    checklist_allowed = not (
        CFG.get("strategy_builder", {}).get("require_checklist_to_publish", False)
        and score.get("required_missed", 0) > 0
    )
    if not checklist_allowed:
        st.warning("تمام موارد اجباری چک‌لیست باید تیک بخورند.")

    if st.button("ارسال سیگنال", type="primary", width="stretch",
                 disabled=not (valid and signal_id.startswith("NX-") and checklist_allowed)):
        try:
            path = SIGNAL_DIR / f"{signal_id}.png"
            screenshot = capture_current_chart(path, CFG)
            if not screenshot.get("ok"):
                st.error("تصویر خام چارت MT5 گرفته نشد؛ چارت MetaTrader را باز نگه دارید و دوباره تلاش کنید. خطا: " + str(screenshot.get("error") or "نامشخص"))
                return
            mt5_enabled = execution == "تلگرام + اجرای MT5"
            trailing = build_signal_plan(signal_id, profile, tp_levels, enabled=bool(trailing_enabled and mt5_enabled), client_id="ADMIN")
            card = signal_card(signal_id, symbol, direction, timeframe, entry, take_profit, stop_loss, risk, lot, targets=tp_levels)
            payload = {
                "signal_id": signal_id, "symbol": symbol, "direction": direction, "timeframe": timeframe,
                "entry": entry, "tp": take_profit, "sl": stop_loss, "risk_percent": risk, "lot": lot,
                "rr": rr, "setup_image_path": str(path), "mt5_enabled": mt5_enabled,
                "mt5_status": "NOT_REQUESTED", "setup_tag": setup["name"],
                "strategy_version": CFG.get("analytics", {}).get("default_strategy_version", "NEXUS-v1"),
                "requested_risk_percent": risk,
            }
            created = create_signal_durable(payload, score, trailing, {"image_path": str(path), "text": card})
            audit(signal_id, "SIGNAL_CREATED", "DONE", f"{signal_id}:SIGNAL_CREATED", source="DASHBOARD", detail="Signal registered")
            delivery_result = deliver_item(created["outbox"])
            if not delivery_result.get("sent"):
                st.warning("سیگنال ذخیره شد و در صف امن تلگرام قرار گرفت. تا تأیید ارسال، سفارشی به MT5 فرستاده نمی‌شود.")
            else:
                st.success(f"سیگنال با موفقیت در تلگرام ارسال شد · message_id={delivery_result.get('message_id')}")
                if mt5_enabled:
                    with st.spinner("در حال ارسال سفارش به MT5…"):
                        result = execute_persisted_signal(signal_id, CFG)
                    if result.get("success"):
                        st.success(f"سفارش MT5 ثبت شد · ticket={result.get('ticket')}")
                    else:
                        st.error(f"ارسال MT5 انجام نشد: {result.get('error') or 'خطای نامشخص'}")
        except DuplicateSignalError:
            st.error("این شناسه قبلاً ثبت شده است؛ شناسه جدید انتخاب کنید.")
        except Exception as exc:
            st.error(f"صدور سیگنال کامل نشد: {exc}")


def _next_signal_id():
    from storage.repo import next_signal_id
    return next_signal_id()


@st.fragment
def render_setups():
    st.caption("هر ستاپ چک‌لیست اختصاصی دارد. پاسخ‌های زمان صدور سیگنال به‌صورت Snapshot ذخیره و مبنای گزارش‌های آینده می‌شوند.")
    with st.expander("ساخت ستاپ جدید", expanded=not bool(list_setups())):
        with st.form("new_setup", clear_on_submit=True):
            name = st.text_input("نام ستاپ")
            description = st.text_area("توضیح کوتاه")
            if st.form_submit_button("ساخت ستاپ", type="primary", width="stretch"):
                try:
                    create_setup(name, description)
                    st.success("ستاپ ساخته شد.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    setups = list_setups(active_only=False)
    if not setups:
        return
    selected_name = st.selectbox("انتخاب ستاپ برای مدیریت", [s["name"] for s in setups])
    setup = next(s for s in setups if s["name"] == selected_name)
    with st.form(f"setup_settings_{setup['id']}"):
        edit_name = st.text_input("نام", value=setup["name"])
        edit_description = st.text_area("توضیحات", value=setup.get("description") or "")
        active = st.checkbox("فعال و قابل انتخاب در صدور سیگنال", value=bool(setup.get("active")))
        if st.form_submit_button("ذخیره تنظیمات"):
            update_setup(setup["id"], edit_name, edit_description, active)
            st.success("تغییرات ذخیره شد.")
            st.rerun()

    st.subheader("آیتم‌های چک‌لیست")
    items = list_setup_items(setup["id"], active_only=False)
    for item in items:
        with st.expander(f"{'✅' if item.get('active') else '○'} {item['item_text']}"):
            with st.form(f"item_{item['id']}"):
                text = st.text_input("متن شرط", value=item["item_text"])
                c1, c2 = st.columns(2)
                weight = c1.number_input("امتیاز", min_value=0.0, value=float(item.get("weight") or 0), step=0.5)
                required = c2.checkbox("اجباری", value=bool(item.get("required")))
                item_active = st.checkbox("فعال", value=bool(item.get("active")))
                if st.form_submit_button("ذخیره آیتم"):
                    update_setup_item(item["id"], text, weight, required, item_active)
                    st.success("آیتم ذخیره شد.")
                    st.rerun()
    with st.form(f"add_item_{setup['id']}", clear_on_submit=True):
        st.markdown("**افزودن شرط جدید**")
        text = st.text_input("متن شرط")
        c1, c2 = st.columns(2)
        weight = c1.number_input("امتیاز شرط", min_value=0.0, value=1.0, step=0.5)
        required = c2.checkbox("شرط اجباری")
        if st.form_submit_button("افزودن به چک‌لیست", type="primary", width="stretch"):
            valid_item, validation_error = validate_checklist_item_input(text, weight)
            if not valid_item:
                st.error(validation_error)
            else:
                add_setup_item(setup["id"], text, weight, required)
                st.success("شرط به چک‌لیست اضافه شد.")
                st.rerun()


@st.fragment
def render_archive():
    signals = list_signals()
    events = list_trade_events()
    rows = trade_menu_rows(signals, events)
    selected = st.session_state.get("archive_selected")
    if selected and not any(row["signal_id"] == selected for row in rows):
        selected = None
        st.session_state.pop("archive_selected", None)

    if not selected:
        st.caption("برای مشاهده پرونده کامل، روی یکی از معاملات کلیک کنید.")
        query = st.text_input("جست‌وجو با شناسه، نماد یا ستاپ", placeholder="مثلاً NX-100 یا XAUUSD")
        visible = [r for r in rows if not query or query.lower() in " ".join(map(str, r.values())).lower()]
        if not visible:
            st.info("معامله‌ای برای نمایش وجود ندارد.")
        for row in visible:
            result_icon = {"TP": "🟢", "SL": "🔴", "OPEN": "🟡", "BREAKEVEN": "⚪"}.get(row["result"], "🔹")
            label = f"{result_icon} {row['signal_id']}  |  {row['symbol']}  |  {row['direction']}  |  {row['setup']}  |  {row['result']}"
            if st.button(label, key=f"trade_menu_{row['signal_id']}", width="stretch"):
                st.session_state["archive_selected"] = row["signal_id"]
                st.rerun()
        return

    if st.button("بازگشت به فهرست معاملات", icon="↩️"):
        st.session_state.pop("archive_selected", None)
        st.rerun()
    signal = get_signal(selected) or {}
    signal_events = list_trade_events(selected)
    score = get_signal_setup_score(selected) or {}
    final = next((e for e in signal_events if str(e.get("event_type") or "").upper() == "FINAL_CLOSE"), {})
    cards = st.columns(6)
    cards[0].metric("شناسه", selected)
    cards[1].metric("نماد", signal.get("symbol") or "—")
    cards[2].metric("جهت", signal.get("direction") or "—")
    cards[3].metric("ستاپ", score.get("setup_name") or signal.get("setup_tag") or "—")
    cards[4].metric("امتیاز", "—" if score.get("score_percent") is None else f"{float(score['score_percent']):.0f}% · {score.get('grade')}")
    cards[5].metric("نتیجه", final.get("result_type") or "OPEN", f"{float(final.get('total_profit') or 0):+,.2f}")

    archive_files = list_archive_files(selected)
    manual_results = [r for r in list_results() if r.get("signal_id") == selected]
    images = collect_trade_images(signal, signal_events, manual_results, archive_files)
    st.subheader("تصاویر تحلیل و معامله")
    if images:
        columns = st.columns(min(3, len(images)))
        for index, item in enumerate(images):
            with columns[index % len(columns)]:
                st.image(item["path"], width="stretch")
                st.caption(f"{item['category']} · {item.get('caption') or ''}")
    else:
        st.caption("تصویری برای این معامله ذخیره نشده است.")

    with st.expander("افزودن تصویر به پرونده"):
        category = st.selectbox("نوع تصویر", ["BEFORE_ANALYSIS", "AFTER_ANALYSIS", "EXECUTION", "OTHER"])
        caption = st.text_input("توضیح تصویر")
        uploads = st.file_uploader("انتخاب تصاویر", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key=f"archive_{selected}")
        if st.button("ذخیره تصاویر", disabled=not uploads):
            folder = ARCHIVE_DIR / selected
            folder.mkdir(parents=True, exist_ok=True)
            for upload in uploads:
                filename = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}_{safe_filename(upload.name)}"
                path = folder / filename
                path.write_bytes(upload.getbuffer())
                add_archive_file(selected, category, str(path), caption, "ADMIN_UPLOAD")
            st.success("تصاویر ذخیره شدند.")
            st.rerun()

    st.subheader("چک‌لیست ثبت‌شده در زمان صدور")
    try:
        snapshot = json.loads(score.get("checklist_json") or "[]")
    except Exception:
        snapshot = []
    if snapshot:
        st.dataframe(pd.DataFrame(checklist_snapshot_rows(snapshot)), hide_index=True, width="stretch")
    else:
        st.caption("برای این معامله Snapshot چک‌لیست وجود ندارد.")
    if score.get("rationale"):
        st.info(f"یادداشت ستاپ: {score['rationale']}")

    with st.expander("اطلاعات کامل معامله"):
        fields = ["entry", "tp", "sl", "rr", "risk_percent", "mt5_status", "mt5_ticket", "mt5_position_id", "monitor_state", "created_at", "closed_at"]
        st.dataframe(pd.DataFrame([{key: signal.get(key) for key in fields}]), hide_index=True, width="stretch")
    with st.expander("رویدادهای معامله"):
        if signal_events:
            st.dataframe(pd.DataFrame(signal_events), hide_index=True, width="stretch")
        else:
            st.caption("رویدادی ثبت نشده است.")
    with st.expander("مدیریت Trailing"):
        plan = get_signal_trailing_plan(selected)
        actions = list_trailing_actions(selected, 200)
        if plan:
            st.json(plan)
        if actions:
            st.dataframe(pd.DataFrame(actions), hide_index=True, width="stretch")
        if not plan and not actions:
            st.caption("اطلاعات Trailing وجود ندارد.")


if page == "خانه":
    render_home()
elif page == "صدور سیگنال":
    render_signal()
elif page == "ستاپ‌ها و چک‌لیست":
    render_setups()
elif page == "بایگانی معاملات":
    render_archive()
else:
    st.info("این بخش فقط برای تنظیمات، گزارش‌ها و بررسی‌های تخصصی است. بارگذاری آن ممکن است چند ثانیه طول بکشد.")
    from Dashboard import advanced_app  # noqa: F401,E402
