from pathlib import Path
import shutil,sqlite3,datetime,sys
from storage.backup import sqlite_backup,timestamped_backup,integrity_check
import psutil

ROOT=Path(__file__).resolve().parent
CURRENT=ROOT/'storage'/'NEXUS_DATA.db'
pid_file=ROOT/'storage'/'mt5_monitor.pid'
if pid_file.exists():
    try:
        running_pid=int(pid_file.read_text(encoding='utf-8').strip())
        if psutil.pid_exists(running_pid):
            print(f'Migration aborted: NEXUS monitor PID {running_pid} is running. Stop it safely first.');sys.exit(4)
    except ValueError:pass

def signal_count(path):
    try:
        c=sqlite3.connect(path); n=c.execute("SELECT COUNT(*) FROM signals").fetchone()[0]; c.close(); return int(n)
    except Exception:return -1

siblings=[]
for p in ROOT.parent.glob('Nexus_v*'):
    db=p/'storage'/'NEXUS_DATA.db'
    if p.resolve()!=ROOT.resolve() and db.exists():
        siblings.append((db.stat().st_mtime,signal_count(db),db))
if not siblings:
    print('No previous NEXUS database found next to this folder.'); sys.exit(1)
siblings.sort(reverse=True)
print('Previous databases found:')
for i,(mt,n,db) in enumerate(siblings[:10],1):
    print(f'{i}. {db.parent.parent.name} | signals={n} | modified={datetime.datetime.fromtimestamp(mt)}')
choice=input('Choose number to migrate [1]: ').strip() or '1'
try: src=siblings[int(choice)-1][2]
except Exception:
    print('Invalid choice.'); sys.exit(2)
backup=None
if CURRENT.exists():
    backup=timestamped_backup(CURRENT,CURRENT.parent/'backups','NEXUS_DATA_before_migration')['destination']
staged=CURRENT.with_name('NEXUS_DATA.migration_staged.db')
report=sqlite_backup(src,staged)
ok,detail=integrity_check(staged)
if not ok:
    print(f'Migration aborted: staged database integrity failed: {detail}');sys.exit(3)
staged.replace(CURRENT)
print(f'Migrated DB: {src}')
print(f'Current DB: {CURRENT}')
print(f'Backup: {backup or "not required (no destination DB existed)"}')
print(f"Migrated bytes: {report['bytes']} | integrity: {report['integrity']}")
with sqlite3.connect(CURRENT) as migrated:
    tables=[r[0] for r in migrated.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    counts={name:migrated.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in tables}
print('Migrated row counts: '+', '.join(f'{k}={v}' for k,v in counts.items()))
# Preserve historical signal/result/archive images so the Trade Archive remains complete.
src_root=src.parent.parent
src_uploads=src_root/'uploads'
dst_uploads=ROOT/'uploads'
if src_uploads.exists():
    shutil.copytree(src_uploads,dst_uploads,dirs_exist_ok=True)
    print(f'Migrated uploads: {src_uploads} -> {dst_uploads}')
else:
    print('Previous uploads folder not found; DB migration continues.')
# Run schema migration for the new version.
from storage.repo import migrate,ensure_default_trailing_profiles
migrate();ensure_default_trailing_profiles()
from storage.repo import schema_version
print(f'Schema upgrade + trailing profiles: OK | schema version={schema_version()}')
