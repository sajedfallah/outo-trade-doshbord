
import time,os
from pathlib import Path
from datetime import datetime,timezone,timedelta

ROOT=Path(__file__).resolve().parent.parent

from storage.repo import (
    monitored_signals,get_signal,update_signal,event_exists,insert_event,
    update_event_message,list_trade_events,save_account_snapshot_if_due,set_state,get_trade_metrics,
    get_signal_trailing_plan,update_signal_trailing_plan,enqueue_outbox,list_signals,
    next_signal_id,create_signal_durable
)
from telegram.outbox import deliver_item,deliver_due,startup_recovery
from Dashboard.cards import partial_close_card,final_mt5_card,imported_mt5_signal_card
from monitor.window_capture import capture_current_chart
from monitor.performance_reports import check_scheduled_reports
from monitor.trade_metrics import compute_trade_metrics
from monitor.trade_review import finalize_trade_review
from monitor.workflow import audit
from risk.risk_engine import evaluate_account_state
from trailing.engine import process_trailing
from config_loader import load_config
from mt5trade.service import resume_ready_signals
from monitor.event_logic import (
    weighted_exit_price,weighted_r,net_profit,classify_final,event_time_iso
)

def log(msg):
    line=f"{datetime.now().isoformat(timespec='seconds')} | {msg}"
    print(line,flush=True)
    try:
        with open(ROOT/"storage"/"mt5_monitor.log","a",encoding="utf-8") as f:
            f.write(line+"\n")
    except Exception:
        pass

def load_cfg():
    return load_config()

def mt5_connect(cfg):
    import MetaTrader5 as mt5
    path=cfg["mt5"].get("terminal_path","")
    ok=mt5.initialize(path=path) if path else mt5.initialize()
    if not ok:
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    return mt5

def find_position(mt5,signal):
    sid=signal["signal_id"].upper()
    pid=str(signal.get("mt5_position_id") or "")
    ticket=str(signal.get("mt5_ticket") or "")
    positions=list(mt5.positions_get() or [])

    if pid:
        for p in positions:
            if str(getattr(p,"identifier",p.ticket))==pid or str(p.ticket)==pid:
                return p
    if ticket:
        for p in positions:
            if str(p.ticket)==ticket:
                return p
    key=f"NEXUS {sid}"
    for p in positions:
        if key in str(getattr(p,"comment","")).upper():
            return p
    return None

def find_pending(mt5,signal):
    sid=signal["signal_id"].upper()
    ticket=str(signal.get("mt5_ticket") or "")
    key=f"NEXUS {sid}"
    for o in (mt5.orders_get() or []):
        if ticket and str(o.ticket)==ticket:
            return o
        if key in str(getattr(o,"comment","")).upper():
            return o
    return None


def _is_buy(mt5,order_type):
    return int(order_type) in {int(getattr(mt5,'POSITION_TYPE_BUY',0)),int(getattr(mt5,'ORDER_TYPE_BUY',0)),
                               int(getattr(mt5,'ORDER_TYPE_BUY_LIMIT',2)),int(getattr(mt5,'ORDER_TYPE_BUY_STOP',4))}


def _has_registered_entity(signals,*,ticket=None,position_id=None):
    ticket=str(ticket or '');position_id=str(position_id or '')
    return any((ticket and str(row.get('mt5_ticket') or '')==ticket) or
               (position_id and str(row.get('mt5_position_id') or '')==position_id)
               for row in signals)


def import_account_entities(mt5,cfg):
    """Adopt every new position/order in this dedicated MT5 account into NEXUS.

    The imported row is a published record, not an MT5 execution request, so it
    can never re-open or change the external position.
    """
    if not cfg.get('monitor',{}).get('auto_import_account_entities',True):
        return []
    signals=list_signals();created=[]
    entities=[('OPEN',row) for row in list(mt5.positions_get() or [])]
    entities += [('PENDING',row) for row in list(mt5.orders_get() or [])]
    for status,row in entities:
        ticket=str(getattr(row,'ticket','') or '')
        position_id=str(getattr(row,'identifier','') or ticket) if status=='OPEN' else ''
        if _has_registered_entity(signals,ticket=ticket,position_id=position_id):
            continue
        entry=float(getattr(row,'price_open',0) or 0);symbol=str(getattr(row,'symbol','') or '')
        if not ticket or not symbol or entry<=0:
            log(f'ACCOUNT IMPORT skipped invalid {status} entity ticket={ticket} symbol={symbol}')
            continue
        side='BUY' if _is_buy(mt5,getattr(row,'type',-1)) else 'SELL'
        signal_id=next_signal_id();sl=float(getattr(row,'sl',0) or 0);tp=float(getattr(row,'tp',0) or 0)
        volume=float(getattr(row,'volume',getattr(row,'volume_current',getattr(row,'volume_initial',0))) or 0)
        screenshot_path=ROOT/'uploads'/'signals'/f'{signal_id}.png'
        capture=capture_current_chart(screenshot_path,cfg,expected_symbol=symbol)
        if not capture.get('ok'):
            screenshot_path=None
            log(f'{signal_id} ACCOUNT IMPORT chart unavailable: {capture.get("error")}')
        payload={
            'signal_id':signal_id,'symbol':symbol,'direction':side,'timeframe':'MT5',
            'entry':entry,'tp':tp,'sl':sl,'risk_percent':None,'lot':volume,'rr':None,
            'setup_image_path':str(screenshot_path) if screenshot_path else None,'mt5_enabled':True,
            'mt5_status':status,'mt5_ticket':ticket,'mt5_position_id':position_id or None,
            'mt5_symbol':symbol,'mt5_volume':volume,'initial_volume':volume if status=='OPEN' else None,
            'last_volume':volume if status=='OPEN' else None,'monitor_state':status,
            'setup_tag':'UNCLASSIFIED','strategy_version':'MT5_ACCOUNT_IMPORT'
        }
        card=imported_mt5_signal_card(payload,status)
        result=create_signal_durable(payload,None,None,{'image_path':str(screenshot_path) if screenshot_path else None,'text':card})
        audit(signal_id,'SIGNAL_CREATED','DONE',f'{signal_id}:ACCOUNT_IMPORT:{status}:{ticket}',source='MT5_ACCOUNT_IMPORT',detail=f'{symbol} {side} ticket={ticket}')
        delivery=deliver_item(result['outbox'])
        log(f'{signal_id} ACCOUNT IMPORT {status} ticket={ticket} telegram={delivery.get("sent")}')
        signals.append(result['signal']);created.append(result['signal'])
    return created

def deals_for_position(mt5,position_id):
    """
    Read MT5 history by position id, not by datetime range.

    On the target Roco/MT5 setup, history_deals_get(from,to) can return an empty
    result even though history_deals_get(position=...) returns the exact deals.
    Position-based history is therefore authoritative for Nexus trade lifecycle.
    """
    if not position_id:
        return []
    try:
        rows=mt5.history_deals_get(position=int(position_id))
    except Exception:
        rows=None
    return list(rows or [])

def position_id_from_order_history(mt5,ticket):
    """
    Fallback for a pending order that may have filled and fully closed between
    monitor polls before a live position was observed.
    """
    if not ticket:
        return ""
    try:
        rows=mt5.history_orders_get(ticket=int(ticket))
    except Exception:
        rows=None
    for o in (rows or []):
        pid=str(getattr(o,"position_id","") or "")
        if pid and pid!="0":
            return pid
    return ""

def deal_dict(d):
    return {
        "ticket":str(d.ticket),
        "order":str(getattr(d,"order","")),
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
        "comment":str(getattr(d,"comment",""))
    }

def resolve_position_id(signal,deals):
    pid=str(signal.get("mt5_position_id") or "")
    if pid:
        return pid
    key=f"NEXUS {signal['signal_id']}".upper()
    tagged=[d for d in deals if key in d["comment"].upper()]
    if tagged:
        tagged.sort(key=lambda x:x["time"])
        return tagged[0]["position_id"]
    return ""

def existing_exit_tickets(signal_id):
    ev=list_trade_events(signal_id)
    tickets=set()
    for e in ev:
        raw=str(e.get("deal_ticket") or "")
        for t in raw.split(","):
            if t.strip():
                tickets.add(t.strip())
    return tickets


def publish_event(mt5,cfg,signal,event,card):
    charts=ROOT/"uploads"/"mt5_events"
    charts.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    path=charts/f"{signal['signal_id']}_{event['event_type']}_{stamp}.png"

    # Lifecycle notices intentionally reply to the original signal card, not
    # to the preceding notice, so partial updates remain easy to find.
    reply_to=(signal.get("telegram_message_id") or signal.get("last_event_message_id"))
    event["reply_to_message_id"]=reply_to

    # Partial exits are compact reply cards only. The final close receives the
    # untouched screenshot of the visible MT5 chart panel.
    if event.get('event_type')=='FINAL_CLOSE':
        try:
            chart_result=capture_current_chart(path,cfg,expected_symbol=signal.get('mt5_symbol') or signal.get('symbol'))
        except Exception as e:
            chart_result={"ok":False,"error":str(e)}
        event["screenshot_path"]=str(path) if chart_result.get("ok") else None
        if chart_result.get("ok"):
            log(f"{signal['signal_id']} raw MT5 chart captured mode={chart_result.get('mode')}")
        else:
            log(f"{signal['signal_id']} raw MT5 chart capture failed: {chart_result.get('error')}")
    else:
        event["screenshot_path"]=None
    operation='TELEGRAM_PARTIAL' if event.get('event_type')=='PARTIAL_CLOSE' else 'TELEGRAM_FINAL'
    item=enqueue_outbox(f"{event['event_key']}:TELEGRAM",operation,{
        'text':card,'image_path':event.get('screenshot_path'),'reply_to_message_id':reply_to,
        'event_key':event['event_key'],'event_type':event.get('event_type')
    },signal['signal_id'])
    delivery=deliver_item(item)
    if not delivery.get('sent'):
        log(f"{signal['signal_id']} Telegram queued status={delivery.get('status') or delivery.get('reason')}")
        return None
    msg_id=delivery['message_id'];event["telegram_message_id"]=msg_id
    if event.get('event_type')=='FINAL_CLOSE':
        audit(signal['signal_id'],'RESULT_SENT','DONE',f"{signal['signal_id']}:RESULT_SENT:{msg_id}",event_time=event.get('event_time'),source='TELEGRAM',detail='Final result published',telegram_message_id=msg_id,mt5_ticket=signal.get('mt5_ticket'),position_id=event.get('position_id'))
    elif event.get('event_type')=='PARTIAL_CLOSE':
        audit(signal['signal_id'],'PARTIAL_CLOSE','DONE',f"{signal['signal_id']}:PARTIAL_TELEGRAM:{msg_id}",event_time=event.get('event_time'),source='TELEGRAM',detail='Partial update published',telegram_message_id=msg_id,mt5_ticket=signal.get('mt5_ticket'),position_id=event.get('position_id'))
    return msg_id

def process_signal(mt5,cfg,signal):
    sid=signal["signal_id"]
    pos=find_position(mt5,signal)
    pending=find_pending(mt5,signal)

    pid=""
    if pos is not None:
        pid=str(getattr(pos,"identifier",pos.ticket) or pos.ticket)
    if not pid:
        pid=str(signal.get("mt5_position_id") or "")
    if not pid:
        pid=position_id_from_order_history(mt5,signal.get("mt5_ticket"))
    if not pid:
        pid=str(signal.get("mt5_ticket") or "")

    deals=[deal_dict(d) for d in deals_for_position(mt5,pid)]
    resolved=resolve_position_id(signal,deals)
    if resolved:
        pid=resolved
        deals=[deal_dict(d) for d in deals_for_position(mt5,pid)]

    if pos is not None:
        pos_id=str(getattr(pos,"identifier",pos.ticket))
        volume=float(pos.volume)
        initial=float(signal.get("initial_volume") or signal.get("mt5_volume") or volume)
        last=float(signal.get("last_volume") or initial)

        update_signal(
            sid,mt5_position_id=pos_id,initial_volume=initial,last_volume=volume,
            mt5_status="OPEN",monitor_state="OPEN",mt5_symbol=pos.symbol
        )
        audit(sid,'POSITION_OPEN','DONE',f'{sid}:POSITION_OPEN:{pos_id}',source='MT5_MONITOR',detail=f'{pos.symbol} volume={volume}',mt5_ticket=signal.get('mt5_ticket'),position_id=pos_id)

        # v0.9.19: trailing management runs before lifecycle-history detection.
        # If TP1 causes a partial close, the existing position-based history path
        # below detects the close deal and publishes the normal Partial reply.
        trail=process_trailing(mt5,cfg,signal,pos,logger=log)
        if trail.get('changed'):
            refreshed_pos=find_position(mt5,signal)
            if refreshed_pos is None:
                # A management action may have closed the final remainder. Let the
                # next 2-second poll build the canonical FINAL event from MT5 history.
                return
            pos=refreshed_pos
            pos_id=str(getattr(pos,'identifier',pos.ticket))
            volume=float(pos.volume)
            signal=get_signal(sid) or signal
            update_signal(sid,mt5_position_id=pos_id,last_volume=volume,mt5_status='OPEN',monitor_state='OPEN',mt5_symbol=pos.symbol)

        chain=[deal_dict(d) for d in deals_for_position(mt5,pos_id)]
        exit_entries={
            getattr(mt5,"DEAL_ENTRY_OUT",1),
            getattr(mt5,"DEAL_ENTRY_INOUT",2),
            getattr(mt5,"DEAL_ENTRY_OUT_BY",3)
        }
        exits=[d for d in chain if d["entry"] in exit_entries]
        seen=existing_exit_tickets(sid)
        new_exits=[d for d in exits if d["ticket"] not in seen]

        # A partial close exists when exit deal(s) appeared and position remains open.
        if new_exits:
            closed=sum(d["volume"] for d in new_exits)
            minimum=float(cfg["monitor"].get("partial_close_min_volume",0.000001))
            if closed>=minimum:
                all_exits=exits
                event_r=weighted_r(signal,new_exits,initial)
                total_r=weighted_r(signal,all_exits,initial)
                event_profit=net_profit(new_exits)
                total_profit=net_profit(chain)
                px=weighted_exit_price(new_exits)
                key=f"{sid}:PARTIAL:{','.join(d['ticket'] for d in new_exits)}"
                event={
                    "event_key":key,"signal_id":sid,"event_type":"PARTIAL_CLOSE",
                    "position_id":pos_id,
                    "deal_ticket":",".join(d["ticket"] for d in new_exits),
                    "event_time":event_time_iso(max(d["time"] for d in new_exits)),
                    "closed_volume":closed,"remaining_volume":volume,
                    "exit_price":px,"event_profit":event_profit,
                    "total_profit":total_profit,"event_r":event_r,"total_r":total_r,
                    "result_type":"PARTIAL","raw_reason":"PARTIAL_CLOSE"
                }
                tplan=get_signal_trailing_plan(sid)
                if tplan and int(tplan.get('enabled') or 0) and int(tplan.get('current_stage') or 0)>0:
                    stage=int(tplan.get('current_stage') or 0)
                    targets=tplan.get('targets') or []
                    if str(tplan.get('mode') or '').upper()=='LADDER':
                        moved_to='ENTRY / BE' if stage==1 else (f"TP{stage-1}" if stage>1 else 'PROTECTED')
                        event['management_note']=f"Trailing TP{stage}: SL → {moved_to}"
                        event['raw_reason']=f"TRAILING_STAGE_{stage}"

                if not event_exists(key) and insert_event(event):
                    update_signal(sid,last_volume=volume,monitor_state="OPEN",mt5_status="OPEN")
                    audit(sid,'PARTIAL_CLOSE','DONE',f'{sid}:PARTIAL_CLOSE:{key}',event_time=event.get('event_time'),source='MT5_HISTORY',detail=f"closed={closed} remaining={volume} P/L={event_profit:+.2f}",mt5_ticket=signal.get('mt5_ticket'),position_id=pos_id,metadata={'deal_ticket':event.get('deal_ticket')})
                    refreshed=get_signal(sid)
                    if cfg["monitor"].get("auto_publish_partial",True):
                        card=partial_close_card(refreshed,event)
                        publish_event(mt5,cfg,refreshed,event,card)
                    log(f"{sid} PARTIAL closed={closed} remaining={volume} totalR={total_r:.2f} eventR={event_r:.2f}")

        return

    # No live position.
    if pending is not None:
        update_signal(
            sid,mt5_status="PENDING",monitor_state="PENDING",
            mt5_ticket=str(pending.ticket),mt5_symbol=pending.symbol
        )
        audit(sid,'MT5_ORDER','DONE',f'{sid}:MT5_ORDER:{pending.ticket}',source='MT5_MONITOR',detail='Pending order active',mt5_ticket=str(pending.ticket))
        return

    # No position/pending: determine whether it traded and is now fully closed.
    if not pid:
        log(f"{sid} cannot resolve MT5 position id.")
        return

    log(f"{sid} history lookup by position_id={pid}")

    chain=[deal_dict(d) for d in deals_for_position(mt5,pid)]
    if not chain:
        log(f"{sid} no deals for position_id={pid} last_error={mt5.last_error()}")
        return

    entry_in=getattr(mt5,"DEAL_ENTRY_IN",0)
    exit_entries={
        getattr(mt5,"DEAL_ENTRY_OUT",1),
        getattr(mt5,"DEAL_ENTRY_INOUT",2),
        getattr(mt5,"DEAL_ENTRY_OUT_BY",3)
    }
    opens=[d for d in chain if d["entry"]==entry_in]
    exits=[d for d in chain if d["entry"] in exit_entries]
    if not exits:
        return

    initial=float(signal.get("initial_volume") or signal.get("mt5_volume") or sum(d["volume"] for d in opens) or 0)
    if initial<=0:
        return

    seen=existing_exit_tickets(sid)
    new_exits=[d for d in exits if d["ticket"] not in seen]
    # Final event represents the whole trade, while new_exits identifies unique close.
    last=sorted(exits,key=lambda x:x["time"])[-1]
    key=f"{sid}:FINAL:{last['ticket']}"
    if event_exists(key):
        update_signal(sid,mt5_status="CLOSED",monitor_state="FINAL",last_volume=0.0)
        if get_signal_trailing_plan(sid):update_signal_trailing_plan(sid,status='COMPLETE',last_error=None)
        return

    total_r=weighted_r(signal,exits,initial)
    total_profit=net_profit(chain)
    event_r=weighted_r(signal,new_exits or [last],initial)
    event_profit=net_profit(new_exits or [last])
    px=weighted_exit_price(exits)
    reason_tp=getattr(mt5,"DEAL_REASON_TP",-1001)
    reason_sl=getattr(mt5,"DEAL_REASON_SL",-1002)
    result_type=classify_final(total_r,last["reason"],reason_tp,reason_sl)
    closed_at=event_time_iso(last["time"])

    event={
        "event_key":key,"signal_id":sid,"event_type":"FINAL_CLOSE",
        "position_id":pid,"deal_ticket":",".join(d["ticket"] for d in (new_exits or [last])),
        "event_time":closed_at,"closed_volume":sum(d["volume"] for d in (new_exits or [last])),
        "remaining_volume":0.0,"exit_price":px,
        "event_profit":event_profit,"total_profit":total_profit,
        "event_r":event_r,"total_r":total_r,"result_type":result_type,
        "raw_reason":f"DEAL_REASON_{last['reason']}"
    }

    if insert_event(event):
        update_signal(
            sid,mt5_status="CLOSED",monitor_state="FINAL",last_volume=0.0,
            mt5_position_id=pid,closed_at=closed_at
        )
        if get_signal_trailing_plan(sid):update_signal_trailing_plan(sid,status='COMPLETE',last_error=None)
        audit(sid,'FINAL_CLOSE','DONE',f'{sid}:FINAL_CLOSE:{key}',event_time=closed_at,source='MT5_HISTORY',detail=f'{result_type} · P/L {total_profit:+.2f}',mt5_ticket=signal.get('mt5_ticket'),position_id=pid,metadata={'deal_ticket':event.get('deal_ticket'),'total_r':total_r})
        refreshed=get_signal(sid)
        metric={}
        try:
            metric=compute_trade_metrics(mt5,cfg,refreshed,chain,exits,total_r,total_profit,result_type)
            log(f"{sid} METRICS status={metric.get('metric_status')} MFE={metric.get('mfe_r')} MAE={metric.get('mae_r')}")
        except Exception as e:
            metric=get_trade_metrics(sid) or {}
            log(f"{sid} METRICS ERROR {e}")
        if cfg["monitor"].get("auto_publish_final",True):
            try:
                card=final_mt5_card(refreshed,event)
                publish_event(mt5,cfg,refreshed,event,card)
            except Exception as e:
                log(f"{sid} FINAL PUBLISH ERROR {e}")
        if cfg.get('risk_intelligence',{}).get('trade_review',{}).get('enabled',True):
            try:
                review=finalize_trade_review(get_signal(sid) or refreshed,event,metric,cfg)
                log(f"{sid} REVIEW grade={review.get('review_grade')} score={review.get('review_score'):.0f}")
            except Exception as e:
                log(f"{sid} REVIEW ERROR {e}")
        log(f"{sid} FINAL type={result_type} totalR={total_r:.2f} totalP/L={total_profit:.2f}")

def run_once():
    cfg=load_cfg()
    if not cfg.get('monitor',{}).get('enabled',True):
        log('Monitor disabled by configuration.')
        return
    try:
        deliver_due(20)
        for sid,result in resume_ready_signals(cfg):log(f"{sid} DEFERRED MT5 success={result.get('success')} status={result.get('status')} error={result.get('error')}")
    except Exception as e:log(f"OUTBOX/DEFERRED EXECUTION ERROR {e}")
    mt5=mt5_connect(cfg)
    try:
        try:
            a=mt5.account_info()
            positions=list(mt5.positions_get() or [])
            if a is not None:
                snap={
                    "balance":float(a.balance),"equity":float(a.equity),"margin":float(a.margin),
                    "free_margin":float(a.margin_free),"floating_pl":float(a.equity-a.balance),
                    "open_positions":len(positions)
                }
                save_account_snapshot_if_due(snap,300)
                set_state("monitor_heartbeat",{"ok":True,"time":datetime.now().astimezone().isoformat(timespec="seconds"),"login":str(a.login),"server":str(a.server)})
                try:
                    evaluate_account_state(mt5,cfg,persist=True)
                except Exception as e:
                    log(f"RISK ENGINE ERROR {e}")
        except Exception as e:
            set_state("monitor_heartbeat",{"ok":False,"time":datetime.now().astimezone().isoformat(timespec="seconds"),"error":str(e)})
        signals=monitored_signals()
        try:
            imported=import_account_entities(mt5,cfg)
            if imported:log(f'Imported {len(imported)} account MT5 entities into NEXUS.')
            signals=monitored_signals()
        except Exception as e:
            log(f'ACCOUNT IMPORT ERROR {e}')
        if not signals:
            log("No monitored Nexus signals.")
        for signal in signals:
            try:
                process_signal(mt5,cfg,signal)
            except Exception as e:
                log(f"{signal['signal_id']} ERROR {e}")
                try:audit(signal['signal_id'],'WORKFLOW_ERROR','ERROR',f"{signal['signal_id']}:WORKFLOW_ERROR:{datetime.now().strftime('%Y%m%d%H%M')}",source='MT5_MONITOR',detail=str(e))
                except Exception:pass

        try:
            check_scheduled_reports(mt5,cfg,log=log)
        except Exception as e:
            log(f"REPORT ERROR {e}")
    finally:
        mt5.shutdown()

def main():
    from filelock import FileLock,Timeout
    lock=FileLock(str(ROOT/"storage"/"mt5_monitor.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        print("NEXUS MT5 monitor is already running.")
        return

    pid_path=ROOT/"storage"/"mt5_monitor.pid"
    pid_path.write_text(str(os.getpid()),encoding="utf-8")
    recovered=startup_recovery()
    if recovered:log(f"OUTBOX RECOVERY marked {recovered} interrupted deliveries UNKNOWN")
    log("MT5 monitor started.")
    cfg=load_cfg()
    seconds=max(1,float(cfg["monitor"].get("poll_seconds",3)))
    try:
        while True:
            try:
                run_once()
            except Exception as e:
                log(f"LOOP ERROR {e}")
            time.sleep(seconds)
    except KeyboardInterrupt:
        log("MT5 monitor stopped.")
    finally:
        try:pid_path.unlink()
        except Exception:pass
        lock.release()

if __name__=="__main__":
    main()
