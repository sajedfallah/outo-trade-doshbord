from datetime import datetime,timezone,timedelta
from storage.repo import upsert_trade_metrics,list_signals,list_trade_events
from monitor.event_logic import weighted_exit_price,weighted_r,net_profit

def _iso(ts):
    return datetime.fromtimestamp(int(ts),tz=timezone.utc).astimezone().isoformat(timespec='seconds')

def _dd(x):
    try:return float(x)
    except Exception:return 0.0

def _deal_dict(d):
    return {
        'ticket':str(getattr(d,'ticket','')),
        'position_id':str(getattr(d,'position_id','')),
        'time':int(getattr(d,'time',0) or 0),
        'entry':int(getattr(d,'entry',-1)),
        'volume':_dd(getattr(d,'volume',0)),
        'price':_dd(getattr(d,'price',0)),
        'profit':_dd(getattr(d,'profit',0)),
        'commission':_dd(getattr(d,'commission',0)),
        'swap':_dd(getattr(d,'swap',0)),
        'fee':_dd(getattr(d,'fee',0)),
    }

def compute_trade_metrics(mt5,cfg,signal,chain,exits,total_r=None,total_profit=None,result_type=None):
    entry_in=getattr(mt5,'DEAL_ENTRY_IN',0)
    opens=[d for d in chain if int(d.get('entry',-1))==entry_in]
    if not opens or not exits:
        data={'signal_id':signal['signal_id'],'position_id':signal.get('mt5_position_id'),
              'metric_status':'NO_OPEN_OR_EXIT_DEALS','bars_used':0}
        upsert_trade_metrics(data); return data

    opens=sorted(opens,key=lambda x:x['time']); exits=sorted(exits,key=lambda x:x['time'])
    open_ts=opens[0]['time']; close_ts=exits[-1]['time']
    duration=max(0.0,(close_ts-open_ts)/60.0)
    risk=abs(float(signal.get('entry') or 0)-float(signal.get('sl') or 0))
    symbol=str(signal.get('mt5_symbol') or exits[-1].get('symbol') or signal.get('symbol') or '')
    entry_price=float(signal.get('entry') or weighted_exit_price(opens) or opens[0]['price'])
    bars=[]; status='OK'
    try:
        start=datetime.fromtimestamp(open_ts,tz=timezone.utc)-timedelta(minutes=2)
        end=datetime.fromtimestamp(close_ts,tz=timezone.utc)+timedelta(minutes=2)
        raw=mt5.copy_rates_range(symbol,getattr(mt5,'TIMEFRAME_M1',1),start,end)
        if raw is not None:
            bars=list(raw)
    except Exception as e:
        status=f'BARS_ERROR:{e}'

    mfe=None; mae=None; eff=None
    if risk>0 and bars:
        highs=[float(r['high']) for r in bars]
        lows=[float(r['low']) for r in bars]
        if str(signal.get('direction','BUY')).upper()=='BUY':
            mfe=(max(highs)-entry_price)/risk
            mae=(min(lows)-entry_price)/risk
        else:
            mfe=(entry_price-min(lows))/risk
            mae=(entry_price-max(highs))/risk
        mfe=max(0.0,float(mfe))
        mae=min(0.0,float(mae))
        if mfe>0 and total_r is not None:
            eff=max(0.0,min(150.0,float(total_r)/mfe*100.0))
    elif not bars and status=='OK':
        status='NO_M1_BARS'
    elif risk<=0:
        status='INVALID_RISK_DISTANCE'

    initial=float(signal.get('initial_volume') or signal.get('mt5_volume') or sum(d['volume'] for d in opens) or 0)
    data={
        'signal_id':signal['signal_id'],
        'position_id':str(signal.get('mt5_position_id') or exits[-1].get('position_id') or ''),
        'open_time':_iso(open_ts),'close_time':_iso(close_ts),'duration_minutes':duration,
        'mfe_r':mfe,'mae_r':mae,'exit_efficiency_pct':eff,
        'planned_rr':float(signal.get('rr') or 0),'realized_r':float(total_r or 0),
        'net_profit':float(total_profit or 0),'initial_volume':initial,
        'exit_price':weighted_exit_price(exits),'result_type':result_type,
        'bars_used':len(bars),'metric_status':status
    }
    upsert_trade_metrics(data)
    return data

def backfill_trade_metrics(mt5,cfg):
    exit_entries={getattr(mt5,'DEAL_ENTRY_OUT',1),getattr(mt5,'DEAL_ENTRY_INOUT',2),getattr(mt5,'DEAL_ENTRY_OUT_BY',3)}
    done=0; skipped=0; failed=[]
    for signal in list_signals():
        pid=str(signal.get('mt5_position_id') or signal.get('mt5_ticket') or '')
        if not pid:
            skipped+=1; continue
        try: raw=mt5.history_deals_get(position=int(pid))
        except Exception as e:
            failed.append((signal['signal_id'],str(e))); continue
        chain=[_deal_dict(d) for d in (raw or [])]
        exits=[d for d in chain if d['entry'] in exit_entries]
        if not exits:
            skipped+=1; continue
        initial=float(signal.get('initial_volume') or signal.get('mt5_volume') or 0)
        if initial<=0:
            entry_in=getattr(mt5,'DEAL_ENTRY_IN',0)
            initial=sum(d['volume'] for d in chain if d['entry']==entry_in)
        tr=weighted_r(signal,exits,initial) if initial>0 else 0.0
        profit=net_profit(chain)
        finals=[e for e in list_trade_events(signal['signal_id']) if e.get('event_type')=='FINAL_CLOSE']
        result_type=finals[0].get('result_type') if finals else None
        try:
            compute_trade_metrics(mt5,cfg,signal,chain,exits,tr,profit,result_type)
            done+=1
        except Exception as e:
            failed.append((signal['signal_id'],str(e)))
    return {'ok':len(failed)==0,'updated':done,'skipped':skipped,'failed':failed[:20]}
