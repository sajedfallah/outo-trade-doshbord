"""Fail CI if a Telegram-token-shaped value is present in publishable files."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
TOKEN=re.compile(rb'(?<![A-Za-z0-9_-])\d{8,}:[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])')
SKIP={'.git','.pytest_cache','__pycache__','storage','uploads'}
hits=[]
for path in ROOT.rglob('*'):
    if not path.is_file() or any(part in SKIP for part in path.relative_to(ROOT).parts):continue
    try:data=path.read_bytes()
    except OSError:continue
    if TOKEN.search(data):hits.append(str(path.relative_to(ROOT)))
if hits:
    print('Credential-like Telegram token found in:')
    for item in hits:print(f' - {item}')
    raise SystemExit(1)
print('No embedded Telegram token-shaped values found.')
