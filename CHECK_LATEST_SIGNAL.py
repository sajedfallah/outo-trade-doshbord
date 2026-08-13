
import sqlite3
from pathlib import Path

db=Path(__file__).resolve().parent/"storage"/"NEXUS_DATA.db"
c=sqlite3.connect(db)
row=c.execute("""
SELECT signal_id,mt5_enabled,mt5_status,mt5_ticket,mt5_position_id,
       mt5_action,mt5_error,monitor_state
FROM signals
ORDER BY created_at DESC
LIMIT 1
""").fetchone()

if not row:
    print("No signal found.")
else:
    labels=[
        "signal_id","mt5_enabled","mt5_status","mt5_ticket","mt5_position_id",
        "mt5_action","mt5_error","monitor_state"
    ]
    print(dict(zip(labels,row)))
