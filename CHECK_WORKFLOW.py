
from storage.repo import list_signals,list_trade_events,list_trade_metrics,list_report_runs,list_workflow_events
from monitor.workflow import build_workflow_registry
rows,details=build_workflow_registry(list_signals(),list_workflow_events(limit=100000),list_trade_events(),list_trade_metrics(),list_report_runs(10000))
print('WORKFLOWS:',len(rows),'AUDIT EVENTS:',len(list_workflow_events(limit=100000)))
for r in rows[:15]:
    print(r['signal_id'],r['health'],r['current_stage'],'MT5=',r['mt5_status'],'PID=',r['position_id'],'issue=',r['issue'])
