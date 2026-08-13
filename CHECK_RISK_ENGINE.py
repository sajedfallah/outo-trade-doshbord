
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
from config_loader import load_config
from storage.repo import migrate,list_trade_reviews,list_auto_journal,get_state
migrate()
cfg=load_config()
print('Risk Intelligence enabled:',cfg.get('risk_intelligence',{}).get('enabled'))
print('Pre-Trade Safety:',cfg.get('risk_intelligence',{}).get('pre_trade_safety',{}).get('enabled'))
print('Risk Throttle:',cfg.get('risk_intelligence',{}).get('risk_throttle',{}).get('enabled'))
print('Kill threshold:',cfg.get('risk_intelligence',{}).get('kill_switch',{}).get('max_consecutive_losses'))
print('Reviews:',len(list_trade_reviews()))
print('Auto journal:',len(list_auto_journal()))
print('Live risk state:',get_state('risk_intelligence_state'))
