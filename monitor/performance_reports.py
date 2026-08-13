
from datetime import datetime,timedelta,time as dt_time
from zoneinfo import ZoneInfo
from collections import defaultdict
import math

from storage.repo import (
    list_signals,report_sent,save_report_run,list_trade_events
)
from telegram.publisher import send_message
from Dashboard.cards import performance_report_card
from monitor.event_logic import weighted_r,net_profit
from monitor.workflow import audit
from storage.repo import enqueue_outbox
from telegram.outbox import deliver_item

def _deal_dict(d):
    return {
        "ticket":str(d.ticket),
        "position_id":str(getattr(d,"position_id","")),
        "time":int(getattr(d,"time",0) or 0),
        "entry":int(getattr(d,"entry",-1)),
        "reason":int(getattr(d,"reason",-1)),
        "symbol":str(getattr(d,"symbol","")),
        "volume":float(getattr(d,"volume",0) or 0),
        "price":float(getattr(d,"price",0) or 0),
        "profit":float(getattr(d,"profit",0) or 0),
        "commission":float(getattr(d,"commission",0) or 0),
        "swap":float(getattr(d,"swap",0) or 0),
        "fee":float(getattr(d,"fee",0) or 0),
    }

def _history_for_position(mt5,pid):
    if not pid:
        return []
    try:
        rows=mt5.history_deals_get(position=int(pid))
    except Exception:
        rows=None
    return [_deal_dict(d) for d in (rows or [])]

def _account_snapshot(mt5):
    a=mt5.account_info()
    positions=list(mt5.positions_get() or [])
    if a is None:
        return {
            "balance":0.0,"equity":0.0,"open_positions":len(positions),
            "current_drawdown_pct":0.0
        }
    balance=float(a.balance)
    equity=float(a.equity)
    dd=((balance-equity)/balance*100.0) if balance>0 and equity<balance else 0.0
    return {
        "balance":balance,"equity":equity,
        "open_positions":len(positions),
        "current_drawdown_pct":dd
    }

def collect_period_stats(mt5,cfg,period_start,period_end):
    """
    MT5 history source is position-based because that path was confirmed reliable
    on this broker, while datetime-range history returned zero rows.

    A trade belongs to the period when its final MT5 exit deal occurs inside the
    requested time window.
    """
    exit_entries={
        getattr(mt5,"DEAL_ENTRY_OUT",1),
        getattr(mt5,"DEAL_ENTRY_INOUT",2),
        getattr(mt5,"DEAL_ENTRY_OUT_BY",3)
    }
    entry_in=getattr(mt5,"DEAL_ENTRY_IN",0)

    start_ts=period_start.timestamp()
    end_ts=period_end.timestamp()

    rows=[]
    symbol_map=defaultdict(lambda:{"trades":0,"profit":0.0,"r":0.0})

    signals=list_signals()
    for s in signals:
        if not int(s.get("mt5_enabled") or 0):
            continue
        pid=str(s.get("mt5_position_id") or s.get("mt5_ticket") or "")
        if not pid:
            continue

        chain=_history_for_position(mt5,pid)
        if not chain:
            continue

        opens=[d for d in chain if d["entry"]==entry_in]
        exits=[d for d in chain if d["entry"] in exit_entries]
        if not exits:
            continue

        last=max(exits,key=lambda d:d["time"])
        if not (start_ts <= last["time"] < end_ts):
            continue

        initial=float(
            s.get("initial_volume") or s.get("mt5_volume")
            or sum(d["volume"] for d in opens) or 0
        )
        if initial<=0:
            continue

        tr=weighted_r(s,exits,initial)
        profit=net_profit(chain)

        if abs(tr)<=0.10:
            result="BREAKEVEN"
        elif profit>0:
            result="WIN"
        elif profit<0:
            result="LOSS"
        else:
            result="BREAKEVEN"

        item={
            "signal_id":s["signal_id"],
            "symbol":s.get("symbol") or last.get("symbol"),
            "r":float(tr),
            "profit":float(profit),
            "result":result,
            "close_time":datetime.fromtimestamp(last["time"],tz=period_start.tzinfo)
        }
        rows.append(item)

        sm=symbol_map[item["symbol"]]
        sm["trades"]+=1
        sm["profit"]+=profit
        sm["r"]+=tr

    wins=sum(1 for x in rows if x["result"]=="WIN")
    losses=sum(1 for x in rows if x["result"]=="LOSS")
    be=sum(1 for x in rows if x["result"]=="BREAKEVEN")
    net=sum(x["profit"] for x in rows)
    total_r=sum(x["r"] for x in rows)
    avg_r=(total_r/len(rows)) if rows else 0.0
    gp=sum(x["profit"] for x in rows if x["profit"]>0)
    gl=abs(sum(x["profit"] for x in rows if x["profit"]<0))
    pf=(gp/gl) if gl>0 else (math.inf if gp>0 else 0.0)

    best=max(rows,key=lambda x:x["r"]) if rows else None
    worst=min(rows,key=lambda x:x["r"]) if rows else None

    # Partial-close count is sourced from lifecycle records whose event time is in
    # the report window; those records themselves originate from MT5 exit history.
    partial=0
    for e in list_trade_events():
        if e.get("event_type")!="PARTIAL_CLOSE":
            continue
        try:
            dt=datetime.fromisoformat(str(e.get("event_time")))
            if dt.tzinfo is None:
                dt=dt.replace(tzinfo=period_start.tzinfo)
            dt=dt.astimezone(period_start.tzinfo)
            if period_start <= dt < period_end:
                partial+=1
        except Exception:
            pass

    snap=_account_snapshot(mt5)
    symbols=[]
    for symbol,v in symbol_map.items():
        symbols.append({
            "symbol":symbol,"trades":v["trades"],
            "profit":v["profit"],"r":v["r"]
        })
    symbols.sort(key=lambda x:x["profit"],reverse=True)

    return {
        "closed_trades":len(rows),
        "wins":wins,"losses":losses,"breakeven":be,
        "net_profit":net,"total_r":total_r,"avg_r":avg_r,
        "profit_factor":pf,
        "profit_factor_text":"∞" if math.isinf(pf) else f"{pf:.2f}",
        "best_trade":best,"worst_trade":worst,
        "partial_exits":partial,
        "symbol_summary":symbols,
        "signal_ids":[x["signal_id"] for x in rows],
        **snap
    }

def _parse_hhmm(value):
    h,m=str(value).split(":",1)
    return int(h),int(m)

def _after_schedule(now,hhmm):
    h,m=_parse_hhmm(hhmm)
    return now.time() >= dt_time(hour=h,minute=m)

def _day_bounds(day,tz):
    start=datetime(day.year,day.month,day.day,tzinfo=tz)
    return start,start+timedelta(days=1)

def _week_bounds(now,tz):
    # Trading week: Monday 00:00 through Saturday 00:00 (Mon-Fri).
    start_day=now.date()-timedelta(days=now.weekday())
    start=datetime(start_day.year,start_day.month,start_day.day,tzinfo=tz)
    return start,start+timedelta(days=5)

def send_report(mt5,cfg,report_type,period_start,period_end,report_key,period_label):
    stats=collect_period_stats(mt5,cfg,period_start,period_end)
    reporting=cfg.get("reporting",{})
    mode=reporting.get(report_type,{})
    if not stats["closed_trades"] and not mode.get("send_when_no_closed_trades",True):
        return {"sent":False,"reason":"NO_CLOSED_TRADES","stats":stats}

    card=performance_report_card(stats,report_type,period_label)
    record={
        "report_key":report_key,
        "report_type":report_type,
        "period_start":period_start.isoformat(),
        "period_end":period_end.isoformat(),
        "telegram_message_id":mid,
        "closed_trades":stats["closed_trades"],
        "net_profit":stats["net_profit"],
        "total_r":stats["total_r"]
    }
    item=enqueue_outbox(f"REPORT:{report_key}:TELEGRAM",'TELEGRAM_REPORT',{
        'text':card,'report_record':record,'signal_ids':stats.get('signal_ids',[])
    })
    delivery=deliver_item(item)
    return {"sent":bool(delivery.get('sent')),"message_id":delivery.get('message_id'),"stats":stats,
            "outbox_status":delivery.get('status') or delivery.get('reason')}

def check_scheduled_reports(mt5,cfg,log=None):
    rcfg=cfg.get("reporting",{})
    if not rcfg.get("enabled",False):
        return []

    tz=ZoneInfo(rcfg.get("timezone","Asia/Tehran"))
    now=datetime.now(tz)
    sent=[]

    daily=rcfg.get("daily",{})
    if daily.get("enabled",True):
        if now.weekday() in daily.get("weekdays",[0,1,2,3,4]) and _after_schedule(now,daily.get("time","23:55")):
            start,end=_day_bounds(now.date(),tz)
            key=f"daily:{start.date().isoformat()}"
            if not report_sent(key):
                result=send_report(
                    mt5,cfg,"daily",start,end,key,
                    start.strftime("%d %b %Y")
                )
                sent.append((key,result))
                if log:
                    log(f"REPORT {key} sent={result.get('sent')}")

    weekly=rcfg.get("weekly",{})
    if weekly.get("enabled",True):
        if now.weekday()==int(weekly.get("weekday",4)) and _after_schedule(now,weekly.get("time","23:58")):
            start,end=_week_bounds(now,tz)
            iso=start.isocalendar()
            key=f"weekly:{iso.year}-W{iso.week:02d}"
            if not report_sent(key):
                label=f"{start.strftime('%d %b')} → {(end-timedelta(seconds=1)).strftime('%d %b %Y')}"
                result=send_report(mt5,cfg,"weekly",start,end,key,label)
                sent.append((key,result))
                if log:
                    log(f"REPORT {key} sent={result.get('sent')}")

    return sent

def manual_report(mt5,cfg,report_type):
    tz=ZoneInfo(cfg.get("reporting",{}).get("timezone","Asia/Tehran"))
    now=datetime.now(tz)
    if report_type=="daily":
        start,end=_day_bounds(now.date(),tz)
        key=f"manual-daily:{now.strftime('%Y%m%d-%H%M%S')}"
        label=start.strftime("%d %b %Y")
    else:
        start,end=_week_bounds(now,tz)
        key=f"manual-weekly:{now.strftime('%Y%m%d-%H%M%S')}"
        label=f"{start.strftime('%d %b')} → {(end-timedelta(seconds=1)).strftime('%d %b %Y')}"
    return send_report(mt5,cfg,report_type,start,end,key,label)
