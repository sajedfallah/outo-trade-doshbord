"""MT5-backed result chart rendering.

V3 separates price action from the full risk/reward map.  This keeps candles
readable even when distant take-profit levels would otherwise flatten them.
"""

from pathlib import Path
from datetime import datetime, timezone, timedelta

TIMEFRAME_SHORT={'1 دقیقه':'M1','2 دقیقه':'M2','3 دقیقه':'M3','5 دقیقه':'M5','10 دقیقه':'M10','15 دقیقه':'M15','30 دقیقه':'M30','45 دقیقه':'M45','1 ساعت':'H1','2 ساعت':'H2','4 ساعت':'H4'}

TIMEFRAME_ATTR={
    '1 دقیقه':'TIMEFRAME_M1','2 دقیقه':'TIMEFRAME_M2','3 دقیقه':'TIMEFRAME_M3','5 دقیقه':'TIMEFRAME_M5',
    '10 دقیقه':'TIMEFRAME_M10','15 دقیقه':'TIMEFRAME_M15','30 دقیقه':'TIMEFRAME_M30','45 دقیقه':'TIMEFRAME_M45',
    '1 ساعت':'TIMEFRAME_H1','2 ساعت':'TIMEFRAME_H2','4 ساعت':'TIMEFRAME_H4',
}

COLORS={
    'bg':'#060d18','panel':'#0a1524','map':'#081321','grid':'#24344b','text':'#edf4ff','muted':'#8ea2bc',
    'up':'#22c55e','down':'#f05252','entry':'#38bdf8','tp':'#2dd477','sl':'#f43f5e','exit':'#f5a524',
    'partial':'#a78bfa','border':'#2a3b54'
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
    extremes=[float(r[key]) for r in rows for key in ('high','low')]
    span=max(extremes)-min(extremes) if extremes else 1.0
    min_body=max(span*0.0014,1e-8);width=.58
    for i,row in enumerate(rows):
        o=float(row['open']);h=float(row['high']);low=float(row['low']);close=float(row['close'])
        color=COLORS['up'] if close>=o else COLORS['down']
        ax.vlines(i,low,h,color=color,linewidth=.82,zorder=3,alpha=.95)
        bottom=min(o,close);height=max(abs(close-o),min_body)
        ax.add_patch(patches.Rectangle((i-width/2,bottom),width,height,facecolor=color,edgecolor=color,linewidth=.55,zorder=4))


def _dt_ts(value):
    if not value:return None
    try:
        parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    except Exception:return None


def _trade_open_time(mt5,signal):
    pid=signal.get('mt5_position_id') or signal.get('mt5_ticket')
    if not pid:return None
    try:deals=list(mt5.history_deals_get(position=int(pid)) or [])
    except Exception:deals=[]
    entry_in=getattr(mt5,'DEAL_ENTRY_IN',0)
    openings=[deal for deal in deals if int(getattr(deal,'entry',-1))==entry_in]
    return min((int(getattr(deal,'time',0) or 0) for deal in openings),default=None)


def _target_levels(signal):
    explicit=signal.get('targets')
    if isinstance(explicit,(list,tuple)):
        vals=[float(value) for value in explicit if float(value or 0)]
        if vals:return vals
    try:
        from storage.repo import get_signal_trailing_plan
        plan=get_signal_trailing_plan(signal.get('signal_id'))
        vals=[float(value) for value in (plan.get('targets') or [])] if plan else []
        if vals:return vals
    except Exception:pass
    tp=float(signal.get('tp') or 0)
    return [tp] if tp else []


def _exit_points(signal,event):
    """Return all persisted partial/final exits, including the current event."""
    rows=[]
    try:
        from storage.repo import list_trade_events
        rows=list_trade_events(signal.get('signal_id'))
    except Exception:pass
    rows.append(dict(event or {}));out=[];seen=set()
    for row in rows:
        if str(row.get('event_type') or '').upper() not in ('PARTIAL_CLOSE','FINAL_CLOSE'):continue
        price=float(row.get('exit_price') or 0)
        if not price:continue
        key=str(row.get('event_key') or f"{row.get('event_type')}:{row.get('event_time')}:{price}")
        if key in seen:continue
        seen.add(key);out.append({'price':price,'time':_dt_ts(row.get('event_time')),'type':str(row.get('event_type')).upper()})
    return sorted(out,key=lambda row:(row.get('time') is None,row.get('time') or 0))


def _spread_positions(values,lower,upper,min_gap_ratio=.055):
    """Spread label positions while retaining their actual-price connectors."""
    if not values:return []
    span=max(upper-lower,1e-9);gap=span*min_gap_ratio
    ordered=sorted(enumerate(values),key=lambda pair:pair[1]);placed=[]
    cursor=lower
    for index,value in ordered:
        position=max(float(value),cursor)
        placed.append([index,position]);cursor=position+gap
    overflow=placed[-1][1]-upper
    if overflow>0:
        for item in placed:item[1]-=overflow
    underflow=lower-placed[0][1]
    if underflow>0:
        for item in placed:item[1]+=underflow
    result=[0.0]*len(values)
    for index,position in placed:result[index]=position
    return result


def _price_label(value,digits):
    return f'{float(value):.{max(0,int(digits))}f}'


def _select_view(rows,open_ts,event_ts,display,max_bars=240):
    """Keep both trade endpoints and context when MT5 returned enough history."""
    if not rows:return []
    times=[row['time'] for row in rows];last=len(rows)-1
    exit_index=_nearest_index(times,event_ts) if event_ts else last
    if exit_index is None:exit_index=last
    open_index=_nearest_index(times,open_ts) if open_ts else None
    left=max(0,(open_index if open_index is not None else exit_index-display+1)-12)
    right=min(last,exit_index+12)
    required=right-left+1
    count=min(max_bars,max(int(display),required))
    if required<count:
        spare=count-required;left=max(0,left-spare//2);right=min(last,left+count-1);left=max(0,right-count+1)
    elif required>max_bars:
        left=max(0,right-max_bars+1)
    return rows[left:right+1]


def _market_bounds(view,entry,exits,sl,targets):
    lows=[row['low'] for row in view];highs=[row['high'] for row in view]
    focus=lows+highs+([entry] if entry else [])+[row['price'] for row in exits]
    low=min(focus);high=max(focus);span=max(high-low,abs(entry or high)*.0008,1e-6)
    for level in ([sl] if sl else [])+list(targets):
        if low-span*.45<=level<=high+span*.45:
            low=min(low,level);high=max(high,level)
    pad=max((high-low)*.09,span*.09)
    return low-pad,high+pad


def _draw_main_level(ax,price,color,style,width,visible_bounds):
    if price and visible_bounds[0]<=price<=visible_bounds[1]:
        ax.axhline(price,color=color,linewidth=width,linestyle=style,alpha=.78,zorder=1)


def _trade_map(ax,entry,sl,targets,exits,digits):
    all_prices=([entry] if entry else [])+([sl] if sl else [])+list(targets)+[item['price'] for item in exits]
    if not all_prices:return
    low=min(all_prices);high=max(all_prices);span=max(high-low,abs(entry or high)*.001,1e-6);pad=span*.10
    lower=low-pad;upper=high+pad;ax.set_ylim(lower,upper);ax.set_xlim(0,1)
    if entry and sl:
        ax.axhspan(min(entry,sl),max(entry,sl),color=COLORS['sl'],alpha=.13,zorder=0)
    if entry and targets:
        furthest=max(targets) if max(targets)>entry else min(targets)
        ax.axhspan(min(entry,furthest),max(entry,furthest),color=COLORS['tp'],alpha=.10,zorder=0)
    ax.axvline(.28,color=COLORS['border'],linewidth=1.0,alpha=.8,zorder=1)

    levels=[]
    if sl:levels.append((sl,'SL',COLORS['sl'],'s'))
    if entry:levels.append((entry,'ENTRY',COLORS['entry'],'o'))
    for index,target in enumerate(targets,1):levels.append((target,f'TP{index}',COLORS['tp'],'^'))
    partial_number=0
    for item in exits:
        if item['type']=='PARTIAL_CLOSE':
            partial_number+=1;label=f'EXIT {partial_number}';color=COLORS['partial'];marker='D'
        else:label='FINAL';color=COLORS['exit'];marker='D'
        levels.append((item['price'],label,color,marker))
    label_positions=_spread_positions([item[0] for item in levels],lower+span*.02,upper-span*.02)
    for (actual,label,color,marker),label_y in zip(levels,label_positions):
        ax.hlines(actual,.08,.58,color=color,linewidth=1.2,alpha=.84,zorder=2)
        ax.scatter([.28],[actual],s=34,marker=marker,color=color,edgecolor='#f8fbff',linewidth=.55,zorder=4)
        ax.plot([.58,.67],[actual,label_y],color=color,linewidth=.62,alpha=.72,zorder=2)
        ax.text(.70,label_y,f'{label}  {_price_label(actual,digits)}',ha='left',va='center',fontsize=7.1,
                color=COLORS['text'],fontweight='bold',
                bbox=dict(boxstyle='round,pad=.22',facecolor=COLORS['panel'],edgecolor=color,linewidth=.72,alpha=.96),zorder=5)
    ax.text(.06,.975,'TRADE MAP',transform=ax.transAxes,ha='left',va='top',fontsize=8.2,color=COLORS['muted'],fontweight='bold')
    ax.set_xticks([]);ax.set_yticks([])
    for spine in ax.spines.values():spine.set_color(COLORS['border']);spine.set_alpha(.75)


def generate_result_chart(signal,event,cfg,output_path,mt5_instance=None):
    """Generate a collision-aware NEXUS V3 result card from MT5 OHLC data."""
    output_path=Path(output_path);output_path.parent.mkdir(parents=True,exist_ok=True)
    owned=mt5_instance is None;mt5=mt5_instance or _connect(cfg)
    try:
        symbol=_broker_symbol(signal,cfg);info=mt5.symbol_info(symbol)
        if info is None:raise RuntimeError(f'MT5 symbol not found: {symbol}')
        if not info.visible:mt5.symbol_select(symbol,True)
        digits=int(getattr(info,'digits',2) or 2);tf=_tf(mt5,signal.get('timeframe'));chart_cfg=cfg.get('monitor',{}).get('result_chart',{})
        event_ts=_dt_ts(event.get('event_time'));open_ts=_trade_open_time(mt5,signal)
        display=max(70,int(chart_cfg.get('display_bars',110)));seconds_per_bar={getattr(mt5,'TIMEFRAME_M1',1):60,getattr(mt5,'TIMEFRAME_M5',5):300,getattr(mt5,'TIMEFRAME_M15',15):900,getattr(mt5,'TIMEFRAME_M30',30):1800,getattr(mt5,'TIMEFRAME_H1',16385):3600}.get(tf,900)
        rates=None
        if event_ts:
            try:
                default_start=event_ts-seconds_per_bar*display
                start_ts=min(default_start,(open_ts-seconds_per_bar*12) if open_ts else default_start)
                start=datetime.fromtimestamp(start_ts,tz=timezone.utc);end=datetime.fromtimestamp(event_ts,tz=timezone.utc)+timedelta(seconds=seconds_per_bar*15)
                rates=mt5.copy_rates_range(symbol,tf,start,end)
            except Exception:rates=None
        if rates is None or len(rates)<25:
            count=max(100,int(chart_cfg.get('bars',220)));rates=mt5.copy_rates_from_pos(symbol,tf,0,count)
        if rates is None or len(rates)<20:raise RuntimeError(f'MT5 candle data failed: {mt5.last_error()}')
        rows=[{'time':int(row['time']),'open':float(row['open']),'high':float(row['high']),'low':float(row['low']),'close':float(row['close'])} for row in rates]
        view=_select_view(rows,open_ts,event_ts,display)

        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.ticker import MaxNLocator,FormatStrFormatter

        entry=float(signal.get('entry') or 0);sl=float(signal.get('sl') or 0);targets=_target_levels(signal);exits=_exit_points(signal,event)
        bounds=_market_bounds(view,entry,exits,sl,targets)
        fig=plt.figure(figsize=(14.2,7.6),facecolor=COLORS['bg'])
        grid=fig.add_gridspec(1,2,width_ratios=[4.55,1.45],left=.05,right=.98,bottom=.105,top=.84,wspace=.055)
        ax=fig.add_subplot(grid[0,0]);map_ax=fig.add_subplot(grid[0,1]);ax.set_facecolor(COLORS['panel']);map_ax.set_facecolor(COLORS['map'])
        _candles(ax,view);ax.set_ylim(*bounds);ax.set_xlim(-1,len(view)+2)
        if chart_cfg.get('show_entry',True):_draw_main_level(ax,entry,COLORS['entry'],'--',1.25,bounds)
        if chart_cfg.get('show_tp',True):
            for target in targets:_draw_main_level(ax,target,COLORS['tp'],':',1.0,bounds)
        if chart_cfg.get('show_sl',True):_draw_main_level(ax,sl,COLORS['sl'],'-.',1.15,bounds)
        for item in exits:
            if not chart_cfg.get('show_exit',True):break
            _draw_main_level(ax,item['price'],COLORS['partial'] if item['type']=='PARTIAL_CLOSE' else COLORS['exit'],'-',1.0,bounds)

        local_times=[row['time'] for row in view]
        if open_ts and entry:
            index=_nearest_index(local_times,open_ts)
            if index is not None:
                ax.scatter([index],[entry],s=44,color=COLORS['entry'],edgecolor='#ffffff',linewidth=.65,zorder=8)
                ax.annotate('IN',(index,entry),xytext=(0,10),textcoords='offset points',ha='center',fontsize=6.9,color=COLORS['text'],fontweight='bold',bbox=dict(boxstyle='round,pad=.2',facecolor=COLORS['bg'],edgecolor=COLORS['entry'],linewidth=.7,alpha=.94),zorder=9)
        partial_count=0
        for item in exits:
            index=_nearest_index(local_times,item.get('time')) if item.get('time') else len(view)-1
            if index is None:index=len(view)-1
            if item['type']=='PARTIAL_CLOSE':partial_count+=1;tag=f'P{partial_count}';color=COLORS['partial'];marker='D';offset=11
            else:tag='OUT';color=COLORS['exit'];marker='D';offset=-16
            ax.scatter([index],[item['price']],s=48,color=color,marker=marker,edgecolor='#ffffff',linewidth=.65,zorder=8)
            ax.annotate(tag,(index,item['price']),xytext=(0,offset),textcoords='offset points',ha='center',fontsize=6.9,color=COLORS['text'],fontweight='bold',bbox=dict(boxstyle='round,pad=.2',facecolor=COLORS['bg'],edgecolor=color,linewidth=.7,alpha=.94),zorder=9)

        _trade_map(map_ax,entry,sl,targets,exits,digits)
        direction=str(signal.get('direction','')).upper();status='PARTIAL UPDATE' if event.get('event_type')=='PARTIAL_CLOSE' else 'TRADE CLOSED';profit=float(event.get('total_profit') or 0)
        profit_color=COLORS['up'] if profit>0 else (COLORS['down'] if profit<0 else COLORS['muted'])
        fig.text(.05,.955,str(signal.get('signal_id')),color=COLORS['text'],fontsize=16.5,fontweight='bold',ha='left',va='top')
        fig.text(.05,.905,f"{signal.get('symbol')}  ·  {direction}  ·  {TIMEFRAME_SHORT.get(str(signal.get('timeframe')),str(signal.get('timeframe')))}",color=COLORS['muted'],fontsize=9.2,fontweight='bold',ha='left',va='center')
        fig.text(.25,.938,status,color=COLORS['text'],fontsize=8.0,fontweight='bold',ha='left',va='center',bbox=dict(boxstyle='round,pad=.30',facecolor='#132238',edgecolor=COLORS['border'],linewidth=.75))
        fig.text(.37,.938,f'P/L  {profit:+,.2f}',color=profit_color,fontsize=10.2,fontweight='bold',ha='left',va='center')
        fig.text(.98,.895,'PRICE ACTION  +  COMPLETE TRADE MAP',color=COLORS['muted'],fontsize=7.6,fontweight='bold',ha='right',va='center')

        ax.grid(True,color=COLORS['grid'],alpha=.30,linewidth=.55);ax.yaxis.tick_right();ax.yaxis.set_label_position('right');ax.yaxis.set_major_formatter(FormatStrFormatter(f'%.{digits}f'));ax.xaxis.set_major_locator(MaxNLocator(7,integer=True))
        ticks=ax.get_xticks();labels=[]
        for tick in ticks:
            index=int(round(tick))
            if 0<=index<len(view):labels.append(datetime.fromtimestamp(view[index]['time'],tz=timezone.utc).astimezone().strftime('%m-%d\n%H:%M'))
            else:labels.append('')
        ax.set_xticks(ticks);ax.set_xticklabels(labels,fontsize=7.6,color=COLORS['muted']);ax.tick_params(axis='y',colors=COLORS['muted'],labelsize=7.8,pad=4);ax.tick_params(axis='x',colors=COLORS['muted'])
        for spine in ax.spines.values():spine.set_color(COLORS['border']);spine.set_alpha(.78)
        dpi=max(110,int(chart_cfg.get('dpi',160)));fig.savefig(output_path,dpi=dpi,facecolor=fig.get_facecolor());plt.close(fig)
        return {'ok':True,'path':str(output_path),'mode':'mt5_data_chart_v3','symbol':symbol,'timeframe':str(signal.get('timeframe')),'bars':len(view),'event_time':event.get('event_time'),'targets':targets,'exits':len(exits)}
    finally:
        if owned:mt5.shutdown()
