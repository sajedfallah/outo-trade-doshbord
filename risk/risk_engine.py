
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import json

from storage.repo import list_trade_events,list_account_snapshots,get_state,set_state


def _num(v,default=0.0):
    try:return float(v if v is not None else default)
    except Exception:return float(default)


def _state_value(wrapper,default=None):
    if isinstance(wrapper,dict) and 'value' in wrapper:
        return wrapper.get('value',default)
    return wrapper if wrapper is not None else default


def current_loss_streak():
    finals=[e for e in list_trade_events() if e.get('event_type')=='FINAL_CLOSE']
    # list_trade_events is newest-first, which is what streak logic needs.
    streak=0
    for e in finals:
        rt=str(e.get('result_type') or '').upper()
        r=_num(e.get('total_r'))
        loss=(rt in ('SL','LOSS')) or (rt not in ('TP','PROFIT','BREAKEVEN') and r < -0.10)
        be=(rt=='BREAKEVEN') or abs(r)<=0.10
        if loss:
            streak+=1
        else:
            break
    return streak


def _today_baseline(cfg):
    tz=ZoneInfo(cfg.get('analytics',{}).get('timezone','Asia/Tehran'))
    today=datetime.now(tz).date()
    candidates=[]
    for s in list_account_snapshots(5000):
        try:
            dt=datetime.fromisoformat(str(s.get('snapshot_time')))
            if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
            local=dt.astimezone(tz)
            if local.date()==today:
                candidates.append((local,_num(s.get('equity'))))
        except Exception:
            pass
    if not candidates:return None
    return sorted(candidates,key=lambda x:x[0])[0][1]


def _position_risk(mt5,p):
    sl=_num(getattr(p,'sl',0))
    if sl<=0:return None
    typ=mt5.ORDER_TYPE_BUY if int(getattr(p,'type',0))==0 else mt5.ORDER_TYPE_SELL
    try:
        val=mt5.order_calc_profit(typ,str(p.symbol),float(p.volume),float(p.price_open),sl)
        return abs(min(0.0,_num(val)))
    except Exception:
        return None


def manual_kill_switch():
    raw=_state_value(get_state('manual_kill_switch'),{}) or {}
    if not isinstance(raw,dict):raw={}
    return {
        'enabled':bool(raw.get('enabled',False)),
        'reason':str(raw.get('reason') or ''),
        'changed_at':raw.get('changed_at')
    }


def set_manual_kill_switch(enabled,reason='ADMIN'):
    value={'enabled':bool(enabled),'reason':str(reason or 'ADMIN'),'changed_at':datetime.now(timezone.utc).isoformat(timespec='seconds')}
    set_state('manual_kill_switch',value)
    return value


def throttle_multiplier(loss_streak,cfg):
    rcfg=cfg.get('risk_intelligence',{}).get('risk_throttle',{})
    if not cfg.get('risk_intelligence',{}).get('enabled',True) or not rcfg.get('enabled',True):return 1.0
    levels=rcfg.get('loss_streak_levels',{}) or {}
    mult=1.0
    for k,v in levels.items():
        try:
            if int(loss_streak)>=int(k):mult=min(mult,float(v))
        except Exception:pass
    floor=max(0.0,min(1.0,_num(rcfg.get('minimum_multiplier',0.25),0.25)))
    return max(floor,min(1.0,mult))


def evaluate_account_state(mt5,cfg,persist=False):
    ri=cfg.get('risk_intelligence',{})
    enabled=bool(ri.get('enabled',True))
    a=mt5.account_info()
    if a is None:
        state={'enabled':enabled,'status':'RED','allow_new_orders':False,'kill_switch':True,
               'kill_reasons':['ACCOUNT_INFO_FAILED'],'warnings':[],'throttle_multiplier':0.0,
               'loss_streak':current_loss_streak()}
        if persist:set_state('risk_intelligence_state',state)
        return state

    positions=list(mt5.positions_get() or [])
    orders=list(mt5.orders_get() or [])
    equity=_num(a.equity); balance=_num(a.balance)
    open_risk=0.0; unprotected=0
    for p in positions:
        r=_position_risk(mt5,p)
        if r is None:unprotected+=1
        else:open_risk+=r
    open_risk_pct=(open_risk/equity*100.0) if equity>0 else 0.0
    loss_streak=current_loss_streak()
    mult=throttle_multiplier(loss_streak,cfg)
    baseline=_today_baseline(cfg)
    daily_pl=(equity-baseline) if baseline is not None else None

    kill_reasons=[]; warnings=[]
    manual=manual_kill_switch()
    if manual['enabled']:kill_reasons.append('MANUAL_KILL_SWITCH')

    kcfg=ri.get('kill_switch',{})
    if enabled and kcfg.get('enabled',True):
        max_losses=int(kcfg.get('max_consecutive_losses',5) or 5)
        if max_losses>0 and loss_streak>=max_losses:
            kill_reasons.append('MAX_CONSECUTIVE_LOSSES')
        pcfg=cfg.get('prop_firm',{})
        if kcfg.get('use_prop_firm_limits',True) and pcfg.get('enabled',False):
            start=_num(pcfg.get('starting_balance'))
            if start>0:
                max_floor=start*(1-_num(pcfg.get('max_loss_limit_percent',10))/100.0)
                if equity<=max_floor:kill_reasons.append('PROP_MAX_LOSS_LIMIT')
                daily_limit=start*_num(pcfg.get('daily_loss_limit_percent',5))/100.0
                if daily_pl is not None and daily_pl<=-daily_limit:kill_reasons.append('PROP_DAILY_LOSS_LIMIT')
            if daily_pl is None:warnings.append('NO_DAILY_BASELINE')

    scfg=ri.get('pre_trade_safety',{})
    max_slots=int(cfg.get('risk_management',{}).get('max_open_positions',3) or 3)
    if enabled and scfg.get('enabled',True) and scfg.get('enforce_max_open_positions',True):
        if len(positions)+len(orders)>=max_slots:
            warnings.append('MAX_POSITION_SLOTS_REACHED')
    if unprotected:
        if scfg.get('block_unprotected_positions',False):warnings.append('UNPROTECTED_POSITION_BLOCK')
        elif scfg.get('warn_unprotected_positions',True):warnings.append('UNPROTECTED_POSITION')

    kill=bool(kill_reasons)
    blocked=kill
    if enabled and scfg.get('enabled',True):
        if 'MAX_POSITION_SLOTS_REACHED' in warnings or 'UNPROTECTED_POSITION_BLOCK' in warnings:
            blocked=True
    if not enabled:
        # Disabling automatic intelligence never disables an explicit manual emergency stop.
        if manual['enabled']:
            kill=True; blocked=True; mult=1.0
        else:
            kill=False; blocked=False; mult=1.0

    max_open_risk=_num(cfg.get('risk_management',{}).get('max_total_open_risk_percent',4.0),4.0)
    if kill:status='RED'
    elif blocked or mult<1.0 or (max_open_risk>0 and open_risk_pct>=max_open_risk*0.70) or unprotected:status='YELLOW'
    else:status='GREEN'

    state={
        'enabled':enabled,'status':status,'allow_new_orders':not blocked,'kill_switch':kill,
        'kill_reasons':kill_reasons,'warnings':warnings,'throttle_multiplier':mult,
        'loss_streak':loss_streak,'equity':equity,'balance':balance,
        'open_positions':len(positions),'pending_orders':len(orders),'position_slots_used':len(positions)+len(orders),
        'max_position_slots':max_slots,'open_risk_amount':open_risk,'open_risk_pct':open_risk_pct,
        'max_open_risk_pct':max_open_risk,'unprotected_positions':unprotected,
        'daily_start_equity':baseline,'daily_pl':daily_pl,'manual_kill_switch':manual,
        'evaluated_at':datetime.now(timezone.utc).isoformat(timespec='seconds')
    }
    if persist:set_state('risk_intelligence_state',state)
    return state


def validate_projected_risk(mt5,cfg,state,symbol,side,volume,entry,sl):
    ri=cfg.get('risk_intelligence',{})
    scfg=ri.get('pre_trade_safety',{})
    if not ri.get('enabled',True) or not scfg.get('enabled',True) or not scfg.get('enforce_max_total_open_risk',True):
        return {'allow':True,'planned_loss':None,'projected_open_risk_pct':state.get('open_risk_pct',0.0),'reason':None}
    typ=mt5.ORDER_TYPE_BUY if str(side).upper()=='BUY' else mt5.ORDER_TYPE_SELL
    try:calc=mt5.order_calc_profit(typ,symbol,float(volume),float(entry),float(sl))
    except Exception:calc=None
    if calc is None:
        return {'allow':False,'planned_loss':None,'projected_open_risk_pct':None,'reason':'PROJECTED_RISK_CALC_FAILED'}
    planned=abs(min(0.0,_num(calc)))
    equity=_num(state.get('equity'))
    projected=((_num(state.get('open_risk_amount'))+planned)/equity*100.0) if equity>0 else 999.0
    cap=_num(cfg.get('risk_management',{}).get('max_total_open_risk_percent',4.0),4.0)
    return {'allow':projected<=cap+1e-9,'planned_loss':planned,'projected_open_risk_pct':projected,
            'reason':None if projected<=cap+1e-9 else 'MAX_TOTAL_OPEN_RISK'}
