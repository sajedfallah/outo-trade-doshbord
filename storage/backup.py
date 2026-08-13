"""WAL-safe SQLite backup and validation helpers."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


def integrity_check(path: str | Path) -> tuple[bool, str]:
    path=Path(path)
    try:
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro",uri=True) as con:
            result=str(con.execute('PRAGMA integrity_check').fetchone()[0])
        return result.lower()=='ok',result
    except Exception as exc:
        return False,str(exc)


def sqlite_backup(source: str | Path,destination: str | Path) -> dict:
    """Use SQLite's online backup API so committed WAL pages are included."""
    source=Path(source);destination=Path(destination)
    if not source.exists():raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True,exist_ok=True)
    src=sqlite3.connect(f"file:{source.resolve()}?mode=ro",uri=True,timeout=30)
    dst=sqlite3.connect(destination,timeout=30)
    try:
        src.backup(dst,pages=256)
        dst.commit()
    finally:
        dst.close();src.close()
    ok,detail=integrity_check(destination)
    if not ok:
        try:destination.unlink()
        except Exception:pass
        raise RuntimeError(f'Backup integrity check failed: {detail}')
    return {'source':str(source.resolve()),'destination':str(destination.resolve()),
            'bytes':destination.stat().st_size,'integrity':detail}


def timestamped_backup(source: str | Path,backup_dir: str | Path | None=None,prefix='NEXUS_DATA') -> dict:
    source=Path(source)
    folder=Path(backup_dir) if backup_dir else source.parent/'backups'
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    destination=folder/f'{prefix}_{stamp}.db'
    return sqlite_backup(source,destination)
