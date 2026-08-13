
from __future__ import annotations
from datetime import datetime,timezone
import json

from storage.repo import (
    record_workflow_event,list_workflow_events,list_signals,list_trade_events,
    list_trade_metrics,list_report_runs,list_trailing_actions
)

STAGES=[
    'SIGNAL_CREATED','TELEGRAM_SENT','PRE_TRADE_GATE','MT5_ORDER',
    'POSITION_OPEN','TRAILING_MANAGEMENT','PARTIAL_CLOSE','FINAL_CLOSE','RESULT_SENT','REPORT_INCLUDED'
]
STAGE_INDEX={s:i for i,s in enumerate(STAGES)}


def _dt(v):
    if not v:return None
    try:
        d=datetime.fromisoformat(str(v).replace('Z','+00:00'))
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:return None


def _iso(v=None):
    d=_dt(v) if v else datetime.now(timezone.utc)
    return d.isoformat(timespec='seconds') if d else datetime.now(timezone.utc).isoformat(timespec='seconds')


def audit(signal_id,stage,status='DONE',event_key=None,event_time=None,source='NEXUS',detail=None,
          telegram_message_id=None,mt5_ticket=None,position_id=None,metadata=None):
    key=event_key or f'{signal_id}:{stage}:{status}'
    return record_workflow_event({
        'event_key':key,'signal_id':signal_id,'stage':stage,'status':status,
        'event_time':_iso(event_time),'source':source,'detail':detail,
        'telegram_message_id':telegram_message_id,'mt5_ticket':mt5_ticket,
        'position_id':position_id,'metadata':metadata
    })


def _report_matches_signal(report,signal):
    closed=_dt(signal.get('closed_at'))
    if not closed:return False
    start=_dt(report.get('period_start')); end=_dt(report.get('period_end'))
    return bool(start and end and start<=closed<end)


def backfill_workflow_from_existing():
    """Create missing workflow events from the canonical NEXUS registries.

    This is intentionally INSERT-OR-IGNORE and can be run repeatedly. It does not
    alter signals/trades/results; it only reconstructs the audit trail.
    """
    signals=list_signals(); events=list_trade_events(); metrics={m['signal_id']:m for m in list_trade_metrics()}
    reports=list_report_runs(10000); trailing_actions=list_trailing_actions(limit=100000)
    by_signal={}; trail_by_signal={}
    for e in events:by_signal.setdefault(e.get('signal_id'),[]).append(e)
    for a in trailing_actions:trail_by_signal.setdefault(a.get('signal_id'),[]).append(a)
    inserted=0
    for s in signals:
        sid=s['signal_id']; se=by_signal.get(sid,[]); metric=metrics.get(sid,{})
        inserted+=int(audit(sid,'SIGNAL_CREATED','DONE',f'{sid}:SIGNAL_CREATED',s.get('created_at'),'DATABASE','Signal registered') or 0)
        if s.get('telegram_message_id'):
            inserted+=int(audit(sid,'TELEGRAM_SENT','DONE',f"{sid}:TELEGRAM_SENT:{s.get('telegram_message_id')}",s.get('created_at'),'TELEGRAM','Signal published',s.get('telegram_message_id')) or 0)

        if int(s.get('mt5_enabled') or 0):
            safety=str(s.get('safety_status') or '').upper()
            st='BLOCKED' if str(s.get('mt5_status') or '').upper()=='BLOCKED' else ('WARN' if safety=='YELLOW' else 'DONE')
            if safety or s.get('safety_reasons'):
                inserted+=int(audit(sid,'PRE_TRADE_GATE',st,f'{sid}:PRE_TRADE_GATE:BACKFILL',s.get('created_at'),'RISK_ENGINE',s.get('safety_reasons') or safety,metadata={'safety_status':safety}) or 0)
            ms=str(s.get('mt5_status') or 'NOT_REQUESTED').upper()
            if ms not in ('NOT_REQUESTED',''):
                ost='BLOCKED' if ms=='BLOCKED' else ('ERROR' if ms in ('FAILED','CANCELED') else 'DONE')
                inserted+=int(audit(sid,'MT5_ORDER',ost,f"{sid}:MT5_ORDER:{s.get('mt5_ticket') or ms}",s.get('created_at'),'MT5',s.get('mt5_error') or s.get('mt5_action') or ms,mt5_ticket=s.get('mt5_ticket'),position_id=s.get('mt5_position_id')) or 0)
        else:
            inserted+=int(audit(sid,'PRE_TRADE_GATE','SKIPPED',f'{sid}:PRE_TRADE_GATE:TELEGRAM_ONLY',s.get('created_at'),'DASHBOARD','Telegram-only mode') or 0)
            inserted+=int(audit(sid,'MT5_ORDER','SKIPPED',f'{sid}:MT5_ORDER:TELEGRAM_ONLY',s.get('created_at'),'DASHBOARD','Telegram-only mode') or 0)

        pid=s.get('mt5_position_id')
        open_time=metric.get('open_time')
        done_trail=[x for x in trail_by_signal.get(sid,[]) if str(x.get('status') or '').upper()=='DONE']
        if done_trail:
            ta=sorted(done_trail,key=lambda x:x.get('id') or 0)[-1]
            inserted+=int(audit(sid,'TRAILING_MANAGEMENT','DONE',f"{sid}:TRAILING_BACKFILL:{ta.get('id')}",ta.get('updated_at') or ta.get('created_at'),'TRAILING_ENGINE',f"{ta.get('action_type')} · {ta.get('executed_value')}",mt5_ticket=s.get('mt5_ticket'),position_id=pid,metadata={'stage':ta.get('stage'),'action_key':ta.get('action_key')}) or 0)
        if pid and (open_time or str(s.get('monitor_state') or '').upper() in ('OPEN','FINAL')):
            inserted+=int(audit(sid,'POSITION_OPEN','DONE',f'{sid}:POSITION_OPEN:{pid}',open_time or s.get('created_at'),'MT5_MONITOR','Position identified',mt5_ticket=s.get('mt5_ticket'),position_id=pid) or 0)

        for e in sorted(se,key=lambda x:x.get('id') or 0):
            et=e.get('event_type')
            if et=='PARTIAL_CLOSE':
                inserted+=int(audit(sid,'PARTIAL_CLOSE','DONE',f"{sid}:PARTIAL_CLOSE:{e.get('event_key')}",e.get('event_time'),'MT5_HISTORY',f"closed={e.get('closed_volume')} remaining={e.get('remaining_volume')}",e.get('telegram_message_id'),s.get('mt5_ticket'),e.get('position_id'),{'deal_ticket':e.get('deal_ticket')}) or 0)
            elif et=='FINAL_CLOSE':
                inserted+=int(audit(sid,'FINAL_CLOSE','DONE',f"{sid}:FINAL_CLOSE:{e.get('event_key')}",e.get('event_time'),'MT5_HISTORY',f"result={e.get('result_type')} P/L={e.get('total_profit')}",None,s.get('mt5_ticket'),e.get('position_id'),{'deal_ticket':e.get('deal_ticket')}) or 0)
                if e.get('telegram_message_id'):
                    inserted+=int(audit(sid,'RESULT_SENT','DONE',f"{sid}:RESULT_SENT:{e.get('telegram_message_id')}",e.get('event_time'),'TELEGRAM','Final result published',e.get('telegram_message_id'),s.get('mt5_ticket'),e.get('position_id')) or 0)

        for r in reports:
            if _report_matches_signal(r,s):
                inserted+=int(audit(sid,'REPORT_INCLUDED','DONE',f"{sid}:REPORT_INCLUDED:{r.get('report_key')}",r.get('created_at'),'REPORT_ENGINE',f"{r.get('report_type')} · {r.get('report_key')}",r.get('telegram_message_id'),s.get('mt5_ticket'),pid,{'report_key':r.get('report_key'),'report_type':r.get('report_type')}) or 0)
    return {'signals':len(signals),'inserted':inserted,'audit_events':len(list_workflow_events(limit=100000))}


def _event_time_map(audits):
    out={}
    for a in sorted(audits,key=lambda x:x.get('id') or 0):
        out.setdefault(a.get('stage'),a)
        # Keep most recent report/partial but first occurrence for core stages.
        if a.get('stage') in ('TRAILING_MANAGEMENT','PARTIAL_CLOSE','REPORT_INCLUDED','WORKFLOW_ERROR'):
            out[a.get('stage')]=a
    return out


def workflow_detail(signal,audits,events=None,reports=None,metric=None,stall_wait_minutes=5):
    events=events or []; reports=reports or []; metric=metric or {}
    amap=_event_time_map(audits)
    partials=[e for e in events if e.get('event_type')=='PARTIAL_CLOSE']
    finals=[e for e in events if e.get('event_type')=='FINAL_CLOSE']
    final=sorted(finals,key=lambda x:x.get('id') or 0)[-1] if finals else None
    ms=str(signal.get('mt5_status') or 'NOT_REQUESTED').upper(); mon=str(signal.get('monitor_state') or 'WAITING').upper()
    mt5_enabled=bool(int(signal.get('mt5_enabled') or 0))

    def stage(name,status,detail='',when=None,optional=False):
        a=amap.get(name)
        if a:
            status=str(a.get('status') or status); detail=a.get('detail') or detail; when=a.get('event_time') or when
        return {'stage':name,'status':status,'detail':detail,'event_time':when,'optional':optional}

    created=signal.get('created_at')
    stages=[]
    stages.append(stage('SIGNAL_CREATED','DONE','Signal registered',created))
    stages.append(stage('TELEGRAM_SENT','DONE' if signal.get('telegram_message_id') else 'WAITING',
                        f"message_id={signal.get('telegram_message_id')}" if signal.get('telegram_message_id') else 'Waiting for Telegram',created))
    if not mt5_enabled:
        stages.append(stage('PRE_TRADE_GATE','SKIPPED','Telegram-only mode',created))
        stages.append(stage('MT5_ORDER','SKIPPED','Telegram-only mode',created))
        stages.append(stage('POSITION_OPEN','SKIPPED','Telegram-only mode',created))
    else:
        gate='BLOCKED' if ms=='BLOCKED' else ('WARN' if str(signal.get('safety_status') or '').upper()=='YELLOW' else ('DONE' if signal.get('safety_status') else 'WAITING'))
        stages.append(stage('PRE_TRADE_GATE',gate,signal.get('safety_reasons') or signal.get('safety_status') or 'Waiting for safety evaluation',created))
        order_status='BLOCKED' if ms=='BLOCKED' else ('ERROR' if ms in ('FAILED','CANCELED') else ('DONE' if ms in ('SENT','PENDING','OPEN','CLOSED') else 'WAITING'))
        stages.append(stage('MT5_ORDER',order_status,signal.get('mt5_error') or signal.get('mt5_action') or ms,created))
        open_done=bool(signal.get('mt5_position_id') or metric.get('open_time') or mon in ('OPEN','FINAL'))
        stages.append(stage('POSITION_OPEN','DONE' if open_done else ('ERROR' if ms in ('FAILED','CANCELED','BLOCKED') else 'WAITING'),
                            f"position_id={signal.get('mt5_position_id')}" if signal.get('mt5_position_id') else 'Waiting for live position',metric.get('open_time')))
    trail_a=amap.get('TRAILING_MANAGEMENT')
    stages.append(stage('TRAILING_MANAGEMENT','DONE' if trail_a else 'OPTIONAL',trail_a.get('detail') if trail_a else 'No automatic trailing action yet',trail_a.get('event_time') if trail_a else None,True))
    stages.append(stage('PARTIAL_CLOSE','DONE' if partials else 'OPTIONAL',f'{len(partials)} partial close(s)' if partials else 'No partial close',partials[-1].get('event_time') if partials else None,True))
    stages.append(stage('FINAL_CLOSE','DONE' if final else ('ERROR' if ms in ('FAILED','CANCELED','BLOCKED') else 'WAITING'),
                        f"{final.get('result_type')} · P/L {float(final.get('total_profit') or 0):+,.2f}" if final else 'Position not fully closed',final.get('event_time') if final else signal.get('closed_at')))
    result_sent=bool(final and final.get('telegram_message_id')) or bool(amap.get('RESULT_SENT'))
    stages.append(stage('RESULT_SENT','DONE' if result_sent else ('WAITING' if final else 'PENDING'),
                        f"message_id={final.get('telegram_message_id')}" if final and final.get('telegram_message_id') else 'Final result not sent yet',final.get('event_time') if final else None))
    matched_reports=[r for r in reports if _report_matches_signal(r,signal)]
    stages.append(stage('REPORT_INCLUDED','DONE' if matched_reports else ('WAITING' if final else 'PENDING'),
                        f"{len(matched_reports)} report(s)" if matched_reports else ('Waiting for scheduled report' if final else 'Trade still active'),matched_reports[-1].get('created_at') if matched_reports else None))

    # Overall health/current stage.
    attention=[x for x in stages if x['status'] in ('ERROR','BLOCKED')]
    if attention:health='RED'
    else:
        created_dt=_dt(created); age=(datetime.now(timezone.utc)-created_dt).total_seconds()/60 if created_dt else 0
        stalled=mt5_enabled and ms in ('SENT','NOT_REQUESTED') and mon=='WAITING' and age>=float(stall_wait_minutes)
        health='YELLOW' if stalled or any(x['status']=='WARN' for x in stages) else 'GREEN'
    completed=[x for x in stages if x['status']=='DONE' and not x['optional']]
    current='SIGNAL_CREATED'
    for x in stages:
        if x['status'] in ('DONE','SKIPPED','OPTIONAL'):current=x['stage']
        elif x['status'] in ('ERROR','BLOCKED','WAITING','PENDING','WARN'):
            current=x['stage']; break
    if final and result_sent:current='RESULT_SENT'
    if matched_reports:current='REPORT_INCLUDED'
    first=_dt(created); last_times=[_dt(x.get('event_time')) for x in stages if _dt(x.get('event_time'))]
    last=max(last_times) if last_times else first
    elapsed=(datetime.now(timezone.utc)-first).total_seconds()/60 if first and not final else ((last-first).total_seconds()/60 if first and last else None)
    return {'stages':stages,'health':health,'current_stage':current,'partial_count':len(partials),'final':final,
            'report_count':len(matched_reports),'elapsed_minutes':elapsed,'last_activity':last.isoformat(timespec='seconds') if last else created,
            'issue':(attention[0]['detail'] if attention else (signal.get('mt5_error') or ''))}


def build_workflow_registry(signals=None,audits=None,events=None,metrics=None,reports=None,stall_wait_minutes=5):
    signals=signals if signals is not None else list_signals()
    audits=audits if audits is not None else list_workflow_events(limit=100000)
    events=events if events is not None else list_trade_events()
    metrics=metrics if metrics is not None else list_trade_metrics()
    reports=reports if reports is not None else list_report_runs(10000)
    amap={}; emap={}; mmap={m['signal_id']:m for m in metrics}
    for a in audits:amap.setdefault(a.get('signal_id'),[]).append(a)
    for e in events:emap.setdefault(e.get('signal_id'),[]).append(e)
    rows=[]; details={}
    for s in signals:
        sid=s['signal_id']; d=workflow_detail(s,amap.get(sid,[]),emap.get(sid,[]),reports,mmap.get(sid),stall_wait_minutes)
        details[sid]=d
        final=d.get('final') or {}
        rows.append({
            'signal_id':sid,'symbol':s.get('symbol'),'direction':s.get('direction'),'health':d['health'],
            'current_stage':d['current_stage'],'mt5_status':s.get('mt5_status'),'monitor_state':s.get('monitor_state'),
            'telegram_signal_id':s.get('telegram_message_id'),'mt5_ticket':s.get('mt5_ticket'),'position_id':s.get('mt5_position_id'),
            'partials':d['partial_count'],'result':final.get('result_type'),'result_message_id':final.get('telegram_message_id'),
            'reports':d['report_count'],'elapsed_min':None if d['elapsed_minutes'] is None else round(d['elapsed_minutes'],1),
            'last_activity':d['last_activity'],'issue':d['issue']
        })
    return rows,details
