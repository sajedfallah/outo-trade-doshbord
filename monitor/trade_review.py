
import json
from storage.repo import (
    upsert_trade_review,upsert_auto_journal,list_signals,list_trade_events,
    list_trade_metrics,get_trade_review,get_signal_setup_score,get_signal_trailing_plan,list_trailing_actions
)


def _num(v,default=0.0):
    try:return float(v if v is not None else default)
    except Exception:return float(default)


def _grade(score):
    return 'A' if score>=90 else ('B' if score>=78 else ('C' if score>=65 else 'D'))


def generate_trade_review(signal,event,metric,cfg):
    metric=metric or {}; score=100.0; flags=[]; fa=[]; en=[]; rec_fa=[]; rec_en=[]
    realized=_num(event.get('total_r')); mfe=metric.get('mfe_r'); mae=metric.get('mae_r'); eff=metric.get('exit_efficiency_pct')
    planned=_num(signal.get('rr')); min_rr=_num(cfg.get('risk_management',{}).get('min_reward_risk',1.0),1.0)
    requested=signal.get('requested_risk_percent',signal.get('risk_percent')); effective=signal.get('effective_risk_percent')
    max_risk=_num(cfg.get('risk_management',{}).get('max_risk_percent_per_trade',2.0),2.0)

    if planned<min_rr:
        score-=20;flags.append('LOW_PLANNED_RR');fa.append('RR برنامه‌ریزی‌شده پایین‌تر از حد استاندارد سیستم بوده است.');en.append('Planned RR was below the system minimum.')
    else:
        fa.append(f'ساختار اولیه معامله با RR حدود {planned:.2f} مطابق حداقل قوانین NEXUS بوده است.');en.append(f'The initial setup RR ({planned:.2f}) met the NEXUS minimum.')
    if requested is not None and _num(requested)>max_risk:
        score-=30;flags.append('OVERRISK');fa.append('ریسک درخواستی بالاتر از سقف مجاز بوده است.');en.append('Requested risk exceeded the configured cap.')
    elif effective is not None and requested is not None and _num(effective)<_num(requested)-1e-9:
        flags.append('RISK_THROTTLED');fa.append(f'موتور ریسک، ریسک را از {_num(requested):.2f}% به {_num(effective):.2f}% کاهش داده است.');en.append(f'Risk Intelligence throttled risk from {_num(requested):.2f}% to {_num(effective):.2f}%.')

    if mae is not None:
        mae=_num(mae)
        if mae<=-1.0:score-=18;flags.append('DEEP_MAE');rec_fa.append('کیفیت ورود/محل استاپ را بررسی کن؛ معامله حداقل 1R فشار منفی دیده است.');rec_en.append('Review entry quality / stop placement; adverse excursion reached at least 1R.')
        elif mae<=-0.6:score-=9;flags.append('ELEVATED_MAE')
        else:fa.append(f'فشار منفی معامله محدود بوده (MAE {mae:.2f}R).');en.append(f'Adverse excursion stayed contained (MAE {mae:.2f}R).')

    if mfe is not None:
        mfe=_num(mfe)
        fa.append(f'بیشترین فرصت شناور معامله حدود +{mfe:.2f}R بوده است.');en.append(f'Maximum favorable excursion reached about +{mfe:.2f}R.')
        if mfe>=1.0 and realized<0.25:
            score-=15;flags.append('MFE_NOT_CAPTURED');rec_fa.append('مدیریت خروج را بررسی کن؛ معامله بیش از +1R فرصت داده ولی بخش کمی از آن محقق شده است.');rec_en.append('Review exit management; the trade offered >1R but little of it was realized.')

    if eff is not None:
        eff=_num(eff)
        if eff<25:score-=18;flags.append('LOW_EXIT_EFFICIENCY')
        elif eff<50:score-=10;flags.append('MEDIUM_EXIT_EFFICIENCY')
        elif eff>=75:flags.append('STRONG_EXIT_EFFICIENCY')
        fa.append(f'راندمان خروج حدود {eff:.0f}% از MFE ثبت‌شده بوده است.');en.append(f'Exit efficiency captured about {eff:.0f}% of recorded MFE.')

    rt=str(event.get('result_type') or '').upper()
    if rt=='BREAKEVEN' and mfe is not None and _num(mfe)>=0.75:
        flags.append('BE_AFTER_GOOD_MFE');rec_fa.append('قانون انتقال استاپ/Partial را بازبینی کن؛ معامله قبل از BE فضای سود مناسبی داشته است.');rec_en.append('Review breakeven/partial rules; the trade had meaningful favorable excursion before BE.')
    if rt in ('TP','PROFIT') and realized>0:fa.append('نتیجه نهایی مثبت بوده و چرخه معامله با سود بسته شده است.');en.append('The trade lifecycle finished with a positive realized result.')
    elif rt in ('SL','LOSS') or realized<-0.10:fa.append('نتیجه نهایی منفی بوده؛ تمرکز بازبینی باید روی کیفیت ورود و مدیریت فشار منفی باشد.');en.append('The realized result was negative; review entry quality and adverse-excursion management.')
    else:fa.append('نتیجه در محدوده سر‌به‌سر قرار گرفته است.');en.append('The realized result finished in the breakeven zone.')

    score=max(0.0,min(100.0,score));grade=_grade(score)
    if not rec_fa:rec_fa.append('انحراف مهمی از داده‌های ثبت‌شده دیده نشد؛ اجرای همین قواعد را پایدار نگه دار.')
    if not rec_en:rec_en.append('No major issue stands out from recorded data; keep execution rules consistent.')
    return {'signal_id':signal['signal_id'],'review_score':score,'review_grade':grade,'flags':flags,
            'flags_json':json.dumps(flags,ensure_ascii=False),'summary_fa':' '.join(fa),'summary_en':' '.join(en),
            'recommendation_fa':' '.join(rec_fa),'recommendation_en':' '.join(rec_en),'engine_version':'LOCAL_EXPERT_V1'}


def finalize_trade_review(signal,event,metric,cfg):
    review=generate_trade_review(signal,event,metric,cfg);upsert_trade_review(review)
    setup_score=get_signal_setup_score(signal['signal_id'])
    trailing_plan=get_signal_trailing_plan(signal['signal_id']) or {}
    trailing_actions=list(reversed(list_trailing_actions(signal['signal_id'],500)))
    snap={
        'signal':{k:signal.get(k) for k in ['signal_id','symbol','direction','timeframe','setup_tag','strategy_version','entry','tp','sl','rr','risk_percent','requested_risk_percent','effective_risk_percent','risk_throttle_multiplier','safety_status','safety_reasons','telegram_message_id','setup_image_path']},
        'setup_score':setup_score or {},
        'trailing_plan':trailing_plan,
        'trailing_actions':trailing_actions,
        'event':{k:event.get(k) for k in ['event_key','event_time','exit_price','total_profit','total_r','result_type','telegram_message_id','screenshot_path']},
        'metrics':metric or {},'review':review
    }
    upsert_auto_journal({
        'signal_id':signal['signal_id'],'symbol':signal.get('symbol'),'direction':signal.get('direction'),'timeframe':signal.get('timeframe'),
        'setup_tag':signal.get('setup_tag'),'strategy_version':signal.get('strategy_version'),'entry':signal.get('entry'),'tp':signal.get('tp'),'sl':signal.get('sl'),
        'planned_rr':signal.get('rr'),'requested_risk_percent':signal.get('requested_risk_percent',signal.get('risk_percent')),
        'effective_risk_percent':signal.get('effective_risk_percent'),'risk_throttle_multiplier':signal.get('risk_throttle_multiplier',1.0),
        'safety_status':signal.get('safety_status'),'safety_reasons':signal.get('safety_reasons'),'result_type':event.get('result_type'),
        'total_profit':event.get('total_profit'),'total_r':event.get('total_r'),'open_time':(metric or {}).get('open_time'),'close_time':(metric or {}).get('close_time') or event.get('event_time'),
        'duration_minutes':(metric or {}).get('duration_minutes'),'mfe_r':(metric or {}).get('mfe_r'),'mae_r':(metric or {}).get('mae_r'),
        'exit_efficiency_pct':(metric or {}).get('exit_efficiency_pct'),'review_score':review.get('review_score'),'review_grade':review.get('review_grade'),
        'review_flags':','.join(review.get('flags',[])),'telegram_signal_message_id':signal.get('telegram_message_id'),
        'telegram_result_message_id':event.get('telegram_message_id'),'setup_image_path':signal.get('setup_image_path'),'result_image_path':event.get('screenshot_path'),
        'snapshot_json':json.dumps(snap,ensure_ascii=False,default=str)
    })
    return review


def backfill_trade_reviews(cfg):
    signals={s['signal_id']:s for s in list_signals()}; metrics={m['signal_id']:m for m in list_trade_metrics()}; finals={}
    for e in list_trade_events():
        if e.get('event_type')=='FINAL_CLOSE' and e.get('signal_id') not in finals:finals[e['signal_id']]=e
    done=0;failed=[]
    for sid,event in finals.items():
        sig=signals.get(sid)
        if not sig:continue
        try:finalize_trade_review(sig,event,metrics.get(sid,{}),cfg);done+=1
        except Exception as e:failed.append((sid,str(e)))
    return {'ok':not failed,'updated':done,'failed':failed[:20]}
