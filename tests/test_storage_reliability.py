import sqlite3

import pytest

from storage import repo
from storage.backup import sqlite_backup,integrity_check
from tests.conftest import signal


def test_nx_id_uniqueness(repo_db):
    repo.save_signal(signal())
    with pytest.raises(repo.DuplicateSignalError):repo.save_signal(signal())


def test_durable_signal_insertion_creates_outbox(repo_db):
    result=repo.create_signal_durable(signal(),outbox_payload={'text':'safe'})
    assert repo.get_signal('NX-001')['publication_status']=='PENDING'
    assert result['outbox']['idempotency_key']=='NX-001:TELEGRAM:SIGNAL'


def test_outbox_idempotency(repo_db):
    a=repo.enqueue_outbox('same','TELEGRAM_SIGNAL',{'text':'x'},'NX-001')
    b=repo.enqueue_outbox('same','TELEGRAM_SIGNAL',{'text':'y'},'NX-001')
    assert a['id']==b['id']
    assert len(repo.list_outbox())==1


def test_bounded_retry_and_dead_letter(repo_db):
    item=repo.enqueue_outbox('retry','TELEGRAM_SIGNAL',{},'NX-001')
    for expected in ['FAILED','FAILED','DEAD']:
        assert repo.mark_outbox_sending(item['id'])
        assert repo.mark_outbox_failed(item['id'],'definite',max_attempts=3,base_seconds=0)==expected


def test_ambiguous_delivery_is_not_retried(repo_db):
    item=repo.enqueue_outbox('unknown','TELEGRAM_FINAL',{},'NX-001')
    repo.mark_outbox_sending(item['id'])
    assert repo.mark_outbox_failed(item['id'],'timeout',ambiguous=True)=='UNKNOWN'
    assert not repo.due_outbox()


def test_report_duplicate_protection_key(repo_db):
    repo.enqueue_outbox('REPORT:daily:2026-08-13:TELEGRAM','TELEGRAM_REPORT',{'text':'one'})
    repo.enqueue_outbox('REPORT:daily:2026-08-13:TELEGRAM','TELEGRAM_REPORT',{'text':'two'})
    assert len(repo.list_outbox())==1


def test_schema_migrations_are_repeat_safe(repo_db):
    repo.migrate();repo.migrate()
    assert repo.schema_version()==repo.SCHEMA_VERSION
    assert [x['version'] for x in repo.list_schema_migrations()]==[1,2]
    with sqlite3.connect(repo_db) as con:assert con.execute('PRAGMA user_version').fetchone()[0]==2


def test_migrate_uses_a_process_cache_after_the_first_check(repo_db,monkeypatch):
    calls=[]
    monkeypatch.setattr(repo,'_migrate_unlocked',lambda: calls.append(True))
    repo.migrate()
    assert calls==[]


def test_existing_database_gets_timestamped_pre_migration_backup(tmp_path,monkeypatch):
    legacy=tmp_path/'legacy.db'
    with sqlite3.connect(legacy) as con:
        con.execute('CREATE TABLE signals(signal_id TEXT PRIMARY KEY)')
        con.execute("INSERT INTO signals VALUES('NX-OLD')")
    monkeypatch.setattr(repo,'DB',legacy)
    repo.migrate()
    backups=list((tmp_path/'backups').glob('NEXUS_DATA_before_schema_v2_*.db'))
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as con:assert con.execute('SELECT signal_id FROM signals').fetchone()[0]=='NX-OLD'


def test_sqlite_backup_includes_committed_wal(tmp_path):
    source=tmp_path/'source.db';dest=tmp_path/'backup.db'
    writer=sqlite3.connect(source)
    writer.execute('PRAGMA journal_mode=WAL');writer.execute('PRAGMA wal_autocheckpoint=0')
    writer.execute('CREATE TABLE sample(value TEXT)');writer.commit()
    writer.execute("INSERT INTO sample VALUES('from-wal')");writer.commit()
    try:sqlite_backup(source,dest)
    finally:writer.close()
    with sqlite3.connect(dest) as con:assert con.execute('SELECT value FROM sample').fetchone()[0]=='from-wal'
    assert integrity_check(dest)==(True,'ok')
