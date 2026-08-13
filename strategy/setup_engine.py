
import json
from collections import defaultdict
import pandas as pd


def _grade(score,thresholds=None):
    if score is None:return 'N/A'
    score=float(score)
    levels=thresholds or {'A+':90,'A':80,'B':70,'C':60,'D':0}
    for grade in ('A+','A','B','C','D'):
        if score>=float(levels.get(grade,0)):return grade
    return 'D'


def score_checklist(setup,items,answers,rationale='',grade_thresholds=None):
    """Score a setup checklist and return an immutable snapshot for the signal.

    answers can be {item_id: bool}. Historical snapshots keep item text/weight so
    later edits to the setup template never rewrite past trade context.
    """
    answers={str(k):bool(v) for k,v in (answers or {}).items()}
    active=[x for x in (items or []) if int(x.get('active',1))]
    max_points=sum(max(0.0,float(x.get('weight') or 0)) for x in active)
    earned=0.0;required_missed=0;snapshot=[]
    for item in active:
        checked=bool(answers.get(str(item.get('id')),False))
        weight=max(0.0,float(item.get('weight') or 0))
        if checked: earned+=weight
        if int(item.get('required') or 0) and not checked: required_missed+=1
        snapshot.append({
            'item_id':item.get('id'),'text':item.get('item_text'),'weight':weight,
            'required':bool(item.get('required')),'checked':checked
        })
    pct=(earned/max_points*100.0) if max_points>0 else None
    return {
        'setup_id':setup.get('id') if setup else None,
        'setup_name':(setup or {}).get('name') or 'UNSPECIFIED',
        'score_points':earned,'max_points':max_points,'score_percent':pct,
        'grade':_grade(pct,grade_thresholds),'required_missed':required_missed,
        'rationale':str(rationale or '').strip(),
        'checklist':snapshot,'checklist_json':json.dumps(snapshot,ensure_ascii=False)
    }


def _result(row):
    try:r=float(row.get('total_r') or 0)
    except Exception:r=0
    return 'WIN' if r>0.10 else ('LOSS' if r<-0.10 else 'BE')


def setup_performance(scores,trades):
    sdf=pd.DataFrame(scores or []);tdf=trades.copy() if isinstance(trades,pd.DataFrame) else pd.DataFrame(trades or [])
    if sdf.empty or tdf.empty or 'signal_id' not in tdf.columns:return pd.DataFrame()
    keep=[c for c in ['signal_id','setup_name','score_percent','grade','required_missed'] if c in sdf.columns]
    df=tdf.merge(sdf[keep].drop_duplicates('signal_id'),on='signal_id',how='left')
    if df.empty:return pd.DataFrame()
    df['Score']=pd.to_numeric(df.get('score_percent'),errors='coerce')
    df['P/L']=pd.to_numeric(df.get('total_profit'),errors='coerce').fillna(0)
    df['R']=pd.to_numeric(df.get('total_r'),errors='coerce').fillna(0)
    df['Result']=df.apply(_result,axis=1)
    rows=[]
    for name,g in df.groupby('setup_name',dropna=True):
        decisive=g[g['Result'].isin(['WIN','LOSS'])]
        wr=(decisive['Result'].eq('WIN').mean()*100) if len(decisive) else 0.0
        rows.append({'Setup':name,'Trades':len(g),'Avg Score':float(g['Score'].mean()) if g['Score'].notna().any() else None,
                     'Win Rate':float(wr),'P/L':float(g['P/L'].sum()),'Avg R':float(g['R'].mean()),
                     'A/A+ %':float(g['grade'].isin(['A','A+']).mean()*100) if 'grade' in g else 0.0})
    return pd.DataFrame(rows).sort_values(['P/L','Win Rate'],ascending=False) if rows else pd.DataFrame()


def score_band_performance(scores,trades):
    sdf=pd.DataFrame(scores or []);tdf=trades.copy() if isinstance(trades,pd.DataFrame) else pd.DataFrame(trades or [])
    if sdf.empty or tdf.empty:return pd.DataFrame()
    df=tdf.merge(sdf[['signal_id','score_percent']].drop_duplicates('signal_id'),on='signal_id',how='inner')
    if df.empty:return pd.DataFrame()
    df['score_percent']=pd.to_numeric(df['score_percent'],errors='coerce')
    df=df[df['score_percent'].notna()].copy()
    if df.empty:return pd.DataFrame()
    df['Band']=pd.cut(df['score_percent'],bins=[-0.01,59.999,69.999,79.999,89.999,100.001],labels=['<60','60–69','70–79','80–89','90–100'])
    df['Result']=df.apply(_result,axis=1);df['P/L']=pd.to_numeric(df.get('total_profit'),errors='coerce').fillna(0);df['R']=pd.to_numeric(df.get('total_r'),errors='coerce').fillna(0)
    rows=[]
    for band,g in df.groupby('Band',observed=True):
        decisive=g[g['Result'].isin(['WIN','LOSS'])];wr=(decisive['Result'].eq('WIN').mean()*100) if len(decisive) else 0.0
        rows.append({'Score Band':str(band),'Trades':len(g),'Win Rate':float(wr),'P/L':float(g['P/L'].sum()),'Avg R':float(g['R'].mean())})
    return pd.DataFrame(rows)


def checklist_edge_analysis(scores,trades,setup_name=None):
    tdf=trades.copy() if isinstance(trades,pd.DataFrame) else pd.DataFrame(trades or [])
    if tdf.empty:return pd.DataFrame()
    trade_map={str(r['signal_id']):r for _,r in tdf.iterrows()}
    buckets=defaultdict(lambda:{'yes':[],'no':[]})
    for s in scores or []:
        if setup_name and str(s.get('setup_name'))!=str(setup_name):continue
        tr=trade_map.get(str(s.get('signal_id')))
        if tr is None:continue
        try:items=json.loads(s.get('checklist_json') or '[]')
        except Exception:items=[]
        for item in items:
            key=(str(s.get('setup_name')),str(item.get('text')),float(item.get('weight') or 0),bool(item.get('required')))
            buckets[key]['yes' if item.get('checked') else 'no'].append(tr)
    rows=[]
    for (setup,text,weight,required),b in buckets.items():
        def stats(arr):
            if not arr:return (0,None,None)
            results=[_result(x) for x in arr];dec=[x for x in results if x in ('WIN','LOSS')]
            wr=(sum(x=='WIN' for x in dec)/len(dec)*100) if dec else 0.0
            avgr=sum(float(x.get('total_r') or 0) for x in arr)/len(arr)
            return len(arr),wr,avgr
        yn,ywr,yr=stats(b['yes']);nn,nwr,nr=stats(b['no'])
        rows.append({'Setup':setup,'Checklist Item':text,'Weight':weight,'Required':required,
                     'Checked Trades':yn,'Checked Win Rate':ywr,'Checked Avg R':yr,
                     'Unchecked Trades':nn,'Unchecked Win Rate':nwr,'Unchecked Avg R':nr,
                     'Avg R Edge':None if yr is None or nr is None else yr-nr})
    out=pd.DataFrame(rows)
    if not out.empty:out=out.sort_values(['Setup','Avg R Edge'],ascending=[True,False],na_position='last')
    return out
