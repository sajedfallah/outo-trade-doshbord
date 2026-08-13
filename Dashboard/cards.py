
from datetime import datetime

def _fmt(v):
    if v is None:
        return ""
    if isinstance(v,float):
        return f"{v:.8f}".rstrip("0").rstrip(".")
    return str(v)

def _r_fmt(v):
    v=float(v or 0)
    sign="+" if v>0 else ""
    return f"{sign}{v:.2f}R"

def _now():
    return datetime.now().astimezone()

def _tz_label(dt):
    z=dt.strftime("%z") or "+0000"
    return f"UTC{z[:3]}:{z[3:]}"

def _time_label(dt):
    return f"{dt.strftime('%d %b %Y')} · {dt.strftime('%H:%M')} · {_tz_label(dt)}"

def valid_geometry(direction,entry,tp,sl):
    e,t,s=float(entry),float(tp),float(sl)
    return (s<e<t) if direction=="BUY" else (t<e<s)

def rr_value(entry,tp,sl):
    risk=abs(float(entry)-float(sl))
    reward=abs(float(tp)-float(entry))
    return reward/risk if risk else 0.0

def signal_card(signal_id,symbol,direction,timeframe,entry,tp,sl,risk_percent=None,lot=None,targets=None):
    side="🟢 خرید / لانگ" if direction=="BUY" else "🔴 فروش / شورت"
    rr=rr_value(entry,tp,sl)
    if lot is not None and float(lot)>0:
        sizing=f"💼 حجم: {_fmt(float(lot))}"
    else:
        sizing=f"⚖️ ریسک: {_fmt(float(risk_percent))}%"
    vals=[float(x) for x in (targets or [tp]) if x not in (None,'')]
    if not vals:vals=[float(tp)]
    target_lines=[f"🎯 هدف: {_fmt(vals[0])}"]
    for i,v in enumerate(vals[1:],2):target_lines.append(f"🎯 TP{i}: {_fmt(v)}")
    target_block="\n".join(target_lines)
    return f"""━━━━━━━━━━━━━━━━━━
⚡️ سیگنال نکسوس | {signal_id}

🪙 نماد: {symbol}
{side} | ⏱️ {timeframe}

📥 ورود: {_fmt(float(entry))}
{target_block}
🛑 حد ضرر: {_fmt(float(sl))}
{sizing}
📊 RR: 1:{rr:.2f}

🕒 صدور: {_time_label(_now())}
📌 وضعیت: فعال

#{signal_id.replace("-","")} #{symbol} #NEXUS_SIGNAL
━━━━━━━━━━━━━━━━━━"""

def result_card(signal,result_type,exit_price,result_r,return_percent):
    labels={
        "TP":"✅ هدف فعال شد",
        "SL":"❌ حد ضرر فعال شد",
        "BREAKEVEN":"🟡 ریسک‌فری / سر‌به‌سر",
        "EXTENSION":"🚀 اکستنشن پس از هدف",
        "MANUAL":"⚪ بسته‌شدن دستی"
    }
    tags={
        "TP":"NEXUS_RESULT",
        "SL":"NEXUS_RESULT",
        "BREAKEVEN":"NEXUS_BREAKEVEN",
        "EXTENSION":"NEXUS_EXTENSION",
        "MANUAL":"NEXUS_RESULT"
    }
    rsign="+" if float(result_r)>0 else ""
    psign="+" if float(return_percent)>0 else ""
    return f"""━━━━━━━━━━━━━━━━━━
🏆 نتیجه نکسوس | {signal['signal_id']}

🪙 نماد: {signal['symbol']}
{labels[result_type]}

📥 ورود: {_fmt(float(signal['entry']))}
🏁 خروج: {_fmt(float(exit_price))}
📈 بازده: {psign}{_fmt(float(return_percent))}%
⚖️ نتیجه: {rsign}{_fmt(float(result_r))}R

🏁 پایان: {_time_label(_now())}

#{signal['signal_id'].replace("-","")} #{signal['symbol']} #{tags[result_type]}
━━━━━━━━━━━━━━━━━━"""


def partial_close_card(signal,event):
    def signed(v):
        return f"+{_fmt(float(v))}" if float(v)>0 else _fmt(float(v))
    return f"""━━━━━━━━━━━━━━━━━━
🟡 آپدیت معامله نکسوس | {signal['signal_id']}

🪙 نماد: {signal['symbol']}
✂️ بخشی از حجم بسته شد

📦 حجم اولیه: {_fmt(float(signal['initial_volume']))}
✅ حجم بسته‌شده: {_fmt(float(event['closed_volume']))}
📌 حجم باز: {_fmt(float(event['remaining_volume']))}

🏁 قیمت خروج این بخش: {_fmt(float(event['exit_price']))}
💵 P/L این بخش: {signed(event['event_profit'])}
{('🧭 مدیریت: '+str(event.get('management_note'))+chr(10)) if event.get('management_note') else ''}🟢 وضعیت: پوزیشن همچنان باز است

🕒 بروزرسانی: {_time_label(_now())}

#{signal['signal_id'].replace("-","")} #{signal['symbol']} #NEXUS_PARTIAL
━━━━━━━━━━━━━━━━━━"""

def final_mt5_card(signal,event):
    def signed(v):
        return f"+{_fmt(float(v))}" if float(v)>0 else _fmt(float(v))
    labels={
        "TP":"✅ معامله با هدف بسته شد",
        "SL":"❌ معامله با حد ضرر بسته شد",
        "BREAKEVEN":"🟡 معامله سر‌به‌سر بسته شد",
        "PROFIT":"✅ معامله با سود بسته شد",
        "LOSS":"❌ معامله با ضرر بسته شد",
        "MANUAL":"⚪ معامله بسته شد"
    }
    return f"""━━━━━━━━━━━━━━━━━━
🏆 نتیجه نهایی نکسوس | {signal['signal_id']}

🪙 نماد: {signal['symbol']}
{labels.get(event.get('result_type'),labels['MANUAL'])}

📥 ورود: {_fmt(float(signal['entry']))}
🏁 میانگین/آخرین خروج: {_fmt(float(event['exit_price']))}

📦 حجم اولیه: {_fmt(float(signal['initial_volume']))}
✅ حجم باز باقی‌مانده: 0

💵 P/L کل معامله: {signed(event['total_profit'])}

📌 وضعیت: معامله کاملاً بسته شد
🕒 پایان: {_time_label(_now())}

#{signal['signal_id'].replace("-","")} #{signal['symbol']} #NEXUS_RESULT
━━━━━━━━━━━━━━━━━━"""


def _report_num(v):
    v=float(v or 0)
    return f"{v:+,.2f}"

def performance_report_card(stats,report_type,period_label):
    is_daily=(report_type=="daily")
    title="📊 گزارش روزانه نکسوس" if is_daily else "📈 گزارش هفتگی نکسوس"
    tag="#NEXUS_DAILY_REPORT" if is_daily else "#NEXUS_WEEKLY_REPORT"

    trades=int(stats.get("closed_trades",0))
    wins=int(stats.get("wins",0))
    losses=int(stats.get("losses",0))
    be=int(stats.get("breakeven",0))
    decisive=wins+losses
    win_rate=(wins/decisive*100.0) if decisive else 0.0

    best=stats.get("best_trade")
    worst=stats.get("worst_trade")
    best_text=(
        f"{best['signal_id']} · {_r_fmt(best['r'])}"
        if best else "—"
    )
    worst_text=(
        f"{worst['signal_id']} · {_r_fmt(worst['r'])}"
        if worst else "—"
    )

    symbols=stats.get("symbol_summary") or []
    symbol_lines=[]
    for s in symbols[:4]:
        symbol_lines.append(
            f"• {s['symbol']}: {int(s['trades'])} معامله · "
            f"{_report_num(s['profit'])} P/L · {_r_fmt(s['r'])}"
        )
    symbol_block="\n".join(symbol_lines) if symbol_lines else "• بدون معامله بسته‌شده"

    return f"""━━━━━━━━━━━━━━━━━━
{title}

🗓️ دوره: {period_label}

🧾 معاملات بسته: {trades}
✅ برد: {wins}   |   ❌ باخت: {losses}   |   🟡 BE: {be}
🎯 Win Rate: {win_rate:.1f}%

💵 P/L خالص: {_report_num(stats.get('net_profit',0))}
⚖️ مجموع نتیجه: {_r_fmt(stats.get('total_r',0))}
📊 میانگین R: {_r_fmt(stats.get('avg_r',0))}
📈 Profit Factor: {stats.get('profit_factor_text','0.00')}

🏆 بهترین: {best_text}
📉 ضعیف‌ترین: {worst_text}
✂️ خروج‌های بخشی: {int(stats.get('partial_exits',0))}

📌 پوزیشن باز فعلی: {int(stats.get('open_positions',0))}
💰 Balance: {float(stats.get('balance',0)):,.2f}
⚡ Equity: {float(stats.get('equity',0)):,.2f}
📉 Drawdown فعلی: {float(stats.get('current_drawdown_pct',0)):.2f}%

🪙 عملکرد نمادها:
{symbol_block}

🕒 صدور گزارش: {_time_label(_now())}

{tag} #NEXUS_PERFORMANCE
━━━━━━━━━━━━━━━━━━"""
