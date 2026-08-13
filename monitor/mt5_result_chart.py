from pathlib import Path
from datetime import datetime, timezone, timedelta

TIMEFRAME_SHORT={'1 دقیقه':'M1','2 دقیقه':'M2','3 دقیقه':'M3','5 دقیقه':'M5','10 دقیقه':'M10','15 دقیقه':'M15','30 دقیقه':'M30','45 دقیقه':'M45','1 ساعت':'H1','2 ساعت':'H2','4 ساعت':'H4'}

TIMEFRAME_ATTR={
    '1 دقیقه':'TIMEFRAME_M1','2 دقیقه':'TIMEFRAME_M2','3 دقیقه':'TIMEFRAME_M3','5 دقیقه':'TIMEFRAME_M5',
    '10 دقیقه':'TIMEFRAME_M10','15 دقیقه':'TIMEFRAME_M15','30 دقیقه':'TIMEFRAME_M30','45 دقیقه':'TIMEFRAME_M45',
    '1 ساعت':'TIMEFRAME_H1','2 ساعت':'TIMEFRAME_H2','4 ساعت':'TIMEFRAME_H4',
}

COLORS={
    'bg':'#07101c','panel':'#0b1626','grid':'#23344f','text':'#e8eef8','muted':'#8fa4bf',
    'up':'#22c55e','down':'#ef4444','entry':'#38bdf8','tp':'#22c55e','sl':'#f43f5e','exit':'#f59e0b',
    'partial':'#a78bfa'
}


def _tf(mt5,label):
    return getattr(mt5,TIMEFRAME_ATTR.get(str(label),'TIMEFRAME_M5'),getattr(mt5,'TIMEFRAME_M5'))


def _broker_symbol(signal,cfg):
    if signal.get('mt5_symbol'):return str(signal['mt5_symbol'])
    src=str(signal.get('symbol',''));return str(cfg.get('symbol_map',{}).get(src,src))


def _connect(cfg):
    import MetaTrader5 as mt5
    path=cfg.get('mt5',{}).get('terminal_path','')
    ok=mt5.initialize(path=path) if path else mt5.initialize()
    if not ok:raise RuntimeError(f'MT5 initialize failed: {mt5.last_error()}')
    return mt5


def _nearest_index(times,target_ts):
    if not times or target_ts is None:return None
    return min(range(len(times)),key=lambda i:abs(times[i]-target_ts))


def _candles(ax,rows):
    import matplotlib.patches as patches
    if not rows:return
    prices=[float(r['close']) for r in rows]
    span=max(prices)-min(prices) if prices else 1.0
    min_body=max(span*0.0015,1e-8);width=.62
    for i,r in enumerate(rows):
        o=float(r['open']);h=float(r['high']);l=float(r['low']);c=float(r['close']);up=c>=o;color=COLORS['up'] if up else COLORS['down']
        ax.vlines(i,l,h,color=color,linewidth=1.0,zorder=2,alpha=.95)
        bottom=min(o,c);height=max(abs(c-o),min_body)
        ax.add_patch(patches.Rectangle((i-width/2,bottom),width,height,facecolor=color,edgecolor=color,linewidth=.7,zorder=3))


def _dt_ts(v):
    if not v:return None
    try:
        d=datetime.fromisoformat(str(v).replace('Z','+00:00'))
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        return int(d.timestamp())
    except Exception:return None


def _trade_open_time(mt5,signal):
    pid=signal.get('mt5_position_id') or signal.get('mt5_ticket')
    if not pid:return None
    try:deals=list(mt5.history_deals_get(position=int(pid)) or [])
    except Exception:deals=[]
    entry_in=getattr(mt5,'DEAL_ENTRY_IN',0)
    ins=[d for d in deals if int(getattr(d,'entry',-1))==entry_in]
    if not ins:return None
    return min(int(getattr(d,'time',0) or 0) for d in ins)


def _target_levels(signal):
    try:
        from storage.repo import get_signal_trailing_plan
        p=get_signal_trailing_plan(signal.get('signal_id'))
        vals=[float(x) for x in (p.get('targets') or [])] if p else []
        if vals:return vals
    except Exception:pass
    tp=float(signal.get('tp') or 0)
    return [tp] if tp else []


def _level(ax,price,label,color,linestyle='--',linewidth=1.45,alpha=.95):
    from matplotlib.transforms import blended_transform_factory
    ax.axhline(price,color=color,linewidth=linewidth,linestyle=linestyle,alpha=alpha,zorder=1)
    trans=blended_transform_factory(ax.transAxes,ax.transData)
    ax.text(.988,price,f'  {label}  ',transform=trans,ha='right',va='center',fontsize=9.2,color='#ffffff',fontweight='bold',
            bbox=dict(boxstyle='round,pad=.32',facecolor=color,edgecolor=color,alpha=.92),zorder=8,clip_on=False)


def generate_result_chart(signal,event,cfg,output_path,mt5_instance=None):
    """Generate a presentation-quality NEXUS result image from MT5 OHLC data."""
    output_path=Path(output_path);output_path.parent.mkdir(parents=True,exist_ok=True)
    owned=mt5_instance is None
    mt5=mt5_instance or _connect(cfg)
    try:
        symbol=_broker_symbol(signal,cfg);info=mt5.symbol_info(symbol)
        if info is None:raise RuntimeError(f'MT5 symbol not found: {symbol}')
        if not info.visible:mt5.symbol_select(symbol,True)
        tf=_tf(mt5,signal.get('timeframe'));chart_cfg=cfg.get('monitor',{}).get('result_chart',{})

        event_ts=_dt_ts(event.get('event_time'));open_ts=_trade_open_time(mt5,signal)
        display=max(70,int(chart_cfg.get('display_bars',110)))
        # Prefer time-centered history so old closed trades still show the actual trade, not today's candles.
        rates=None
        if event_ts:
            try:
                # Wide enough window around the event; MT5 returns oldest -> newest.
                seconds_per_bar={getattr(mt5,'TIMEFRAME_M1',1):60,getattr(mt5,'TIMEFRAME_M5',5):300,getattr(mt5,'TIMEFRAME_M15',15):900,
                                 getattr(mt5,'TIMEFRAME_M30',30):1800,getattr(mt5,'TIMEFRAME_H1',16385):3600}.get(tf,900)
                start=datetime.fromtimestamp(event_ts,tz=timezone.utc)-timedelta(seconds=seconds_per_bar*display)
                end=datetime.fromtimestamp(event_ts,tz=timezone.utc)+timedelta(seconds=seconds_per_bar*15)
                rates=mt5.copy_rates_range(symbol,tf,start,end)
            except Exception:rates=None
        if rates is None or len(rates)<25:
            count=max(100,int(chart_cfg.get('bars',220)));rates=mt5.copy_rates_from_pos(symbol,tf,0,count)
        if rates is None or len(rates)<20:raise RuntimeError(f'MT5 candle data failed: {mt5.last_error()}')

        rows=[{'time':int(r['time']),'open':float(r['open']),'high':float(r['high']),'low':float(r['low']),'close':float(r['close'])} for r in rates]
        times=[r['time'] for r in rows];end_idx=len(rows)-1
        if event_ts:
            near=_nearest_index(times,event_ts)
            if near is not None:end_idx=min(len(rows)-1,near+10)
        start_idx=max(0,end_idx-display+1);view=rows[start_idx:end_idx+1]

        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.ticker import MaxNLocator

        fig,ax=plt.subplots(figsize=(13.4,7.15));fig.patch.set_facecolor(COLORS['bg']);ax.set_facecolor(COLORS['panel']);_candles(ax,view)
        entry=float(signal.get('entry') or 0);sl=float(signal.get('sl') or 0);exit_price=float(event.get('exit_price') or 0);targets=_target_levels(signal)

        if entry and chart_cfg.get('show_entry',True):_level(ax,entry,f'ENTRY  {entry:g}',COLORS['entry'],'--',1.7)
        if chart_cfg.get('show_tp',True):
            for i,tp in enumerate(targets,1):
                if tp:_level(ax,float(tp),f'TP{i}  {float(tp):g}',COLORS['tp'],':',1.35,alpha=max(.55,1.0-i*.07))
        if sl and chart_cfg.get('show_sl',True):_level(ax,sl,f'SL  {sl:g}',COLORS['sl'],'-.',1.55)
        if exit_price and chart_cfg.get('show_exit',True):_level(ax,exit_price,f'EXIT  {exit_price:g}',COLORS['exit'],'-',1.8)

        local_times=[r['time'] for r in view]
        if open_ts and entry:
            oi=_nearest_index(local_times,open_ts)
            if oi is not None:
                ax.scatter([oi],[entry],s=95,color=COLORS['entry'],edgecolor='#ffffff',linewidth=.8,zorder=9)
                ax.annotate(' ENTRY',(oi,entry),xytext=(9,13),textcoords='offset points',fontsize=9,color=COLORS['text'],fontweight='bold',
                            bbox=dict(boxstyle='round,pad=.25',facecolor=COLORS['bg'],edgecolor=COLORS['entry'],alpha=.9))
        if exit_price:
            xi=_nearest_index(local_times,event_ts) if event_ts else len(view)-1
            if xi is None:xi=len(view)-1
            ax.scatter([xi],[exit_price],s=105,color=COLORS['exit'],edgecolor='#ffffff',linewidth=.8,zorder=9)
            ax.annotate(' EXIT',(xi,exit_price),xytext=(9,-22),textcoords='offset points',fontsize=9,color=COLORS['text'],fontweight='bold',
                        bbox=dict(boxstyle='round,pad=.25',facecolor=COLORS['bg'],edgecolor=COLORS['exit'],alpha=.9))

        direction=str(signal.get('direction','')).upper();status='PARTIAL' if event.get('event_type')=='PARTIAL_CLOSE' else 'FINAL';pl=float(event.get('total_profit') or 0)
        pl_color=COLORS['up'] if pl>0 else (COLORS['down'] if pl<0 else COLORS['muted'])
        fig.text(.055,.955,f"{signal.get('signal_id')}   •   {signal.get('symbol')}   •   {direction}   •   {TIMEFRAME_SHORT.get(str(signal.get('timeframe')),str(signal.get('timeframe')))}",color=COLORS['text'],fontsize=14,fontweight='bold',ha='left',va='top')
        fig.text(.055,.915,f'{status}',color=COLORS['muted'],fontsize=10.5,ha='left',va='top')
        fig.text(.17,.915,f'P/L  {pl:+,.2f}',color=pl_color,fontsize=10.5,fontweight='bold',ha='left',va='top')

        ax.grid(True,color=COLORS['grid'],alpha=.34,linewidth=.65);ax.yaxis.tick_right();ax.yaxis.set_label_position('right');ax.xaxis.set_major_locator(MaxNLocator(8,integer=True))
        xticks=ax.get_xticks();labels=[]
        for x in xticks:
            i=int(round(x))
            if 0<=i<len(view):
                dt=datetime.fromtimestamp(view[i]['time'],tz=timezone.utc).astimezone();labels.append(dt.strftime('%m-%d\n%H:%M'))
            else:labels.append('')
        ax.set_xticks(xticks);ax.set_xticklabels(labels,fontsize=8.5,color=COLORS['muted'])
        ax.tick_params(axis='y',colors=COLORS['muted'],labelsize=9);ax.tick_params(axis='x',colors=COLORS['muted'])
        for spine in ax.spines.values():spine.set_color(COLORS['grid']);spine.set_alpha(.8)
        ax.margins(x=.01);fig.subplots_adjust(left=.055,right=.955,bottom=.10,top=.86)
        dpi=max(110,int(chart_cfg.get('dpi',160)));fig.savefig(output_path,dpi=dpi,bbox_inches='tight',facecolor=fig.get_facecolor());plt.close(fig)
        return {'ok':True,'path':str(output_path),'mode':'mt5_data_chart_v2','symbol':symbol,'timeframe':str(signal.get('timeframe')),'bars':len(view),'event_time':event.get('event_time'),'targets':targets}
    finally:
        if owned:mt5.shutdown()
