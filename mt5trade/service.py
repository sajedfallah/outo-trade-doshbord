"""Crash-aware orchestration around direct MT5 execution."""
from __future__ import annotations

from storage.repo import get_signal,list_signals,update_signal
from mt5trade.executor import MT5Executor
from mt5trade.gateway import RealMetaTrader5Gateway


def _matching_order_or_position(mt5,signal_id):
    key=f'NEXUS {signal_id}'.upper()
    for row in list(mt5.positions_get() or [])+list(mt5.orders_get() or []):
        if key in str(getattr(row,'comment','')).upper():return row
    return None


def reconcile_interrupted_execution(signal,cfg,gateway=None):
    mt5=gateway or RealMetaTrader5Gateway();owned=gateway is None
    if owned and not mt5.initialize(path=cfg.get('mt5',{}).get('terminal_path','')):
        return {'success':False,'error':'MT5_RECONNECT_FAILED','unknown':True}
    try:
        row=_matching_order_or_position(mt5,signal['signal_id'])
        if row:
            ticket=str(getattr(row,'ticket',''));pid=str(getattr(row,'identifier','') or '')
            update_signal(signal['signal_id'],mt5_status='SENT',mt5_ticket=ticket,mt5_position_id=pid or None,
                          mt5_symbol=getattr(row,'symbol',None),mt5_volume=getattr(row,'volume',None),monitor_state='WAITING')
            return {'success':True,'reconciled':True,'ticket':ticket,'position_id':pid}
        update_signal(signal['signal_id'],mt5_status='UNKNOWN',monitor_state='BLOCKED',mt5_error='INTERRUPTED_EXECUTION_OUTCOME_UNKNOWN')
        return {'success':False,'unknown':True,'error':'INTERRUPTED_EXECUTION_OUTCOME_UNKNOWN'}
    finally:
        if owned:mt5.shutdown()


def execute_persisted_signal(signal_id,cfg,gateway=None):
    signal=get_signal(signal_id)
    if not signal:return {'success':False,'error':'SIGNAL_NOT_FOUND'}
    status=str(signal.get('mt5_status') or 'NOT_REQUESTED').upper()
    if status in ('SENT','PENDING','OPEN','CLOSED','BLOCKED','FAILED','UNKNOWN'):
        return {'success':status in ('SENT','PENDING','OPEN','CLOSED'),'already_handled':True,'status':status,'error':signal.get('mt5_error')}
    if status=='EXECUTING':return reconcile_interrupted_execution(signal,cfg,gateway)
    if str(signal.get('publication_status') or '').upper()!='SENT':return {'success':False,'error':'TELEGRAM_NOT_CONFIRMED'}
    update_signal(signal_id,mt5_status='EXECUTING',monitor_state='WAITING',mt5_error=None)
    result=MT5Executor(cfg,gateway=gateway).execute(signal)
    common=dict(requested_risk_percent=result.get('requested_risk_percent',signal.get('risk_percent')),
                effective_risk_percent=result.get('effective_risk_percent'),risk_throttle_multiplier=result.get('risk_throttle_multiplier',1.0),
                safety_status=result.get('safety_status'),safety_reasons=result.get('safety_reasons'))
    if result.get('success'):
        update_signal(signal_id,mt5_status='SENT',mt5_ticket=result.get('ticket'),mt5_symbol=result.get('symbol'),mt5_volume=result.get('volume'),
                      mt5_action=result.get('action'),initial_volume=result.get('volume'),last_volume=result.get('volume'),monitor_state='WAITING',**common)
    elif result.get('blocked'):
        update_signal(signal_id,mt5_status='BLOCKED',monitor_state='BLOCKED',mt5_error=result.get('error'),**common)
    else:update_signal(signal_id,mt5_status='FAILED',monitor_state='CANCELED',mt5_error=result.get('error'),**common)
    return result


def resume_ready_signals(cfg,limit=10):
    rows=[s for s in list_signals() if int(s.get('mt5_enabled') or 0) and str(s.get('publication_status') or '').upper()=='SENT' and str(s.get('mt5_status') or '').upper() in ('NOT_REQUESTED','EXECUTING')]
    return [(s['signal_id'],execute_persisted_signal(s['signal_id'],cfg)) for s in rows[:int(limit)]]
