
from datetime import datetime,timezone

def signed_price_r(signal,price):
    entry=float(signal["entry"])
    sl=float(signal["sl"])
    risk=abs(entry-sl)
    if risk<=0:
        return 0.0
    if signal["direction"]=="BUY":
        move=float(price)-entry
    else:
        move=entry-float(price)
    return move/risk

def weighted_exit_price(deals):
    vol=sum(float(d["volume"]) for d in deals)
    if vol<=0:
        return 0.0
    return sum(float(d["price"])*float(d["volume"]) for d in deals)/vol

def weighted_r(signal,deals,initial_volume):
    initial=float(initial_volume or 0)
    if initial<=0:
        return 0.0
    total=0.0
    for d in deals:
        total += signed_price_r(signal,d["price"]) * (float(d["volume"])/initial)
    return total

def net_profit(deals):
    return sum(
        float(d.get("profit",0) or 0)+
        float(d.get("commission",0) or 0)+
        float(d.get("swap",0) or 0)+
        float(d.get("fee",0) or 0)
        for d in deals
    )

def classify_final(total_r,last_reason,reason_tp,reason_sl):
    if last_reason==reason_tp:
        return "TP"
    if last_reason==reason_sl:
        return "SL"
    if abs(float(total_r))<=0.10:
        return "BREAKEVEN"
    if total_r>0:
        return "PROFIT"
    if total_r<0:
        return "LOSS"
    return "MANUAL"

def event_time_iso(unix_time):
    return datetime.fromtimestamp(int(unix_time),tz=timezone.utc).astimezone().isoformat(timespec="seconds")
