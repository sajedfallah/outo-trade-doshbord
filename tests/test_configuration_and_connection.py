import json
from pathlib import Path

from config_audit import audit_config
from config_loader import load_config
from monitor.mt5_result_chart import generate_result_chart,_spread_positions
from mt5trade.executor import MT5Executor
from mt5trade.gateway import FakeMT5Gateway
from mt5trade.service import execute_persisted_signal
from storage import repo
from tests.conftest import signal as make_signal


def test_public_config_contains_no_telegram_secret(monkeypatch,tmp_path):
    monkeypatch.delenv('NEXUS_TELEGRAM_BOT_TOKEN',raising=False)
    raw=json.loads(Path('config.json').read_text(encoding='utf-8'))
    assert 'bot_token' not in raw['telegram']
    isolated=tmp_path/'config.json'
    isolated.write_text(json.dumps(raw),encoding='utf-8')
    assert load_config(isolated)['telegram']['bot_token']==''


def test_configuration_audit_has_only_known_statuses():
    rows=audit_config()
    assert rows and {x['status'] for x in rows}<={'USED','DEPRECATED','UNUSED','INVALID'}


def test_shared_result_chart_does_not_shutdown_mt5(tmp_path,base_config,repo_db):
    fake=FakeMT5Gateway()
    fake.rates=[{'time':1_700_000_000+i*300,'open':100+i*.01,'high':101+i*.01,'low':99+i*.01,'close':100.5+i*.01} for i in range(30)]
    signal={'signal_id':'NX-001','symbol':'XAUUSD','mt5_symbol':'XAUUSD','direction':'BUY','timeframe':'M5','entry':100,'tp':102,'sl':99,'targets':[102,110,120]}
    event={'event_type':'FINAL_CLOSE','exit_price':101,'total_profit':10,'event_time':'2023-11-14T22:20:00+00:00'}
    cfg={**base_config,'monitor':{'result_chart':{'enabled':True,'display_bars':70,'dpi':110}}}
    result=generate_result_chart(signal,event,cfg,tmp_path/'chart.png',mt5_instance=fake)
    assert result['ok'] and result['mode']=='mt5_data_chart_v3'
    assert result['targets']==[102.0,110.0,120.0]
    assert (tmp_path/'chart.png').stat().st_size>20_000
    assert fake.shutdown_calls==0


def test_result_chart_label_positions_do_not_overlap():
    placed=_spread_positions([100,100.01,100.02,100.03],99,101,min_gap_ratio=.05)
    assert all(right-left>=.099 for left,right in zip(sorted(placed),sorted(placed)[1:]))


def test_executor_surfaces_order_rejection(repo_db,base_config):
    fake=FakeMT5Gateway();fake.reject_orders=True
    cfg={**base_config,'trading':{**base_config['trading'],'market_entry_tolerance_price':{'XAUUSD':1.0}}}
    result=MT5Executor(cfg,gateway=fake).execute({'signal_id':'NX-001','symbol':'XAUUSD','direction':'BUY','entry':100,'tp':102,'sl':99,'risk_percent':1})
    assert not result['success'] and result['error']=='MT5_ORDER_REJECTED'


def test_persisted_execution_waits_for_telegram(repo_db,base_config):
    repo.save_signal(make_signal())
    fake=FakeMT5Gateway()
    assert execute_persisted_signal('NX-001',base_config,gateway=fake)['error']=='TELEGRAM_NOT_CONFIRMED'
    assert not fake.sent_requests
    repo.update_signal('NX-001',publication_status='SENT')
    result=execute_persisted_signal('NX-001',base_config,gateway=fake)
    assert result['success'] and repo.get_signal('NX-001')['mt5_status']=='SENT'
