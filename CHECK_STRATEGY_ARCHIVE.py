
import json
from storage.repo import list_setups,list_signal_setup_scores,list_archive_files
print('SETUPS:')
for x in list_setups():print(x)
print('\nLATEST SETUP SCORES:')
for x in list_signal_setup_scores()[:10]:
    print({k:x.get(k) for k in ['signal_id','setup_name','score_percent','grade','required_missed']})
print('\nLATEST ARCHIVE FILES:')
for x in list_archive_files()[-20:]:print(x)
