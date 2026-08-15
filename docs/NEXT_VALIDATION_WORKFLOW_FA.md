# NEXUS — وورک‌فلو تست و اعتبارسنجی مرحله بعد

## هدف

نسخه پایه فعلی **v0.9.39.1** است. از این نقطه تا قبل از `v0.9.40 STABLE BETA` اولویت اصلی افزودن قابلیت جدید نیست؛ اولویت این است که کل زنجیره فعلی روی Windows + MT5 Demo از ابتدا تا انتها بدون خطا و بدون نشت داده بین مشتری‌ها تأیید شود.

---

# 1) آماده‌سازی محیط تست

سه پنجره CMD جدا باز بماند.

## Client API

```cmd
RUN_CLIENT_API_SERVER.cmd
```

انتظار:

```text
NEXUS Client API listening on http://0.0.0.0:8790
```

## Admin

```cmd
RUN_NEXUS.cmd
```

آدرس:

```text
http://localhost:8501
```

## Client

```cmd
RUN_CLIENT_PANEL.cmd
```

آدرس:

```text
http://localhost:8502
```

### معیار قبولی

- هر سه سرویس همزمان بالا باشند.
- Client هنگام Login خطای `WinError 10061` نداشته باشد.
- Client API روی 8790 پاسخ بدهد.

---

# 2) ساخت مشتری تست استاندارد

برای تست اصلی یک مشتری تازه بساز تا داده‌های قدیمی وارد نتیجه نشوند.

نمونه:

```text
Display Name: NEXUS Demo QA
Username: nexus_demo_qa
Role: AUTO_TRADE_USER یا PRO_USER
Client ID: شناسه جدید و یکتا
Plan: AUTOTRADE یا NEXUS-PRO متناسب با سناریو
Subscription: ACTIVE
License: لایسنس جدید
```

### بررسی Admin

پس از Quick Create باید موارد زیر به هم متصل باشند:

```text
User
  ↕
Client ID
  ↕
Subscription
  ↕
License
```

### معیار قبولی

- User تکراری ایجاد نشود.
- Client ID یکتا باشد.
- Subscription فعال باشد.
- License ACTIVE باشد.
- ارتباط Client/License در صفحه مدیریت واضح باشد.

---

# 3) تست Login و Data Isolation

با کاربر جدید وارد Client شو.

بررسی کن:

- Role درست نمایش داده شود.
- Plan درست نمایش داده شود.
- Subscription درست نمایش داده شود.
- License متعلق به همان Client ID باشد.
- اطلاعات مشتری دیگری نمایش داده نشود.

سپس حداقل یک Client دوم ایجاد کن و تست منفی بگیر.

### تست منفی ضروری

```text
CLIENT-A نباید Signal / Trade / Report / License متعلق به CLIENT-B را ببیند.
```

### معیار قبولی

هیچ Cross-Client Data Leakage وجود نداشته باشد.

---

# 4) اتصال MT5 Demo به Client

فقط حساب Demo استفاده شود.

در Client:

1. مسیر `terminal64.exe` را وارد کن.
2. دکمه اتصال MT5 را اجرا کن.
3. Login حساب و Server را بررسی کن.
4. License Key همان مشتری را وارد کن.
5. Activate را اجرا کن.

انتظار:

```text
MT5: CONNECTED
License: ACTIVE
Binding: ACTIVE/BOUND
```

### معیار قبولی

- MT5 Login درست تشخیص داده شود.
- MT5 Server درست باشد.
- License به همان MT5 Login و Device متصل شود.
- Binding تکراری ساخته نشود.

---

# 5) تست Persistence لایسنس

پس از فعال‌سازی:

1. Client را ببند.
2. Client API را Restart کن.
3. Client را دوباره باز کن.
4. Login کن.

### معیار قبولی

Binding پابرجا باشد و فعال‌سازی از بین نرود.

---

# 6) تست امنیت Binding

با همان License تلاش کن آن را روی MT5 Login یا Device متفاوت فعال کنی.

### انتظار

سیستم باید درخواست را رد کند.

سپس از Admin `Reset Binding` را اجرا کن و دوباره تست کن.

### معیار قبولی

- بدون Reset جابه‌جایی ممکن نباشد.
- بعد از Reset، Binding جدید فقط یک‌بار ایجاد شود.
- عملیات Reset در Admin واضح باشد.

---

# 7) اولین Signal End-to-End

یک Signal کنترل‌شده روی Demo ایجاد کن.

ابتدا با حجم/ریسک بسیار کوچک.

مسیر مورد انتظار:

```text
Admin
 ↓
Signal Created
 ↓
Assigned to Client
 ↓
Client API
 ↓
Client Signal View
 ↓
Permission Check
 ↓
Subscription Check
 ↓
License Check
 ↓
MT5 Check
 ↓
Risk Engine
 ↓
Execution
```

### تست شماره 1

BUY

### تست شماره 2

SELL

### معیار قبولی

- Signal فقط برای مشتری Assigned دیده شود.
- دقیقاً یک Order در MT5 ایجاد شود.
- Entry/SL/TP صحیح باشند.
- حجم با Risk Plan سازگار باشد.
- Refresh یا Login مجدد باعث اجرای دوباره نشود.

---

# 8) تست Reject سناریوها

هر سناریو جداگانه تست شود:

## MT5 Offline

انتظار: Signal ممکن است قابل مشاهده باشد، اما Execution انجام نشود و Reason واضح باشد.

## License Invalid/Unbound

انتظار: Execution Block.

## Subscription Suspended/Expired

انتظار: Execution Block.

## Kill Switch

انتظار: New MT5 Order Block.

## Risk Limit

انتظار: Order Block یا Risk Adjustment طبق Policy.

### معیار قبولی

هیچ Block نباید Silent باشد؛ Reason باید ثبت/نمایش داده شود.

---

# 9) تست Position Lifecycle

پس از باز شدن معامله Demo:

بررسی کن:

- Entry ثبت شده است.
- SL ثبت شده است.
- TPها صحیح هستند.
- Active Trade در Admin دیده می‌شود.
- همان Trade در Client دیده می‌شود.

سپس بر اساس Setup تست:

- TP1
- Partial Close
- Break Even
- Trailing
- TP2/TP3 در صورت وجود
- Final Close

### معیار قبولی

- هر Partial فقط یک‌بار انجام شود.
- هر SL Move فقط یک‌بار اجرا شود.
- Restart باعث تکرار Action نشود.

---

# 10) تست Restart وسط معامله

در حالی که Position باز است:

1. Monitor را Stop کن.
2. دوباره اجرا کن.
3. Admin/Client را Refresh کن.

### معیار قبولی

- Position پیدا شود.
- Trailing Stage درست بازسازی شود.
- Partial قبلی دوباره تکرار نشود.
- Final lifecycle از بین نرود.

---

# 11) تست Manual Close و Reverse Sync

یک Position را از خود MT5 به‌صورت دستی Close کن.

NEXUS باید از طریق `position_id` آن را به معامله صحیح مرتبط کند.

### بررسی

```text
MT5 Closed
  ↓
Monitor Detects Deal
  ↓
Signal Finalized
  ↓
Admin Updated
  ↓
Client Updated
  ↓
Result / Report Updated
```

### معیار قبولی

- Trade در حالت Active باقی نماند.
- Final Close دوبار ثبت نشود.
- Result با Broker History تطبیق داشته باشد.

---

# 12) تست Pending Order

در صورت پشتیبانی سناریوی انتخابی:

```text
Pending
 ↓
Filled
 ↓
Active Position
```

و جداگانه:

```text
Pending
 ↓
Canceled / Expired
```

### معیار قبولی

Pending لغوشده نباید در آمار Trade نهایی به عنوان معامله واقعی محاسبه شود.

---

# 13) تست Performance و Reports

بعد از چند معامله بسته‌شده Demo بررسی شود:

- Balance
- Equity
- Today P/L
- Total Trades
- Win/Loss/BE
- Win Rate
- R
- Duration
- Drawdown
- MAE/MFE در صورت موجود بودن داده
- Daily Report
- Weekly Report

### معیار قبولی

اعداد باید با داده MT5/NEXUS lifecycle سازگار باشند و معامله Active/Canceled به شکل اشتباه وارد آمار نشود.

---

# 14) تست UI نهایی

هم Admin و هم Client در چهار حالت:

```text
FA / DARK
FA / LIGHT
EN / DARK
EN / LIGHT
```

و در اندازه‌ها:

```text
1920×1080
1366×768
1024px
768px
390×844
```

بررسی:

- فونت‌ها خوانا باشند.
- عنوان‌های داخلی وسط‌چین باشند.
- Horizontal Overflow نداشته باشیم.
- Tableها در موبایل قابل استفاده باشند.
- Buttonها Touch Friendly باشند.
- Sidebar/Menu در موبایل قابل کنترل باشد.

---

# 15) تست Secret / Public Repository Hygiene

قبل از هر Push/Release عمومی:

- `.env` نباشد.
- Telegram Token نباشد.
- DB واقعی نباشد.
- WAL/SHM نباشد.
- Log/PID/Lock نباشد.
- Device Fingerprint واقعی نباشد.
- فایل Upload شخصی/اسکرین‌شات حساس نباشد.
- `config.json` برای داده محلی/شناسه‌های خصوصی بازبینی شود.

---

# 16) Gate نسخه v0.9.40

فقط وقتی تمام موارد بالا Pass شدند نسخه زیر ساخته شود:

```text
NEXUS v0.9.40 STABLE BETA
```

حداقل Evidence لازم:

- BUY E2E PASS
- SELL E2E PASS
- Restart PASS
- Binding Security PASS
- Client Isolation PASS
- Reverse Sync PASS
- Reporting Reconciliation PASS
- Responsive/Theme/Language PASS
- Public Secret Scan PASS

---

# گزارش تست پیشنهادی

برای هر Test Case ثبت شود:

```text
Test ID:
Date/Time:
Version:
Client ID:
MT5 Login:
Symbol:
Scenario:
Expected:
Actual:
PASS/FAIL:
Evidence/Screenshot:
Error/Log:
Fix Version:
```

این گزارش‌ها مبنای تصمیم برای `v0.9.40 STABLE BETA` خواهند بود.
