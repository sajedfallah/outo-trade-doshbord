import sys,json,time,io,calendar,uuid
from pathlib import Path
from datetime import datetime,timezone,time as dt_time
from zoneinfo import ZoneInfo
import streamlit as st
import pandas as pd

from config_loader import load_config

ROOT=Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from Dashboard.cards import signal_card,result_card,valid_geometry,rr_value
from Dashboard.i18n import tr,localize_df,option_label,timeframe_label,weekdays_short
from Dashboard.analytics import mt5_snapshot,performance,calendar_matrix,read_monitor_alerts,prop_firm_status,bootstrap_simulation
from telegram.publisher import get_me,send_photo
from storage.repo import (
    next_signal_id,save_signal,update_mt5,list_signals,get_signal,save_result,list_results,
    list_trade_events,list_report_runs,list_trade_metrics,list_trade_notes,upsert_trade_note,
    list_account_snapshots,get_state,list_trade_reviews,list_auto_journal,
    ensure_setup_names,create_setup,update_setup,list_setups,get_setup,add_setup_item,
    update_setup_item,delete_setup_item,list_setup_items,save_signal_setup_score,
    get_signal_setup_score,list_signal_setup_scores,add_archive_file,list_archive_files,
    ensure_default_trailing_profiles,list_trailing_profiles,get_trailing_profile,save_trailing_profile,
    save_signal_trailing_plan,get_signal_trailing_plan,update_signal_trailing_plan,list_signal_trailing_plans,list_trailing_actions,
    upsert_autotrade_client,list_autotrade_clients,save_client_trailing_policy,get_client_trailing_policy,
    list_client_trailing_policies,client_trailing_access,
    create_signal_durable,outbox_status,list_outbox,schema_version
)
from mt5trade.executor import MT5Executor
from mt5trade.service import execute_persisted_signal
from monitor.mt5_result_chart import generate_result_chart
from monitor.performance_reports import manual_report
from monitor.trade_metrics import backfill_trade_metrics
from monitor.trade_review import backfill_trade_reviews
from risk.risk_engine import set_manual_kill_switch,manual_kill_switch
from monitor.workflow import audit,backfill_workflow_from_existing,build_workflow_registry,STAGES
from storage.repo import list_workflow_events
from strategy.setup_engine import score_checklist,setup_performance,score_band_performance,checklist_edge_analysis
from Dashboard.trade_archive import collect_trade_images,safe_filename,parse_snapshot
from trailing.engine import build_signal_plan,validate_targets
from telegram.outbox import deliver_item

CFG=load_config()
LANG=str(CFG.get('dashboard',{}).get('language','fa')).lower()
if LANG not in ('fa','en'): LANG='fa'
t=lambda key,**kw:tr(LANG,key,**kw)
SYMBOLS=CFG['symbols']; TIMEFRAMES=CFG['timeframes']
SIG_DIR=ROOT/'uploads'/'signals'; RES_DIR=ROOT/'uploads'/'results'; PREVIEW_DIR=ROOT/'uploads'/'preview'; ARCHIVE_DIR=ROOT/'uploads'/'archive'
for p in (SIG_DIR,RES_DIR,PREVIEW_DIR,ARCHIVE_DIR):p.mkdir(parents=True,exist_ok=True)
ensure_setup_names(CFG.get('analytics',{}).get('setup_tags',['SCALP']))
ensure_default_trailing_profiles()

def _save_dashboard_language(code):
    path=ROOT/'config.json'
    data=json.load(open(path,'r',encoding='utf-8'))
    data.setdefault('dashboard',{})['language']=code
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(path)

def show_df(data,**kwargs):
    return st.dataframe(localize_df(data,LANG),**kwargs)

st.set_page_config(page_title=t('NEXUS v0.9.20 Stabilization & Reliability'),page_icon='⚡',layout='wide',initial_sidebar_state='collapsed')
rtl='rtl' if LANG=='fa' else 'ltr'; align='right' if LANG=='fa' else 'left'
st.markdown(f'''<style>
.stApp{{background:#070A11;direction:{rtl}}}.block-container{{max-width:1720px;padding-top:.8rem;padding-bottom:2rem}}
.hero{{padding:19px 24px;border:1px solid #24304A;border-radius:20px;background:linear-gradient(135deg,#11192A,#090F1B);margin-bottom:12px;text-align:{align}}}
.hero h2{{margin:0 0 3px 0}}.hero small{{opacity:.72}}.section{{font-weight:700;letter-spacing:.04em;font-size:.78rem;opacity:.72;margin:8px 0 5px;text-align:{align}}}
[data-testid="stMetric"]{{background:#0E1420;border:1px solid #222D43;padding:12px;border-radius:15px}}
[data-testid="stMetricValue"]{{direction:ltr;text-align:{align}}}
.health{{padding:8px 12px;border-radius:999px;border:1px solid #2A3650;display:inline-block;margin:2px 5px 2px 0;font-weight:650}}
.cal{{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}}.cal-head{{font-size:.72rem;opacity:.65;text-align:center;padding:5px}}
.cal-cell{{min-height:78px;border:1px solid #202B40;border-radius:11px;padding:8px;background:#0D1320}}.cal-dim{{opacity:.22}}.cal-pos{{border-color:#24583D}}.cal-neg{{border-color:#633238}}.cal-flat{{border-color:#2A3549}}
.cal-day{{font-weight:700}}.cal-pl{{font-size:.92rem;margin-top:9px;direction:ltr}}.timeline{{border-{'right' if LANG=='fa' else 'left'}:2px solid #2B3852;padding-{'right' if LANG=='fa' else 'left'}:14px;margin-{'right' if LANG=='fa' else 'left'}:8px}}.timeline-item{{margin:0 0 10px;padding:8px 10px;border:1px solid #202B40;border-radius:10px;background:#0C121D}}
.stCodeBlock, code, pre{{direction:ltr;text-align:left}}
.wf-card{{padding:11px;border:1px solid #28344C;border-radius:13px;background:#0D1421;min-height:92px;text-align:center}}
.wf-done{{border-color:#24583D}}.wf-warn{{border-color:#7A6420}}.wf-error{{border-color:#71353D}}.wf-skip{{opacity:.55}}
.wf-title{{font-size:.76rem;font-weight:700;opacity:.78}}.wf-state{{font-size:.82rem;margin-top:8px;font-weight:750}}.wf-time{{font-size:.65rem;opacity:.58;margin-top:5px;direction:ltr}}
</style>''',unsafe_allow_html=True)

lc1,lc2=st.columns([8,1.35])
with lc2:
    selected_lang=st.selectbox(t('Language / زبان'),['fa','en'],index=0 if LANG=='fa' else 1,format_func=lambda x:t('Persian') if x=='fa' else t('English'),key='dashboard_language_selector')
if selected_lang!=LANG:
    _save_dashboard_language(selected_lang)
    st.rerun()

st.markdown(f'<div class="hero"><h2>⚡ NEXUS v0.9.20</h2><small>Stabilization & Reliability · {t("Trailing profiles • Multi-TP ladder management • Client policies • Strategy Builder • Trade Archive")}</small></div>',unsafe_allow_html=True)

signals=list_signals(); events=list_trade_events(); metrics=list_trade_metrics(); notes=list_trade_notes(); manual_results=list_results(); snapshots=list_account_snapshots(5000)
reviews=list_trade_reviews(); auto_journal=list_auto_journal(); review_map={r['signal_id']:r for r in reviews}; journal_map={r['signal_id']:r for r in auto_journal}
setup_defs=list_setups(); setup_scores=list_signal_setup_scores(); setup_score_map={r['signal_id']:r for r in setup_scores}
workflow_audit=list_workflow_events(limit=100000); workflow_rows,workflow_details=build_workflow_registry(signals,workflow_audit,events,metrics,list_report_runs(10000),CFG.get('workflow',{}).get('stall_wait_minutes',5))
risk_wrap=get_state('risk_intelligence_state'); risk_state=(risk_wrap.get('value',{}) if isinstance(risk_wrap,dict) else {}) or {}; manual_kill=manual_kill_switch()
snap=mt5_snapshot(CFG,signals)
perf=performance(signals,events,metrics,notes,CFG,manual_results)
prop=prop_firm_status(CFG,snap,snapshots)
delivery_state=outbox_status();db_schema_version=schema_version()

# Health strip
heartbeat=get_state('monitor_heartbeat')
mon_age=None
if heartbeat:
    try:
        h=datetime.fromisoformat(str(heartbeat['updated_at'])).replace(tzinfo=timezone.utc)
        mon_age=(datetime.now(timezone.utc)-h).total_seconds()
    except Exception:pass
mt5_label=t('MT5 LIVE') if snap.get('connected') else t('MT5 OFFLINE')
monitor_label=t('MONITOR LIVE') if mon_age is not None and mon_age<20 else t('MONITOR STALE')
report_runs=list_report_runs(1); last_report=report_runs[0]['created_at'] if report_runs else '—'
st.markdown(f'<span class="health">{mt5_label}</span><span class="health">{monitor_label}</span><span class="health">OUTBOX {delivery_state.get("pending",0)} queued / {delivery_state.get("failed",0)} attention</span><span class="health">DB v{db_schema_version}</span><span class="health">{t('RISK')} {option_label(perf['risk_health'],LANG)}</span><span class="health">{t('NEXUS SCORE')} {perf['nexus_score']:.0f}/100</span><span class="health">{t('Kill Switch')} {t('ACTIVE') if risk_state.get('kill_switch') or manual_kill.get('enabled') else t('READY')}</span><span class="health">{t('LAST REPORT')} {last_report}</span>',unsafe_allow_html=True)

tabs=st.tabs([f'🏠 {t("COMMAND")}',f'🔄 {t("WORKFLOW")}',f'🧩 {t("STRATEGY BUILDER")}',f'🧭 {t("TRAILING")}',f'📈 {t("ANALYTICS")}',f'🛡️ {t("RISK TAB")}',f'📅 {t("CALENDAR")}',f'📤 {t("SIGNAL")}',f'🗃️ {t("TRADE ARCHIVE")}',f'📝 {t("JOURNAL")}',f'📑 {t("REPORTS")}',f'📚 {t("EXPLORER")}',f'🛟 {t("OVERRIDE")}',f'⚙️ {t("SYSTEM")}'])
tab_cmd,tab_workflow,tab_strategy,tab_trailing,tab_an,tab_risk,tab_cal,tab_sig,tab_archive,tab_journal,tab_reports,tab_explorer,tab_manual,tab_system=tabs

with tab_cmd:
    st.markdown(f'<div class="section">{t("MT5 ACCOUNT — LIVE")}</div>',unsafe_allow_html=True)
    a=st.columns(7)
    a[0].metric(t('Balance'),f"{snap['balance']:,.2f}"); a[1].metric(t('Equity'),f"{snap['equity']:,.2f}",f"{snap['floating_pl']:+,.2f} {t('floating')}")
    a[2].metric(t('Free Margin'),f"{snap['free_margin']:,.2f}"); a[3].metric(t('Open'),snap['open_positions']); a[4].metric(t('Pending'),snap['pending_orders'])
    a[5].metric(t('Account DD'),f"{snap['current_drawdown_pct']:.2f}%"); a[6].metric(t('NEXUS Open Risk'),f"{snap['nexus_open_risk_pct']:.2f}%")

    st.markdown(f'<div class="section">{t("NEXUS STRATEGY — REALIZED")}</div>',unsafe_allow_html=True)
    n=st.columns(8)
    n[0].metric(t('Closed'),perf['total_trades']); n[1].metric(t('Win Rate'),f"{perf['win_rate']:.1f}%"); n[2].metric(t('Net P/L'),f"{perf['net_profit']:+,.2f}")
    pf=perf['profit_factor']; n[3].metric(t('Profit Factor'),'∞' if pf==float('inf') else f'{pf:.2f}'); n[4].metric(t('Expectancy'),f"{perf['expectancy_r']:+.2f}R")
    n[5].metric(t('Max DD'),f"{perf['max_drawdown_r']:.2f}R"); n[6].metric(t('Consistency'),f"{perf['consistency_score']:.0f}/100"); n[7].metric(t('Score'),f"{perf['nexus_score']:.0f}/100")

    c1,c2=st.columns([1.7,1],gap='large')
    with c1:
        st.subheader(t('Equity / R Performance'))
        if perf['curve'].empty:st.info(t('No fully closed NEXUS trades yet.'))
        else:
            curve_view=localize_df(perf['curve'],LANG)
            trade_col='معامله' if LANG=='fa' else 'Trade'; pl_col='سود/زیان تجمعی' if LANG=='fa' else 'Cumulative P/L'; ddr_col='افت R' if LANG=='fa' else 'Drawdown R'
            st.line_chart(curve_view.set_index(trade_col)[[pl_col]],height=300,use_container_width=True)
            st.area_chart(curve_view.set_index(trade_col)[[ddr_col]],height=190,use_container_width=True)
    with c2:
        st.subheader(t('NEXUS Score'))
        st.progress(min(1.0,max(0.0,perf['nexus_score']/100.0)))
        comp=pd.DataFrame([{'Component':option_label(k,LANG),'Points':v} for k,v in perf['score_components'].items()])
        if not comp.empty:st.bar_chart(comp.set_index('Component'),height=250,use_container_width=True)
        s=perf['streaks']; st.caption(f"{t('Best win streak')}: {s['best_win_streak']} · {t('Best loss streak')}: {s['best_loss_streak']} · {t('Current')}: {option_label(s['current_streak_type'],LANG)} {s['current_streak']}")

    st.subheader(t('Live MT5 Positions'))
    if snap['positions']:show_df(pd.DataFrame(snap['positions']),use_container_width=True,hide_index=True,height=260)
    else:st.caption(t('No live MT5 positions.'))
    st.subheader(t('Lifecycle Timeline'))
    if events:
        html='<div class="timeline">'
        for e in events[:10]:
            html+=f'<div class="timeline-item"><b>{e.get("signal_id")}</b> · {option_label(e.get('event_type'),LANG)} · P/L {float(e.get("event_profit") or 0):+,.2f}<br><small>{e.get("event_time") or ""}</small></div>'
        html+='</div>'; st.markdown(html,unsafe_allow_html=True)
    else:st.caption(t('No lifecycle events yet.'))


with tab_workflow:
    st.subheader(t('Workflow Manager'))
    st.caption(t('End-to-end audit trail from signal creation to reporting.'))
    total=len(workflow_rows)
    attention=sum(1 for x in workflow_rows if x.get('health') in ('RED','YELLOW'))
    completed=sum(1 for x in workflow_rows if x.get('current_stage') in ('RESULT_SENT','REPORT_INCLUDED'))
    reported=sum(1 for x in workflow_rows if int(x.get('reports') or 0)>0)
    active=sum(1 for x in workflow_rows if x.get('current_stage') not in ('RESULT_SENT','REPORT_INCLUDED') and x.get('mt5_status') not in ('FAILED','BLOCKED'))
    k=st.columns(5)
    k[0].metric(t('Total Workflows'),total); k[1].metric(t('Active Workflows'),active); k[2].metric(t('Completed Trades'),completed); k[3].metric(t('Needs Attention'),attention); k[4].metric(t('Reported'),reported)

    if not workflow_rows:
        st.info(t('No workflow exists yet.'))
    else:
        wfdf=pd.DataFrame(workflow_rows)
        f1,f2,f3=st.columns([1,1.5,1])
        health_options=['ALL','GREEN','YELLOW','RED']
        hf=f1.selectbox(t('Health Filter'),health_options,format_func=lambda x:t('ALL') if x=='ALL' else option_label(x,LANG))
        visible=wfdf if hf=='ALL' else wfdf[wfdf['health']==hf]
        sid_options=visible['signal_id'].astype(str).tolist() if not visible.empty else wfdf['signal_id'].astype(str).tolist()
        selected=f2.selectbox(t('Select Workflow'),sid_options,key='workflow_sid')
        if f3.button(t('BACKFILL / REPAIR WORKFLOW AUDIT'),use_container_width=True):
            try:
                r=backfill_workflow_from_existing(); st.session_state['workflow_backfill']=r
                st.success(t('Workflow audit rebuilt safely.')); time.sleep(.25); st.rerun()
            except Exception as e:st.error(str(e))

        st.write(t('Workflow Registry'))
        show_cols=[c for c in ['signal_id','symbol','direction','health','current_stage','mt5_status','monitor_state','mt5_ticket','position_id','partials','result','reports','elapsed_min','last_activity','issue'] if c in visible.columns]
        show_df(visible[show_cols],use_container_width=True,hide_index=True,height=245)

        sig=next((x for x in signals if x.get('signal_id')==selected),None)
        detail=workflow_details.get(selected,{})
        if sig:
            st.divider(); st.subheader(f"{t('Stage Board')} · {selected}")
            board=detail.get('stages',[])
            labels={
                'SIGNAL_CREATED':t('Signal Created'),'TELEGRAM_SENT':t('Telegram Sent'),'PRE_TRADE_GATE':t('Pre-Trade Gate Stage'),
                'MT5_ORDER':t('MT5 Order Stage'),'POSITION_OPEN':t('Position Open Stage'),'TRAILING_MANAGEMENT':t('Trailing Management'),'PARTIAL_CLOSE':t('Partial Close Stage'),
                'FINAL_CLOSE':t('Final Close Stage'),'RESULT_SENT':t('Result Sent Stage'),'REPORT_INCLUDED':t('Report Included Stage')
            }
            icons={'DONE':'✅','WARN':'⚠️','ERROR':'❌','BLOCKED':'⛔','SKIPPED':'➖','OPTIONAL':'○','WAITING':'⏳','PENDING':'…'}
            # stages in two compact rows for legibility.
            for chunk in (board[:5],board[5:]):
                cols=st.columns(len(chunk))
                for col,item in zip(cols,chunk):
                    status=str(item.get('status') or 'PENDING'); cls='wf-done' if status=='DONE' else ('wf-warn' if status in ('WARN','WAITING','PENDING') else ('wf-error' if status in ('ERROR','BLOCKED') else 'wf-skip'))
                    when=str(item.get('event_time') or '')
                    col.markdown(f'<div class="wf-card {cls}"><div class="wf-title">{labels.get(item.get("stage"),item.get("stage"))}</div><div class="wf-state">{icons.get(status,"•")} {option_label(status,LANG)}</div><div class="wf-time">{when[:19]}</div></div>',unsafe_allow_html=True)

            info=st.columns(6)
            info[0].metric(t('Health'),option_label(detail.get('health','UNKNOWN'),LANG)); info[1].metric(t('Current Stage'),option_label(detail.get('current_stage','—'),LANG))
            info[2].metric('Telegram ID',sig.get('telegram_message_id') or '—'); info[3].metric('MT5 Ticket',sig.get('mt5_ticket') or '—'); info[4].metric('Position ID',sig.get('mt5_position_id') or '—'); info[5].metric(t('Elapsed'),'—' if detail.get('elapsed_minutes') is None else f"{detail.get('elapsed_minutes'):.1f} min")
            if detail.get('issue'):st.warning(f"{t('Attention')}: {detail.get('issue')}")

            st.subheader(t('Workflow Timeline'))
            audits=list_workflow_events(selected,limit=500,ascending=True)
            if audits:
                html='<div class="timeline">'
                for a in audits:
                    html+=f'<div class="timeline-item"><b>{option_label(a.get("stage"),LANG)}</b> · {option_label(a.get("status"),LANG)} · <small>{a.get("source") or ""}</small><br>{a.get("detail") or ""}<br><small>{a.get("event_time") or ""}</small></div>'
                html+='</div>'; st.markdown(html,unsafe_allow_html=True)
            else:st.caption(t('No audit event recorded for this workflow yet.'))

            with st.expander(t('Workflow Diagnostics')):
                dcols=[c for c in ['signal_id','symbol','direction','timeframe','mt5_status','monitor_state','mt5_ticket','mt5_position_id','telegram_message_id','last_event_message_id','safety_status','safety_reasons','mt5_error','created_at','closed_at'] if c in sig]
                show_df(pd.DataFrame([{c:sig.get(c) for c in dcols}]),use_container_width=True,hide_index=True)
                raw=list_workflow_events(selected,limit=500,ascending=True)
                if raw:show_df(pd.DataFrame(raw),use_container_width=True,hide_index=True)


with tab_strategy:
    st.subheader(t('NEXUS Strategy Builder'))
    st.caption(t('Create your own setups, give every checklist rule a weight, and preserve the exact checklist snapshot used for every signal.'))
    left,right=st.columns([1,1.35],gap='large')
    with left:
        st.write(t('**Setup Library**'))
        with st.form('create_setup_form',clear_on_submit=True):
            new_name=st.text_input(t('Setup Name'),placeholder='NY Liquidity Sweep')
            new_desc=st.text_area(t('Setup Description'),height=90)
            if st.form_submit_button(t('CREATE / UPDATE SETUP'),type='primary',use_container_width=True):
                try:
                    create_setup(new_name,new_desc);st.success(t('Setup saved.'));time.sleep(.2);st.rerun()
                except Exception as e:st.error(str(e))
        setups_now=list_setups()
        if setups_now:
            setup_ids={f"{x['name']} {'✓' if x.get('active') else '○'}":x['id'] for x in setups_now}
            selected_label=st.selectbox(t('Manage Setup'),list(setup_ids.keys()))
            managed=get_setup(setup_ids[selected_label])
            with st.form('edit_setup_form'):
                ename=st.text_input(t('Setup Name'),value=managed.get('name') or '')
                edesc=st.text_area(t('Setup Description'),value=managed.get('description') or '',height=85)
                eactive=st.checkbox(t('Active'),value=bool(managed.get('active',1)))
                if st.form_submit_button(t('SAVE SETUP SETTINGS'),use_container_width=True):
                    try:update_setup(managed['id'],ename,edesc,eactive);st.success(t('Setup updated.'));time.sleep(.2);st.rerun()
                    except Exception as e:st.error(str(e))
    with right:
        st.write(t('**Weighted Checklist**'))
        active_setups=list_setups(active_only=False)
        if not active_setups:st.info(t('Create a setup first.'))
        else:
            by_name={x['name']:x for x in active_setups}; cname=st.selectbox(t('Checklist Setup'),list(by_name.keys()),key='builder_checklist_setup');csetup=by_name[cname]
            items=list_setup_items(csetup['id'],active_only=False)
            if items:
                item_df=pd.DataFrame([{'ID':x['id'],'Checklist Item':x['item_text'],'Weight':x['weight'],'Required':bool(x['required']),'Active':bool(x['active']),'Order':x['sort_order']} for x in items])
                show_df(item_df,use_container_width=True,hide_index=True,height=250)
            else:st.caption(t('No checklist items yet.'))
            with st.form('add_checklist_item',clear_on_submit=True):
                ci1,ci2,ci3=st.columns([3,1,1])
                item_text=ci1.text_input(t('Checklist Item'))
                weight=ci2.number_input(t('Weight'),min_value=0.1,max_value=100.0,value=10.0,step=1.0)
                required=ci3.checkbox(t('Required'))
                if st.form_submit_button(t('ADD CHECKLIST ITEM'),type='primary',use_container_width=True):
                    try:add_setup_item(csetup['id'],item_text,weight,required);st.success(t('Checklist item added.'));time.sleep(.2);st.rerun()
                    except Exception as e:st.error(str(e))
            if items:
                edit_ids={f"#{x['id']} · {x['item_text']}":x for x in items}; el=st.selectbox(t('Edit Checklist Item'),list(edit_ids.keys()));ei=edit_ids[el]
                ec1,ec2,ec3,ec4=st.columns([3,1,1,1])
                etext=ec1.text_input(t('Checklist Item'),value=ei['item_text'],key=f"eit_{ei['id']}")
                eweight=ec2.number_input(t('Weight'),0.1,100.0,float(ei['weight']),1.0,key=f"eiw_{ei['id']}")
                ereq=ec3.checkbox(t('Required'),value=bool(ei['required']),key=f"eir_{ei['id']}")
                eact=ec4.checkbox(t('Active'),value=bool(ei['active']),key=f"eia_{ei['id']}")
                b1,b2=st.columns(2)
                if b1.button(t('UPDATE CHECKLIST ITEM'),use_container_width=True):
                    update_setup_item(ei['id'],etext,eweight,ereq,eact);st.rerun()
                if b2.button(t('DELETE CHECKLIST ITEM'),use_container_width=True):
                    delete_setup_item(ei['id']);st.rerun()
    st.divider();st.subheader(t('Setup Evolution'))
    st.caption(t('Historical performance by setup score and by individual checklist condition. This is descriptive analytics, not a prediction.'))
    sp=setup_performance(list_signal_setup_scores(),perf['trades']);bands=score_band_performance(list_signal_setup_scores(),perf['trades'])
    p1,p2=st.columns(2,gap='large')
    with p1:
        st.write(t('**Setup Performance**'));show_df(sp,use_container_width=True,hide_index=True,height=280) if not sp.empty else st.caption(t('No scored closed trades yet.'))
    with p2:
        st.write(t('**Score Bands**'));show_df(bands,use_container_width=True,hide_index=True,height=280) if not bands.empty else st.caption(t('No scored closed trades yet.'))
    setups_for_edge=['ALL']+[x['name'] for x in list_setups()]
    edge_filter=st.selectbox(t('Checklist Impact Setup'),setups_for_edge)
    edge=checklist_edge_analysis(list_signal_setup_scores(),perf['trades'],None if edge_filter=='ALL' else edge_filter)
    st.write(t('**Checklist Impact / Edge**'))
    if edge.empty:st.caption(t('More scored closed trades are needed for checklist impact analysis.'))
    else:show_df(edge,use_container_width=True,hide_index=True,height=330)


with tab_trailing:
    st.subheader(t('Trailing Profiles & Client Policies'))
    st.caption(t('Create reusable trade-management profiles. Admin controls which AutoTrade clients may use trailing and whether they may customize it.'))
    profiles=list_trailing_profiles(active_only=False)
    profile_by_name={x['name']:x for x in profiles}

    c1,c2=st.columns([1.05,1.35],gap='large')
    with c1:
        st.write(t('**Trailing Profile Library**'))
        if profiles:
            pdf=pd.DataFrame([{
                'ID':x['id'],'Name':x['name'],'Mode':x['mode'],'Active':bool(x['active']),
                'User Override':bool(x['allow_user_override']),'Description':x.get('description') or ''
            } for x in profiles])
            show_df(pdf,use_container_width=True,hide_index=True,height=260)
        manage_options=['+ NEW PROFILE']+[x['name'] for x in profiles]
        selected_profile_name=st.selectbox(t('Manage Trailing Profile'),manage_options,key='trail_profile_manage')
        managed_profile=profile_by_name.get(selected_profile_name)
        defaults=(managed_profile.get('params') if managed_profile else {}) or {}
        default_mode=(managed_profile.get('mode') if managed_profile else 'LADDER')
        mode_options=['LADDER','R_BASED','FIXED_R','ATR','MANUAL']
        mode_idx=mode_options.index(default_mode) if default_mode in mode_options else 0
        pmode=st.selectbox(t('Trailing Mode'),mode_options,index=mode_idx,key=f'trailing_mode_{selected_profile_name}')
        with st.form('trailing_profile_form'):
            pname=st.text_input(t('Profile Name'),value=managed_profile.get('name','') if managed_profile else '')
            pdesc=st.text_area(t('Profile Description'),value=managed_profile.get('description','') if managed_profile else '',height=85)
            pa1,pa2=st.columns(2)
            pactive=pa1.checkbox(t('Active'),value=bool(managed_profile.get('active',1)) if managed_profile else True)
            poverride=pa2.checkbox(t('Allow User Customization'),value=bool(managed_profile.get('allow_user_override',0)) if managed_profile else True)
            params={}
            if pmode=='LADDER':
                a,b,c,d=st.columns(4)
                first_partial=a.number_input(t('TP1 Partial %'),min_value=0.0,max_value=95.0,value=float(defaults.get('first_partial_percent',50.0)),step=5.0)
                hard_final=b.checkbox(t('Hard Final TP'),value=bool(defaults.get('hard_final_target',True)))
                max_targets=c.number_input(t('Max Targets'),min_value=2,max_value=8,value=int(defaults.get('max_targets',5)),step=1)
                basis=d.selectbox(t('Partial Basis'),['INITIAL','REMAINING'],index=0 if str(defaults.get('close_percent_basis','INITIAL')).upper()=='INITIAL' else 1)
                params={'first_partial_percent':first_partial,'close_percent_basis':basis,'hard_final_target':hard_final,
                        'broker_tp_mode':'LAST_TARGET' if hard_final else 'NONE','max_targets':int(max_targets),'min_targets':2,'publish_management_updates':False}
            elif pmode=='R_BASED':
                st.caption(t('Define stages as JSON: trigger_r, lock_r and optional close_percent.'))
                raw_default=json.dumps(defaults.get('stages',[{'trigger_r':1.0,'lock_r':0.0,'close_percent':0.0}]),ensure_ascii=False,indent=2)
                raw_stages=st.text_area(t('R-Based Stages JSON'),value=raw_default,height=180)
                broker=st.selectbox(t('Broker TP Mode'),['SIGNAL_TP','NONE'],index=0 if defaults.get('broker_tp_mode','SIGNAL_TP')=='SIGNAL_TP' else 1)
                try:stages_json=json.loads(raw_stages)
                except Exception:stages_json=None
                params={'stages':stages_json or [],'broker_tp_mode':broker}
                if stages_json is None:st.warning(t('Invalid JSON; saving is blocked until it is valid.'))
            elif pmode=='FIXED_R':
                a,b,c,d=st.columns(4)
                activation=a.number_input(t('Activation R'),min_value=0.1,max_value=10.0,value=float(defaults.get('activation_r',1.0)),step=.1)
                distance=b.number_input(t('Trail Distance R'),min_value=0.05,max_value=5.0,value=float(defaults.get('trail_distance_r',.5)),step=.05)
                step=c.number_input(t('Trail Step R'),min_value=0.01,max_value=2.0,value=float(defaults.get('step_r',.1)),step=.05)
                broker=d.selectbox(t('Broker TP Mode'),['NONE','SIGNAL_TP'],index=0 if defaults.get('broker_tp_mode','NONE')=='NONE' else 1)
                params={'activation_r':activation,'trail_distance_r':distance,'step_r':step,'broker_tp_mode':broker}
            elif pmode=='ATR':
                a,b,c,d=st.columns(4)
                activation=a.number_input(t('Activation R'),min_value=0.1,max_value=10.0,value=float(defaults.get('activation_r',1.0)),step=.1)
                period=b.number_input(t('ATR Period'),min_value=2,max_value=100,value=int(defaults.get('atr_period',14)),step=1)
                mult=c.number_input(t('ATR Multiplier'),min_value=.1,max_value=10.0,value=float(defaults.get('atr_multiplier',2.0)),step=.1)
                tf=d.selectbox(t('ATR Timeframe'),['M1','M5','M15','M30','H1'],index=['M1','M5','M15','M30','H1'].index(str(defaults.get('timeframe','M5'))) if str(defaults.get('timeframe','M5')) in ['M1','M5','M15','M30','H1'] else 1)
                broker=st.selectbox(t('Broker TP Mode'),['NONE','SIGNAL_TP'],index=0 if defaults.get('broker_tp_mode','NONE')=='NONE' else 1)
                params={'activation_r':activation,'atr_period':int(period),'atr_multiplier':mult,'timeframe':tf,'broker_tp_mode':broker}
            else:
                params={'broker_tp_mode':'SIGNAL_TP'}
            can_save=bool(pname.strip()) and not (pmode=='R_BASED' and stages_json is None)
            if st.form_submit_button(t('SAVE TRAILING PROFILE'),type='primary',use_container_width=True,disabled=not can_save):
                try:
                    save_trailing_profile(pname,pmode,pdesc,params,pactive,poverride,managed_profile.get('id') if managed_profile else None)
                    st.success(t('Trailing profile saved.'));time.sleep(.2);st.rerun()
                except Exception as e:st.error(str(e))

    with c2:
        st.write(t('**Live Trailing Registry**'))
        plans=list_signal_trailing_plans()
        if plans:
            show_df(pd.DataFrame([{
                'signal_id':x['signal_id'],'Profile':x.get('profile_name'),'Mode':x.get('mode'),'Enabled':bool(x.get('enabled')),
                'Stage':x.get('current_stage'),'Status':x.get('status'),'Targets':', '.join(str(v) for v in (x.get('targets') or [])),
                'Last Error':x.get('last_error') or ''
            } for x in plans]),use_container_width=True,hide_index=True,height=260)
        else:st.caption(t('No signal trailing plan exists yet.'))
        actions=list_trailing_actions(limit=250)
        with st.expander(t('Recent Trailing Actions'),expanded=False):
            if actions:show_df(pd.DataFrame(actions),use_container_width=True,hide_index=True,height=300)
            else:st.caption(t('No trailing action exists yet.'))

    st.divider();st.subheader(t('AutoTrade Client Policies'))
    st.caption(t('This admin policy layer is ready now. Actual remote execution on customer PCs will be consumed by the upcoming AutoTrade Client / Signal Server.'))
    clients=list_autotrade_clients();policies={x['client_id']:x for x in list_client_trailing_policies()}
    left,right=st.columns(2,gap='large')
    with left:
        st.write(t('**Client Registry**'))
        if clients:show_df(pd.DataFrame(clients),use_container_width=True,hide_index=True,height=230)
        with st.form('autotrade_client_form'):
            client_id=st.text_input(t('Client ID'),placeholder='CLIENT-001').strip().upper()
            display_name=st.text_input(t('Client Name'),placeholder='Ali / Account 1')
            z1,z2,z3=st.columns([1,1,1])
            client_enabled=z1.checkbox(t('Enabled'),value=True)
            exp_date=z2.date_input(t('Subscription Expiry Date'))
            exp_time=z3.time_input(t('Expiry Time'),value=dt_time(23,59))
            client_notes=st.text_area(t('Client Notes'),height=70)
            if st.form_submit_button(t('SAVE CLIENT'),type='primary',use_container_width=True,disabled=not(client_id and display_name.strip())):
                tz=ZoneInfo(CFG.get('analytics',{}).get('timezone','Asia/Tehran'))
                expiry=datetime.combine(exp_date,exp_time,tzinfo=tz).isoformat(timespec='minutes')
                upsert_autotrade_client(client_id,display_name,client_enabled,expiry,client_notes)
                st.success(t('Client saved.'));time.sleep(.2);st.rerun()
    with right:
        st.write(t('**Trailing Access Policy**'))
        clients=list_autotrade_clients()
        if not clients:st.info(t('Create an AutoTrade client first.'))
        else:
            client_map={f"{x['display_name']} · {x['client_id']}":x for x in clients}
            csel=st.selectbox(t('Manage Client Policy'),list(client_map.keys()));client=client_map[csel];curpol=policies.get(client['client_id']) or {}
            active_profiles=list_trailing_profiles(active_only=True);profile_map={x['name']:x for x in active_profiles}
            assigned_id=curpol.get('assigned_profile_id');assigned_name=next((x['name'] for x in active_profiles if x['id']==assigned_id),active_profiles[0]['name'] if active_profiles else '')
            with st.form('client_trailing_policy_form'):
                pe=st.checkbox(t('Enable Trailing For Client'),value=bool(curpol.get('enabled',0)))
                assigned=st.selectbox(t('Assigned Profile'),list(profile_map.keys()),index=list(profile_map.keys()).index(assigned_name) if assigned_name in profile_map else 0) if profile_map else ''
                customize=st.checkbox(t('Allow User Customization'),value=bool(curpol.get('allow_user_customize',0)))
                current_allowed=[x['name'] for x in active_profiles if x['id'] in (curpol.get('allowed_profile_ids') or [])]
                allowed=st.multiselect(t('Allowed Profiles'),list(profile_map.keys()),default=current_allowed or ([assigned] if assigned else []))
                if st.form_submit_button(t('SAVE CLIENT TRAILING POLICY'),type='primary',use_container_width=True,disabled=not assigned):
                    save_client_trailing_policy(client['client_id'],pe,profile_map[assigned]['id'],customize,[profile_map[x]['id'] for x in allowed],{})
                    st.success(t('Client trailing policy saved.'));time.sleep(.2);st.rerun()
            access=client_trailing_access(client['client_id'])
            if access.get('allowed'):st.success(f"{t('Access Status')}: {t('ALLOWED')} · {access.get('profile',{}).get('name')}")
            else:st.warning(f"{t('Access Status')}: {access.get('reason')}")

with tab_an:
    st.subheader(t('Performance Intelligence'))
    k=st.columns(7)
    k[0].metric(t('Avg Win'),f"{perf['avg_win_r']:+.2f}R"); k[1].metric(t('Avg Loss'),f"{perf['avg_loss_r']:+.2f}R"); k[2].metric(t('Payoff'),'∞' if perf['payoff_ratio']==float('inf') else f"{perf['payoff_ratio']:.2f}")
    k[3].metric(t('Recovery'),'∞' if perf['recovery_factor']==float('inf') else f"{perf['recovery_factor']:.2f}"); k[4].metric(t('Green Days'),perf['profitable_days']); k[5].metric(t('Red Days'),perf['loss_days']); k[6].metric(t('Compliance'),f"{perf['compliance_avg']:.0f}%")
    left,right=st.columns(2,gap='large')
    with left:
        st.write(t('**By Symbol**')); show_df(perf['symbol'],use_container_width=True,hide_index=True,height=235)
        st.write(t('**By Timeframe**')); show_df(perf['timeframe'],use_container_width=True,hide_index=True,height=235)
        st.write(t('**By Setup**')); show_df(perf['setup'],use_container_width=True,hide_index=True,height=235)
    with right:
        st.write(t('**BUY vs SELL**')); show_df(perf['direction'],use_container_width=True,hide_index=True,height=180)
        st.write(t('**Entry Session (UTC buckets)**')); show_df(perf['session'],use_container_width=True,hide_index=True,height=210)
        st.write(t('**Strategy Version**')); show_df(perf['strategy'],use_container_width=True,hide_index=True,height=210)
    c1,c2=st.columns(2,gap='large')
    with c1:
        st.write(t('**Day of Week**')); show_df(perf['weekday'],use_container_width=True,hide_index=True)
    with c2:
        st.write(t('**Entry Hour**')); show_df(perf['hour'],use_container_width=True,hide_index=True)
    st.divider(); st.subheader(t('MAE / MFE & Exit Quality'))
    if perf['trades'].empty:st.caption(t('Metrics will appear after closed trades are analyzed.'))
    else:
        cols=[c for c in ['signal_id','symbol','Result','duration_minutes','mfe_r','mae_r','exit_efficiency_pct','Grade','Compliance','metric_status'] if c in perf['trades'].columns]
        show_df(perf['trades'][cols].sort_values('signal_id',ascending=False),use_container_width=True,hide_index=True)
    st.divider(); st.subheader(t('Historical Bootstrap — What-if'))
    st.caption(t('Resamples your realized NEXUS R distribution. This is a historical stress simulation, not a forecast.'))
    q1,q2,q3=st.columns(3); future=q1.slider(t('Future trades'),20,200,50,10); sims=q2.select_slider(t('Simulations'),options=[500,1000,2000,5000],value=2000); ddlim=q3.number_input(t('DD threshold (R)'),1.0,20.0,5.0,.5)
    vals=perf['trades']['total_r'].tolist() if not perf['trades'].empty else []
    sim=bootstrap_simulation(vals,future,sims,ddlim)
    if sim.get('ok'):
        x=st.columns(5); x[0].metric(t('Median Final'),f"{sim['median_final_r']:+.2f}R"); x[1].metric(t('10th %ile'),f"{sim['p10_final_r']:+.2f}R"); x[2].metric(t('90th %ile'),f"{sim['p90_final_r']:+.2f}R"); x[3].metric(t('End Positive'),f"{sim['positive_pct']:.1f}%"); x[4].metric(f'{t("Max DD")} ≥ {ddlim:.1f}R',f"{sim['dd_breach_pct']:.1f}%")
    else:st.info(t(sim.get('reason','Not enough data.')))

with tab_risk:
    st.subheader(t('Risk Center'))
    max_total=float(CFG.get('risk_management',{}).get('max_total_open_risk_percent',4.0)); used=float(snap.get('nexus_open_risk_pct',0)); max_trade=float(CFG.get('risk_management',{}).get('max_risk_percent_per_trade',2.0))
    safe=max(0.0,min(max_trade,max_total-used))
    c=st.columns(6); c[0].metric(t('Risk Health'),option_label(perf['risk_health'],LANG)); c[1].metric(t('Open NEXUS Risk'),f'{used:.2f}%'); c[2].metric(t('Risk Capacity'),f'{max_total:.2f}%'); c[3].metric(t('Safe Next Risk'),f'{safe:.2f}%'); c[4].metric(t('Current DD'),f"{snap['current_drawdown_pct']:.2f}%"); c[5].metric(t('Unprotected Pos.'),snap.get('unprotected_positions',0))
    st.progress(min(1.0,used/max_total if max_total>0 else 0.0)); st.caption(t('Open-risk estimate uses actual MT5 position volume and SL via order_calc_profit for NEXUS-matched positions.'))
    if snap['positions']:
        p=pd.DataFrame(snap['positions']); cols=[x for x in ['NEXUS','Symbol','Type','Volume','P/L','Risk→SL','Reward→TP','Floating R','SL','TP'] if x in p.columns]; show_df(p[cols],use_container_width=True,hide_index=True)
    st.divider(); st.subheader(t('Risk Intelligence Engine'))
    ri=risk_state or {}
    rcols=st.columns(6)
    rcols[0].metric(t('Pre-Trade Gate'),option_label(ri.get('status','UNKNOWN'),LANG))
    rcols[1].metric(t('Kill Switch'),t('ACTIVE') if ri.get('kill_switch') or manual_kill.get('enabled') else t('READY'))
    rcols[2].metric(t('Throttle'),f"{float(ri.get('throttle_multiplier',1.0)):.2f}x")
    rcols[3].metric(t('Loss Streak'),int(ri.get('loss_streak',0)))
    rcols[4].metric(t('Slots'),f"{int(ri.get('position_slots_used',0))}/{int(ri.get('max_position_slots',CFG.get('risk_management',{}).get('max_open_positions',3)))}")
    rcols[5].metric(t('Open Risk'),f"{float(ri.get('open_risk_pct',used)):.2f}%")
    reasons=(ri.get('kill_reasons') or [])+(ri.get('warnings') or [])
    if reasons:st.warning(f"{t('Safety Warnings')}: "+' · '.join(map(str,reasons)))
    else:st.caption(t('No active safety warning.'))
    if ri.get('kill_switch') or manual_kill.get('enabled'):st.error(t('Telegram will still publish the signal; MT5 execution is blocked by the safety engine.'))
    elif float(ri.get('throttle_multiplier',1.0))<1.0:st.info(t('Current risk throttle will reduce the requested MT5 risk.'))
    st.divider(); st.subheader(t('Prop-Firm Mode'))
    if not prop['enabled']:
        st.info(t('Prop-Firm Mode is disabled. Configure it in SYSTEM when you want challenge limits tracked.'))
    else:
        p=st.columns(6); p[0].metric(t('Start'),f"{prop['starting_balance']:,.2f}"); p[1].metric(t('Target'),f"{prop['target_equity']:,.2f}"); p[2].metric(t('Remaining'),f"{prop['target_remaining']:,.2f}"); p[3].metric(t('Max-Loss Buffer'),f"{prop['max_loss_buffer']:,.2f}"); p[4].metric(t('Daily P/L'),'—' if prop['daily_pl'] is None else f"{prop['daily_pl']:+,.2f}"); p[5].metric(t('Daily Buffer'),'—' if prop['daily_loss_buffer'] is None else f"{prop['daily_loss_buffer']:,.2f}")
        if prop['daily_pl'] is None:st.caption(t('Daily-loss baseline appears after the monitor has recorded the first account snapshot for today.'))

with tab_cal:
    st.subheader(t('Daily P/L Calendar'))
    daily=perf['daily']
    tz=ZoneInfo(CFG.get('analytics',{}).get('timezone','Asia/Tehran')); now=datetime.now(tz)
    months=[]
    if not daily.empty:
        for d in daily['date']:
            key=f'{d.year:04d}-{d.month:02d}'
            if key not in months:months.append(key)
    cur=f'{now.year:04d}-{now.month:02d}'
    if cur not in months:months.append(cur)
    months=sorted(months,reverse=True); sel=st.selectbox(t('Month'),months,index=0); y,m=map(int,sel.split('-'))
    weeks=calendar_matrix(daily,y,m); heads=weekdays_short(LANG)
    html='<div class="cal">'+''.join(f'<div class="cal-head">{h}</div>' for h in heads)
    for week in weeks:
        for d in week:
            cls='cal-dim' if not d['in_month'] else ('cal-pos' if d['pl']>0 else ('cal-neg' if d['pl']<0 else 'cal-flat'))
            pl='—' if d['trades']==0 else f"{d['pl']:+,.2f}"
            r='—' if d['trades']==0 else f"{d['r']:+.2f}R"
            html+=f'<div class="cal-cell {cls}"><div class="cal-day">{d["date"].day}</div><div class="cal-pl">{pl}</div><small>{d["trades"]} {t('trades')} · {r}</small></div>'
    html+='</div>'; st.markdown(html,unsafe_allow_html=True)
    if not daily.empty:
        month_df=daily[daily['date'].apply(lambda d:d.year==y and d.month==m)].copy(); show_df(month_df,use_container_width=True,hide_index=True)

with tab_sig:
    left,right=st.columns([1,1.25],gap='large')
    with left:
        st.subheader(t('Manual Signal'))
        sid=st.text_input(t('Signal ID'),value=next_signal_id()).strip().upper(); symbol=st.selectbox(t('Symbol'),SYMBOLS); direction=st.radio(t('Direction'),['BUY','SELL'],horizontal=True,format_func=lambda x:option_label(x,LANG)); timeframe=st.selectbox(t('Timeframe'),TIMEFRAMES,index=5 if len(TIMEFRAMES)>5 else 0,format_func=lambda x:timeframe_label(x,LANG))
        active_setups=list_setups(active_only=True)
        if not active_setups:
            st.warning(t('No active setup exists. Create one in Strategy Builder.'))
            setup_obj={'id':None,'name':'UNSPECIFIED','description':''};setup='UNSPECIFIED'
        else:
            setup_names=[x['name'] for x in active_setups];setup=st.selectbox(t('Setup'),setup_names);setup_obj=next(x for x in active_setups if x['name']==setup)
            if setup_obj.get('description'):st.caption(setup_obj.get('description'))
        strategy=st.text_input(t('Strategy Version'),value=CFG.get('analytics',{}).get('default_strategy_version','NEXUS-v1')).strip() or 'NEXUS-v1'
        checklist_items=list_setup_items(setup_obj['id']) if setup_obj.get('id') else []
        checklist_answers={}
        if checklist_items:
            st.markdown(f'**{t("Pre-Trade Setup Checklist")}**')
            for item in checklist_items:
                label=f"{item['item_text']} · {float(item.get('weight') or 0):g} pt"+(' ⭐' if item.get('required') else '')
                checklist_answers[str(item['id'])]=st.checkbox(label,key=f"sig_check_{setup_obj['id']}_{item['id']}")
        else:st.caption(t('This setup has no checklist yet.'))
        setup_rationale=st.text_area(t('Setup Rationale / Notes'),height=90,placeholder=t('Why does this setup qualify?'))
        setup_score=score_checklist(setup_obj,checklist_items,checklist_answers,setup_rationale,CFG.get('strategy_builder',{}).get('score_grades'))
        entry=st.number_input(t('Entry'),value=0.0,format='%.8f')
        sl=st.number_input(t('Stop Loss'),value=0.0,format='%.8f')
        st.markdown(f'**{t("Trade Management / Trailing")}**')
        trail_profiles_sig=list_trailing_profiles(active_only=True)
        trail_name_map={x['name']:x for x in trail_profiles_sig}
        default_trail_name=CFG.get('trailing',{}).get('default_profile_name','NEXUS Ladder 50 + BE')
        default_idx=next((i for i,x in enumerate(trail_profiles_sig) if x['name']==default_trail_name),0)
        trailing_enabled=st.checkbox(t('Enable Trailing Management'),value=bool(CFG.get('trailing',{}).get('default_enabled',True)))
        trail_profile_name=st.selectbox(t('Trailing Profile'),[x['name'] for x in trail_profiles_sig],index=default_idx) if trail_profiles_sig else ''
        trail_profile=trail_name_map.get(trail_profile_name) or {'id':None,'name':'Manual / No Trailing','mode':'MANUAL','params':{}}
        trail_mode=str(trail_profile.get('mode') or 'MANUAL').upper();trail_params=trail_profile.get('params') or {};trail_overrides={}
        if trailing_enabled and trail_mode=='LADDER':
            max_targets=max(2,min(8,int(trail_params.get('max_targets',5))))
            target_count=st.number_input(t('Number of Targets'),min_value=2,max_value=max_targets,value=min(3,max_targets),step=1)
            tp_levels=[]
            for start in range(0,int(target_count),3):
                cols=st.columns(min(3,int(target_count)-start))
                for j,col in enumerate(cols,start+1):
                    tp_levels.append(col.number_input(f'TP{j}',value=0.0,format='%.8f',key=f'signal_tp_{j}'))
            tr1,tr2=st.columns(2)
            trail_overrides['first_partial_percent']=tr1.number_input(t('TP1 Partial %'),min_value=0.0,max_value=95.0,value=float(trail_params.get('first_partial_percent',50.0)),step=5.0,key='signal_tp1_partial')
            trail_overrides['hard_final_target']=tr2.checkbox(t('Hard Final TP'),value=bool(trail_params.get('hard_final_target',True)),key='signal_hard_final')
            trail_overrides['broker_tp_mode']='LAST_TARGET' if trail_overrides['hard_final_target'] else 'NONE'
            st.caption(t('Ladder rule: TP1 closes the configured partial and moves SL to Entry; each next target moves SL to the previous TP.'))
        else:
            tp=st.number_input(t('Take Profit'),value=0.0,format='%.8f')
            tp_levels=[tp]
            if trailing_enabled:st.caption(f"{t('Trailing Mode')}: {trail_mode} · {trail_profile.get('description') or ''}")
        tp=float(tp_levels[0]) if tp_levels else 0.0
        sizing=st.radio(t('Sizing'),['Risk %','Fixed Lot'],horizontal=True,format_func=lambda x:t(x)); risk=None; lot=None
        if sizing=='Risk %':risk=st.number_input(t('Risk %'),min_value=.01,max_value=10.0,value=float(CFG['risk_management']['default_risk_percent']),step=.1)
        else:lot=st.number_input(t('Lot'),min_value=.001,value=.01,step=.01,format='%.3f')
        chart=st.file_uploader(t('TradingView Chart'),type=['png','jpg','jpeg','webp'],key='signal_chart')
        default_mt5=bool(CFG.get('execution',{}).get('execute_by_default',True)) and not bool(CFG.get('execution',{}).get('telegram_only_default',False))
        publish_mode=st.radio(t('Execution Mode'),['Telegram + MT5 + Auto Tracking','Telegram Only'],index=0 if default_mt5 else 1,format_func=lambda x:t(x)); mt5_enabled=publish_mode.startswith('Telegram +')
        if not mt5_enabled:st.warning(t('Telegram Only: no MT5 order and no automatic lifecycle tracking.'))
        trail_plan_preview=build_signal_plan(sid,trail_profile,tp_levels,enabled=bool(trailing_enabled and mt5_enabled),client_id='ADMIN',overrides=trail_overrides)
    with right:
        st.subheader(t('Signal Preview')); values_ok=entry>0 and sl>0 and bool(tp_levels) and all(float(v)>0 for v in tp_levels); targets_ok,target_reason=validate_targets(direction,entry,tp_levels) if values_ok else (False,'INCOMPLETE'); valid=values_ok and targets_ok and valid_geometry(direction,entry,tp,sl); rr=rr_value(entry,tp,sl) if values_ok else 0.0
        q=st.columns(6); q[0].metric(t('RR'),f'1 : {rr:.2f}' if rr else '-'); q[1].metric(t('Setup'),setup); q[2].metric(t('Checklist Score'),'—' if setup_score.get('score_percent') is None else f"{setup_score['score_percent']:.0f}% · {setup_score['grade']}"); q[3].metric(t('Required Missed'),setup_score.get('required_missed',0)); q[4].metric(t('Trailing'),trail_profile_name if trailing_enabled and mt5_enabled else t('OFF')); q[5].metric(t('Execution'),t('MT5 + TRACK') if mt5_enabled else t('TELEGRAM'))
        if setup_score.get('required_missed',0)>0:st.warning(f"{t('Required Checklist Items Missing')}: {setup_score.get('required_missed')}")
        if values_ok:
            if valid:st.success(t('Price geometry valid.'))
            else:st.error(f"{t('Invalid BUY/SELL price geometry.')} · {target_reason}")
        ri_now=risk_state or {}
        gate_status=option_label(ri_now.get('status','UNKNOWN'),LANG)
        gate_mult=float(ri_now.get('throttle_multiplier',1.0))
        if ri_now.get('kill_switch') or manual_kill.get('enabled'):
            st.error(f"{t('Pre-Trade Gate')}: {gate_status} · {t('Kill Switch')}: {t('ACTIVE')}")
        elif gate_mult<1.0:
            st.warning(f"{t('Pre-Trade Gate')}: {gate_status} · {t('Throttle')}: {gate_mult:.2f}x")
        else:
            st.caption(f"{t('Pre-Trade Gate')}: {gate_status} · {t('Throttle')}: {gate_mult:.2f}x")
        card=signal_card(sid,symbol,direction,timeframe,entry,tp,sl,risk,lot,targets=tp_levels); st.code(card,language=None)
        if chart:st.image(chart,caption=t('Signal Chart'),use_container_width=True)
        checklist_allowed=not (CFG.get('strategy_builder',{}).get('require_checklist_to_publish',False) and setup_score.get('required_missed',0)>0)
        if st.button(t('📤 PUBLISH SIGNAL'),type='primary',use_container_width=True,disabled=not(valid and chart and sid.startswith('NX-') and checklist_allowed)):
            try:
                ext=Path(chart.name).suffix.lower() or '.png'; p=SIG_DIR/f'{sid}{ext}'; p.write_bytes(chart.getbuffer())
                payload={'signal_id':sid,'symbol':symbol,'direction':direction,'timeframe':timeframe,'entry':entry,'tp':tp,'sl':sl,'risk_percent':risk,'lot':lot,'rr':rr,'telegram_message_id':None,'setup_image_path':str(p),'mt5_enabled':mt5_enabled,'mt5_status':'NOT_REQUESTED','setup_tag':setup,'strategy_version':strategy,'requested_risk_percent':risk,'risk_throttle_multiplier':1.0,'publication_status':'PENDING'}
                created=create_signal_durable(payload,setup_score,trail_plan_preview,{'image_path':str(p),'text':card})
                payload['_trailing_plan']=trail_plan_preview
                audit(sid,'SIGNAL_CREATED','DONE',f'{sid}:SIGNAL_CREATED',source='DASHBOARD',detail='Signal registered')
                delivery=deliver_item(created['outbox'])
                if not delivery.get('sent'):
                    st.warning(f"Telegram queued safely · status={delivery.get('status') or delivery.get('reason')} · MT5 not sent until publication succeeds")
                    st.stop()
                mid=delivery['message_id'];payload['telegram_message_id']=mid
                st.success((f'در تلگرام منتشر شد — message_id={mid}' if LANG=='fa' else f'Telegram published — message_id={mid}'))
                audit(sid,'TELEGRAM_SENT','DONE',f'{sid}:TELEGRAM_SENT:{mid}',source='TELEGRAM',detail='Signal published through durable outbox',telegram_message_id=mid)
                if trail_plan_preview.get('enabled'):
                    audit(sid,'TRAILING_MANAGEMENT','WAITING',f'{sid}:TRAILING:ARMED',source='DASHBOARD',detail=f"{trail_plan_preview.get('profile_name')} · targets={tp_levels}",metadata={'profile':trail_plan_preview.get('profile_name'),'targets':tp_levels})
                if mt5_enabled:
                    with st.spinner(t('Sending manual values to MT5...')):exe=execute_persisted_signal(sid,CFG)
                    st.session_state['last_mt5']=exe
                    safety_json=json.dumps(exe.get('risk_intelligence',{}),ensure_ascii=False,default=str)
                    common_risk=dict(requested_risk_percent=exe.get('requested_risk_percent',risk),effective_risk_percent=exe.get('effective_risk_percent'),risk_throttle_multiplier=exe.get('risk_throttle_multiplier',1.0),safety_status=exe.get('safety_status'),safety_reasons=exe.get('safety_reasons'),safety_snapshot_json=safety_json)
                    if exe.get('success'):
                        update_mt5(sid,mt5_enabled=1,mt5_status='SENT',mt5_ticket=exe.get('ticket'),mt5_symbol=exe.get('symbol'),mt5_volume=exe.get('volume'),mt5_action=exe.get('action'),mt5_error=None,initial_volume=exe.get('volume'),last_volume=exe.get('volume'),monitor_state='WAITING',**common_risk)
                        audit(sid,'PRE_TRADE_GATE','WARN' if str(exe.get('safety_status')).upper()=='YELLOW' else 'DONE',f'{sid}:PRE_TRADE_GATE:{exe.get("ticket") or "SENT"}',source='RISK_ENGINE',detail=exe.get('safety_reasons') or exe.get('safety_status'),metadata=exe.get('risk_intelligence'))
                        audit(sid,'MT5_ORDER','DONE',f'{sid}:MT5_ORDER:{exe.get("ticket")}',source='MT5',detail=exe.get('action'),mt5_ticket=exe.get('ticket'),metadata={'volume':exe.get('volume'),'symbol':exe.get('symbol')})
                        eff=exe.get('effective_risk_percent'); throttle=exe.get('risk_throttle_multiplier',1.0)
                        detail=(f" · risk={eff:.2f}% · throttle={throttle:.2f}x" if eff is not None else f" · throttle={throttle:.2f}x")
                        st.success((f"ارسال به MT5 انجام شد — {exe.get('action')} · ticket={exe.get('ticket')} · lot={exe.get('volume')}{detail}" if LANG=='fa' else f"MT5 sent — {exe.get('action')} · ticket={exe.get('ticket')} · lot={exe.get('volume')}{detail}"))
                    elif exe.get('blocked'):
                        update_mt5(sid,mt5_enabled=1,mt5_status='BLOCKED',mt5_error=exe.get('error'),monitor_state='BLOCKED',**common_risk)
                        update_signal_trailing_plan(sid,status='BLOCKED',last_error=exe.get('error'))
                        audit(sid,'PRE_TRADE_GATE','BLOCKED',f'{sid}:PRE_TRADE_GATE:BLOCKED',source='RISK_ENGINE',detail=exe.get('error'),metadata=exe.get('risk_intelligence'))
                        audit(sid,'MT5_ORDER','BLOCKED',f'{sid}:MT5_ORDER:BLOCKED',source='RISK_ENGINE',detail=exe.get('error'))
                        st.warning(f"{t('MT5 BLOCKED — Telegram published')}: {exe.get('error')}"); st.json(exe)
                    else:
                        update_mt5(sid,mt5_enabled=1,mt5_status='FAILED',mt5_error=exe.get('error'),monitor_state='CANCELED',**common_risk); update_signal_trailing_plan(sid,status='ERROR',last_error=exe.get('error')); audit(sid,'PRE_TRADE_GATE','DONE',f'{sid}:PRE_TRADE_GATE:FAILED_ORDER',source='RISK_ENGINE',detail=exe.get('safety_reasons') or exe.get('safety_status')); audit(sid,'MT5_ORDER','ERROR',f'{sid}:MT5_ORDER:FAILED',source='MT5',detail=exe.get('error'),metadata=exe); st.error((f"اجرای MT5 ناموفق بود: {exe.get('error')}" if LANG=='fa' else f"MT5 execution failed: {exe.get('error')}")); st.json(exe)
                else:
                    audit(sid,'PRE_TRADE_GATE','SKIPPED',f'{sid}:PRE_TRADE_GATE:TELEGRAM_ONLY',source='DASHBOARD',detail='Telegram-only mode')
                    audit(sid,'MT5_ORDER','SKIPPED',f'{sid}:MT5_ORDER:TELEGRAM_ONLY',source='DASHBOARD',detail='Telegram-only mode')
                    st.warning(t('Telegram-only mode: MT5 order intentionally not requested.'))
            except Exception as e:st.error(str(e))
        if st.session_state.get('last_mt5'):
            with st.expander(t('Last MT5 diagnostics')):st.json(st.session_state['last_mt5'])


with tab_archive:
    st.subheader(t('Trade Archive'))
    st.caption(t('Every NX-ID is a permanent case file: pre-trade analysis, checklist snapshot, MT5 lifecycle, result chart, post-trade images, review and notes.'))
    all_sigs=list_signals()
    if not all_sigs:st.info(t('No signal exists yet.'))
    else:
        all_ids=[x['signal_id'] for x in all_sigs]
        default_sid=st.session_state.get('archive_sid',all_ids[0]);
        if default_sid not in all_ids:default_sid=all_ids[0]
        st.write(t('**Recent Trade Files — click NX-ID**'))
        recent=all_ids[:int(CFG.get('strategy_builder',{}).get('archive_max_recent_buttons',24))]
        for start in range(0,len(recent),8):
            cols=st.columns(min(8,len(recent[start:start+8])))
            for col,sx in zip(cols,recent[start:start+8]):
                if col.button(sx,key=f'arc_btn_{sx}',use_container_width=True):st.session_state['archive_sid']=sx;st.rerun()
        sid_arc=st.selectbox(t('Open Trade File'),all_ids,index=all_ids.index(default_sid),key='archive_select')
        if sid_arc!=st.session_state.get('archive_sid'):st.session_state['archive_sid']=sid_arc
        sig=get_signal(sid_arc) or {};sev=list_trade_events(sid_arc);mres=[x for x in list_results() if x.get('signal_id')==sid_arc]
        metric=next((x for x in metrics if x.get('signal_id')==sid_arc),{});review=review_map.get(sid_arc,{});jn=journal_map.get(sid_arc,{})
        note=next((x for x in notes if x.get('signal_id')==sid_arc),{});ss=get_signal_setup_score(sid_arc) or {}
        finals=[x for x in sev if x.get('event_type')=='FINAL_CLOSE'];final=finals[0] if finals else {}
        arfiles=list_archive_files(sid_arc);images=collect_trade_images(sig,sev,mres,arfiles)
        h=st.columns(7)
        h[0].metric('NX-ID',sid_arc);h[1].metric(t('Symbol'),sig.get('symbol') or '—');h[2].metric(t('Direction'),option_label(sig.get('direction','—'),LANG));h[3].metric(t('Setup'),ss.get('setup_name') or sig.get('setup_tag') or '—')
        h[4].metric(t('Checklist Score'),'—' if ss.get('score_percent') is None else f"{float(ss['score_percent']):.0f}% · {ss.get('grade') or ''}")
        h[5].metric(t('Result'),option_label(final.get('result_type') or jn.get('result_type') or 'OPEN',LANG));h[6].metric(t('P/L'),f"{float(final.get('total_profit') or jn.get('total_profit') or 0):+,.2f}")
        if ss.get('rationale'):st.info(f"{t('Setup Rationale / Notes')}: {ss.get('rationale')}")
        st.divider();st.subheader(t('Visual Archive'))
        if images:
            for start in range(0,len(images),3):
                cols=st.columns(min(3,len(images[start:start+3])))
                for col,img in zip(cols,images[start:start+3]):
                    with col:
                        st.image(img['path'],use_container_width=True)
                        st.caption(f"{option_label(img['category'],LANG)} · {img.get('caption') or ''} · {img.get('source') or ''}")
        else:st.caption(t('No images are stored for this trade yet.'))
        with st.expander(t('ADD BEFORE / AFTER ANALYSIS IMAGES'),expanded=False):
            category=st.selectbox(t('Image Category'),['BEFORE_ANALYSIS','AFTER_ANALYSIS','EXECUTION','OTHER'],format_func=lambda x:option_label(x,LANG))
            caption=st.text_input(t('Image Caption'))
            uploaded=st.file_uploader(t('Archive Images'),type=['png','jpg','jpeg','webp'],accept_multiple_files=True,key=f'archive_upload_{sid_arc}')
            if st.button(t('SAVE IMAGES TO TRADE ARCHIVE'),type='primary',use_container_width=True,disabled=not uploaded):
                folder=ARCHIVE_DIR/sid_arc;folder.mkdir(parents=True,exist_ok=True)
                for up in uploaded:
                    filename=f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}_{safe_filename(up.name)}";path=folder/filename;path.write_bytes(up.getbuffer());add_archive_file(sid_arc,category,str(path),caption,'ADMIN_UPLOAD')
                st.success(t('Images saved to this trade file.'));time.sleep(.2);st.rerun()
        st.divider();st.subheader(t('Setup Checklist Snapshot'))
        try:check_items=json.loads(ss.get('checklist_json') or '[]')
        except Exception:check_items=[]
        if check_items:
            cdf=pd.DataFrame([{'Status':'✅' if x.get('checked') else '❌','Checklist Item':x.get('text'),'Weight':x.get('weight'),'Required':bool(x.get('required'))} for x in check_items])
            show_df(cdf,use_container_width=True,hide_index=True)
        else:st.caption(t('No checklist snapshot exists for this signal.'))
        d1,d2=st.columns(2,gap='large')
        with d1:
            with st.expander(t('Full Signal / MT5 Details'),expanded=True):
                wanted=['signal_id','symbol','direction','timeframe','entry','tp','sl','rr','risk_percent','lot','setup_tag','strategy_version','requested_risk_percent','effective_risk_percent','risk_throttle_multiplier','safety_status','safety_reasons','mt5_status','mt5_action','mt5_ticket','mt5_position_id','mt5_symbol','mt5_volume','monitor_state','telegram_message_id','last_event_message_id','created_at','closed_at']
                show_df(pd.DataFrame([{k:sig.get(k) for k in wanted if k in sig}]),use_container_width=True,hide_index=True)
            with st.expander(t('MT5 Lifecycle Events')):
                if sev:show_df(pd.DataFrame(list(reversed(sev))),use_container_width=True,hide_index=True)
                else:st.caption(t('No lifecycle events yet.'))
            with st.expander(t('Trailing Management'),expanded=False):
                tp_arc=get_signal_trailing_plan(sid_arc);ta_arc=list_trailing_actions(sid_arc,500)
                if tp_arc:
                    st.write(f"**{t('Profile')}:** {tp_arc.get('profile_name') or '—'} · **{t('Mode')}:** {tp_arc.get('mode') or '—'} · **{t('Status')}:** {tp_arc.get('status') or '—'} · **{t('Stage')}:** {tp_arc.get('current_stage') or 0}")
                    st.write(f"**{t('Targets')}:** {', '.join(str(x) for x in (tp_arc.get('targets') or [])) or '—'}")
                    if tp_arc.get('last_error'):st.error(tp_arc.get('last_error'))
                else:st.caption(t('No signal trailing plan exists yet.'))
                if ta_arc:show_df(pd.DataFrame(list(reversed(ta_arc))),use_container_width=True,hide_index=True,height=260)
        with d2:
            with st.expander(t('Performance Metrics'),expanded=True):
                show_df(pd.DataFrame([metric]),use_container_width=True,hide_index=True) if metric else st.caption(t('No metrics yet.'))
            with st.expander(t('Trade Review / Journal')):
                if review:
                    st.metric(t('Review Score'),f"{float(review.get('review_score') or 0):.0f}/100 · {review.get('review_grade') or '—'}")
                    st.info(review.get('summary_fa') if LANG=='fa' else review.get('summary_en'))
                    st.success(review.get('recommendation_fa') if LANG=='fa' else review.get('recommendation_en'))
                if note:st.write(f"**{t('Admin Note')}:** {note.get('note') or '—'} · {t('Grade')}: {note.get('grade')} · {t('Mistake Tag')}: {option_label(note.get('mistake_tag'),LANG)}")
                if not review and not note:st.caption(t('No review or journal note yet.'))
            with st.expander(t('Workflow Timeline')):
                wa=list_workflow_events(sid_arc,limit=500,ascending=True)
                if wa:show_df(pd.DataFrame(wa),use_container_width=True,hide_index=True)
                else:st.caption(t('No audit event recorded for this workflow yet.'))

with tab_journal:
    st.subheader(t('Trade Journal & Rule Compliance'))
    if perf['trades'].empty:st.info(t('Close at least one NEXUS trade to use the journal.'))
    else:
        ids=list(reversed(perf['trades']['signal_id'].astype(str).tolist())); sidj=st.selectbox(t('Trade'),ids,key='journal_sid')
        row=perf['trades'][perf['trades']['signal_id']==sidj].iloc[-1]; note_map={n['signal_id']:n for n in notes}; cur=note_map.get(sidj,{})
        x=st.columns(6); x[0].metric(t('Result'),option_label(row.get('Result'),LANG)); x[1].metric(t('P/L'),f"{float(row.get('total_profit') or 0):+,.2f}"); x[2].metric(t('Realized'),f"{float(row.get('total_r') or 0):+.2f}R"); x[3].metric(t('MFE'),'—' if pd.isna(row.get('mfe_r')) else f"{float(row.get('mfe_r')):+.2f}R"); x[4].metric(t('MAE'),'—' if pd.isna(row.get('mae_r')) else f"{float(row.get('mae_r')):+.2f}R"); x[5].metric(t('Auto Grade'),row.get('Auto Grade'))
        st.caption(f"{t('Compliance')} {float(row.get('Compliance') or 0):.0f}% · {row.get('Compliance Flags')}")
        ssj=get_signal_setup_score(sidj) or {}
        if ssj:
            sc1,sc2,sc3=st.columns(3);sc1.metric(t('Setup'),ssj.get('setup_name') or '—');sc2.metric(t('Checklist Score'),'—' if ssj.get('score_percent') is None else f"{float(ssj['score_percent']):.0f}% · {ssj.get('grade') or ''}");sc3.metric(t('Required Missed'),int(ssj.get('required_missed') or 0))
            if ssj.get('rationale'):st.info(f"{t('Setup Rationale / Notes')}: {ssj.get('rationale')}")
            try:jc=json.loads(ssj.get('checklist_json') or '[]')
            except Exception:jc=[]
            if jc:
                with st.expander(t('Setup Checklist Snapshot')):
                    show_df(pd.DataFrame([{'Status':'✅' if x.get('checked') else '❌','Checklist Item':x.get('text'),'Weight':x.get('weight'),'Required':bool(x.get('required'))} for x in jc]),use_container_width=True,hide_index=True)
        review=review_map.get(sidj); journal=journal_map.get(sidj)
        st.divider(); st.subheader(t('AI Trade Review — Local Intelligence'))
        st.caption(t('Local deterministic expert engine; no external AI/API key is required.'))
        if review:
            rv=st.columns(3); rv[0].metric(t('Review Score'),f"{float(review.get('review_score') or 0):.0f}/100"); rv[1].metric(t('Review Grade'),review.get('review_grade') or '—'); rv[2].metric(t('Review Flags'),len(json.loads(review.get('flags_json') or '[]')))
            st.info(review.get('summary_fa') if LANG=='fa' else review.get('summary_en'))
            st.success(f"{t('Recommendation')}: "+str(review.get('recommendation_fa') if LANG=='fa' else review.get('recommendation_en')))
            flags=json.loads(review.get('flags_json') or '[]')
            if flags:st.caption(' · '.join(flags))
        else:st.caption(t('No automatic review for this trade yet.'))
        if journal:
            with st.expander(t('Auto Journal Snapshot')):
                show_df(pd.DataFrame([{k:v for k,v in journal.items() if k!='snapshot_json'}]),use_container_width=True,hide_index=True)
        with st.form('journal_form'):
            g=st.selectbox(t('Grade'),['AUTO','A','B','C','D'],index=['AUTO','A','B','C','D'].index(cur.get('grade','AUTO') if cur.get('grade','AUTO') in ['AUTO','A','B','C','D'] else 'AUTO'))
            tags=CFG.get('journal',{}).get('mistake_tags',['NONE']); ct=cur.get('mistake_tag','NONE'); mistake=st.selectbox(t('Mistake Tag'),tags,index=tags.index(ct) if ct in tags else 0,format_func=lambda x:option_label(x,LANG)); note=st.text_area(t('Admin Note'),value=cur.get('note',''),height=130)
            if st.form_submit_button(t('SAVE JOURNAL'),type='primary'):
                upsert_trade_note(sidj,g,mistake,note); st.success('ژورنال ذخیره شد. در حال تازه‌سازی…' if LANG=='fa' else 'Journal saved. Refreshing…'); time.sleep(.3); st.rerun()
        st.write(t('**Trade Details**')); show=[c for c in ['symbol','direction','timeframe','setup_tag','strategy_version','rr','risk_percent','requested_risk_percent','effective_risk_percent','risk_throttle_multiplier','safety_status','safety_reasons','duration_minutes','exit_efficiency_pct','metric_status'] if c in row.index]; show_df(pd.DataFrame([{c:row.get(c) for c in show}]),use_container_width=True,hide_index=True)

with tab_reports:
    st.subheader(t('Report Center'))
    rcfg=CFG.get('reporting',{}); c=st.columns(4); c[0].metric(t('Timezone'),rcfg.get('timezone','Asia/Tehran')); c[1].metric(t('Daily'),rcfg.get('daily',{}).get('time','23:55')); c[2].metric(t('Weekly'),f"{('جمعه' if LANG=='fa' else 'Friday')} {rcfg.get('weekly',{}).get('time','23:58')}"); c[3].metric(t('Reports Sent'),len(list_report_runs(100)))
    b1,b2=st.columns(2)
    def _send(which):
        import MetaTrader5 as mt5
        path=CFG['mt5'].get('terminal_path',''); ok=mt5.initialize(path=path) if path else mt5.initialize()
        if not ok:raise RuntimeError(f"{t('MT5 initialize failed')}: {mt5.last_error()}")
        try:return manual_report(mt5,CFG,which)
        finally:mt5.shutdown()
    if b1.button(t('SEND DAILY REPORT NOW'),use_container_width=True):
        try:r=_send('daily');st.success((f"گزارش روزانه ارسال شد · message_id={r.get('message_id')}" if LANG=='fa' else f"Daily report sent · message_id={r.get('message_id')}"))
        except Exception as e:st.error(str(e))
    if b2.button(t('SEND WEEKLY REPORT NOW'),use_container_width=True):
        try:r=_send('weekly');st.success((f"گزارش هفتگی ارسال شد · message_id={r.get('message_id')}" if LANG=='fa' else f"Weekly report sent · message_id={r.get('message_id')}"))
        except Exception as e:st.error(str(e))
    show_df(list_report_runs(100),use_container_width=True,hide_index=True)

with tab_explorer:
    st.subheader(t('Trade Explorer'))
    df=perf['trades'].copy()
    if df.empty:st.info(t('No closed trades yet.'))
    else:
        f1,f2,f3,f4=st.columns(4)
        sym=f1.selectbox(t('Symbol'),['ALL']+sorted([str(x) for x in df['symbol'].dropna().unique()]),format_func=lambda x:t('ALL') if x=='ALL' else x); res=f2.selectbox(t('Result'),['ALL','WIN','LOSS','BE'],format_func=lambda x:t('ALL') if x=='ALL' else option_label(x,LANG)); setup=f3.selectbox(t('Setup Filter'),['ALL']+sorted([str(x) for x in df.get('setup_tag',pd.Series()).dropna().unique()]),format_func=lambda x:t('ALL') if x=='ALL' else x); strat=f4.selectbox(t('Strategy Filter'),['ALL']+sorted([str(x) for x in df.get('strategy_version',pd.Series()).dropna().unique()]),format_func=lambda x:t('ALL') if x=='ALL' else x)
        if sym!='ALL':df=df[df['symbol']==sym]
        if res!='ALL':df=df[df['Result']==res]
        if setup!='ALL':df=df[df['setup_tag']==setup]
        if strat!='ALL':df=df[df['strategy_version']==strat]
        cols=[c for c in ['signal_id','symbol','direction','timeframe','setup_tag','strategy_version','Result','total_profit','total_r','requested_risk_percent','effective_risk_percent','risk_throttle_multiplier','safety_status','duration_minutes','mfe_r','mae_r','exit_efficiency_pct','Grade','Compliance','event_time'] if c in df.columns]
        outdf=df[cols].sort_values('event_time',ascending=False); show_df(outdf,use_container_width=True,hide_index=True,height=430)
        csv=outdf.to_csv(index=False).encode('utf-8-sig'); st.download_button(t('⬇️ EXPORT CSV'),csv,'NEXUS_trade_explorer.csv','text/csv')
        try:
            bio=io.BytesIO()
            with pd.ExcelWriter(bio,engine='openpyxl') as w:outdf.to_excel(w,index=False,sheet_name='Trades')
            st.download_button(t('⬇️ EXPORT EXCEL'),bio.getvalue(),'NEXUS_trade_explorer.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        except Exception as e:st.caption(f"{t('Excel export requires openpyxl')}: {e}")
    st.divider(); st.write(t('**Raw Signal Registry**')); show_df(signals,use_container_width=True,hide_index=True)
    with st.expander(t('Raw MT5 Lifecycle Events')):show_df(events,use_container_width=True,hide_index=True)
    with st.expander(t('Auto Journal Registry')):show_df(auto_journal,use_container_width=True,hide_index=True)

with tab_manual:
    st.info(t('Manual Override is emergency-only. Normal Partial/Final results are automatic from MT5.'))
    sigs=list_signals()
    if sigs:
        l,r=st.columns([1,1.2],gap='large')
        with l:
            ids=[s['signal_id'] for s in sigs]; sidr=st.selectbox(t('Signal ID'),ids,key='manual_result_signal'); sig=get_signal(sidr); result_type=st.selectbox(t('Manual Result'),['TP','SL','BREAKEVEN','EXTENSION','MANUAL'],format_func=lambda x:option_label(x,LANG)); exit_price=st.number_input(t('Exit Price'),value=0.0,format='%.8f')
            riskdist=abs(float(sig['entry'])-float(sig['sl'])); move=((exit_price-float(sig['entry'])) if sig['direction']=='BUY' else (float(sig['entry'])-exit_price)) if exit_price>0 else 0; auto_r=move/riskdist if riskdist else 0
            result_r=st.number_input(t('Result R'),value=float(round(auto_r,2)),step=.01); ret=st.number_input(t('Return %'),value=float(round((move/float(sig['entry'])*100 if exit_price>0 and float(sig['entry']) else 0),3)),step=.001); rimg=st.file_uploader(t('Optional Result Image'),type=['png','jpg','jpeg','webp'],key='manual_result_chart')
        with r:
            rcard=result_card(sig,result_type,exit_price,result_r,ret); st.code(rcard,language=None)
            if rimg:st.image(rimg,use_container_width=True)
            if st.button(t('🛟 SEND MANUAL OVERRIDE'),type='primary',use_container_width=True,disabled=exit_price<=0):
                try:
                    reply_to=sig.get('last_event_message_id') or sig.get('telegram_message_id')
                    if rimg:
                        ext=Path(rimg.name).suffix.lower() or '.png'; p=RES_DIR/f'{sidr}_{result_type}_MANUAL{ext}'; p.write_bytes(rimg.getbuffer()); resp=send_photo(str(p),rcard,reply_to_message_id=reply_to); img_path=str(p)
                    else:
                        from telegram.publisher import send_message; resp=send_message(rcard,reply_to_message_id=reply_to); img_path=None
                    mid=resp['result']['message_id']; save_result({'signal_id':sidr,'result_type':result_type,'exit_price':exit_price,'result_r':result_r,'return_percent':ret,'telegram_message_id':mid,'result_image_path':img_path}); st.success((f'اصلاح دستی ارسال شد — message_id={mid}' if LANG=='fa' else f'Manual override sent — message_id={mid}'))
                except Exception as e:st.error(str(e))
    else:st.caption(t('No signal exists yet.'))

with tab_system:
    st.subheader('Reliability Status')
    rel=st.columns(6)
    rel[0].metric('MT5','CONNECTED' if snap.get('connected') else 'OFFLINE')
    rel[1].metric('Telegram Queue',delivery_state.get('pending',0))
    rel[2].metric('Outbound Attention',delivery_state.get('failed',0))
    rel[3].metric('Schema',f"v{db_schema_version}")
    rel[4].metric('Last Telegram',delivery_state.get('last_sent_at') or '—')
    rel[5].metric('Trailing Errors',sum(1 for x in list_signal_trailing_plans() if str(x.get('status')).upper()=='ERROR'))
    failed_outbox=list_outbox(['DEAD','UNKNOWN'],50)
    if failed_outbox:
        st.warning('Outbound items requiring manual review. UNKNOWN is never automatically replayed to avoid duplicates.')
        show_df(pd.DataFrame([{k:v for k,v in x.items() if k not in ('payload','payload_json')} for x in failed_outbox]),use_container_width=True,hide_index=True)
    c1,c2=st.columns(2,gap='large')
    with c1:
        st.subheader(t('System Health'))
        st.write(t('MT5:'), t('Connected') if snap.get('connected') else snap.get('error',t('Offline'))); st.write(t('Monitor heartbeat:'),heartbeat or t('No heartbeat yet')); st.write(t('Poll:'),CFG.get('monitor',{}).get('poll_seconds'),t('sec'))
        if st.button(t('TEST TELEGRAM'),use_container_width=True):
            try:me=get_me();st.success((f"تلگرام متصل است — @{me['result'].get('username','bot')}" if LANG=='fa' else f"Telegram OK — @{me['result'].get('username','bot')}"))
            except Exception as e:st.error(str(e))
        st.write(t('**Recent Alerts**')); alerts=read_monitor_alerts(25)
        if alerts:
            for x in alerts:st.code(x,language=None)
        else:st.caption(t('No monitor errors detected in the log.'))
    with c2:
        st.subheader(t('Data & Metrics'))
        st.caption(t('MAE/MFE is calculated from MT5 M1 candles between actual open and final close. Existing closed trades can be backfilled.'))
        if st.button(t('BACKFILL MAE/MFE METRICS'),use_container_width=True):
            try:
                import MetaTrader5 as mt5
                path=CFG['mt5'].get('terminal_path',''); ok=mt5.initialize(path=path) if path else mt5.initialize()
                if not ok:st.error(f"{t('MT5 initialize failed')}: {mt5.last_error()}")
                else:
                    try:r=backfill_trade_metrics(mt5,CFG);st.session_state['backfill']=r;st.success((f"{r.get('updated')} معامله به‌روزرسانی شد · {r.get('skipped')} مورد رد شد" if LANG=='fa' else f"Updated {r.get('updated')} trades · skipped {r.get('skipped')}"))
                    finally:mt5.shutdown()
            except Exception as e:st.error(str(e))
        if st.session_state.get('backfill'):st.json(st.session_state['backfill'])
        if st.button(t('BACKFILL REVIEWS + AUTO JOURNAL'),use_container_width=True):
            try:
                rr=backfill_trade_reviews(CFG); st.session_state['review_backfill']=rr
                st.success((f"{rr.get('updated')} بازبینی/ژورنال بازسازی شد" if LANG=='fa' else f"Backfilled {rr.get('updated')} reviews/journal entries"))
            except Exception as e:st.error(str(e))
        if st.session_state.get('review_backfill'):st.json(st.session_state['review_backfill'])
        recent=[x for x in signals if x.get('mt5_symbol') or x.get('mt5_enabled')]
        if recent:
            test_sid=st.selectbox(t('Result Chart Preview'),[x['signal_id'] for x in recent])
            if st.button(t('TEST MT5 RESULT CHART'),use_container_width=True):
                try:
                    sig=get_signal(test_sid); ev={'event_type':'FINAL_CLOSE','event_time':None,'exit_price':float(sig.get('entry') or 0),'total_r':0.0,'total_profit':0.0}; out=PREVIEW_DIR/'mt5_result_chart_preview.png'; result=generate_result_chart(sig,ev,CFG,out)
                    if result.get('ok'):st.success(t('MT5 data chart ready.'));st.image(str(out),use_container_width=True)
                    else:st.error(result.get('error'))
                except Exception as e:st.error(str(e))
    st.divider(); st.subheader(t('Dashboard Language'))
    st.caption(t('Dashboard language is saved in config.json and survives restart. Telegram cards are unchanged.'))
    lang_cols=st.columns([1,3])
    lang_cols[0].metric(t('Dashboard Language'),t('Persian') if LANG=='fa' else t('English'))
    st.divider(); st.subheader(t('Risk Intelligence Configuration'))
    ricfg=CFG.get('risk_intelligence',{}); scfg=ricfg.get('pre_trade_safety',{}); thcfg=ricfg.get('risk_throttle',{}); kcfg=ricfg.get('kill_switch',{})
    st.caption(t('Manual kill switch blocks new MT5 orders only; Telegram publishing continues.'))
    kill_cols=st.columns(2)
    if manual_kill.get('enabled'):
        if kill_cols[0].button(t('DISABLE MANUAL KILL SWITCH'),type='primary',use_container_width=True):set_manual_kill_switch(False,'ADMIN_RESET');time.sleep(.2);st.rerun()
    else:
        if kill_cols[0].button(t('ENABLE MANUAL KILL SWITCH'),type='primary',use_container_width=True):set_manual_kill_switch(True,'ADMIN');time.sleep(.2);st.rerun()
    kill_cols[1].metric(t('Kill Switch'),t('ACTIVE') if manual_kill.get('enabled') else t('READY'))
    with st.form('risk_intelligence_form'):
        z=st.columns(4)
        ri_enabled=z[0].checkbox(t('Enabled'),value=bool(ricfg.get('enabled',True)))
        safety_enabled=z[1].checkbox(t('Pre-Trade Safety'),value=bool(scfg.get('enabled',True)))
        throttle_enabled=z[2].checkbox(t('Risk Throttle'),value=bool(thcfg.get('enabled',True)))
        use_prop=z[3].checkbox(t('Use Prop-Firm Limits'),value=bool(kcfg.get('use_prop_firm_limits',True)))
        y=st.columns(5)
        max_losses=y[0].number_input(t('Max Consecutive Losses'),min_value=1,max_value=20,value=int(kcfg.get('max_consecutive_losses',5)),step=1)
        levels=thcfg.get('loss_streak_levels',{}) or {}
        m2=y[1].number_input(t('2-loss Multiplier'),min_value=0.05,max_value=1.0,value=float(levels.get('2',.75)),step=.05)
        m3=y[2].number_input(t('3-loss Multiplier'),min_value=0.05,max_value=1.0,value=float(levels.get('3',.50)),step=.05)
        m4=y[3].number_input(t('4-loss Multiplier'),min_value=0.05,max_value=1.0,value=float(levels.get('4',.25)),step=.05)
        block_unprotected=y[4].checkbox(t('Block Unprotected Positions'),value=bool(scfg.get('block_unprotected_positions',False)))
        if st.form_submit_button(t('SAVE RISK INTELLIGENCE')):
            path=ROOT/'config.json'; data=json.load(open(path,'r',encoding='utf-8'))
            data['risk_intelligence']={'enabled':ri_enabled,'telegram_continues_when_blocked':True,
                'pre_trade_safety':{'enabled':safety_enabled,'block_unprotected_positions':block_unprotected,'warn_unprotected_positions':True,'enforce_max_open_positions':True,'enforce_max_total_open_risk':True},
                'risk_throttle':{'enabled':throttle_enabled,'loss_streak_levels':{'2':m2,'3':m3,'4':m4},'minimum_multiplier':min(m2,m3,m4)},
                'kill_switch':{'enabled':True,'max_consecutive_losses':int(max_losses),'use_prop_firm_limits':use_prop,'block_new_mt5_orders':True},
                'trade_review':data.get('risk_intelligence',{}).get('trade_review',{'enabled':True,'engine':'LOCAL_EXPERT_V1'})}
            tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path);st.success('ذخیره شد. در حال بارگذاری مجدد…' if LANG=='fa' else 'Saved. Reloading…');time.sleep(.4);st.rerun()
    st.divider(); st.subheader(t('Prop-Firm Configuration'))
    pcfg=CFG.get('prop_firm',{})
    with st.form('prop_form'):
        z=st.columns(6); enabled=z[0].checkbox(t('Enabled'),value=bool(pcfg.get('enabled',False))); starting=z[1].number_input(t('Start Balance'),value=float(pcfg.get('starting_balance',10000.0)),step=100.0); target=z[2].number_input(t('Target %'),value=float(pcfg.get('profit_target_percent',10.0)),step=.5); daily_loss=z[3].number_input(t('Daily Loss %'),value=float(pcfg.get('daily_loss_limit_percent',5.0)),step=.5); max_loss=z[4].number_input(t('Max Loss %'),value=float(pcfg.get('max_loss_limit_percent',10.0)),step=.5); min_days=z[5].number_input(t('Min Days'),min_value=0,value=int(pcfg.get('minimum_trading_days',5)),step=1)
        if st.form_submit_button(t('SAVE PROP SETTINGS')):
            try:
                path=ROOT/'config.json'; data=json.load(open(path,'r',encoding='utf-8')); data['prop_firm']={'enabled':enabled,'starting_balance':starting,'profit_target_percent':target,'daily_loss_limit_percent':daily_loss,'max_loss_limit_percent':max_loss,'minimum_trading_days':int(min_days)}; tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(path); st.success('ذخیره شد. در حال بارگذاری مجدد…' if LANG=='fa' else 'Saved. Reloading…'); time.sleep(.4); st.rerun()
            except Exception as e:st.error(str(e))
    st.caption(t('For continuity when moving to a new ZIP, run MIGRATE_FROM_PREVIOUS.cmd once before RUN_NEXUS.cmd. It backs up the new DB and imports your previous live NEXUS database.'))
