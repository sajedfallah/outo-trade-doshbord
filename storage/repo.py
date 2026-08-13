from pathlib import Path
import sqlite3,re,json,os
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta

DB=Path(os.getenv("NEXUS_DB_PATH", Path(__file__).resolve().parent/"NEXUS_DATA.db"))
SCHEMA_VERSION=2


class DuplicateSignalError(ValueError):
    pass

SIGNAL_EXTRA={
    "mt5_position_id":"TEXT",
    "initial_volume":"REAL",
    "last_volume":"REAL",
    "last_event_message_id":"INTEGER",
    "monitor_state":"TEXT DEFAULT 'WAITING'",
    "closed_at":"TEXT",
    "setup_tag":"TEXT DEFAULT 'SCALP'",
    "strategy_version":"TEXT DEFAULT 'NEXUS-v1'",
    "requested_risk_percent":"REAL",
    "effective_risk_percent":"REAL",
    "risk_throttle_multiplier":"REAL DEFAULT 1.0",
    "safety_status":"TEXT",
    "safety_reasons":"TEXT",
    "safety_snapshot_json":"TEXT",
    "publication_status":"TEXT DEFAULT 'PENDING'",
    "telegram_error":"TEXT",
    "persisted_at":"TEXT"
}

@contextmanager
def _con():
    c=sqlite3.connect(DB,timeout=10)
    c.row_factory=sqlite3.Row
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()

def _cols(c,table):
    return {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}

def migrate():
    with _con() as c:
        try:
            c.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        c.execute("""CREATE TABLE IF NOT EXISTS signals(
            signal_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            entry REAL NOT NULL,
            tp REAL NOT NULL,
            sl REAL NOT NULL,
            risk_percent REAL,
            lot REAL,
            rr REAL,
            telegram_message_id INTEGER,
            setup_image_path TEXT,
            mt5_enabled INTEGER DEFAULT 0,
            mt5_status TEXT DEFAULT 'NOT_REQUESTED',
            mt5_ticket TEXT,
            mt5_symbol TEXT,
            mt5_volume REAL,
            mt5_action TEXT,
            mt5_error TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS results(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT NOT NULL,
            result_type TEXT NOT NULL,
            exit_price REAL,
            result_r REAL,
            return_percent REAL,
            telegram_message_id INTEGER,
            result_image_path TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        sc=_cols(c,"signals")
        for name,typ in SIGNAL_EXTRA.items():
            if name not in sc:
                c.execute(f"ALTER TABLE signals ADD COLUMN {name} {typ}")

        c.execute("""CREATE TABLE IF NOT EXISTS trade_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key TEXT UNIQUE NOT NULL,
            signal_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            position_id TEXT,
            deal_ticket TEXT,
            event_time TEXT,
            closed_volume REAL,
            remaining_volume REAL,
            exit_price REAL,
            event_profit REAL,
            total_profit REAL,
            event_r REAL,
            total_r REAL,
            result_type TEXT,
            telegram_message_id INTEGER,
            reply_to_message_id INTEGER,
            screenshot_path TEXT,
            raw_reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS report_runs(
            report_key TEXT PRIMARY KEY,
            report_type TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            telegram_message_id INTEGER,
            closed_trades INTEGER DEFAULT 0,
            net_profit REAL DEFAULT 0,
            total_r REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS trade_metrics(
            signal_id TEXT PRIMARY KEY,
            position_id TEXT,
            open_time TEXT,
            close_time TEXT,
            duration_minutes REAL,
            mfe_r REAL,
            mae_r REAL,
            exit_efficiency_pct REAL,
            planned_rr REAL,
            realized_r REAL,
            net_profit REAL,
            initial_volume REAL,
            exit_price REAL,
            result_type TEXT,
            bars_used INTEGER DEFAULT 0,
            metric_status TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS trade_notes(
            signal_id TEXT PRIMARY KEY,
            grade TEXT DEFAULT 'AUTO',
            mistake_tag TEXT DEFAULT 'NONE',
            note TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS account_snapshots(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_time TEXT NOT NULL,
            balance REAL,
            equity REAL,
            margin REAL,
            free_margin REAL,
            floating_pl REAL,
            open_positions INTEGER,
            UNIQUE(snapshot_time)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS system_state(
            state_key TEXT PRIMARY KEY,
            state_value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS trade_reviews(
            signal_id TEXT PRIMARY KEY,
            review_score REAL,
            review_grade TEXT,
            flags_json TEXT,
            summary_fa TEXT,
            summary_en TEXT,
            recommendation_fa TEXT,
            recommendation_en TEXT,
            engine_version TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS auto_journal(
            signal_id TEXT PRIMARY KEY,
            symbol TEXT,
            direction TEXT,
            timeframe TEXT,
            setup_tag TEXT,
            strategy_version TEXT,
            entry REAL,
            tp REAL,
            sl REAL,
            planned_rr REAL,
            requested_risk_percent REAL,
            effective_risk_percent REAL,
            risk_throttle_multiplier REAL,
            safety_status TEXT,
            safety_reasons TEXT,
            result_type TEXT,
            total_profit REAL,
            total_r REAL,
            open_time TEXT,
            close_time TEXT,
            duration_minutes REAL,
            mfe_r REAL,
            mae_r REAL,
            exit_efficiency_pct REAL,
            review_score REAL,
            review_grade TEXT,
            review_flags TEXT,
            telegram_signal_message_id INTEGER,
            telegram_result_message_id INTEGER,
            setup_image_path TEXT,
            result_image_path TEXT,
            snapshot_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS workflow_audit(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key TEXT UNIQUE NOT NULL,
            signal_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            event_time TEXT NOT NULL,
            source TEXT,
            detail TEXT,
            telegram_message_id INTEGER,
            mt5_ticket TEXT,
            position_id TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")

        # --- v0.9.18 Strategy Builder / Trade Archive ---
        c.execute("""CREATE TABLE IF NOT EXISTS setup_definitions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE COLLATE NOCASE NOT NULL,
            description TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS setup_checklist_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setup_id INTEGER NOT NULL,
            item_text TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            required INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS signal_setup_scores(
            signal_id TEXT PRIMARY KEY,
            setup_id INTEGER,
            setup_name TEXT NOT NULL,
            score_points REAL DEFAULT 0,
            max_points REAL DEFAULT 0,
            score_percent REAL,
            grade TEXT,
            required_missed INTEGER DEFAULT 0,
            rationale TEXT,
            checklist_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS trade_archive_files(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT NOT NULL,
            category TEXT NOT NULL,
            file_path TEXT NOT NULL,
            caption TEXT,
            source TEXT DEFAULT 'ADMIN_UPLOAD',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(signal_id,file_path)
        )""")

        # --- v0.9.19 Trailing Profiles / AutoTrade Client Policies ---
        c.execute("""CREATE TABLE IF NOT EXISTS trailing_profiles(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE COLLATE NOCASE NOT NULL,
            mode TEXT NOT NULL,
            description TEXT,
            params_json TEXT NOT NULL DEFAULT '{}',
            active INTEGER DEFAULT 1,
            allow_user_override INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS signal_trailing_plans(
            signal_id TEXT PRIMARY KEY,
            profile_id INTEGER,
            profile_name TEXT,
            mode TEXT,
            enabled INTEGER DEFAULT 0,
            targets_json TEXT,
            plan_json TEXT,
            current_stage INTEGER DEFAULT 0,
            status TEXT DEFAULT 'OFF',
            last_error TEXT,
            client_id TEXT DEFAULT 'ADMIN',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS trailing_actions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_key TEXT UNIQUE NOT NULL,
            signal_id TEXT NOT NULL,
            stage INTEGER,
            action_type TEXT NOT NULL,
            trigger_price REAL,
            requested_value REAL,
            executed_value REAL,
            status TEXT NOT NULL,
            error TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS autotrade_clients(
            client_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            subscription_expires_at TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS client_trailing_policies(
            client_id TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            assigned_profile_id INTEGER,
            allow_user_customize INTEGER DEFAULT 0,
            allowed_profile_ids_json TEXT,
            overrides_json TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")

        # --- v0.9.20 Stabilization & Reliability ---
        c.execute("""CREATE TABLE IF NOT EXISTS schema_migrations(
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS outbox(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key TEXT NOT NULL UNIQUE,
            operation_type TEXT NOT NULL,
            signal_id TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            next_retry_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sent_at TEXT,
            telegram_message_id INTEGER
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_outbox_due ON outbox(status,next_retry_at,id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_trade_events_signal_type ON trade_events(signal_id,event_type,id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_workflow_signal_id ON workflow_audit(signal_id,id)")
        c.execute("INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(1,'v0.9.19 baseline')")
        c.execute("INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(2,'v0.9.20 reliability outbox')")
        c.execute(f'PRAGMA user_version={SCHEMA_VERSION}')

def next_signal_id():
    mx=0
    with _con() as c:
        rows=c.execute("SELECT signal_id FROM signals").fetchall()
    for r in rows:
        m=re.match(r"NX-(\d+)$",r["signal_id"] or "")
        if m: mx=max(mx,int(m.group(1)))
    return f"NX-{mx+1:03d}"

def save_signal(d):
    migrate()
    with _con() as c:
        try:
            c.execute("""INSERT INTO signals
        (signal_id,symbol,direction,timeframe,entry,tp,sl,risk_percent,lot,rr,
         telegram_message_id,setup_image_path,mt5_enabled,mt5_status,
         mt5_ticket,mt5_symbol,mt5_volume,mt5_action,mt5_error,
         mt5_position_id,initial_volume,last_volume,last_event_message_id,monitor_state,closed_at,
         setup_tag,strategy_version,requested_risk_percent,effective_risk_percent,
         risk_throttle_multiplier,safety_status,safety_reasons,safety_snapshot_json,
         publication_status,telegram_error,persisted_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
            d["signal_id"],d["symbol"],d["direction"],d["timeframe"],
            d["entry"],d["tp"],d["sl"],d.get("risk_percent"),d.get("lot"),d.get("rr"),
            d.get("telegram_message_id"),d.get("setup_image_path"),
            int(bool(d.get("mt5_enabled"))),d.get("mt5_status","NOT_REQUESTED"),
            d.get("mt5_ticket"),d.get("mt5_symbol"),d.get("mt5_volume"),
            d.get("mt5_action"),d.get("mt5_error"),d.get("mt5_position_id"),
            d.get("initial_volume"),d.get("last_volume"),d.get("last_event_message_id"),
            d.get("monitor_state","WAITING"),d.get("closed_at"),
            d.get("setup_tag","SCALP"),d.get("strategy_version","NEXUS-v1"),
            d.get("requested_risk_percent",d.get("risk_percent")),d.get("effective_risk_percent"),
            d.get("risk_throttle_multiplier",1.0),d.get("safety_status"),d.get("safety_reasons"),
            d.get("safety_snapshot_json"),d.get("publication_status","PENDING"),d.get("telegram_error"),
            d.get("persisted_at") or datetime.now(timezone.utc).isoformat(timespec='seconds')
        ))
        except sqlite3.IntegrityError as exc:
            if 'signals.signal_id' in str(exc) or 'UNIQUE constraint failed' in str(exc):
                raise DuplicateSignalError(f"Signal ID already exists: {d.get('signal_id')}") from exc
            raise

def update_signal(sid,**fields):
    migrate()
    allowed={
        "mt5_enabled","mt5_status","mt5_ticket","mt5_symbol","mt5_volume",
        "mt5_action","mt5_error","mt5_position_id","initial_volume","last_volume",
        "last_event_message_id","monitor_state","closed_at","setup_tag","strategy_version",
        "requested_risk_percent","effective_risk_percent","risk_throttle_multiplier",
        "safety_status","safety_reasons","safety_snapshot_json","publication_status",
        "telegram_error","telegram_message_id","setup_image_path"
    }
    items=[(k,v) for k,v in fields.items() if k in allowed]
    if not items:return
    sql=", ".join(f"{k}=?" for k,_ in items)
    vals=[v for _,v in items]+[sid]
    with _con() as c:
        c.execute(f"UPDATE signals SET {sql} WHERE signal_id=?",vals)

update_mt5=update_signal

def list_signals():
    migrate()
    with _con() as c:
        return [dict(r) for r in c.execute("SELECT * FROM signals ORDER BY created_at DESC").fetchall()]

def monitored_signals():
    migrate()
    with _con() as c:
        return [dict(r) for r in c.execute("""
            SELECT * FROM signals
            WHERE mt5_enabled=1
              AND COALESCE(monitor_state,'WAITING') NOT IN ('FINAL','CANCELED','BLOCKED')
              AND COALESCE(mt5_status,'NOT_REQUESTED') NOT IN ('NOT_REQUESTED','FAILED','BLOCKED')
            ORDER BY created_at ASC
        """).fetchall()]

def get_signal(sid):
    migrate()
    with _con() as c:
        r=c.execute("SELECT * FROM signals WHERE signal_id=?",(sid,)).fetchone()
        return dict(r) if r else None

def save_result(d):
    migrate()
    with _con() as c:
        c.execute("""INSERT INTO results
        (signal_id,result_type,exit_price,result_r,return_percent,
         telegram_message_id,result_image_path)
        VALUES(?,?,?,?,?,?,?)""",(
            d["signal_id"],d["result_type"],d["exit_price"],d["result_r"],
            d["return_percent"],d.get("telegram_message_id"),d.get("result_image_path")
        ))

def list_results():
    migrate()
    with _con() as c:
        return [dict(r) for r in c.execute("SELECT * FROM results ORDER BY created_at DESC").fetchall()]

def event_exists(event_key):
    migrate()
    with _con() as c:
        return c.execute("SELECT 1 FROM trade_events WHERE event_key=?",(event_key,)).fetchone() is not None

def insert_event(d):
    migrate()
    with _con() as c:
        cur=c.execute("""INSERT OR IGNORE INTO trade_events
        (event_key,signal_id,event_type,position_id,deal_ticket,event_time,
         closed_volume,remaining_volume,exit_price,event_profit,total_profit,
         event_r,total_r,result_type,telegram_message_id,reply_to_message_id,
         screenshot_path,raw_reason)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
            d["event_key"],d["signal_id"],d["event_type"],d.get("position_id"),
            d.get("deal_ticket"),d.get("event_time"),d.get("closed_volume"),
            d.get("remaining_volume"),d.get("exit_price"),d.get("event_profit"),
            d.get("total_profit"),d.get("event_r"),d.get("total_r"),
            d.get("result_type"),d.get("telegram_message_id"),
            d.get("reply_to_message_id"),d.get("screenshot_path"),d.get("raw_reason")
        ))
        return cur.rowcount>0

def update_event_message(event_key,message_id,screenshot_path=None):
    migrate()
    with _con() as c:
        c.execute("""UPDATE trade_events
        SET telegram_message_id=?,screenshot_path=COALESCE(?,screenshot_path)
        WHERE event_key=?""",(message_id,screenshot_path,event_key))

def list_trade_events(signal_id=None):
    migrate()
    q="SELECT * FROM trade_events"; vals=[]
    if signal_id:
        q+=" WHERE signal_id=?"; vals.append(signal_id)
    q+=" ORDER BY id DESC"
    with _con() as c:
        return [dict(r) for r in c.execute(q,vals).fetchall()]

def report_sent(report_key):
    migrate()
    with _con() as c:
        return c.execute("SELECT 1 FROM report_runs WHERE report_key=?",(report_key,)).fetchone() is not None

def save_report_run(d):
    migrate()
    with _con() as c:
        c.execute("""INSERT OR REPLACE INTO report_runs
        (report_key,report_type,period_start,period_end,telegram_message_id,
         closed_trades,net_profit,total_r)
        VALUES(?,?,?,?,?,?,?,?)""",(
            d["report_key"],d["report_type"],d["period_start"],d["period_end"],
            d.get("telegram_message_id"),d.get("closed_trades",0),
            d.get("net_profit",0),d.get("total_r",0)
        ))

def list_report_runs(limit=100):
    migrate()
    with _con() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM report_runs ORDER BY created_at DESC LIMIT ?",(int(limit),)
        ).fetchall()]

def upsert_trade_metrics(d):
    migrate()
    with _con() as c:
        c.execute("""INSERT INTO trade_metrics
        (signal_id,position_id,open_time,close_time,duration_minutes,mfe_r,mae_r,
         exit_efficiency_pct,planned_rr,realized_r,net_profit,initial_volume,
         exit_price,result_type,bars_used,metric_status,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(signal_id) DO UPDATE SET
         position_id=excluded.position_id,open_time=excluded.open_time,close_time=excluded.close_time,
         duration_minutes=excluded.duration_minutes,mfe_r=excluded.mfe_r,mae_r=excluded.mae_r,
         exit_efficiency_pct=excluded.exit_efficiency_pct,planned_rr=excluded.planned_rr,
         realized_r=excluded.realized_r,net_profit=excluded.net_profit,
         initial_volume=excluded.initial_volume,exit_price=excluded.exit_price,
         result_type=excluded.result_type,bars_used=excluded.bars_used,
         metric_status=excluded.metric_status,updated_at=CURRENT_TIMESTAMP""",(
            d["signal_id"],d.get("position_id"),d.get("open_time"),d.get("close_time"),
            d.get("duration_minutes"),d.get("mfe_r"),d.get("mae_r"),
            d.get("exit_efficiency_pct"),d.get("planned_rr"),d.get("realized_r"),
            d.get("net_profit"),d.get("initial_volume"),d.get("exit_price"),
            d.get("result_type"),d.get("bars_used",0),d.get("metric_status")
        ))

def get_trade_metrics(signal_id):
    migrate()
    with _con() as c:
        r=c.execute("SELECT * FROM trade_metrics WHERE signal_id=?",(signal_id,)).fetchone()
        return dict(r) if r else None

def list_trade_metrics():
    migrate()
    with _con() as c:
        return [dict(r) for r in c.execute("SELECT * FROM trade_metrics ORDER BY close_time DESC").fetchall()]

def upsert_trade_note(signal_id,grade='AUTO',mistake_tag='NONE',note=''):
    migrate()
    with _con() as c:
        c.execute("""INSERT INTO trade_notes(signal_id,grade,mistake_tag,note,updated_at)
        VALUES(?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(signal_id) DO UPDATE SET grade=excluded.grade,mistake_tag=excluded.mistake_tag,
        note=excluded.note,updated_at=CURRENT_TIMESTAMP""",(signal_id,grade,mistake_tag,note))

def get_trade_note(signal_id):
    migrate()
    with _con() as c:
        r=c.execute("SELECT * FROM trade_notes WHERE signal_id=?",(signal_id,)).fetchone()
        return dict(r) if r else None

def list_trade_notes():
    migrate()
    with _con() as c:
        return [dict(r) for r in c.execute("SELECT * FROM trade_notes ORDER BY updated_at DESC").fetchall()]

def save_account_snapshot_if_due(d,min_seconds=300):
    migrate()
    now=datetime.now(timezone.utc)
    with _con() as c:
        r=c.execute("SELECT snapshot_time FROM account_snapshots ORDER BY id DESC LIMIT 1").fetchone()
        if r:
            try:
                prev=datetime.fromisoformat(r['snapshot_time'])
                if prev.tzinfo is None: prev=prev.replace(tzinfo=timezone.utc)
                if (now-prev).total_seconds()<float(min_seconds):
                    return False
            except Exception:
                pass
        c.execute("""INSERT OR IGNORE INTO account_snapshots
        (snapshot_time,balance,equity,margin,free_margin,floating_pl,open_positions)
        VALUES(?,?,?,?,?,?,?)""",(
            now.isoformat(timespec='seconds'),d.get('balance'),d.get('equity'),d.get('margin'),
            d.get('free_margin'),d.get('floating_pl'),d.get('open_positions')
        ))
        return True

def list_account_snapshots(limit=5000):
    migrate()
    with _con() as c:
        rows=c.execute("SELECT * FROM account_snapshots ORDER BY id DESC LIMIT ?",(int(limit),)).fetchall()
        return [dict(r) for r in rows]

def set_state(key,value):
    migrate()
    raw=json.dumps(value,ensure_ascii=False) if not isinstance(value,str) else value
    with _con() as c:
        c.execute("""INSERT INTO system_state(state_key,state_value,updated_at)
        VALUES(?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(state_key) DO UPDATE SET state_value=excluded.state_value,updated_at=CURRENT_TIMESTAMP""",(key,raw))

def get_state(key,default=None):
    migrate()
    with _con() as c:
        r=c.execute("SELECT state_value,updated_at FROM system_state WHERE state_key=?",(key,)).fetchone()
    if not r:return default
    raw=r['state_value']
    try: val=json.loads(raw)
    except Exception: val=raw
    return {'value':val,'updated_at':r['updated_at']}

def list_states():
    migrate()
    with _con() as c:
        return [dict(r) for r in c.execute("SELECT * FROM system_state ORDER BY state_key").fetchall()]


# --- v0.9.16 Risk Intelligence / Auto Journal ---
def upsert_trade_review(d):
    migrate()
    with _con() as c:
        c.execute("""INSERT INTO trade_reviews
        (signal_id,review_score,review_grade,flags_json,summary_fa,summary_en,
         recommendation_fa,recommendation_en,engine_version,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        ON CONFLICT(signal_id) DO UPDATE SET
         review_score=excluded.review_score,review_grade=excluded.review_grade,
         flags_json=excluded.flags_json,summary_fa=excluded.summary_fa,summary_en=excluded.summary_en,
         recommendation_fa=excluded.recommendation_fa,recommendation_en=excluded.recommendation_en,
         engine_version=excluded.engine_version,updated_at=CURRENT_TIMESTAMP""",(
            d['signal_id'],d.get('review_score'),d.get('review_grade'),d.get('flags_json'),
            d.get('summary_fa'),d.get('summary_en'),d.get('recommendation_fa'),
            d.get('recommendation_en'),d.get('engine_version','LOCAL_EXPERT_V1')
        ))

def get_trade_review(signal_id):
    migrate()
    with _con() as c:
        r=c.execute("SELECT * FROM trade_reviews WHERE signal_id=?",(signal_id,)).fetchone()
        return dict(r) if r else None

def list_trade_reviews():
    migrate()
    with _con() as c:
        return [dict(r) for r in c.execute("SELECT * FROM trade_reviews ORDER BY updated_at DESC").fetchall()]

def upsert_auto_journal(d):
    migrate()
    cols=['signal_id','symbol','direction','timeframe','setup_tag','strategy_version','entry','tp','sl',
          'planned_rr','requested_risk_percent','effective_risk_percent','risk_throttle_multiplier',
          'safety_status','safety_reasons','result_type','total_profit','total_r','open_time','close_time',
          'duration_minutes','mfe_r','mae_r','exit_efficiency_pct','review_score','review_grade','review_flags',
          'telegram_signal_message_id','telegram_result_message_id','setup_image_path','result_image_path','snapshot_json']
    vals=[d.get(k) for k in cols]
    set_sql=','.join(f"{k}=excluded.{k}" for k in cols if k!='signal_id')
    q=f"""INSERT INTO auto_journal ({','.join(cols)},created_at,updated_at)
           VALUES ({','.join('?' for _ in cols)},CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
           ON CONFLICT(signal_id) DO UPDATE SET {set_sql},updated_at=CURRENT_TIMESTAMP"""
    with _con() as c:
        c.execute(q,vals)

def get_auto_journal(signal_id):
    migrate()
    with _con() as c:
        r=c.execute("SELECT * FROM auto_journal WHERE signal_id=?",(signal_id,)).fetchone()
        return dict(r) if r else None

def list_auto_journal():
    migrate()
    with _con() as c:
        return [dict(r) for r in c.execute("SELECT * FROM auto_journal ORDER BY close_time DESC, updated_at DESC").fetchall()]


def record_workflow_event(d):
    """Insert an idempotent workflow audit event.

    event_key must represent the real-world transition (ticket/deal/report key),
    so the 2-second MT5 monitor can safely call this repeatedly without duplicates.
    """
    migrate()
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    metadata=d.get('metadata_json')
    if metadata is None and d.get('metadata') is not None:
        metadata=json.dumps(d.get('metadata'),ensure_ascii=False,default=str)
    with _con() as c:
        cur=c.execute("""INSERT OR IGNORE INTO workflow_audit
        (event_key,signal_id,stage,status,event_time,source,detail,telegram_message_id,
         mt5_ticket,position_id,metadata_json)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(
            str(d['event_key']),str(d['signal_id']),str(d['stage']),str(d.get('status') or 'INFO'),
            str(d.get('event_time') or now),d.get('source'),d.get('detail'),d.get('telegram_message_id'),
            d.get('mt5_ticket'),d.get('position_id'),metadata
        ))
        return cur.rowcount>0


def list_workflow_events(signal_id=None,limit=5000,ascending=False):
    migrate()
    q="SELECT * FROM workflow_audit"; vals=[]
    if signal_id:
        q+=" WHERE signal_id=?"; vals.append(str(signal_id))
    q+=f" ORDER BY id {'ASC' if ascending else 'DESC'} LIMIT ?"; vals.append(int(limit))
    with _con() as c:
        return [dict(r) for r in c.execute(q,vals).fetchall()]


def workflow_event_exists(event_key):
    migrate()
    with _con() as c:
        return c.execute("SELECT 1 FROM workflow_audit WHERE event_key=?",(str(event_key),)).fetchone() is not None


# --- v0.9.18 Strategy Builder / Trade Archive ---
def ensure_setup_names(names):
    migrate()
    names=[str(x).strip() for x in (names or []) if str(x).strip() and str(x).strip().upper()!='OTHER']
    with _con() as c:
        for name in names:
            c.execute("""INSERT OR IGNORE INTO setup_definitions(name,description,active)
                       VALUES(?,?,1)""",(name,''))


def create_setup(name,description=''):
    migrate(); name=str(name or '').strip()
    if not name: raise ValueError('Setup name is required')
    with _con() as c:
        c.execute("""INSERT INTO setup_definitions(name,description,active,updated_at)
                   VALUES(?,?,1,CURRENT_TIMESTAMP)
                   ON CONFLICT(name) DO UPDATE SET description=excluded.description,
                   active=1,updated_at=CURRENT_TIMESTAMP""",(name,str(description or '').strip()))
        r=c.execute("SELECT * FROM setup_definitions WHERE name=? COLLATE NOCASE",(name,)).fetchone()
        return dict(r) if r else None


def update_setup(setup_id,name=None,description=None,active=None):
    migrate(); fields=[]; vals=[]
    if name is not None:
        name=str(name).strip()
        if not name: raise ValueError('Setup name is required')
        fields.append('name=?'); vals.append(name)
    if description is not None: fields.append('description=?'); vals.append(str(description))
    if active is not None: fields.append('active=?'); vals.append(int(bool(active)))
    if not fields:return
    fields.append('updated_at=CURRENT_TIMESTAMP'); vals.append(int(setup_id))
    with _con() as c:c.execute(f"UPDATE setup_definitions SET {','.join(fields)} WHERE id=?",vals)


def list_setups(active_only=False):
    migrate(); q='SELECT * FROM setup_definitions'
    if active_only:q+=' WHERE active=1'
    q+=' ORDER BY active DESC,name COLLATE NOCASE'
    with _con() as c:return [dict(r) for r in c.execute(q).fetchall()]


def get_setup(setup_id):
    migrate()
    with _con() as c:
        r=c.execute('SELECT * FROM setup_definitions WHERE id=?',(int(setup_id),)).fetchone()
        return dict(r) if r else None


def add_setup_item(setup_id,item_text,weight=1.0,required=False,sort_order=None):
    migrate(); text=str(item_text or '').strip()
    if not text: raise ValueError('Checklist item is required')
    with _con() as c:
        if sort_order is None:
            r=c.execute('SELECT COALESCE(MAX(sort_order),0)+1 n FROM setup_checklist_items WHERE setup_id=?',(int(setup_id),)).fetchone()
            sort_order=int(r['n'] or 1)
        cur=c.execute("""INSERT INTO setup_checklist_items
            (setup_id,item_text,weight,required,sort_order,active,updated_at)
            VALUES(?,?,?,?,?,1,CURRENT_TIMESTAMP)""",
            (int(setup_id),text,float(weight),int(bool(required)),int(sort_order)))
        return int(cur.lastrowid)


def update_setup_item(item_id,item_text=None,weight=None,required=None,active=None,sort_order=None):
    migrate(); fields=[]; vals=[]
    if item_text is not None: fields.append('item_text=?');vals.append(str(item_text).strip())
    if weight is not None: fields.append('weight=?');vals.append(float(weight))
    if required is not None: fields.append('required=?');vals.append(int(bool(required)))
    if active is not None: fields.append('active=?');vals.append(int(bool(active)))
    if sort_order is not None: fields.append('sort_order=?');vals.append(int(sort_order))
    if not fields:return
    fields.append('updated_at=CURRENT_TIMESTAMP'); vals.append(int(item_id))
    with _con() as c:c.execute(f"UPDATE setup_checklist_items SET {','.join(fields)} WHERE id=?",vals)


def delete_setup_item(item_id):
    migrate()
    with _con() as c:c.execute('DELETE FROM setup_checklist_items WHERE id=?',(int(item_id),))


def list_setup_items(setup_id,active_only=True):
    migrate(); q='SELECT * FROM setup_checklist_items WHERE setup_id=?'; vals=[int(setup_id)]
    if active_only:q+=' AND active=1'
    q+=' ORDER BY sort_order,id'
    with _con() as c:return [dict(r) for r in c.execute(q,vals).fetchall()]


def save_signal_setup_score(d):
    migrate()
    with _con() as c:
        c.execute("""INSERT INTO signal_setup_scores
        (signal_id,setup_id,setup_name,score_points,max_points,score_percent,grade,
         required_missed,rationale,checklist_json,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        ON CONFLICT(signal_id) DO UPDATE SET
         setup_id=excluded.setup_id,setup_name=excluded.setup_name,
         score_points=excluded.score_points,max_points=excluded.max_points,
         score_percent=excluded.score_percent,grade=excluded.grade,
         required_missed=excluded.required_missed,rationale=excluded.rationale,
         checklist_json=excluded.checklist_json,updated_at=CURRENT_TIMESTAMP""",(
            str(d['signal_id']),d.get('setup_id'),str(d.get('setup_name') or ''),
            d.get('score_points',0),d.get('max_points',0),d.get('score_percent'),d.get('grade'),
            int(d.get('required_missed',0)),d.get('rationale'),d.get('checklist_json')
        ))


def get_signal_setup_score(signal_id):
    migrate()
    with _con() as c:
        r=c.execute('SELECT * FROM signal_setup_scores WHERE signal_id=?',(str(signal_id),)).fetchone()
        return dict(r) if r else None


def list_signal_setup_scores():
    migrate()
    with _con() as c:return [dict(r) for r in c.execute('SELECT * FROM signal_setup_scores ORDER BY created_at DESC').fetchall()]


def add_archive_file(signal_id,category,file_path,caption='',source='ADMIN_UPLOAD'):
    migrate()
    with _con() as c:
        c.execute("""INSERT OR IGNORE INTO trade_archive_files
        (signal_id,category,file_path,caption,source) VALUES(?,?,?,?,?)""",
        (str(signal_id),str(category),str(file_path),str(caption or ''),str(source or 'ADMIN_UPLOAD')))


def list_archive_files(signal_id=None):
    migrate(); q='SELECT * FROM trade_archive_files'; vals=[]
    if signal_id is not None:q+=' WHERE signal_id=?';vals.append(str(signal_id))
    q+=' ORDER BY created_at,id'
    with _con() as c:return [dict(r) for r in c.execute(q,vals).fetchall()]


def delete_archive_file(file_id):
    migrate()
    with _con() as c:c.execute('DELETE FROM trade_archive_files WHERE id=?',(int(file_id),))


# --- v0.9.19 Trailing Profiles / AutoTrade Client Policies ---
def _json_load(raw,default=None):
    if raw in (None,''):
        return {} if default is None else default
    try:return json.loads(raw)
    except Exception:return {} if default is None else default


def ensure_default_trailing_profiles():
    """Seed safe, editable trailing profiles once. Existing user profiles are never overwritten."""
    migrate()
    defaults=[
        {
            'name':'NEXUS Ladder 50 + BE','mode':'LADDER',
            'description':'TP1: close 50% of initial volume and move SL to Entry. Each next target moves SL to the previous target. Last target is a hard broker TP.',
            'allow_user_override':1,
            'params':{
                'first_partial_percent':50.0,'close_percent_basis':'INITIAL',
                'hard_final_target':True,'broker_tp_mode':'LAST_TARGET',
                'max_targets':5,'min_targets':2,'publish_management_updates':False
            }
        },
        {
            'name':'Breakeven at 1R','mode':'R_BASED',
            'description':'At +1R move SL to Entry. Keeps the signal TP as broker TP.',
            'allow_user_override':1,
            'params':{'stages':[{'trigger_r':1.0,'lock_r':0.0,'close_percent':0.0}], 'broker_tp_mode':'SIGNAL_TP'}
        },
        {
            'name':'R Step 1R / 1.5R / 2R','mode':'R_BASED',
            'description':'1R -> BE, 1.5R -> lock +0.5R, 2R -> lock +1R.',
            'allow_user_override':1,
            'params':{'stages':[{'trigger_r':1.0,'lock_r':0.0,'close_percent':0.0},{'trigger_r':1.5,'lock_r':0.5,'close_percent':0.0},{'trigger_r':2.0,'lock_r':1.0,'close_percent':0.0}], 'broker_tp_mode':'NONE'}
        },
        {
            'name':'Fixed 0.50R Trail after 1R','mode':'FIXED_R',
            'description':'After +1R, keep SL 0.50R behind price and ratchet it in 0.10R steps.',
            'allow_user_override':1,
            'params':{'activation_r':1.0,'trail_distance_r':0.50,'step_r':0.10,'broker_tp_mode':'NONE'}
        },
        {
            'name':'ATR Trail','mode':'ATR',
            'description':'After +1R, trail SL by 2x ATR(14) on M5. SL only ratchets toward profit.',
            'allow_user_override':1,
            'params':{'activation_r':1.0,'atr_period':14,'atr_multiplier':2.0,'timeframe':'M5','broker_tp_mode':'NONE'}
        },
        {
            'name':'Manual / No Trailing','mode':'MANUAL',
            'description':'No automatic SL/partial management. Original broker TP/SL remain active.',
            'allow_user_override':0,
            'params':{'broker_tp_mode':'SIGNAL_TP'}
        },
    ]
    with _con() as c:
        for d in defaults:
            c.execute("""INSERT OR IGNORE INTO trailing_profiles
            (name,mode,description,params_json,active,allow_user_override)
            VALUES(?,?,?,?,1,?)""",(
                d['name'],d['mode'],d.get('description'),json.dumps(d['params'],ensure_ascii=False),int(d.get('allow_user_override',0))
            ))


def list_trailing_profiles(active_only=False):
    migrate(); ensure_default_trailing_profiles()
    q='SELECT * FROM trailing_profiles'
    if active_only:q+=' WHERE active=1'
    q+=' ORDER BY id ASC'
    with _con() as c:rows=[dict(r) for r in c.execute(q).fetchall()]
    for r in rows:r['params']=_json_load(r.get('params_json'),{})
    return rows


def get_trailing_profile(profile_id):
    migrate(); ensure_default_trailing_profiles()
    with _con() as c:r=c.execute('SELECT * FROM trailing_profiles WHERE id=?',(int(profile_id),)).fetchone()
    if not r:return None
    d=dict(r);d['params']=_json_load(d.get('params_json'),{});return d


def save_trailing_profile(name,mode,description='',params=None,active=True,allow_user_override=False,profile_id=None):
    migrate(); raw=json.dumps(params or {},ensure_ascii=False)
    with _con() as c:
        if profile_id:
            c.execute("""UPDATE trailing_profiles SET name=?,mode=?,description=?,params_json=?,active=?,allow_user_override=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                      (str(name).strip(),str(mode).upper(),description,raw,int(bool(active)),int(bool(allow_user_override)),int(profile_id)))
            return int(profile_id)
        cur=c.execute("""INSERT INTO trailing_profiles(name,mode,description,params_json,active,allow_user_override)
                         VALUES(?,?,?,?,?,?)""",(str(name).strip(),str(mode).upper(),description,raw,int(bool(active)),int(bool(allow_user_override))))
        return int(cur.lastrowid)


def save_signal_trailing_plan(d):
    migrate()
    targets=d.get('targets') or _json_load(d.get('targets_json'),[])
    plan=d.get('plan') or _json_load(d.get('plan_json'),{})
    with _con() as c:
        c.execute("""INSERT INTO signal_trailing_plans
        (signal_id,profile_id,profile_name,mode,enabled,targets_json,plan_json,current_stage,status,last_error,client_id,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        ON CONFLICT(signal_id) DO UPDATE SET
          profile_id=excluded.profile_id,profile_name=excluded.profile_name,mode=excluded.mode,enabled=excluded.enabled,
          targets_json=excluded.targets_json,plan_json=excluded.plan_json,current_stage=excluded.current_stage,
          status=excluded.status,last_error=excluded.last_error,client_id=excluded.client_id,updated_at=CURRENT_TIMESTAMP""",(
            str(d['signal_id']),d.get('profile_id'),d.get('profile_name'),d.get('mode'),int(bool(d.get('enabled'))),
            json.dumps(targets,ensure_ascii=False),json.dumps(plan,ensure_ascii=False),int(d.get('current_stage',0)),
            d.get('status','ARMED' if d.get('enabled') else 'OFF'),d.get('last_error'),d.get('client_id','ADMIN')
        ))


def get_signal_trailing_plan(signal_id):
    migrate()
    with _con() as c:r=c.execute('SELECT * FROM signal_trailing_plans WHERE signal_id=?',(str(signal_id),)).fetchone()
    if not r:return None
    d=dict(r);d['targets']=_json_load(d.get('targets_json'),[]);d['plan']=_json_load(d.get('plan_json'),{});return d


def update_signal_trailing_plan(signal_id,**fields):
    migrate()
    allowed={'enabled','current_stage','status','last_error','targets_json','plan_json','client_id','profile_id','profile_name','mode'}
    items=[]
    for k,v in fields.items():
        if k not in allowed:continue
        if k in ('targets_json','plan_json') and not isinstance(v,str):v=json.dumps(v,ensure_ascii=False)
        if k=='enabled':v=int(bool(v))
        items.append((k,v))
    if not items:return
    q=', '.join(f'{k}=?' for k,_ in items)+', updated_at=CURRENT_TIMESTAMP'
    vals=[v for _,v in items]+[str(signal_id)]
    with _con() as c:c.execute(f'UPDATE signal_trailing_plans SET {q} WHERE signal_id=?',vals)


def list_signal_trailing_plans():
    migrate()
    with _con() as c:rows=[dict(r) for r in c.execute('SELECT * FROM signal_trailing_plans ORDER BY updated_at DESC').fetchall()]
    for d in rows:d['targets']=_json_load(d.get('targets_json'),[]);d['plan']=_json_load(d.get('plan_json'),{})
    return rows


def trailing_action_succeeded(action_key):
    migrate()
    with _con() as c:r=c.execute("SELECT status FROM trailing_actions WHERE action_key=?",(str(action_key),)).fetchone()
    return bool(r and str(r['status']).upper() in ('DONE','CONFIRMED'))


def get_trailing_action(action_key):
    migrate()
    with _con() as c:r=c.execute('SELECT * FROM trailing_actions WHERE action_key=?',(str(action_key),)).fetchone()
    if not r:return None
    d=dict(r);d['metadata']=_json_load(d.get('metadata_json'),{});return d


def record_trailing_action(d):
    migrate(); meta=d.get('metadata_json')
    if meta is None and d.get('metadata') is not None:meta=json.dumps(d.get('metadata'),ensure_ascii=False,default=str)
    with _con() as c:
        c.execute("""INSERT INTO trailing_actions
        (action_key,signal_id,stage,action_type,trigger_price,requested_value,executed_value,status,error,metadata_json,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        ON CONFLICT(action_key) DO UPDATE SET
          requested_value=excluded.requested_value,executed_value=excluded.executed_value,status=excluded.status,error=excluded.error,
          metadata_json=excluded.metadata_json,updated_at=CURRENT_TIMESTAMP""",(
            str(d['action_key']),str(d['signal_id']),d.get('stage'),str(d['action_type']),d.get('trigger_price'),
            d.get('requested_value'),d.get('executed_value'),str(d.get('status','INFO')),d.get('error'),meta
        ))


def list_trailing_actions(signal_id=None,limit=5000):
    migrate();q='SELECT * FROM trailing_actions';vals=[]
    if signal_id:q+=' WHERE signal_id=?';vals.append(str(signal_id))
    q+=' ORDER BY id DESC LIMIT ?';vals.append(int(limit))
    with _con() as c:return [dict(r) for r in c.execute(q,vals).fetchall()]


def upsert_autotrade_client(client_id,display_name,enabled=True,subscription_expires_at=None,notes=''):
    migrate()
    with _con() as c:
        c.execute("""INSERT INTO autotrade_clients(client_id,display_name,enabled,subscription_expires_at,notes,created_at,updated_at)
        VALUES(?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        ON CONFLICT(client_id) DO UPDATE SET display_name=excluded.display_name,enabled=excluded.enabled,
        subscription_expires_at=excluded.subscription_expires_at,notes=excluded.notes,updated_at=CURRENT_TIMESTAMP""",
        (str(client_id).strip(),str(display_name).strip(),int(bool(enabled)),subscription_expires_at,notes))


def list_autotrade_clients():
    migrate()
    with _con() as c:return [dict(r) for r in c.execute('SELECT * FROM autotrade_clients ORDER BY display_name COLLATE NOCASE').fetchall()]


def get_autotrade_client(client_id):
    migrate()
    with _con() as c:r=c.execute('SELECT * FROM autotrade_clients WHERE client_id=?',(str(client_id),)).fetchone()
    return dict(r) if r else None


def save_client_trailing_policy(client_id,enabled=False,assigned_profile_id=None,allow_user_customize=False,allowed_profile_ids=None,overrides=None):
    migrate()
    with _con() as c:
        c.execute("""INSERT INTO client_trailing_policies(client_id,enabled,assigned_profile_id,allow_user_customize,allowed_profile_ids_json,overrides_json,updated_at)
        VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(client_id) DO UPDATE SET enabled=excluded.enabled,assigned_profile_id=excluded.assigned_profile_id,
        allow_user_customize=excluded.allow_user_customize,allowed_profile_ids_json=excluded.allowed_profile_ids_json,
        overrides_json=excluded.overrides_json,updated_at=CURRENT_TIMESTAMP""",(
            str(client_id),int(bool(enabled)),assigned_profile_id,int(bool(allow_user_customize)),
            json.dumps(allowed_profile_ids or [],ensure_ascii=False),json.dumps(overrides or {},ensure_ascii=False)
        ))


def get_client_trailing_policy(client_id):
    migrate()
    with _con() as c:r=c.execute('SELECT * FROM client_trailing_policies WHERE client_id=?',(str(client_id),)).fetchone()
    if not r:return None
    d=dict(r);d['allowed_profile_ids']=_json_load(d.get('allowed_profile_ids_json'),[]);d['overrides']=_json_load(d.get('overrides_json'),{});return d


def list_client_trailing_policies():
    migrate()
    with _con() as c:rows=[dict(r) for r in c.execute('SELECT * FROM client_trailing_policies ORDER BY client_id').fetchall()]
    for d in rows:d['allowed_profile_ids']=_json_load(d.get('allowed_profile_ids_json'),[]);d['overrides']=_json_load(d.get('overrides_json'),{})
    return rows


def client_trailing_access(client_id,now_iso=None):
    """Server-side policy snapshot for the future AutoTrade Client/Signal Server.

    This is intentionally independent of any UI. A client agent can consume this
    structure later without changing the admin database model.
    """
    client=get_autotrade_client(client_id);policy=get_client_trailing_policy(client_id)
    if not client:return {'allowed':False,'reason':'CLIENT_NOT_FOUND','client_id':str(client_id)}
    if not int(client.get('enabled') or 0):return {'allowed':False,'reason':'CLIENT_DISABLED','client_id':str(client_id)}
    exp=client.get('subscription_expires_at')
    if exp:
        try:
            now=datetime.now(timezone.utc) if not now_iso else datetime.fromisoformat(str(now_iso).replace('Z','+00:00'))
            if now.tzinfo is None:now=now.replace(tzinfo=timezone.utc)
            e=datetime.fromisoformat(str(exp).replace('Z','+00:00'))
            if e.tzinfo is None:e=e.replace(tzinfo=timezone.utc)
            if now.astimezone(timezone.utc)>=e.astimezone(timezone.utc):return {'allowed':False,'reason':'SUBSCRIPTION_EXPIRED','client_id':str(client_id),'expires_at':exp}
        except Exception:pass
    if not policy or not int(policy.get('enabled') or 0):return {'allowed':False,'reason':'TRAILING_NOT_ENABLED_BY_ADMIN','client_id':str(client_id)}
    profile=get_trailing_profile(policy.get('assigned_profile_id')) if policy.get('assigned_profile_id') else None
    return {'allowed':bool(profile and int(profile.get('active') or 0)),'reason':'OK' if profile else 'PROFILE_NOT_FOUND',
            'client_id':str(client_id),'client':client,'policy':policy,'profile':profile}


def resolve_client_trailing_profile(client_id,user_profile_id=None,user_overrides=None):
    """Resolve the effective trailing profile for a customer.

    Priority is intentionally:
      base profile < user preference (only when Admin allows) < Admin policy overrides.
    A future per-signal server override can be applied after this resolver.
    """
    access=client_trailing_access(client_id)
    if not access.get('allowed'):
        return access
    policy=access['policy'];base=access['profile']
    selected=base
    allowed={int(x) for x in (policy.get('allowed_profile_ids') or []) if str(x).isdigit()}
    can_customize=bool(int(policy.get('allow_user_customize') or 0))
    if can_customize and user_profile_id:
        try:uid=int(user_profile_id)
        except Exception:uid=None
        if uid and (not allowed or uid in allowed):
            cand=get_trailing_profile(uid)
            if cand and int(cand.get('active') or 0):selected=cand
    params=dict(selected.get('params') or {})
    if can_customize and int(selected.get('allow_user_override') or 0) and isinstance(user_overrides,dict):
        mode=str(selected.get('mode') or '').upper()
        allowed_keys={
            'LADDER':{'first_partial_percent','close_percent_basis','hard_final_target','broker_tp_mode'},
            'R_BASED':{'stages','broker_tp_mode'},
            'FIXED_R':{'activation_r','trail_distance_r','step_r','broker_tp_mode'},
            'ATR':{'activation_r','atr_period','atr_multiplier','timeframe','broker_tp_mode'},
            'MANUAL':set(),
        }.get(mode,set())
        for k,v in user_overrides.items():
            if k in allowed_keys:params[k]=v
    # Admin policy overrides are applied last and therefore always win.
    for k,v in (policy.get('overrides') or {}).items():params[k]=v
    effective=dict(selected);effective['params']=params;effective['params_json']=json.dumps(params,ensure_ascii=False)
    return {'allowed':True,'reason':'OK','client_id':str(client_id),'client':access['client'],'policy':policy,'profile':effective,
            'user_customization_applied':bool(can_customize and user_overrides)}


# --- v0.9.20 Durable creation / external-effects outbox ---
def schema_version():
    migrate()
    with _con() as c:
        row=c.execute('SELECT COALESCE(MAX(version),0) version FROM schema_migrations').fetchone()
        return int(row['version'] or 0)


def list_schema_migrations():
    migrate()
    with _con() as c:
        return [dict(r) for r in c.execute('SELECT * FROM schema_migrations ORDER BY version').fetchall()]


def enqueue_outbox(idempotency_key,operation_type,payload,signal_id=None):
    """Create one durable external-effect intent and return the canonical row."""
    migrate();raw=json.dumps(payload or {},ensure_ascii=False,default=str)
    with _con() as c:
        c.execute("""INSERT OR IGNORE INTO outbox
        (idempotency_key,operation_type,signal_id,payload_json,status,attempt_count,created_at,updated_at)
        VALUES(?,?,?,?, 'PENDING',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",
        (str(idempotency_key),str(operation_type),str(signal_id) if signal_id else None,raw))
        row=c.execute('SELECT * FROM outbox WHERE idempotency_key=?',(str(idempotency_key),)).fetchone()
        return dict(row) if row else None


def get_outbox_item(idempotency_key=None,item_id=None):
    migrate()
    with _con() as c:
        if item_id is not None:r=c.execute('SELECT * FROM outbox WHERE id=?',(int(item_id),)).fetchone()
        else:r=c.execute('SELECT * FROM outbox WHERE idempotency_key=?',(str(idempotency_key),)).fetchone()
        if not r:return None
        d=dict(r);d['payload']=_json_load(d.get('payload_json'),{});return d


def list_outbox(status=None,limit=500):
    migrate();q='SELECT * FROM outbox';vals=[]
    if status:
        states=[str(x).upper() for x in (status if isinstance(status,(list,tuple,set)) else [status])]
        q+=' WHERE status IN ('+','.join('?' for _ in states)+')';vals.extend(states)
    q+=' ORDER BY id DESC LIMIT ?';vals.append(int(limit))
    with _con() as c:
        rows=[dict(r) for r in c.execute(q,vals).fetchall()]
    for d in rows:d['payload']=_json_load(d.get('payload_json'),{})
    return rows


def due_outbox(limit=25,now_iso=None):
    migrate();now=str(now_iso or datetime.now(timezone.utc).isoformat(timespec='seconds'))
    with _con() as c:
        rows=c.execute("""SELECT * FROM outbox
        WHERE status IN ('PENDING','FAILED') AND (next_retry_at IS NULL OR next_retry_at<=?)
        ORDER BY id LIMIT ?""",(now,int(limit))).fetchall()
    out=[dict(r) for r in rows]
    for d in out:d['payload']=_json_load(d.get('payload_json'),{})
    return out


def mark_outbox_sending(item_id):
    migrate()
    with _con() as c:
        cur=c.execute("""UPDATE outbox SET status='SENDING',attempt_count=attempt_count+1,
        updated_at=CURRENT_TIMESTAMP WHERE id=? AND status IN ('PENDING','FAILED')""",(int(item_id),))
        return cur.rowcount==1


def mark_outbox_sent(item_id,message_id=None):
    migrate()
    with _con() as c:c.execute("""UPDATE outbox SET status='SENT',telegram_message_id=?,sent_at=CURRENT_TIMESTAMP,
        updated_at=CURRENT_TIMESTAMP,last_error=NULL,next_retry_at=NULL WHERE id=?""",(message_id,int(item_id)))


def mark_outbox_failed(item_id,error,max_attempts=5,ambiguous=False,base_seconds=5):
    """Bounded exponential retry; ambiguous network delivery is never auto-replayed."""
    migrate()
    with _con() as c:
        row=c.execute('SELECT attempt_count FROM outbox WHERE id=?',(int(item_id),)).fetchone()
        attempts=int(row['attempt_count'] or 0) if row else 0
        if ambiguous:status='UNKNOWN';next_retry=None
        elif attempts>=int(max_attempts):status='DEAD';next_retry=None
        else:
            status='FAILED';delay=min(3600,int(base_seconds)*(2**max(0,attempts-1)))
            next_retry=(datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat(timespec='seconds')
        c.execute("""UPDATE outbox SET status=?,last_error=?,next_retry_at=?,updated_at=CURRENT_TIMESTAMP
        WHERE id=?""",(status,str(error)[:2000],next_retry,int(item_id)))
        return status


def recover_interrupted_outbox():
    """Fail closed after a crash: SENDING may already have reached Telegram."""
    migrate()
    with _con() as c:
        cur=c.execute("""UPDATE outbox SET status='UNKNOWN',
        last_error=COALESCE(last_error,'Interrupted while delivery outcome was unknown'),
        updated_at=CURRENT_TIMESTAMP WHERE status='SENDING'""")
        return int(cur.rowcount)


def outbox_status():
    migrate()
    with _con() as c:
        counts={r['status']:int(r['n']) for r in c.execute('SELECT status,COUNT(*) n FROM outbox GROUP BY status')}
        last=c.execute("SELECT sent_at,telegram_message_id FROM outbox WHERE status='SENT' ORDER BY sent_at DESC LIMIT 1").fetchone()
    return {'counts':counts,'pending':sum(counts.get(x,0) for x in ('PENDING','FAILED','SENDING')),
            'failed':sum(counts.get(x,0) for x in ('DEAD','UNKNOWN')),
            'last_sent_at':last['sent_at'] if last else None,'last_message_id':last['telegram_message_id'] if last else None}


def create_signal_durable(signal,setup_score=None,trailing_plan=None,outbox_payload=None):
    """Persist all local intent before any Telegram or MT5 call is permitted."""
    signal=dict(signal);signal['publication_status']='PENDING';signal['telegram_message_id']=None
    save_signal(signal)
    try:
        if trailing_plan:save_signal_trailing_plan(trailing_plan)
        if setup_score:
            score=dict(setup_score);score['signal_id']=signal['signal_id'];save_signal_setup_score(score)
        item=None
        if outbox_payload is not None:
            item=enqueue_outbox(f"{signal['signal_id']}:TELEGRAM:SIGNAL",'TELEGRAM_SIGNAL',outbox_payload,signal['signal_id'])
        return {'signal':get_signal(signal['signal_id']),'outbox':item}
    except Exception as exc:
        update_signal(signal['signal_id'],publication_status='PERSIST_FAILED',telegram_error=str(exc))
        raise
