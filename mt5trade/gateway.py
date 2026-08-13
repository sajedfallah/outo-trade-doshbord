"""Incremental MT5 adapter layer used by production code and broker-free tests."""
from __future__ import annotations

from types import SimpleNamespace


class RealMetaTrader5Gateway:
    def __init__(self,module=None):
        if module is None:
            import MetaTrader5 as module
        self._module=module
        self.owns_connection=False

    def initialize(self,**kwargs):
        ok=bool(self._module.initialize(**kwargs));self.owns_connection=ok;return ok

    def shutdown(self):
        if self.owns_connection:
            self._module.shutdown();self.owns_connection=False

    def __getattr__(self,name):return getattr(self._module,name)


class FakeMT5Gateway:
    """Small stateful fake for lifecycle, trailing, disconnect, and reject tests."""
    TRADE_ACTION_DEAL=1;TRADE_ACTION_PENDING=5;TRADE_ACTION_SLTP=6
    ORDER_TYPE_BUY=0;ORDER_TYPE_SELL=1;ORDER_TYPE_BUY_LIMIT=2;ORDER_TYPE_SELL_LIMIT=3;ORDER_TYPE_BUY_STOP=4;ORDER_TYPE_SELL_STOP=5
    POSITION_TYPE_BUY=0;POSITION_TYPE_SELL=1
    ORDER_TIME_GTC=0;ORDER_FILLING_RETURN=2;ORDER_FILLING_IOC=1;ORDER_FILLING_FOK=0
    TRADE_RETCODE_PLACED=10008;TRADE_RETCODE_DONE=10009;TRADE_RETCODE_NO_CHANGES=10025;TRADE_RETCODE_REJECT=10006
    DEAL_ENTRY_IN=0;DEAL_ENTRY_OUT=1;DEAL_ENTRY_INOUT=2;DEAL_ENTRY_OUT_BY=3
    DEAL_REASON_TP=5;DEAL_REASON_SL=4
    TIMEFRAME_M1=1;TIMEFRAME_M5=5;TIMEFRAME_M15=15;TIMEFRAME_M30=30;TIMEFRAME_H1=16385

    def __init__(self):
        self.connected=True;self.reject_orders=False;self.positions=[];self.orders=[];self.deals={};self.rates=[];self.shutdown_calls=0
        self.sent_requests=[];self._next_ticket=1000
        self.account=SimpleNamespace(trade_mode=0,trade_allowed=True,trade_expert=True,equity=10000.0,balance=10000.0,
                                     margin=0.0,margin_free=10000.0,login=1,server='FAKE')
        self.symbols={}

    def initialize(self,**kwargs):return self.connected
    def shutdown(self):self.shutdown_calls+=1
    def disconnect(self):self.connected=False
    def reconnect(self):self.connected=True
    def last_error(self):return (0,'OK') if self.connected else (-1,'DISCONNECTED')
    def account_info(self):return self.account if self.connected else None
    def symbols_get(self):return [SimpleNamespace(name=x) for x in self.symbols]
    def symbol_info(self,symbol):
        return self.symbols.get(symbol) or SimpleNamespace(name=symbol,visible=True,digits=2,point=.01,volume_min=.01,volume_max=100.0,volume_step=.01,trade_stops_level=0,trade_freeze_level=0)
    def symbol_select(self,symbol,visible):return True
    def symbol_info_tick(self,symbol):
        if not self.connected:return None
        return SimpleNamespace(bid=100.0,ask=100.1)
    def positions_get(self,ticket=None):
        rows=self.positions
        return tuple(p for p in rows if ticket is None or int(p.ticket)==int(ticket))
    def orders_get(self):return tuple(self.orders)
    def history_deals_get(self,position=None,**kwargs):return tuple(self.deals.get(int(position),[])) if position is not None else ()
    def history_orders_get(self,ticket=None):return ()
    def order_calc_profit(self,typ,symbol,volume,entry,exit_price):
        sign=1 if typ==self.ORDER_TYPE_BUY else -1
        return sign*(float(exit_price)-float(entry))*float(volume)*100.0
    def copy_rates_from_pos(self,*args):return self.rates[-int(args[-1]):]
    def copy_rates_range(self,*args):return self.rates
    def order_send(self,request):
        self.sent_requests.append(dict(request))
        if not self.connected:return None
        if self.reject_orders:return SimpleNamespace(retcode=self.TRADE_RETCODE_REJECT,comment='FAKE_REJECT',order=0,deal=0)
        if request.get('action')==self.TRADE_ACTION_SLTP:
            for p in self.positions:
                if int(p.ticket)==int(request['position']):p.sl=float(request['sl']);p.tp=float(request.get('tp') or p.tp)
            return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE,comment='DONE',order=0,deal=0)
        self._next_ticket+=1
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE,comment='DONE',order=self._next_ticket,deal=self._next_ticket)
