import pytest

from storage import repo


@pytest.fixture
def repo_db(tmp_path,monkeypatch):
    path=tmp_path/'NEXUS_TEST.db'
    monkeypatch.setattr(repo,'DB',path)
    repo.migrate()
    return path


@pytest.fixture
def base_config():
    return {
        'mt5':{'terminal_path':'','account_mode':'demo'},
        'trading':{'deviation_points':50,'magic_number':320032,'entry_tolerance_points':10,'market_entry_tolerance_price':{}},
        'risk_management':{'default_risk_percent':1.0,'max_risk_percent_per_trade':2.0,'max_open_positions':3,
                           'min_reward_risk':1.0,'max_lot':10.0,'max_total_open_risk_percent':4.0},
        'risk_intelligence':{'enabled':True,'pre_trade_safety':{'enabled':True,'enforce_max_open_positions':True,
                            'enforce_max_total_open_risk':True,'warn_unprotected_positions':True},
                            'risk_throttle':{'enabled':True,'loss_streak_levels':{'2':.75,'3':.5,'4':.25},'minimum_multiplier':.25},
                            'kill_switch':{'enabled':True,'max_consecutive_losses':5,'use_prop_firm_limits':False}},
        'prop_firm':{'enabled':False},'analytics':{'timezone':'Asia/Tehran'},
        'trailing':{'enabled':True},'symbol_map':{}
    }


def signal(signal_id='NX-001'):
    return {'signal_id':signal_id,'symbol':'XAUUSD','direction':'BUY','timeframe':'M5','entry':90.0,'tp':110.0,'sl':80.0,
            'risk_percent':1.0,'lot':None,'rr':2.0,'mt5_enabled':1,'mt5_status':'NOT_REQUESTED'}
