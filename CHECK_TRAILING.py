from storage.repo import (
    ensure_default_trailing_profiles,list_trailing_profiles,list_signal_trailing_plans,
    list_trailing_actions,list_autotrade_clients,list_client_trailing_policies,client_trailing_access
)

ensure_default_trailing_profiles()
profiles=list_trailing_profiles(False)
plans=list_signal_trailing_plans()
actions=list_trailing_actions(limit=20)
clients=list_autotrade_clients();policies=list_client_trailing_policies()
print('NEXUS TRAILING DIAGNOSTICS')
print('Profiles:',len(profiles))
for p in profiles:
    print(f"  #{p['id']} {p['name']} | {p['mode']} | active={p['active']} | user_override={p['allow_user_override']}")
print('\nSignal plans:',len(plans))
for p in plans[:10]:
    print(f"  {p['signal_id']} | {p['profile_name']} | {p['mode']} | enabled={p['enabled']} | stage={p['current_stage']} | status={p['status']} | targets={p.get('targets')}")
print('\nRecent actions:',len(actions))
for a in actions:
    print(f"  {a['signal_id']} | stage={a['stage']} | {a['action_type']} | {a['status']} | req={a['requested_value']} | exec={a['executed_value']} | {a.get('error') or ''}")
print('\nAutoTrade clients:',len(clients),' policies:',len(policies))
for c in clients:
    access=client_trailing_access(c['client_id'])
    print(f"  {c['client_id']} | {c['display_name']} | allowed={access.get('allowed')} | reason={access.get('reason')}")
