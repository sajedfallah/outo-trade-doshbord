from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import math,re
import pandas as pd

ROOT=Path(__file__).resolve().parent.parent

def _num(x,default=0.0):
    try:return float(x if x is not None else default)
    except Exception:return float(default)

def _pct(a,b):
    return (float(a)/float(b)*100.0) if b else 0.0

def _classify_result(row):
    rt=str(row.get('result_type') or '').upper()
    r=_num(row.get('total_r'))
    if rt in ('TP','PROFIT'):return 'WIN'
    if rt in ('SL','LOSS'):return 'LOSS'
    if rt=='BREAKEVEN' or abs(r)<=0.10:return 'BE'
    return 'WIN' if r>0 else ('LOSS' if r<0 else 'BE')

def mt5_snapshot(cfg,signals=None):
    out={
        'connected':False,'balance':0.0,'equity':0.0,'margin':0.0,
        'free_margin':0.0,'floating_pl':0.0,'current_drawdown_pct':0.0,
        'open_positions':0,'pending_orders':0,'positions':[],
        'nexus_open_risk':0.0,'nexus_open_risk_pct':0.0,'unprotected_positions':0
    }
    try:
        import MetaTrader5 as mt5
        path=cfg['mt5'].get('terminal_path','')
        ok=mt5.initialize(path=path) if path else mt5.initialize()
        if not ok:
            out['error']=f'MT5 initialize failed: {mt5.last_error()}'; return out
        a=mt5.account_info()
        if a is None:
            out['error']=f'account_info failed: {mt5.last_error()}'; return out
        positions=list(mt5.positions_get() or []); orders=list(mt5.orders_get() or [])
        balance=_num(a.balance); equity=_num(a.equity); floating=equity-balance
        dd=((balance-equity)/balance*100.0) if balance>0 and equity<balance else 0.0
        sigs=signals or []
        by_pid={str(s.get('mt5_position_id')):s for s in sigs if s.get('mt5_position_id')}
        by_ticket={str(s.get('mt5_ticket')):s for s in sigs if s.get('mt5_ticket')}
        risk_total=0.0; unprotected=0; pos=[]
        for p in positions:
            pid=str(getattr(p,'identifier',p.ticket)); ticket=str(p.ticket)
            comment=str(getattr(p,'comment',''))
            sig=by_pid.get(pid) or by_ticket.get(ticket)
            if not sig:
                m=re.search(r'NEXUS\s+(NX-\d+)',comment,re.I)
                if m:
                    sig=next((s for s in sigs if s.get('signal_id','').upper()==m.group(1).upper()),None)
            nexus_id=sig.get('signal_id') if sig else ''
            order_type=mt5.ORDER_TYPE_BUY if int(p.type)==0 else mt5.ORDER_TYPE_SELL
            risk_to_sl=None; reward_to_tp=None
            if _num(p.sl)>0:
                try:
                    v=mt5.order_calc_profit(order_type,p.symbol,float(p.volume),float(p.price_open),float(p.sl))
                    risk_to_sl=abs(min(0.0,_num(v)))
                    if sig: risk_total+=risk_to_sl
                except Exception: pass
            else:
                unprotected+=1
            if _num(p.tp)>0:
                try:
                    v=mt5.order_calc_profit(order_type,p.symbol,float(p.volume),float(p.price_open),float(p.tp))
                    reward_to_tp=max(0.0,_num(v))
                except Exception: pass
            floating_r=None
            if sig:
                dist=abs(_num(sig.get('entry'))-_num(sig.get('sl')))
                if dist>0:
                    move=(_num(p.price_current)-_num(sig.get('entry'))) if str(sig.get('direction')).upper()=='BUY' else (_num(sig.get('entry'))-_num(p.price_current))
                    floating_r=move/dist
            pos.append({
                'NEXUS':nexus_id or 'ACCOUNT','Ticket':ticket,'Position ID':pid,
                'Symbol':str(p.symbol),'Type':'BUY' if int(p.type)==0 else 'SELL',
                'Volume':_num(p.volume),'Open':_num(p.price_open),'Current':_num(p.price_current),
                'SL':_num(p.sl),'TP':_num(p.tp),'P/L':_num(p.profit),
                'Risk→SL':risk_to_sl,'Reward→TP':reward_to_tp,'Floating R':floating_r,
                'Comment':comment
            })
        out.update({
            'connected':True,'login':str(a.login),'server':str(a.server),'balance':balance,
            'equity':equity,'margin':_num(a.margin),'free_margin':_num(a.margin_free),
            'floating_pl':floating,'current_drawdown_pct':dd,'open_positions':len(positions),
            'pending_orders':len(orders),'positions':pos,'nexus_open_risk':risk_total,
            'nexus_open_risk_pct':_pct(risk_total,equity),'unprotected_positions':unprotected
        })
        return out
    except Exception as e:
        out['error']=str(e); return out
    finally:
        try:mt5.shutdown()
        except Exception:pass


def _utc_datetime_series(values,index):
    """Return a guaranteed tz-aware UTC datetime Series.

    NEXUS databases can contain a mixture of SQLite CURRENT_TIMESTAMP values
    (tz-naive but semantically UTC) and newer ISO values with explicit offsets.
    Pandas .dt.tz_convert() cannot operate on a tz-naive Series, so normalize
    element-by-element before any local timezone conversion.
    """
    if values is None:
        return pd.Series(pd.NaT,index=index,dtype="datetime64[ns, UTC]")

    out=[]
    for value in values:
        if value is None or (isinstance(value,float) and pd.isna(value)):
            out.append(pd.NaT)
            continue
        try:
            ts=pd.Timestamp(value)
            if pd.isna(ts):
                out.append(pd.NaT)
            elif ts.tzinfo is None:
                out.append(ts.tz_localize("UTC"))
            else:
                out.append(ts.tz_convert("UTC"))
        except Exception:
            out.append(pd.NaT)
    return pd.Series(out,index=index,dtype="datetime64[ns, UTC]")

def _merged_trades(signals,events,metrics=None,notes=None,cfg=None):
    sigdf=pd.DataFrame(signals or []); evdf=pd.DataFrame(events or [])
    if evdf.empty or 'event_type' not in evdf.columns:
        return pd.DataFrame()
    finals=evdf[evdf['event_type']=='FINAL_CLOSE'].copy()
    if finals.empty:return finals
    finals['event_time_dt']=_utc_datetime_series(finals.get('event_time'),finals.index)
    finals['total_profit']=pd.to_numeric(finals.get('total_profit'),errors='coerce').fillna(0.0)
    finals['total_r']=pd.to_numeric(finals.get('total_r'),errors='coerce').fillna(0.0)
    if not sigdf.empty:
        cols=[c for c in ['signal_id','symbol','direction','timeframe','rr','risk_percent','lot','mt5_status','mt5_action','setup_tag','strategy_version','created_at','entry','tp','sl','requested_risk_percent','effective_risk_percent','risk_throttle_multiplier','safety_status','safety_reasons'] if c in sigdf.columns]
        finals=finals.merge(sigdf[cols].drop_duplicates('signal_id'),on='signal_id',how='left')
    mdf=pd.DataFrame(metrics or [])
    if not mdf.empty and 'signal_id' in mdf.columns:
        keep=[c for c in ['signal_id','duration_minutes','mfe_r','mae_r','exit_efficiency_pct','metric_status','bars_used'] if c in mdf.columns]
        finals=finals.merge(mdf[keep].drop_duplicates('signal_id'),on='signal_id',how='left')
    ndf=pd.DataFrame(notes or [])
    if not ndf.empty and 'signal_id' in ndf.columns:
        keep=[c for c in ['signal_id','grade','mistake_tag','note'] if c in ndf.columns]
        finals=finals.merge(ndf[keep].drop_duplicates('signal_id'),on='signal_id',how='left')
    finals['Result']=finals.apply(_classify_result,axis=1)
    finals['created_at_dt']=_utc_datetime_series(finals.get('created_at'),finals.index)
    tz=ZoneInfo((cfg or {}).get('analytics',{}).get('timezone','Asia/Tehran'))
    finals['close_local']=finals['event_time_dt'].dt.tz_convert(tz)
    finals['entry_local']=finals['created_at_dt'].dt.tz_convert(tz)
    finals['date']=finals['close_local'].dt.date
    finals['weekday']=finals['close_local'].dt.day_name()
    finals['hour']=finals['entry_local'].dt.hour
    finals['session']=finals['created_at_dt'].apply(lambda x:_session_for(x,(cfg or {}).get('analytics',{}).get('sessions_utc',[])))
    return finals.sort_values(['event_time_dt','id'],na_position='last')

def _session_for(dt,sessions):
    if pd.isna(dt):return 'UNKNOWN'
    h=int(dt.hour)
    for s in sessions:
        start=int(s.get('start',0)); end=int(s.get('end',24))
        if start<=h<end:return str(s.get('name','SESSION'))
    return 'OTHER'

def _group_stats(df,col):
    if df.empty or col not in df.columns:return pd.DataFrame(columns=[col,'Trades','Win Rate','P/L','Avg R','PF'])
    rows=[]
    for k,g in df.groupby(col,dropna=False):
        gp=float(g.loc[g['total_profit']>0,'total_profit'].sum()); gl=abs(float(g.loc[g['total_profit']<0,'total_profit'].sum()))
        pf=gp/gl if gl>0 else (math.inf if gp>0 else 0.0)
        wins=int((g['Result']=='WIN').sum()); decisive=int(g['Result'].isin(['WIN','LOSS']).sum())
        rows.append({col:'Unknown' if pd.isna(k) else k,'Trades':len(g),'Win Rate':_pct(wins,decisive),'P/L':float(g['total_profit'].sum()),'Avg R':float(g['total_r'].mean()),'PF':pf})
    out=pd.DataFrame(rows)
    return out.sort_values('P/L',ascending=False)

def rule_compliance_row(row,cfg,manual_ids=None):
    score=0; flags=[]
    direction=str(row.get('direction') or '').upper(); entry=_num(row.get('entry')); tp=_num(row.get('tp')); sl=_num(row.get('sl'))
    geometry=(sl<entry<tp) if direction=='BUY' else ((tp<entry<sl) if direction=='SELL' else False)
    if geometry:score+=25
    else:flags.append('GEOMETRY')
    min_rr=_num(cfg.get('risk_management',{}).get('min_reward_risk',1.0),1.0)
    if _num(row.get('rr'))>=min_rr:score+=25
    else:flags.append('RR')
    rp=row.get('risk_percent'); max_risk=_num(cfg.get('risk_management',{}).get('max_risk_percent_per_trade',2.0),2.0)
    if pd.isna(rp) or rp is None or _num(rp)<=max_risk:score+=25
    else:flags.append('RISK')
    if str(row.get('mt5_status') or '').upper()!='FAILED':score+=15
    else:flags.append('EXECUTION')
    if row.get('signal_id') not in (manual_ids or set()):score+=10
    else:flags.append('MANUAL_OVERRIDE')
    return score,','.join(flags) if flags else 'OK'

def _streaks(results):
    best_win=best_loss=cur_w=cur_l=0
    for r in results:
        if r=='WIN':cur_w+=1;cur_l=0;best_win=max(best_win,cur_w)
        elif r=='LOSS':cur_l+=1;cur_w=0;best_loss=max(best_loss,cur_l)
        else:cur_w=cur_l=0
    current=0; current_type='NONE'
    for r in reversed(list(results)):
        if r not in ('WIN','LOSS'):break
        if current_type=='NONE':current_type=r
        if r!=current_type:break
        current+=1
    return {'best_win_streak':best_win,'best_loss_streak':best_loss,'current_streak':current,'current_streak_type':current_type}

def performance(signals,events,metrics=None,notes=None,cfg=None,manual_results=None):
    trades=_merged_trades(signals,events,metrics,notes,cfg)
    partials=[e for e in (events or []) if e.get('event_type')=='PARTIAL_CLOSE']
    if trades.empty:
        empty=pd.DataFrame()
        return {'total_trades':0,'wins':0,'losses':0,'breakeven':0,'win_rate':0.0,'net_profit':0.0,'gross_profit':0.0,'gross_loss':0.0,'profit_factor':0.0,'avg_r':0.0,'best_r':0.0,'worst_r':0.0,'max_drawdown':0.0,'max_drawdown_r':0.0,'current_drawdown_r':0.0,'partial_events':len(partials),'curve':empty,'symbol':empty,'trades':empty,'daily':empty,'direction':empty,'timeframe':empty,'weekday':empty,'hour':empty,'session':empty,'setup':empty,'strategy':empty,'expectancy_r':0.0,'avg_win_r':0.0,'avg_loss_r':0.0,'payoff_ratio':0.0,'consistency_score':0.0,'recovery_factor':0.0,'profitable_days':0,'loss_days':0,'streaks':_streaks([]),'compliance_avg':0.0,'nexus_score':0.0,'score_components':{},'risk_health':'GREEN'}
    wins=int((trades['Result']=='WIN').sum()); losses=int((trades['Result']=='LOSS').sum()); be=int((trades['Result']=='BE').sum()); decisive=wins+losses
    net=float(trades['total_profit'].sum()); gp=float(trades.loc[trades['total_profit']>0,'total_profit'].sum()); gl=abs(float(trades.loc[trades['total_profit']<0,'total_profit'].sum()))
    pf=gp/gl if gl>0 else (math.inf if gp>0 else 0.0)
    cumulative=trades['total_profit'].cumsum(); peak=cumulative.cummax(); dd=cumulative-peak
    cumr=trades['total_r'].cumsum(); peakr=cumr.cummax(); ddr=cumr-peakr
    curve=pd.DataFrame({'Trade':trades['signal_id'].astype(str).values,'Cumulative P/L':cumulative.values,'Cumulative R':cumr.values,'Drawdown':dd.values,'Drawdown R':ddr.values})
    daily=trades.groupby('date',dropna=False).agg(**{'P/L':('total_profit','sum'),'R':('total_r','sum'),'Trades':('signal_id','count')}).reset_index()
    for result,label in [('WIN','Wins'),('LOSS','Losses'),('BE','BE')]:
        cnt=trades[trades['Result']==result].groupby('date').size()
        daily[label]=daily['date'].map(cnt).fillna(0).astype(int)
    profitable_days=int((daily['P/L']>0).sum()); loss_days=int((daily['P/L']<0).sum())
    positive_day_ratio=_pct(profitable_days,profitable_days+loss_days) if profitable_days+loss_days else 0.0
    concentration=(float(trades['total_profit'].max())/gp) if gp>0 else 1.0
    consistency=max(0.0,min(100.0,0.65*positive_day_ratio+35.0*(1.0-min(1.0,max(0.0,concentration)))))
    avg_win_r=float(trades.loc[trades['Result']=='WIN','total_r'].mean()) if wins else 0.0
    avg_loss_r=float(trades.loc[trades['Result']=='LOSS','total_r'].mean()) if losses else 0.0
    payoff=abs(avg_win_r/avg_loss_r) if avg_loss_r else (math.inf if avg_win_r>0 else 0.0)
    expectancy=float(trades['total_r'].mean())
    max_dd=abs(float(dd.min())) if len(dd) else 0.0; max_dd_r=abs(float(ddr.min())) if len(ddr) else 0.0; current_dd_r=abs(float(ddr.iloc[-1])) if len(ddr) else 0.0
    recovery=net/max_dd if max_dd>0 else (math.inf if net>0 else 0.0)
    manual_ids={str(x.get('signal_id')) for x in (manual_results or [])}
    scores=[]; flags=[]
    for _,row in trades.iterrows():
        s,f=rule_compliance_row(row,cfg or {},manual_ids); scores.append(s); flags.append(f)
    trades['Compliance']=scores; trades['Compliance Flags']=flags
    def auto_grade(row):
        base=_num(row.get('Compliance')); eff=row.get('exit_efficiency_pct')
        execution=50.0 if pd.isna(eff) else max(0.0,min(100.0,_num(eff)))
        sc=0.75*base+0.25*execution
        return 'A' if sc>=90 else ('B' if sc>=78 else ('C' if sc>=65 else 'D'))
    trades['Auto Grade']=trades.apply(auto_grade,axis=1)
    if 'grade' in trades.columns:
        trades['Grade']=trades.apply(lambda r:r.get('grade') if str(r.get('grade') or 'AUTO')!='AUTO' else r.get('Auto Grade'),axis=1)
    else:trades['Grade']=trades['Auto Grade']
    compliance_avg=float(pd.Series(scores).mean()) if scores else 0.0
    streaks=_streaks(trades['Result'].tolist())
    profitability_component=max(0.0,min(30.0,15.0+expectancy*10.0+(min(pf,3.0)-1.0)*5.0)) if not math.isinf(pf) else 30.0
    consistency_component=consistency/100.0*20.0
    risk_component=compliance_avg/100.0*20.0
    dd_component=max(0.0,15.0*(1.0-max_dd_r/5.0))
    if 'exit_efficiency_pct' in trades.columns and trades['exit_efficiency_pct'].notna().any():
        execution_component=max(0.0,min(15.0,float(trades['exit_efficiency_pct'].dropna().mean())/100.0*15.0))
    else:execution_component=7.5
    score=max(0.0,min(100.0,profitability_component+consistency_component+risk_component+dd_component+execution_component))
    scfg=(cfg or {}).get('analytics',{}).get('score',{})
    red_dd=_num(scfg.get('max_drawdown_r_red',5.0),5.0); yls=int(scfg.get('loss_streak_yellow',3)); rls=int(scfg.get('loss_streak_red',5))
    current_loss_streak=streaks['current_streak'] if streaks['current_streak_type']=='LOSS' else 0
    risk_health='RED' if max_dd_r>=red_dd or current_loss_streak>=rls else ('YELLOW' if max_dd_r>=red_dd*0.6 or current_loss_streak>=yls else 'GREEN')
    return {
        'total_trades':len(trades),'wins':wins,'losses':losses,'breakeven':be,'win_rate':_pct(wins,decisive),
        'net_profit':net,'gross_profit':gp,'gross_loss':gl,'profit_factor':pf,'avg_r':expectancy,
        'best_r':float(trades['total_r'].max()),'worst_r':float(trades['total_r'].min()),'max_drawdown':max_dd,
        'max_drawdown_r':max_dd_r,'current_drawdown_r':current_dd_r,'partial_events':len(partials),'curve':curve,
        'symbol':_group_stats(trades,'symbol'),'direction':_group_stats(trades,'direction'),'timeframe':_group_stats(trades,'timeframe'),
        'weekday':_group_stats(trades,'weekday'),'hour':_group_stats(trades,'hour'),'session':_group_stats(trades,'session'),
        'setup':_group_stats(trades,'setup_tag'),'strategy':_group_stats(trades,'strategy_version'),'trades':trades,'daily':daily,
        'expectancy_r':expectancy,'avg_win_r':avg_win_r,'avg_loss_r':avg_loss_r,'payoff_ratio':payoff,
        'consistency_score':consistency,'recovery_factor':recovery,'profitable_days':profitable_days,'loss_days':loss_days,
        'streaks':streaks,'compliance_avg':compliance_avg,'nexus_score':score,
        'score_components':{'Profitability':profitability_component,'Consistency':consistency_component,'Risk Control':risk_component,'Drawdown':dd_component,'Execution':execution_component},
        'risk_health':risk_health
    }

def calendar_matrix(daily,year,month):
    import calendar
    cal=calendar.Calendar(firstweekday=0)
    weeks=cal.monthdatescalendar(int(year),int(month))
    mp={str(r['date']):r for _,r in daily.iterrows()} if daily is not None and not daily.empty else {}
    rows=[]
    for week in weeks:
        row=[]
        for d in week:
            item=mp.get(str(d))
            row.append({'date':d,'in_month':d.month==month,'pl':_num(item['P/L']) if item is not None else 0.0,'r':_num(item['R']) if item is not None else 0.0,'trades':int(item['Trades']) if item is not None else 0})
        rows.append(row)
    return rows

def read_monitor_alerts(limit=40):
    p=ROOT/'storage'/'mt5_monitor.log'
    if not p.exists():return []
    try:lines=p.read_text(encoding='utf-8',errors='ignore').splitlines()
    except Exception:return []
    keys=(' ERROR ','failed','cannot resolve','no deals','REPORT ERROR','MT5 data chart failed')
    return [x for x in lines if any(k.lower() in x.lower() for k in keys)][-int(limit):][::-1]

def prop_firm_status(cfg,snap,account_snapshots=None):
    pcfg=cfg.get('prop_firm',{}); start=_num(pcfg.get('starting_balance',0)); equity=_num(snap.get('equity'))
    target=start*(1+_num(pcfg.get('profit_target_percent',10))/100.0) if start>0 else 0
    max_floor=start*(1-_num(pcfg.get('max_loss_limit_percent',10))/100.0) if start>0 else 0
    total_buffer=equity-max_floor if start>0 else 0
    target_remaining=max(0.0,target-equity) if target else 0.0
    daily_start=None
    if account_snapshots:
        tz=ZoneInfo(cfg.get('analytics',{}).get('timezone','Asia/Tehran'))
        today=datetime.now(tz).date(); vals=[]
        for s in account_snapshots:
            try:
                dt=datetime.fromisoformat(str(s.get('snapshot_time')))
                if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
                if dt.astimezone(tz).date()==today:vals.append((dt,s))
            except Exception:pass
        if vals:
            daily_start=_num(sorted(vals,key=lambda x:x[0])[0][1].get('equity'))
    daily_limit=start*_num(pcfg.get('daily_loss_limit_percent',5))/100.0 if start>0 else 0.0
    daily_pl=(equity-daily_start) if daily_start is not None else None
    daily_buffer=(daily_limit+daily_pl) if daily_pl is not None else None
    return {'enabled':bool(pcfg.get('enabled')),'starting_balance':start,'target_equity':target,'target_remaining':target_remaining,'max_loss_floor':max_floor,'max_loss_buffer':total_buffer,'daily_start_equity':daily_start,'daily_pl':daily_pl,'daily_loss_buffer':daily_buffer}

def bootstrap_simulation(r_values,n_trades=30,n_sims=2000,dd_limit_r=5.0,seed=42):
    try:
        import numpy as np
        vals=np.array([float(x) for x in r_values if x is not None],dtype=float)
        if len(vals)<3:return {'ok':False,'reason':'Need at least 3 closed trades'}
        rng=np.random.default_rng(seed); samples=rng.choice(vals,size=(int(n_sims),int(n_trades)),replace=True)
        cum=samples.cumsum(axis=1); final=cum[:,-1]
        peak=np.maximum.accumulate(cum,axis=1); dd=peak-cum; maxdd=dd.max(axis=1)
        return {'ok':True,'median_final_r':float(np.median(final)),'p10_final_r':float(np.percentile(final,10)),'p90_final_r':float(np.percentile(final,90)),'positive_pct':float((final>0).mean()*100),'dd_breach_pct':float((maxdd>=float(dd_limit_r)).mean()*100),'median_max_dd_r':float(np.median(maxdd))}
    except Exception as e:return {'ok':False,'reason':str(e)}
