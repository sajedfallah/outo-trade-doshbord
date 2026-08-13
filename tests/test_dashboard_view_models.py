from Dashboard.view_models import account_history_frame, checklist_snapshot_rows, trade_menu_rows


def test_account_history_is_oldest_to_newest():
    frame = account_history_frame([
        {"snapshot_time": "2026-01-02T00:00:00+00:00", "balance": 110, "equity": 108},
        {"snapshot_time": "2026-01-01T00:00:00+00:00", "balance": 100, "equity": 101},
    ])
    assert frame["بالانس"].tolist() == [100, 110]


def test_trade_menu_uses_final_event_without_losing_open_trades():
    rows = trade_menu_rows(
        [{"signal_id": "NX-2", "symbol": "XAUUSD", "direction": "BUY"},
         {"signal_id": "NX-1", "symbol": "EURUSD", "direction": "SELL"}],
        [{"signal_id": "NX-1", "event_type": "FINAL_CLOSE", "result_type": "TP", "total_profit": 12}],
    )
    assert rows[0]["result"] == "OPEN"
    assert rows[1]["result"] == "TP"
    assert rows[1]["profit"] == 12


def test_checklist_snapshot_is_human_readable():
    rows = checklist_snapshot_rows([{"text": "Trend", "checked": True, "weight": 2, "required": True}])
    assert rows == [{"وضعیت": "✅", "شرط چک‌لیست": "Trend", "امتیاز": 2.0, "اجباری": "بله"}]
