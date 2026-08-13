import pandas as pd

from Dashboard.analytics import _utc_datetime_series
from monitor.event_logic import classify_final
from mt5trade.executor import _floor_volume
from risk.risk_engine import throttle_multiplier,evaluate_account_state,set_manual_kill_switch
from strategy.setup_engine import score_checklist
from trailing.engine import validate_targets
from mt5trade.gateway import FakeMT5Gateway


def test_mixed_naive_and_aware_timestamps():
    out=_utc_datetime_series(['2025-01-01 10:00:00','2025-01-01T10:00:00+03:30'],[0,1])
    assert str(out.dtype)=='datetime64[ns, UTC]' and out.notna().all()


def test_broker_volume_step_rounding():
    assert _floor_volume(.057,.01,10,.01,10)==.05
    assert _floor_volume(.009,.01,10,.01,10) is None


def test_risk_throttle(base_config):
    assert throttle_multiplier(2,base_config)==.75
    assert throttle_multiplier(4,base_config)==.25


def test_risk_kill_switch(repo_db,base_config):
    fake=FakeMT5Gateway();set_manual_kill_switch(True,'TEST')
    state=evaluate_account_state(fake,base_config)
    assert state['kill_switch'] and not state['allow_new_orders']


def test_checklist_snapshot_immutability():
    item={'id':1,'item_text':'M1 confirmation','weight':2,'required':1,'active':1}
    snap=score_checklist({'id':1,'name':'Setup'},[item],{'1':True})
    item['item_text']='Changed later';item['weight']=99
    assert snap['checklist'][0]['text']=='M1 confirmation' and snap['score_percent']==100


def test_target_validation():
    assert validate_targets('BUY',100,[110,120])[0]
    assert not validate_targets('SELL',100,[110])[0]


def test_final_classification():
    assert classify_final(.05,0,5,4)=='BREAKEVEN'
    assert classify_final(1,5,5,4)=='TP'
