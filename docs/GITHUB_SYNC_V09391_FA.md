# همگام‌سازی سورس NEXUS v0.9.39.1 با GitHub

این مخزن Public است. فایل ZIP ورک‌استیشن و پوشه اجرایی را بدون پالایش کامل مستقیماً Push نکن.

## مبنا

```text
Version: NEXUS v0.9.39.1
Local artifact: NEXUS_v0.9.39.1_READABILITY_FINAL.zip
SHA-256: 319d47d138a1ca07fa9c1f83e97c777d237fa7460edec2fea0ec0ff7719004b7
Repository: sajedfallah/outo-trade-doshbord
Branch: main
```

قبل از این Sync یک Backup Branch ساخته شده است:

```text
backup/pre-v0.9.39.1-sync-2026-08-16
```

## مواردی که نباید وارد Public GitHub شوند

- `.env`
- Telegram/API secrets
- SQLite DB / WAL / SHM
- logs / PID / lock
- device fingerprint
- داده مشتری
- اسکرین‌شات‌های runtime خصوصی
- `uploads/mt5_events` و `uploads/preview` مگر عمداً برای انتشار انتخاب شده باشند
- مسیرهای شخصی Windows در config

## روش پیشنهادی

یک Clone تمیز از مخزن بساز و سورس نسخه جدید را روی آن Copy کن؛ `.git` و مستندات وضعیت GitHub را حفظ کن.

```cmd
cd "C:\Users\STOCK LAND\OneDrive\Desktop"
git clone https://github.com/sajedfallah/outo-trade-doshbord.git NEXUS_GITHUB_SYNC
```

بعد سورس نسخه v0.9.39.1 را در `NEXUS_GITHUB_SYNC` کپی کن، ولی فایل‌های خصوصی/runtime را وارد نکن.

پس از Copy:

```cmd
cd "C:\Users\STOCK LAND\OneDrive\Desktop\NEXUS_GITHUB_SYNC"
python -m compileall -q .
pytest -q
python scripts\check_no_secrets.py
git status
```

در صورت PASS:

```cmd
git add .
git commit -m "release: sync NEXUS v0.9.39.1 platform source"
git push origin main
```

## فایل‌های وضعیت که باید حفظ شوند

این فایل‌ها در GitHub به‌روز شده‌اند و هنگام Copy نسخه محلی نباید با نسخه قدیمی جایگزین شوند:

```text
README.md
ROADMAP.md
CHANGELOG.md
VERSION.txt
PROJECT_STATUS.md
RELEASE_ARTIFACTS.md
RELEASE_NOTES_v0.9.39.1.txt
FINAL_VALIDATION_v0.9.39.1.txt
docs/NEXT_VALIDATION_WORKFLOW_FA.md
docs/GITHUB_SYNC_V09391_FA.md
```

## انتشار ZIP

چون مخزن Public است، برای GitHub Release ترجیحاً یک ZIP پالایش‌شده Public بساز.

اگر پس از بررسی امنیتی عمداً می‌خواهی همان فایل خصوصی/ورک‌استیشن را Release کنی:

```cmd
gh release create v0.9.39.1 "C:\PATH\NEXUS_v0.9.39.1_READABILITY_FINAL.zip" --repo sajedfallah/outo-trade-doshbord --title "NEXUS v0.9.39.1 — Readability Final" --notes-file RELEASE_NOTES_v0.9.39.1.txt
```

قبل از اجرای دستور بالا حتماً محتوای ZIP را از نظر داده خصوصی بررسی کن.

## مرحله بعد از Source Sync

Issue مربوط به Gate نسخه v0.9.40 را دنبال کن و Test Evidence را همان‌جا ثبت کن.
