
import math
from pathlib import Path

from config_loader import load_config
from risk.risk_engine import evaluate_account_state,validate_projected_risk
from storage.repo import get_signal_trailing_plan
from trailing.engine import broker_tp_for_plan
from mt5trade.gateway import RealMetaTrader5Gateway

ROOT=Path(__file__).resolve().parent.parent

def _floor_volume(raw,vmin,vmax,step,max_lot):
    cap=min(float(vmax),float(max_lot)); raw=min(float(raw),cap)
    if raw<float(vmin):return None
    units=math.floor((raw-float(vmin))/float(step)+1e-12)
    value=float(vmin)+units*float(step)
    return max(float(vmin),min(value,cap))

class MT5Executor:
    def __init__(self,cfg=None,gateway=None):
        self.cfg=cfg or load_config()
        self.gateway=gateway

    def _blocked(self,error,state,**extra):
        out={'success':False,'blocked':True,'error':error,'risk_intelligence':state,
             'safety_status':state.get('status'),'safety_reasons':','.join(state.get('kill_reasons',[])+state.get('warnings',[])),
             'risk_throttle_multiplier':float(state.get('throttle_multiplier',1.0))}
        out.update(extra); return out

    def execute(self,signal):
        try:mt5=self.gateway or RealMetaTrader5Gateway()
        except Exception as e:return {'success':False,'error':f'MetaTrader5 import failed: {e}'}
        path=self.cfg['mt5']['terminal_path']
        if not mt5.initialize(path=path):return {'success':False,'error':f'MT5 initialize failed: {mt5.last_error()}'}
        try:
            a=mt5.account_info()
            if a is None:return {'success':False,'error':f'account_info failed: {mt5.last_error()}'}
            mode={0:'demo',1:'contest',2:'real'}.get(int(a.trade_mode),'unknown'); wanted=self.cfg['mt5'].get('account_mode','demo')
            if wanted!='any' and mode!=wanted:return {'success':False,'error':f'ACCOUNT_MODE_BLOCK config={wanted} actual={mode}'}
            if not a.trade_allowed:return {'success':False,'error':'TRADE_NOT_ALLOWED'}
            if hasattr(a,'trade_expert') and not a.trade_expert:return {'success':False,'error':'EXPERT_TRADING_NOT_ALLOWED'}

            state=evaluate_account_state(mt5,self.cfg,persist=True)
            if not state.get('allow_new_orders',True):
                reasons=state.get('kill_reasons',[])+state.get('warnings',[])
                return self._blocked('PRE_TRADE_SAFETY_BLOCK '+('|'.join(reasons) or 'UNKNOWN'),state)

            src=signal['symbol']; broker=self.cfg.get('symbol_map',{}).get(src,src); info=mt5.symbol_info(broker)
            if info is None:
                candidates=[]
                for s in (mt5.symbols_get() or []):
                    n=s.name.upper()
                    if n==src.upper():candidates.append((100,s.name))
                    elif n.startswith(src.upper()):candidates.append((70,s.name))
                    elif src.upper() in n:candidates.append((30,s.name))
                if candidates:
                    candidates.sort(reverse=True); broker=candidates[0][1]; info=mt5.symbol_info(broker)
            if info is None:return {'success':False,'error':f'SYMBOL_NOT_FOUND {src}','risk_intelligence':state}
            if not info.visible:mt5.symbol_select(broker,True)
            tick=mt5.symbol_info_tick(broker)
            if tick is None:return {'success':False,'error':f'NO_TICK {broker}','risk_intelligence':state}

            side=signal['direction']; entry=float(signal['entry']);tp=float(signal['tp']);sl=float(signal['sl']);digits=int(info.digits)
            entry=round(entry,digits);tp=round(tp,digits);sl=round(sl,digits)
            trailing_plan=signal.get('_trailing_plan') or get_signal_trailing_plan(signal.get('signal_id'))
            broker_tp=round(float(broker_tp_for_plan(tp,trailing_plan) or 0),digits)
            mult=float(state.get('throttle_multiplier',1.0)); max_lot=self.cfg['risk_management']['max_lot']
            requested_risk=signal.get('risk_percent'); effective_risk=None; requested_lot=signal.get('lot')

            if requested_lot:
                throttled_lot=float(requested_lot)*mult
                volume=_floor_volume(throttled_lot,info.volume_min,info.volume_max,info.volume_step,max_lot)
                if volume is None:
                    return self._blocked('THROTTLED_LOT_BELOW_BROKER_MINIMUM',state,requested_lot=float(requested_lot),effective_lot=0.0)
            else:
                requested_risk=float(requested_risk or self.cfg['risk_management']['default_risk_percent'])
                cap=float(self.cfg['risk_management']['max_risk_percent_per_trade'])
                if requested_risk>cap:return {'success':False,'error':f'RISK_LIMIT {requested_risk}% > {cap}%','risk_intelligence':state}
                effective_risk=requested_risk*mult
                base=float(a.equity);typ_calc=mt5.ORDER_TYPE_BUY if side=='BUY' else mt5.ORDER_TYPE_SELL
                one_loss=mt5.order_calc_profit(typ_calc,broker,1.0,entry,sl)
                if one_loss is None or abs(one_loss)<=0:return {'success':False,'error':f'RISK_CALC_FAILED {mt5.last_error()}','risk_intelligence':state}
                raw=(base*effective_risk/100.0)/abs(float(one_loss))
                volume=_floor_volume(raw,info.volume_min,info.volume_max,info.volume_step,max_lot)
                if volume is None:return self._blocked('THROTTLED_LOT_BELOW_BROKER_MINIMUM',state,requested_risk_percent=requested_risk,effective_risk_percent=effective_risk)

            risk=abs(entry-sl);reward=abs(tp-entry);rr=reward/risk if risk else 0;minrr=float(self.cfg['risk_management']['min_reward_risk'])
            if rr<minrr:return {'success':False,'error':f'REWARD_RISK_TOO_LOW {rr:.2f} < {minrr:.2f}','risk_intelligence':state}

            projected=validate_projected_risk(mt5,self.cfg,state,broker,side,volume,entry,sl)
            if not projected.get('allow',True):
                return self._blocked('PRE_TRADE_SAFETY_BLOCK '+str(projected.get('reason')),state,
                    requested_risk_percent=requested_risk,effective_risk_percent=effective_risk,
                    volume=float(volume),projected_risk=projected)

            tolmap=self.cfg['trading'].get('market_entry_tolerance_price',{})
            tolerance=float(tolmap.get(src,max(info.point*self.cfg['trading']['entry_tolerance_points'],info.point)))
            current=float(tick.ask if side=='BUY' else tick.bid)
            if side=='BUY':
                if abs(current-entry)<=tolerance:action=mt5.TRADE_ACTION_DEAL;typ=mt5.ORDER_TYPE_BUY;price=tick.ask;action_name='MARKET_BUY'
                elif entry<current:action=mt5.TRADE_ACTION_PENDING;typ=mt5.ORDER_TYPE_BUY_LIMIT;price=entry;action_name='BUY_LIMIT'
                else:action=mt5.TRADE_ACTION_PENDING;typ=mt5.ORDER_TYPE_BUY_STOP;price=entry;action_name='BUY_STOP'
            else:
                if abs(current-entry)<=tolerance:action=mt5.TRADE_ACTION_DEAL;typ=mt5.ORDER_TYPE_SELL;price=tick.bid;action_name='MARKET_SELL'
                elif entry>current:action=mt5.TRADE_ACTION_PENDING;typ=mt5.ORDER_TYPE_SELL_LIMIT;price=entry;action_name='SELL_LIMIT'
                else:action=mt5.TRADE_ACTION_PENDING;typ=mt5.ORDER_TYPE_SELL_STOP;price=entry;action_name='SELL_STOP'

            base_req={'action':action,'symbol':broker,'volume':float(volume),'type':typ,'price':round(float(price),digits),'sl':sl,'tp':tp,
                      'deviation':int(self.cfg['trading']['deviation_points']),'magic':int(self.cfg['trading']['magic_number']),
                      'comment':f"NEXUS {signal['signal_id']}",'type_time':mt5.ORDER_TIME_GTC}
            base_req['tp']=broker_tp
            good={getattr(mt5,'TRADE_RETCODE_DONE',10009),getattr(mt5,'TRADE_RETCODE_PLACED',10008)};attempts=[]
            for fname in ['ORDER_FILLING_RETURN','ORDER_FILLING_IOC','ORDER_FILLING_FOK']:
                fill=getattr(mt5,fname,None)
                if fill is None:continue
                req=dict(base_req);req['type_filling']=fill;result=mt5.order_send(req)
                if result is None:attempts.append({'fill':fname,'error':str(mt5.last_error())});continue
                attempts.append({'fill':fname,'retcode':int(result.retcode),'comment':str(result.comment)})
                if result.retcode in good:
                    ticket=str(result.order or result.deal or '')
                    return {'success':True,'ticket':ticket,'symbol':broker,'volume':float(volume),'action':action_name,'attempts':attempts,
                            'requested_risk_percent':requested_risk,'effective_risk_percent':effective_risk,
                            'requested_lot':float(requested_lot) if requested_lot else None,'effective_lot':float(volume),
                            'risk_throttle_multiplier':mult,'safety_status':state.get('status'),
                            'safety_reasons':','.join(state.get('warnings',[])),'risk_intelligence':state,'projected_risk':projected,
                            'broker_tp':broker_tp,'trailing_enabled':bool(trailing_plan and int(trailing_plan.get('enabled') or 0)),
                            'trailing_profile':trailing_plan.get('profile_name') if trailing_plan else None}
            return {'success':False,'error':'MT5_ORDER_REJECTED','attempts':attempts,'risk_intelligence':state,
                    'requested_risk_percent':requested_risk,'effective_risk_percent':effective_risk,'risk_throttle_multiplier':mult,
                    'safety_status':state.get('status'),'safety_reasons':','.join(state.get('warnings',[]))}
        finally:mt5.shutdown()
