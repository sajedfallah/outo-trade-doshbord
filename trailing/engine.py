from __future__ import annotations

import json, math
from datetime import datetime, timezone
from pathlib import Path

from storage.repo import (
    get_signal_trailing_plan, update_signal_trailing_plan, trailing_action_succeeded,
    record_trailing_action, get_trailing_profile, get_trailing_action
)
from monitor.workflow import audit

ROOT=Path(__file__).resolve().parent.parent


def _params(profile_or_plan):
    if not profile_or_plan:return {}
    p=profile_or_plan.get('params')
    if isinstance(p,dict):return p
    plan=profile_or_plan.get('plan')
    if isinstance(plan,dict):
        if isinstance(plan.get('params'),dict):return plan['params']
        return plan
    raw=profile_or_plan.get('params_json') or profile_or_plan.get('plan_json')
    if raw:
        try:return json.loads(raw)
        except Exception:return {}
    return {}


def validate_targets(direction,entry,targets):
    vals=[float(x) for x in targets if x not in (None,'')]
    if not vals:return False,'NO_TARGETS'
    e=float(entry)
    if str(direction).upper()=='BUY':
        if any(x<=e for x in vals):return False,'BUY_TARGET_MUST_BE_ABOVE_ENTRY'
        if any(vals[i+1]<=vals[i] for i in range(len(vals)-1)):return False,'BUY_TARGETS_MUST_ASCEND'
    else:
        if any(x>=e for x in vals):return False,'SELL_TARGET_MUST_BE_BELOW_ENTRY'
        if any(vals[i+1]>=vals[i] for i in range(len(vals)-1)):return False,'SELL_TARGETS_MUST_DESCEND'
    return True,'OK'


def build_signal_plan(signal_id,profile,targets,enabled=True,client_id='ADMIN',overrides=None):
    """Freeze the exact trailing rules for one signal.

    The profile can later be edited without changing historical live-trade rules.
    """
    params=dict(_params(profile))
    if overrides:
        params.update(overrides)
    mode=str(profile.get('mode') or 'MANUAL').upper() if profile else 'MANUAL'
    vals=[float(x) for x in (targets or []) if x not in (None,'')]
    plan={
        'engine_version':'TRAILING_V1',
        'mode':mode,
        'params':params,
        'targets':vals,
        'created_at':datetime.now(timezone.utc).isoformat(timespec='seconds')
    }
    return {
        'signal_id':signal_id,
        'profile_id':profile.get('id') if profile else None,
        'profile_name':profile.get('name') if profile else 'Manual / No Trailing',
        'mode':mode,
        'enabled':bool(enabled and mode!='MANUAL'),
        'targets':vals,
        'plan':plan,
        'current_stage':0,
        'status':'ARMED' if enabled and mode!='MANUAL' else 'OFF',
        'last_error':None,
        'client_id':client_id
    }


def broker_tp_for_plan(signal_tp,plan):
    """Choose the protective broker TP without letting TP1 close a ladder trade."""
    if not plan or not int(plan.get('enabled') or 0):
        return float(signal_tp or 0)
    params=_params(plan)
    mode=str(plan.get('mode') or '').upper()
    broker_mode=str(params.get('broker_tp_mode') or ('LAST_TARGET' if mode=='LADDER' else 'SIGNAL_TP')).upper()
    targets=plan.get('targets') or []
    if broker_mode=='NONE':return 0.0
    if broker_mode=='LAST_TARGET' and targets:return float(targets[-1])
    return float(signal_tp or 0)


def _floor_to_step(raw,vmin,vmax,step):
    raw=min(float(raw),float(vmax))
    if raw<float(vmin)-1e-12:return 0.0
    units=math.floor((raw-float(vmin))/float(step)+1e-12)
    return round(float(vmin)+units*float(step),8)


def _partial_volume(info,current_volume,initial_volume,pct,basis='INITIAL'):
    pct=max(0.0,min(100.0,float(pct or 0)))
    if pct<=0:return 0.0
    base=float(initial_volume if str(basis).upper()=='INITIAL' else current_volume)
    raw=base*pct/100.0
    vol=_floor_to_step(raw,info.volume_min,info.volume_max,info.volume_step)
    current=float(current_volume)
    if vol<=0:return 0.0
    if vol>=current-1e-12:
        # Keep at least broker minimum for a partial-close action. Full closes are
        # intentionally left to the final broker TP/manual close in this engine.
        max_partial=current-float(info.volume_min)
        vol=_floor_to_step(max_partial,info.volume_min,info.volume_max,info.volume_step)
    return max(0.0,min(vol,current))


def _fill_attempts(mt5,request):
    good={getattr(mt5,'TRADE_RETCODE_DONE',10009),getattr(mt5,'TRADE_RETCODE_PLACED',10008)}
    attempts=[]
    for fname in ['ORDER_FILLING_RETURN','ORDER_FILLING_IOC','ORDER_FILLING_FOK']:
        fill=getattr(mt5,fname,None)
        if fill is None:continue
        req=dict(request);req['type_filling']=fill
        res=mt5.order_send(req)
        if res is None:
            attempts.append({'fill':fname,'error':str(mt5.last_error())});continue
        item={'fill':fname,'retcode':int(res.retcode),'comment':str(res.comment)};attempts.append(item)
        if int(res.retcode) in good:return True,res,attempts
    return False,None,attempts


def _close_partial(mt5,cfg,signal,pos,volume,action_key,stage,trigger_price):
    if trailing_action_succeeded(action_key):return {'ok':True,'already_done':True,'changed':False}
    info=mt5.symbol_info(pos.symbol);tick=mt5.symbol_info_tick(pos.symbol)
    if info is None or tick is None:
        err='SYMBOL_OR_TICK_UNAVAILABLE';record_trailing_action({'action_key':action_key,'signal_id':signal['signal_id'],'stage':stage,'action_type':'PARTIAL_CLOSE','trigger_price':trigger_price,'requested_value':volume,'status':'ERROR','error':err});return {'ok':False,'error':err}
    if volume<=0:
        record_trailing_action({'action_key':action_key,'signal_id':signal['signal_id'],'stage':stage,'action_type':'PARTIAL_CLOSE','trigger_price':trigger_price,'requested_value':volume,'executed_value':0,'status':'SKIPPED','error':'VOLUME_BELOW_MINIMUM'})
        return {'ok':True,'skipped':True,'changed':False}
    existing=get_trailing_action(action_key) or {}
    position_id=int(getattr(pos,'identifier',pos.ticket))
    if str(existing.get('status') or '').upper() in ('EXECUTING','UNKNOWN'):
        baseline=set(map(str,(existing.get('metadata') or {}).get('baseline_exit_tickets',[])))
        exit_types={getattr(mt5,'DEAL_ENTRY_OUT',1),getattr(mt5,'DEAL_ENTRY_INOUT',2),getattr(mt5,'DEAL_ENTRY_OUT_BY',3)}
        history=list(mt5.history_deals_get(position=position_id) or [])
        new=[d for d in history if int(getattr(d,'entry',-1)) in exit_types and str(getattr(d,'ticket','')) not in baseline]
        if new:
            executed=sum(float(getattr(d,'volume',0) or 0) for d in new)
            record_trailing_action({'action_key':action_key,'signal_id':signal['signal_id'],'stage':stage,'action_type':'PARTIAL_CLOSE','trigger_price':trigger_price,'requested_value':volume,'executed_value':executed,'status':'CONFIRMED','metadata':{'reconciled':True,'deal_tickets':[str(getattr(d,'ticket','')) for d in new]}})
            return {'ok':True,'reconciled':True,'changed':False,'volume':executed}
        record_trailing_action({'action_key':action_key,'signal_id':signal['signal_id'],'stage':stage,'action_type':'PARTIAL_CLOSE','trigger_price':trigger_price,'requested_value':volume,'status':'UNKNOWN','error':'UNCONFIRMED_AFTER_INTERRUPTION','metadata':existing.get('metadata') or {}})
        return {'ok':False,'error':'UNCONFIRMED_AFTER_INTERRUPTION','manual_reconciliation':True}
    exit_types={getattr(mt5,'DEAL_ENTRY_OUT',1),getattr(mt5,'DEAL_ENTRY_INOUT',2),getattr(mt5,'DEAL_ENTRY_OUT_BY',3)}
    before=list(mt5.history_deals_get(position=position_id) or [])
    baseline=[str(getattr(d,'ticket','')) for d in before if int(getattr(d,'entry',-1)) in exit_types]
    record_trailing_action({'action_key':action_key,'signal_id':signal['signal_id'],'stage':stage,'action_type':'PARTIAL_CLOSE','trigger_price':trigger_price,'requested_value':volume,'status':'EXECUTING','metadata':{'baseline_exit_tickets':baseline,'position_id':str(position_id),'pre_volume':float(pos.volume)}})
    is_buy=int(pos.type)==getattr(mt5,'POSITION_TYPE_BUY',0)
    typ=mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
    price=float(tick.bid if is_buy else tick.ask)
    req={'action':mt5.TRADE_ACTION_DEAL,'symbol':pos.symbol,'position':int(pos.ticket),'volume':float(volume),'type':typ,
         'price':round(price,int(info.digits)),'deviation':int(cfg.get('trading',{}).get('deviation_points',50)),
         'magic':int(cfg.get('trading',{}).get('magic_number',320032)),'comment':f"NEXUS TRAIL {signal['signal_id']}",'type_time':mt5.ORDER_TIME_GTC}
    ok,res,attempts=_fill_attempts(mt5,req)
    if ok:
        record_trailing_action({'action_key':action_key,'signal_id':signal['signal_id'],'stage':stage,'action_type':'PARTIAL_CLOSE','trigger_price':trigger_price,'requested_value':volume,'executed_value':float(volume),'status':'CONFIRMED','metadata':{'attempts':attempts,'deal':str(getattr(res,'deal','')),'baseline_exit_tickets':baseline}})
        audit(signal['signal_id'],'TRAILING_MANAGEMENT','DONE',action_key,source='TRAILING_ENGINE',detail=f'Partial close {volume:g} at stage {stage}',mt5_ticket=signal.get('mt5_ticket'),position_id=str(getattr(pos,'identifier',pos.ticket)),metadata={'action':'PARTIAL_CLOSE','volume':volume,'stage':stage})
        return {'ok':True,'changed':True,'volume':float(volume),'attempts':attempts}
    err='PARTIAL_CLOSE_REJECTED'
    record_trailing_action({'action_key':action_key,'signal_id':signal['signal_id'],'stage':stage,'action_type':'PARTIAL_CLOSE','trigger_price':trigger_price,'requested_value':volume,'status':'ERROR','error':err,'metadata':{'attempts':attempts}})
    return {'ok':False,'error':err,'attempts':attempts}


def _is_improvement(direction,current_sl,new_sl):
    cur=float(current_sl or 0);new=float(new_sl or 0)
    if new<=0:return False
    if cur<=0:return True
    return new>cur+1e-12 if str(direction).upper()=='BUY' else new<cur-1e-12


def _modify_sl(mt5,cfg,signal,pos,new_sl,action_key,stage,trigger_price,continuous=False):
    if not continuous and trailing_action_succeeded(action_key):return {'ok':True,'already_done':True,'changed':False}
    info=mt5.symbol_info(pos.symbol);tick=mt5.symbol_info_tick(pos.symbol)
    if info is None or tick is None:return {'ok':False,'error':'SYMBOL_OR_TICK_UNAVAILABLE'}
    digits=int(info.digits);point=float(info.point or 0)
    stops=float(getattr(info,'trade_stops_level',0) or 0)*point
    freeze=float(getattr(info,'trade_freeze_level',0) or 0)*point
    protected_distance=max(stops,freeze)
    direction=str(signal.get('direction','')).upper();desired=float(new_sl)
    market=float(tick.bid if direction=='BUY' else tick.ask)
    # Never send an invalid SL inside the broker stop-distance. Continuous
    # trailing is clamped; discrete BE/TP locks wait and retry if too close.
    if direction=='BUY':max_sl=market-protected_distance;valid=desired<market and (protected_distance<=0 or desired<=max_sl+point*0.1)
    else:min_sl=market+protected_distance;valid=desired>market and (protected_distance<=0 or desired>=min_sl-point*0.1)
    if not valid:
        err='SL_TOO_CLOSE_TO_MARKET'
        record_trailing_action({'action_key':action_key,'signal_id':signal['signal_id'],'stage':stage,'action_type':'MOVE_SL','trigger_price':trigger_price,'requested_value':desired,'status':'WAITING','error':err,'metadata':{'market':market,'stops_distance':stops,'freeze_distance':freeze}})
        return {'ok':False,'retry':True,'error':err}
    desired=round(desired,digits)
    existing=get_trailing_action(action_key) or {}
    if str(existing.get('status') or '').upper() in ('EXECUTING','UNKNOWN'):
        actual=float(getattr(pos,'sl',0) or 0)
        if abs(actual-desired)<=max(point*.5,1e-12):
            record_trailing_action({'action_key':action_key,'signal_id':signal['signal_id'],'stage':stage,'action_type':'MOVE_SL','trigger_price':trigger_price,'requested_value':desired,'executed_value':actual,'status':'CONFIRMED','metadata':{'reconciled':True}})
            return {'ok':True,'changed':False,'reconciled':True,'sl':actual}
        return {'ok':False,'error':'UNCONFIRMED_SL_AFTER_INTERRUPTION','manual_reconciliation':True}
    if not _is_improvement(direction,float(getattr(pos,'sl',0) or 0),desired):
        if not continuous:
            record_trailing_action({'action_key':action_key,'signal_id':signal['signal_id'],'stage':stage,'action_type':'MOVE_SL','trigger_price':trigger_price,'requested_value':desired,'executed_value':float(getattr(pos,'sl',0) or 0),'status':'DONE','metadata':{'reason':'ALREADY_PROTECTED'}})
        return {'ok':True,'changed':False,'already_protected':True,'sl':float(getattr(pos,'sl',0) or 0)}
    record_trailing_action({'action_key':action_key,'signal_id':signal['signal_id'],'stage':stage,'action_type':'MOVE_SL','trigger_price':trigger_price,'requested_value':desired,'status':'EXECUTING','metadata':{'previous_sl':float(getattr(pos,'sl',0) or 0),'position_id':str(getattr(pos,'identifier',pos.ticket))}})
    req={'action':mt5.TRADE_ACTION_SLTP,'symbol':pos.symbol,'position':int(pos.ticket),'sl':desired,'tp':float(getattr(pos,'tp',0) or 0)}
    res=mt5.order_send(req)
    good={getattr(mt5,'TRADE_RETCODE_DONE',10009),getattr(mt5,'TRADE_RETCODE_NO_CHANGES',10025)}
    if res is not None and int(res.retcode) in good:
        record_trailing_action({'action_key':action_key,'signal_id':signal['signal_id'],'stage':stage,'action_type':'MOVE_SL','trigger_price':trigger_price,'requested_value':desired,'executed_value':desired,'status':'CONFIRMED','metadata':{'retcode':int(res.retcode),'comment':str(res.comment)}})
        audit(signal['signal_id'],'TRAILING_MANAGEMENT','DONE',action_key,source='TRAILING_ENGINE',detail=f'SL -> {desired:g} at stage {stage}',mt5_ticket=signal.get('mt5_ticket'),position_id=str(getattr(pos,'identifier',pos.ticket)),metadata={'action':'MOVE_SL','sl':desired,'stage':stage})
        return {'ok':True,'changed':True,'sl':desired}
    err=f"SL_MODIFY_REJECTED {getattr(res,'retcode',None)} {getattr(res,'comment','') if res else mt5.last_error()}"
    record_trailing_action({'action_key':action_key,'signal_id':signal['signal_id'],'stage':stage,'action_type':'MOVE_SL','trigger_price':trigger_price,'requested_value':desired,'status':'ERROR','error':err})
    return {'ok':False,'error':err}


def _crossed(mt5,pos,direction,target,since_time=None):
    tick=mt5.symbol_info_tick(pos.symbol)
    if tick is None:return False,None
    current=float(tick.bid if str(direction).upper()=='BUY' else tick.ask)
    high=low=current
    try:
        rates=mt5.copy_rates_from_pos(pos.symbol,getattr(mt5,'TIMEFRAME_M1'),0,1)
        if rates is not None and len(rates):
            bar=rates[-1];bar_time=int(bar['time']);pos_time=int(getattr(pos,'time',0) or 0)
            # Only use the current M1 high/low when the position was already open
            # at the start of that candle. This avoids a false TP hit caused by a
            # high/low that happened earlier in the same candle before entry.
            if pos_time<=0 or pos_time<=bar_time:
                high=max(high,float(bar['high']));low=min(low,float(bar['low']))
    except Exception:pass
    if since_time:
        try:
            start=datetime.fromisoformat(str(since_time).replace('Z','+00:00'))
            if start.tzinfo is None:start=start.replace(tzinfo=timezone.utc)
            rows=mt5.copy_rates_range(pos.symbol,getattr(mt5,'TIMEFRAME_M1'),start,datetime.now(timezone.utc))
            if rows is not None and len(rows):
                high=max(high,max(float(x['high']) for x in rows));low=min(low,min(float(x['low']) for x in rows))
        except Exception:pass
    hit=(high>=float(target)) if str(direction).upper()=='BUY' else (low<=float(target))
    return bool(hit),current


def _current_r(mt5,pos,signal):
    tick=mt5.symbol_info_tick(pos.symbol)
    if tick is None:return None,None
    direction=str(signal.get('direction','')).upper();entry=float(signal.get('entry') or 0);sl=float(signal.get('sl') or 0);risk=abs(entry-sl)
    if risk<=0:return None,None
    price=float(tick.bid if direction=='BUY' else tick.ask)
    r=(price-entry)/risk if direction=='BUY' else (entry-price)/risk
    return float(r),price


def _r_to_price(signal,lock_r):
    direction=str(signal.get('direction','')).upper();entry=float(signal.get('entry') or 0);risk=abs(entry-float(signal.get('sl') or 0))
    return entry+float(lock_r)*risk if direction=='BUY' else entry-float(lock_r)*risk


def _atr(mt5,symbol,timeframe='M5',period=14):
    tf=getattr(mt5,'TIMEFRAME_'+str(timeframe).upper(),getattr(mt5,'TIMEFRAME_M5'))
    rates=mt5.copy_rates_from_pos(symbol,tf,0,max(int(period)+2,20))
    if rates is None or len(rates)<int(period)+1:return None
    trs=[];prev=None
    for r in rates:
        h=float(r['high']);l=float(r['low']);c=float(r['close'])
        tr=h-l if prev is None else max(h-l,abs(h-prev),abs(l-prev));trs.append(tr);prev=c
    vals=trs[-int(period):]
    return sum(vals)/len(vals) if vals else None


def _process_ladder(mt5,cfg,signal,pos,plan,params):
    targets=[float(x) for x in (plan.get('targets') or [])]
    if len(targets)<int(params.get('min_targets',2)):
        return {'ok':False,'error':'LADDER_REQUIRES_MORE_TARGETS','changed':False}
    hard_final=bool(params.get('hard_final_target',True))
    managed=len(targets)-1 if hard_final and len(targets)>1 else len(targets)
    current=int(plan.get('current_stage') or 0);changed=False;messages=[]
    initial=float(signal.get('initial_volume') or signal.get('mt5_volume') or getattr(pos,'volume',0) or 0)
    first_pct=float(params.get('first_partial_percent',50.0));basis=params.get('close_percent_basis','INITIAL')
    for idx in range(current,managed):
        stage=idx+1;target=targets[idx]
        hit,market=_crossed(mt5,pos,signal.get('direction'),target,plan.get('created_at'))
        if not hit:break
        close_pct=first_pct if stage==1 else float((params.get('stage_close_percent') or {}).get(str(stage),0.0))
        if close_pct>0:
            info=mt5.symbol_info(pos.symbol);vol=_partial_volume(info,float(pos.volume),initial,close_pct,basis)
            key=f"{signal['signal_id']}:TRAIL:{stage}:PARTIAL"
            r=_close_partial(mt5,cfg,signal,pos,vol,key,stage,target)
            if not r.get('ok'):
                update_signal_trailing_plan(signal['signal_id'],status='ERROR',last_error=r.get('error'));return {'ok':False,'error':r.get('error'),'changed':changed}
            changed=changed or r.get('changed',False);messages.append(f'TP{stage} partial {vol:g}')
            # Refresh live position after a real partial close.
            if r.get('changed'):
                rows=list(mt5.positions_get(ticket=int(pos.ticket)) or [])
                if rows:pos=rows[0]
        desired=float(signal.get('entry')) if stage==1 else targets[stage-2]
        key=f"{signal['signal_id']}:TRAIL:{stage}:SL"
        r=_modify_sl(mt5,cfg,signal,pos,desired,key,stage,target)
        if not r.get('ok'):
            if r.get('retry'):
                update_signal_trailing_plan(signal['signal_id'],status='ACTIVE',last_error=r.get('error'));return {'ok':True,'retry':True,'changed':changed,'stage':stage}
            update_signal_trailing_plan(signal['signal_id'],status='ERROR',last_error=r.get('error'));return {'ok':False,'error':r.get('error'),'changed':changed}
        changed=changed or r.get('changed',False);messages.append(f'SL->{desired:g}')
        current=stage
        update_signal_trailing_plan(signal['signal_id'],current_stage=current,status='ACTIVE',last_error=None)
        # Re-fetch the current position for a possible immediately-crossed next stage.
        rows=list(mt5.positions_get(ticket=int(pos.ticket)) or [])
        if rows:pos=rows[0]
        else:break
    return {'ok':True,'changed':changed,'current_stage':current,'messages':messages}


def _process_r_based(mt5,cfg,signal,pos,plan,params):
    stages=list(params.get('stages') or []);current=int(plan.get('current_stage') or 0);changed=False
    current_r,price=_current_r(mt5,pos,signal)
    if current_r is None:return {'ok':False,'error':'NO_TICK_OR_INVALID_RISK','changed':False}
    initial=float(signal.get('initial_volume') or signal.get('mt5_volume') or getattr(pos,'volume',0) or 0)
    for idx in range(current,len(stages)):
        s=stages[idx];stage=idx+1;trigger=float(s.get('trigger_r',0))
        if current_r+1e-12<trigger:break
        pct=float(s.get('close_percent',0) or 0)
        if pct>0:
            info=mt5.symbol_info(pos.symbol);vol=_partial_volume(info,float(pos.volume),initial,pct,s.get('close_percent_basis','INITIAL'))
            key=f"{signal['signal_id']}:TRAILR:{stage}:PARTIAL"
            rr=_close_partial(mt5,cfg,signal,pos,vol,key,stage,price)
            if not rr.get('ok'):update_signal_trailing_plan(signal['signal_id'],status='ERROR',last_error=rr.get('error'));return {'ok':False,'error':rr.get('error'),'changed':changed}
            changed=changed or rr.get('changed',False)
            if rr.get('changed'):
                rows=list(mt5.positions_get(ticket=int(pos.ticket)) or [])
                if rows:pos=rows[0]
        desired=_r_to_price(signal,float(s.get('lock_r',0)))
        key=f"{signal['signal_id']}:TRAILR:{stage}:SL"
        rr=_modify_sl(mt5,cfg,signal,pos,desired,key,stage,price)
        if not rr.get('ok'):
            if rr.get('retry'):return {'ok':True,'retry':True,'changed':changed}
            update_signal_trailing_plan(signal['signal_id'],status='ERROR',last_error=rr.get('error'));return {'ok':False,'error':rr.get('error'),'changed':changed}
        changed=changed or rr.get('changed',False);current=stage
        update_signal_trailing_plan(signal['signal_id'],current_stage=current,status='ACTIVE',last_error=None)
    return {'ok':True,'changed':changed,'current_stage':current,'current_r':current_r}


def _process_fixed_r(mt5,cfg,signal,pos,plan,params):
    current_r,price=_current_r(mt5,pos,signal)
    if current_r is None:return {'ok':False,'error':'NO_TICK_OR_INVALID_RISK','changed':False}
    activation=float(params.get('activation_r',1.0));dist=float(params.get('trail_distance_r',0.5));step=float(params.get('step_r',0.1))
    if current_r<activation:return {'ok':True,'changed':False,'current_r':current_r}
    lock_r=current_r-dist
    desired=_r_to_price(signal,lock_r)
    entry=float(signal.get('entry'));risk=abs(entry-float(signal.get('sl')))
    current_sl=float(getattr(pos,'sl',0) or 0)
    if current_sl>0 and risk>0:
        cur_lock=(current_sl-entry)/risk if signal.get('direction')=='BUY' else (entry-current_sl)/risk
        if lock_r<cur_lock+step:return {'ok':True,'changed':False,'current_r':current_r}
    bucket=int(math.floor(max(lock_r,0)/max(step,0.0001)))
    key=f"{signal['signal_id']}:FIXEDR:SL:{bucket}"
    rr=_modify_sl(mt5,cfg,signal,pos,desired,key,bucket,price,continuous=True)
    if rr.get('ok'):
        update_signal_trailing_plan(signal['signal_id'],status='ACTIVE',last_error=None)
        return {'ok':True,'changed':rr.get('changed',False),'current_r':current_r,'desired_sl':desired}
    return {'ok':False,'error':rr.get('error'),'changed':False}


def _process_atr(mt5,cfg,signal,pos,plan,params):
    current_r,price=_current_r(mt5,pos,signal)
    if current_r is None:return {'ok':False,'error':'NO_TICK_OR_INVALID_RISK','changed':False}
    if current_r<float(params.get('activation_r',1.0)):return {'ok':True,'changed':False,'current_r':current_r}
    atr=_atr(mt5,pos.symbol,params.get('timeframe','M5'),int(params.get('atr_period',14)))
    if not atr:return {'ok':False,'error':'ATR_UNAVAILABLE','changed':False}
    mult=float(params.get('atr_multiplier',2.0));direction=str(signal.get('direction','')).upper()
    desired=price-atr*mult if direction=='BUY' else price+atr*mult
    info=mt5.symbol_info(pos.symbol);point=float(info.point or 0) if info else 0.00001
    bucket=int(round(desired/max(point,1e-12)))
    key=f"{signal['signal_id']}:ATR:SL:{bucket}"
    rr=_modify_sl(mt5,cfg,signal,pos,desired,key,bucket,price,continuous=True)
    if rr.get('ok'):
        update_signal_trailing_plan(signal['signal_id'],status='ACTIVE',last_error=None)
        return {'ok':True,'changed':rr.get('changed',False),'current_r':current_r,'atr':atr,'desired_sl':desired}
    return {'ok':False,'error':rr.get('error'),'changed':False}


def process_trailing(mt5,cfg,signal,pos,logger=None):
    """Execute one safe, idempotent trailing-management pass for a live position."""
    if not cfg.get('trailing',{}).get('enabled',True):return {'ok':True,'enabled':False,'changed':False,'status':'GLOBALLY_DISABLED'}
    plan=get_signal_trailing_plan(signal['signal_id'])
    if not plan or not int(plan.get('enabled') or 0):return {'ok':True,'enabled':False,'changed':False}
    if str(plan.get('status') or '').upper() in ('COMPLETE','OFF','CANCELED'):return {'ok':True,'enabled':True,'changed':False,'status':plan.get('status')}
    params=_params(plan);mode=str(plan.get('mode') or 'MANUAL').upper()
    if str(plan.get('status') or '').upper()=='ARMED':
        update_signal_trailing_plan(signal['signal_id'],status='MONITORING',last_error=None)
        plan=dict(plan);plan['status']='MONITORING'
    try:
        if mode=='LADDER':out=_process_ladder(mt5,cfg,signal,pos,plan,params)
        elif mode=='R_BASED':out=_process_r_based(mt5,cfg,signal,pos,plan,params)
        elif mode=='FIXED_R':out=_process_fixed_r(mt5,cfg,signal,pos,plan,params)
        elif mode=='ATR':out=_process_atr(mt5,cfg,signal,pos,plan,params)
        else:out={'ok':True,'changed':False,'mode':mode}
        if logger and (out.get('changed') or not out.get('ok')):
            logger(f"{signal['signal_id']} TRAILING mode={mode} changed={out.get('changed')} stage={out.get('current_stage')} error={out.get('error')}")
        return {'enabled':True,'mode':mode,**out}
    except Exception as e:
        update_signal_trailing_plan(signal['signal_id'],status='ERROR',last_error=str(e))
        record_trailing_action({'action_key':f"{signal['signal_id']}:TRAIL:ENGINE_ERROR:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",'signal_id':signal['signal_id'],'stage':plan.get('current_stage'),'action_type':'ENGINE_ERROR','status':'ERROR','error':str(e)})
        if logger:logger(f"{signal['signal_id']} TRAILING ERROR {e}")
        return {'ok':False,'enabled':True,'mode':mode,'changed':False,'error':str(e)}
