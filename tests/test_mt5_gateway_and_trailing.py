from types import SimpleNamespace

from mt5trade.gateway import FakeMT5Gateway
from monitor.mt5_monitor import deals_for_position
from storage import repo
from trailing.engine import build_signal_plan,process_trailing


def _position(volume=.10,sl=80.0):
    return SimpleNamespace(ticket=501,identifier=501,symbol='XAUUSD',type=0,volume=volume,sl=sl,tp=110.0,time=0)


def _signal():
    return {'signal_id':'NX-001','symbol':'XAUUSD','direction':'BUY','entry':90.0,'tp':110.0,'sl':80.0,
            'initial_volume':.10,'mt5_volume':.10,'mt5_ticket':'501'}


def _plan(targets,current=0):
    profile={'id':1,'name':'Ladder','mode':'LADDER','params':{'first_partial_percent':50,'close_percent_basis':'INITIAL','hard_final_target':True,'min_targets':2}}
    plan=build_signal_plan('NX-001',profile,targets,True);plan['current_stage']=current
    repo.save_signal_trailing_plan(plan);return plan


def test_position_id_history_reconciliation():
    fake=FakeMT5Gateway();fake.deals[501]=[SimpleNamespace(ticket=1)]
    assert deals_for_position(fake,'501')[0].ticket==1


def test_disconnect_reconnect():
    fake=FakeMT5Gateway();fake.disconnect();assert not fake.initialize()
    fake.reconnect();assert fake.initialize()


def test_ladder_tp1_partial_only_once(repo_db,base_config):
    fake=FakeMT5Gateway();pos=_position();fake.positions=[pos];_plan([99,110])
    first=process_trailing(fake,base_config,_signal(),pos)
    deal_count=sum(x.get('action')==fake.TRADE_ACTION_DEAL for x in fake.sent_requests)
    second=process_trailing(fake,base_config,_signal(),pos)
    assert first['ok'] and second['ok'] and deal_count==1
    assert sum(x.get('action')==fake.TRADE_ACTION_DEAL for x in fake.sent_requests)==1


def test_ladder_tp2_moves_sl_to_tp1(repo_db,base_config):
    fake=FakeMT5Gateway();pos=_position(sl=90);fake.positions=[pos];_plan([95,99,110],current=1)
    out=process_trailing(fake,base_config,_signal(),pos)
    assert out['current_stage']==2 and pos.sl==95


def test_restart_after_tp1_uses_confirmed_actions(repo_db,base_config):
    fake=FakeMT5Gateway();pos=_position(sl=90);fake.positions=[pos];_plan([99,110])
    repo.record_trailing_action({'action_key':'NX-001:TRAIL:1:PARTIAL','signal_id':'NX-001','stage':1,'action_type':'PARTIAL_CLOSE','status':'CONFIRMED'})
    repo.record_trailing_action({'action_key':'NX-001:TRAIL:1:SL','signal_id':'NX-001','stage':1,'action_type':'MOVE_SL','requested_value':90,'executed_value':90,'status':'CONFIRMED'})
    out=process_trailing(fake,base_config,_signal(),pos)
    assert out['current_stage']==1 and not any(x.get('action')==fake.TRADE_ACTION_DEAL for x in fake.sent_requests)


def test_restart_during_partial_reconciles_history(repo_db,base_config):
    fake=FakeMT5Gateway();pos=_position(volume=.05,sl=80);fake.positions=[pos];_plan([99,110])
    repo.record_trailing_action({'action_key':'NX-001:TRAIL:1:PARTIAL','signal_id':'NX-001','stage':1,'action_type':'PARTIAL_CLOSE','requested_value':.05,'status':'EXECUTING','metadata':{'baseline_exit_tickets':[]}})
    fake.deals[501]=[SimpleNamespace(ticket=700,entry=fake.DEAL_ENTRY_OUT,volume=.05)]
    out=process_trailing(fake,base_config,_signal(),pos)
    assert out['ok'] and repo.get_trailing_action('NX-001:TRAIL:1:PARTIAL')['status']=='CONFIRMED'
    assert not any(x.get('action')==fake.TRADE_ACTION_DEAL for x in fake.sent_requests)
