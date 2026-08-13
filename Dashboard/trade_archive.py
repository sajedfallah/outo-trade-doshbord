
from pathlib import Path
import json

IMAGE_EXT={'.png','.jpg','.jpeg','.webp'}


def existing_image(path):
    if not path:return None
    try:
        p=Path(path)
        return p if p.exists() and p.is_file() and p.suffix.lower() in IMAGE_EXT else None
    except Exception:return None


def collect_trade_images(signal,events,manual_results,archive_files):
    """Collect all known before/after/custom images for a trade without duplicates."""
    rows=[];seen=set()
    def add(path,category,caption,source):
        p=existing_image(path)
        if not p:return
        key=str(p.resolve())
        if key in seen:return
        seen.add(key);rows.append({'path':str(p),'category':category,'caption':caption,'source':source})
    add((signal or {}).get('setup_image_path'),'BEFORE_ANALYSIS','Signal / pre-trade analysis','SIGNAL')
    for e in sorted(events or [],key=lambda x:str(x.get('event_time') or '')):
        if e.get('screenshot_path'):
            cat='AFTER_ANALYSIS' if e.get('event_type')=='FINAL_CLOSE' else 'EXECUTION'
            add(e.get('screenshot_path'),cat,str(e.get('event_type') or 'MT5 event'),'MT5_MONITOR')
    for r in manual_results or []:
        if r.get('result_image_path'):add(r.get('result_image_path'),'AFTER_ANALYSIS','Manual result image','MANUAL_OVERRIDE')
    for a in archive_files or []:
        add(a.get('file_path'),a.get('category') or 'OTHER',a.get('caption') or '',a.get('source') or 'ADMIN_UPLOAD')
    return rows


def safe_filename(name):
    p=Path(str(name or 'image.png'));stem=''.join(ch if ch.isalnum() or ch in ('-','_') else '_' for ch in p.stem).strip('_') or 'image'
    ext=p.suffix.lower() if p.suffix.lower() in IMAGE_EXT else '.png'
    return stem[:80]+ext


def parse_snapshot(raw):
    try:return json.loads(raw or '{}')
    except Exception:return {}
