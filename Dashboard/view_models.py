"""Small, side-effect free view models for the streamlined Admin dashboard."""

from __future__ import annotations

import pandas as pd


def account_history_frame(snapshots):
    rows = list(reversed(snapshots or []))
    if not rows:
        return pd.DataFrame(columns=["زمان", "بالانس", "اکوئیتی"])
    frame = pd.DataFrame(rows)
    frame["زمان"] = pd.to_datetime(frame.get("snapshot_time"), errors="coerce", utc=True)
    frame["بالانس"] = pd.to_numeric(frame.get("balance"), errors="coerce")
    frame["اکوئیتی"] = pd.to_numeric(frame.get("equity"), errors="coerce")
    return frame[["زمان", "بالانس", "اکوئیتی"]].dropna(subset=["زمان"])


def trade_menu_rows(signals, events):
    final_by_signal = {}
    for event in events or []:
        if str(event.get("event_type") or "").upper() == "FINAL_CLOSE":
            final_by_signal.setdefault(str(event.get("signal_id")), event)
    rows = []
    for signal in signals or []:
        signal_id = str(signal.get("signal_id") or "")
        final = final_by_signal.get(signal_id, {})
        result = str(final.get("result_type") or "OPEN").upper()
        rows.append({
            "signal_id": signal_id,
            "symbol": str(signal.get("symbol") or "—"),
            "direction": str(signal.get("direction") or "—").upper(),
            "setup": str(signal.get("setup_tag") or "—"),
            "result": result,
            "profit": float(final.get("total_profit") or 0),
            "created_at": signal.get("created_at"),
        })
    return rows


def checklist_snapshot_rows(raw_items):
    return [{
        "وضعیت": "✅" if item.get("checked") else "❌",
        "شرط چک‌لیست": item.get("text") or "—",
        "امتیاز": float(item.get("weight") or 0),
        "اجباری": "بله" if item.get("required") else "خیر",
    } for item in (raw_items or [])]
