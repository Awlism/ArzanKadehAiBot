# ArzanKadeh AI (ارزانکده AI)

یک محل کشف قابل‌اعتماد، زیبا و ساده برای کسب‌وکارهای ایرانی — فروشگاه‌های اینستاگرامی، تلگرامی، کسب‌وکارهای خانگی، محلی، سالن‌های زیبایی، صنایع دستی، غذا، خدمات و محصولات.

ArzanKadeh AI در حال حاضر یک ربات تلگرام MVP است که با Python، aiogram 3.x و معماری ماژولار ساخته شده است.

معماری دیتابیس پروژه از طریق یک Backend abstraction طراحی شده تا منطق برنامه به پیاده‌سازی مستقیم SQLite وابسته نباشد و در مراحل بعدی بتوان Backendهای دیگری مانند Cloudflare D1 را اضافه کرد.

---

## وضعیت فعلی پروژه

Branch اصلی توسعه فعلی:

    cloudflare-webhook-migration

وضعیت فعلی:

- Telegram Bot فعال در قالب MVP
- aiogram 3.x
- جستجوی محلی و رایگان
- معماری ماژولار
- Repository layer
- Service layer
- Database Backend abstraction
- SQLite Backend فعلی
- D1 database برای زیرساخت Cloudflare آماده‌سازی شده است
- مسیر Cloudflare Webhook در حال توسعه است
- Telegram Webhook هنوز به‌عنوان مسیر نهایی Production فعال نشده است
- Telegram Mini App فعلاً placeholder است
- AI Search خارجی و APIهای پولی فعلاً استفاده نمی‌شوند

هدف اصلی این مرحله، تثبیت هسته پروژه و آماده‌سازی صحیح آن برای استقرار Cloudflare/Webhook است.

---

# ویژگی‌های پیاده‌سازی‌شده

- دسته‌بندی چندسطحی محصولات
- ناوبری مبتنی بر دیتابیس با `parent_id`
- جستجوی محلی و رایگان با `LocalQueryParser`
- جستجوی ساختاریافته بر اساس قیمت، شهر، دسته‌بندی، رنگ و جنسیت
- Ranking نتایج بر اساس داده واقعی دیتابیس
- سیستم Referral برای فروشندگان
- صفحه فروشگاه و محصول
- وضعیت تأیید فروشگاه‌ها
- علاقه‌مندی محصولات
- علاقه‌مندی فروشندگان
- امتیازدهی و نظرات
- گزارش تخلف
- درخواست مالکیت فروشگاه
- ثبت فروشگاه
- اعلان‌ها
- حساب کاربری
- انتخاب شهر
- بخش‌های محبوب و جدید
- مقایسه محصولات
- سیستم تبلیغات
- ثبت رویدادهای Analytics
- Fallback handler سراسری
- داده نمایشی اختیاری با `SEED_DEMO_DATA`
- کنترل نقش‌های کاربر
- ساختار Repository برای عملیات دیتابیس
- Serviceهای مستقل برای منطق‌های قابل تفکیک
- Database Backend abstraction
- SQLite Backend
- تراکنش‌های دیتابیس با پشتیبانی از `BEGIN IMMEDIATE`
- تست‌های واحد و Static Analysis

---

# معماری پروژه

پروژه به‌صورت ماژولار طراحی شده و منطق اصلی ربات در یک فایل واحد قرار ندارد.

ساختار اصلی فعلی:

    .
    ├── bot.py
    ├── requirements.txt
    ├── .env.example
    ├── .gitignore
    ├── README.md
    │
    ├── miniapp/
    │   └── index.html
    │
    ├── bot/
    │   ├── __init__.py
    │   ├── config.py
    │   ├── constants.py
    │   ├── database.py
    │   ├── database_backend.py
    │   ├── sqlite_backend.py
    │   ├── keyboards.py
    │   ├── repositories.py
    │   ├── states.py
    │   ├── utils.py
    │   │
    │   ├── handlers/
    │   │   ├── __init__.py
    │   │   ├── account.py
    │   │   ├── admin.py
    │   │   ├── ads.py
    │   │   ├── buyer.py
    │   │   ├── compare.py
    │   │   ├── navigation.py
    │   │   ├── notifications.py
    │   │   ├── products.py
    │   │   ├── referrals.py
    │   │   ├── search.py
    │   │   ├── seller.py
    │   │   └── support.py
    │   │
    │   └── services/
    │       ├── __init__.py
    │       ├── backups.py
    │       ├── notifications.py
    │       ├── referrals.py
    │       └── tasks.py
    │
    └── tests/
        ├── _extract.py
        ├── _fakedb.py
        ├── test_category_navigation_logic.py
        ├── test_local_search_parser.py
        ├── test_phase3_reliability_pagination.py
        ├── test_phase4_admin_ads.py
        ├── test_phase4_admin_requests.py
        ├── test_phase4_admin_users.py
        ├── test_project_files.py
        ├── test_referral_system.py
        ├── test_roles_favorites_compare.py
        ├── test_roles_start_and_public_ads.py
        ├── test_schema_and_seed.py
        ├── test_search_engine_e2e.py
        ├── test_seller_claims.py
        ├── test_static_analysis.py
        ├── test_store_active_toggle.py
        └── test_utils.py

---

# لایه‌های معماری

معماری منطقی فعلی به شکل زیر است:

    Telegram
        │
        ▼
    Handlers
        │
        ▼
    Services
        │
        ▼
    Repositories
        │
        ▼
    DatabaseBackend
        │
        ▼
    SQLiteBackend
        │
        ▼
    SQLite Database

این لایه‌ها مسئولیت‌های متفاوتی دارند و نباید بدون دلیل با یکدیگر ادغام شوند.

---

## Handlers

Handlerها مسئول دریافت ورودی Telegram و مدیریت Flow هستند.

نمونه‌ها:

- `account.py`
- `admin.py`
- `ads.py`
- `buyer.py`
- `compare.py`
- `navigation.py`
- `notifications.py`
- `products.py`
- `referrals.py`
- `search.py`
- `seller.py`
- `support.py`

Handler نباید محل اصلی منطق دیتابیس یا منطق پیچیده کسب‌وکار باشد.

---

## Services

Serviceها برای منطق‌های قابل تفکیک و reusable استفاده می‌شوند.

Serviceهای فعلی:

    bot/services/notifications.py
    bot/services/referrals.py
    bot/services/tasks.py
    bot/services/backups.py

برای مثال، سیستم Notification بین ذخیره‌سازی Notification و ارسال مستقیم پیام Telegram تفکیک شده است.

---

## Repositories

فایل:

    bot/repositories.py

Repository layer مسئول عملیات اصلی داده و persistence مربوط به Entityهای پروژه است.

هدف این لایه این است که Handlerها و Serviceها تا حد امکان مستقیماً با جزئیات پیاده‌سازی دیتابیس درگیر نشوند.

Repositoryها نباید به implementation-specific APIهای SQLite مانند `db.conn` یا `db.execute()` وابسته باشند.

برای عملیات دیتابیس از Backend abstraction استفاده می‌شود.

---

# Database Architecture

معماری دیتابیس پروژه از یک abstraction layer استفاده می‌کند.

ساختار فعلی:

    Application
        │
        ▼
    DatabaseBackend
        │
        ▼
    SQLiteBackend
        │
        ▼
    aiosqlite / SQLite

فایل‌های اصلی:

    bot/database_backend.py
    bot/sqlite_backend.py
    bot/database.py

---

## DatabaseBackend

فایل:

    bot/database_backend.py

این فایل contract مربوط به Backend دیتابیس را تعریف می‌کند.

عملیات اصلی شامل:

- `connect`
- `close`
- `execute`
- `fetchone`
- `fetchall`
- `executemany`
- `transaction`

هدف این abstraction این است که لایه‌های بالاتر پروژه به SQLite-specific implementation وابسته نباشند.

---

## SQLiteBackend

فایل:

    bot/sqlite_backend.py

پیاده‌سازی فعلی `DatabaseBackend` برای SQLite است.

این Backend از `aiosqlite` استفاده می‌کند.

عملیات تراکنشی از جمله:

    BEGIN

و در صورت نیاز:

    BEGIN IMMEDIATE

را پشتیبانی می‌کند.

`BEGIN IMMEDIATE` در بخش‌هایی که نیاز به کنترل race condition و رزرو زودتر write lock دارند استفاده می‌شود.

---

## Database

فایل:

    bot/database.py

این فایل همچنان مسئول بخش low-level مربوط به SQLite است، از جمله:

- ایجاد اتصال
- schema initialization
- migrations
- seed
- عملیات bootstrap دیتابیس

استفاده مستقیم از `db.conn` در این فایل به دلیل نقش low-level آن عمدی است.

بنابراین نباید استفاده‌های داخلی `database.py` از `sqlite3` یا connection-level APIs را با عملیات Repository/Service اشتباه گرفت.

---

# دیتابیس فعلی

پروژه از SQLite برای اجرای فعلی استفاده می‌کند.

جدول‌های اصلی شامل موارد زیر هستند:

    users
    cities
    categories
    sellers
    products
    favorites
    seller_claims
    reviews
    reports
    events
    notifications
    orders
    referrals
    referral_rewards
    seller_favorites
    requests
    audit_log
    compare_selections

Seed شهرها و دسته‌بندی‌ها به‌صورت idempotent طراحی شده‌اند تا اجرای مجدد برنامه باعث ایجاد رکوردهای تکراری نشود.

داده‌های Demo نیز اختیاری هستند و با `SEED_DEMO_DATA` کنترل می‌شوند.

---

# تراکنش‌ها و Consistency

برای عملیات حساس دیتابیس، Transaction از طریق Backend abstraction انجام می‌شود.

Repositoryها نباید Transaction را با اتصال مستقیم به implementation دیتابیس مدیریت کنند.

نمونه مفهومی:

    DatabaseBackend
        └── transaction()
                │
                ├── BEGIN
                └── COMMIT / ROLLBACK

برای عملیات‌هایی که به lock زودهنگام نیاز دارند:

    transaction(immediate=True)

استفاده می‌شود.

این ساختار برای جلوگیری از race condition در عملیات حساس طراحی شده است.

---

# جستجوی محلی

معماری جستجو:

    User Query
        │
        ▼
    QueryParser
        │
        ▼
    StructuredQuery
        │
        ▼
    SearchEngine
        │
        ▼
    Ranking
        │
        ▼
    Results

---

## QueryParser

`QueryParser` یک contract مستقل برای تبدیل متن خام کاربر به Query ساختاریافته است.

---

## LocalQueryParser

پیاده‌سازی فعلی `QueryParser` است و بدون API یا سرویس AI خارجی اجرا می‌شود.

قابلیت‌های آن شامل:

- نرمال‌سازی اعداد فارسی و عربی
- نرمال‌سازی حروف فارسی
- تشخیص محدوده قیمت
- تشخیص شهر
- تشخیص دسته‌بندی
- مترادف‌های رایج
- برخی غلط‌های تایپی رایج
- تشخیص رنگ
- تشخیص جنسیت
- حذف کلمات اضافی و محاوره‌ای

---

## SearchEngine

`SearchEngine` باید به contract مربوط به `QueryParser` وابسته باشد و نباید مستقیماً به `LocalQueryParser` وابسته شود.

این طراحی اجازه می‌دهد در آینده QueryParserهای جدید، از جمله پیاده‌سازی‌های مبتنی بر AI، بدون بازنویسی منطق اصلی SearchEngine اضافه شوند.

---

## Ranking

نتایج بر اساس داده واقعی دیتابیس رتبه‌بندی می‌شوند.

معیارها می‌توانند شامل موارد زیر باشند:

- تطابق دسته‌بندی
- تطابق کلمات کلیدی
- شهر
- محدوده قیمت
- امتیاز
- تعداد نظرات
- بازدید

Search Engine نباید محصول یا نتیجه ساختگی ایجاد کند.

---

# سیستم Compare

سیستم Compare به‌صورت Database-backed طراحی شده است.

انتخاب‌های مقایسه در جدول:

    compare_selections

ذخیره می‌شوند.

هر کاربر می‌تواند حداکثر:

    4

محصول را برای مقایسه انتخاب کند.

وضعیت Compare نباید صرفاً در حافظه process نگهداری شود، زیرا در محیط‌های چند-instance یا پس از restart process از بین خواهد رفت.

---

# سیستم Referral

هر فروشنده می‌تواند لینک معرفی اختصاصی داشته باشد.

ساختار لینک:

    https://t.me/<bot_username>?start=shop_<seller_id>

ورود کاربران از طریق لینک‌های Referral در سیستم ثبت می‌شود.

قابلیت‌های اصلی:

- جلوگیری از ثبت چندباره یک کاربر
- جلوگیری از self-referral
- ثبت آمار معرفی
- نمایش لینک معرفی
- ساختار قابل توسعه برای Rewardها

---

# اعلان‌ها

سیستم Notification در Service مستقل قرار دارد.

مسیر اصلی:

    bot/services/notifications.py

این Service مسئول ذخیره و مدیریت اعلان‌های داخلی دیتابیس است.

قابلیت‌های اصلی:

- ایجاد اعلان
- دریافت اعلان‌های خوانده‌نشده
- خواندن یک اعلان
- خواندن همه اعلان‌ها

ذخیره‌سازی Notification از ارسال مستقیم پیام Telegram جدا نگه داشته شده است.

---

# Telegram Mini App

پوشه:

    miniapp/

در MVP فعلی شامل placeholder اولیه Telegram Mini App است.

فایل فعلی:

    miniapp/index.html

Mini App هنوز منطق اصلی پروژه را در اختیار ندارد و Bot به آن وابسته نیست.

توسعه کامل Mini App در مراحل بعدی انجام خواهد شد.

---

# Cloudflare Architecture

Cloudflare بخش مهمی از معماری Deployment آینده پروژه است.

هدف نهایی این است که Telegram Webhook از طریق Cloudflare دریافت و به Backend مناسب پروژه منتقل شود.

معماری هدف:

    Telegram
        │
        │ Webhook
        ▼
    Cloudflare Worker
        │
        ▼
    Bot Backend
        │
        ▼
    Handlers
        │
        ▼
    Services
        │
        ▼
    Repositories
        │
        ▼
    DatabaseBackend
        │
        ▼
    Cloudflare D1

---

## وضعیت فعلی Cloudflare

در حال حاضر:

- پروژه Cloudflare ایجاد شده است.
- D1 database برای پروژه ایجاد شده است.
- schema مربوط به D1 آماده‌سازی شده است.
- ساختار Backend abstraction در پروژه ایجاد شده است.
- SQLite همچنان Backend فعلی اجرای محلی است.
- Webhook Telegram هنوز به‌صورت نهایی Production فعال نشده است.
- Cloudflare Worker نهایی هنوز جایگزین مسیر فعلی اجرای Bot نشده است.

بنابراین نباید وضعیت فعلی را با Migration کامل به Cloudflare اشتباه گرفت.

---

# D1 و Database Backend

هدف معماری این است که منطق برنامه به SQLite وابسته نباشد.

در حالت فعلی:

    DatabaseBackend
        │
        ▼
    SQLiteBackend
        │
        ▼
    SQLite

در معماری آینده Cloudflare:

    DatabaseBackend
        │
        ▼
    D1 Backend
        │
        ▼
    Cloudflare D1

این جداسازی باعث می‌شود لایه‌های بالاتر پروژه مجبور نباشند برای تغییر دیتابیس بازنویسی شوند.

پیاده‌سازی نهایی D1 Backend باید فقط پس از بررسی دقیق compatibility واقعی Cloudflare Worker، Python runtime و APIهای مورد استفاده انجام شود.

---

# Telegram Bot Runtime

در وضعیت فعلی Bot از polling استفاده می‌کند.

اجرای فعلی:

    python bot.py

مسیر فعلی:

    Telegram
        │
        ▼
    aiogram Dispatcher
        │
        ▼
    Handlers

Webhook مسیر هدف Deployment است اما تا زمانی که Backend دریافت Webhook و چرخه کامل اجرای آن به‌درستی آماده و تست نشده باشد، نباید polling را به‌صورت ناقص حذف کرد.

---

# تنظیمات محیطی

نمونه تنظیمات در:

    .env.example

قرار دارد.

نمونه:

    BOT_TOKEN=your_telegram_bot_token_here
    DATABASE_PATH=arzan_kadeh.db
    SEED_DEMO_DATA=false
    ADMIN_CHAT_ID=your_admin_chat_id_here
    ADMIN_USERNAME=@awlism

---

## BOT_TOKEN

توکن اصلی ربات Telegram است.

این مقدار باید فقط در محیط اجرای واقعی تنظیم شود و نباید داخل Repository یا کد عمومی قرار بگیرد.

---

## DATABASE_PATH

مسیر دیتابیس SQLite محلی را مشخص می‌کند.

مقدار پیش‌فرض:

    arzan_kadeh.db

---

## SEED_DEMO_DATA

برای فعال‌کردن داده‌های نمایشی استفاده می‌شود.

حالت پیش‌فرض:

    false

برای فعال‌کردن:

    SEED_DEMO_DATA=true

---

## ADMIN_CHAT_ID

آیدی عددی Chat مدیر Telegram است.

این مقدار username نیست.

اگر مقدار معتبر وجود نداشته باشد، قابلیت‌هایی که نیاز به ارسال مستقیم پیام مدیریتی دارند باید بدون ایجاد Crash از ارسال مستقیم صرف‌نظر کنند.

---

## ADMIN_USERNAME

username عمومی مدیر برای نمایش در بخش‌های مرتبط با پشتیبانی و مدیریت است.

مقدار فعلی نمونه:

    @awlism

---

# نصب

نیازمندی‌های پروژه در:

    requirements.txt

قرار دارند.

نصب:

    pip install -r requirements.txt

سپس:

    cp .env.example .env

و مقادیر واقعی محیط را داخل `.env` قرار دهید.

فایل `.env` نباید commit شود.

---

# اجرای محلی

پس از نصب dependencies و تنظیم `.env`:

    python bot.py

در وضعیت فعلی، Bot با polling اجرا می‌شود.

---

# تست‌ها

پوشه `tests` شامل تست‌های پروژه و Static Analysis است.

بخش‌هایی مانند موارد زیر پوشش داده می‌شوند:

- Database
- Schema
- Seed
- Navigation
- Utilities
- Repositoryها
- Serviceها
- Handlerها
- Search
- Referral
- Seller Claims
- Compare
- Favorites
- Admin flows
- Static Analysis
- ساختار پروژه
- رفتارهای اصلی MVP

اجرای کامل تست‌ها:

    pytest tests -v

یا:

    python -m unittest discover -s tests -v

---

# Static Analysis

پروژه شامل تست‌های Static Analysis برای شناسایی الگوهای خطرناک و معماری ناسازگار است.

از جمله موارد بررسی‌شده:

- دسترسی مستقیم غیرمجاز به SQLite
- استفاده نامناسب از Database connection
- ساختار Repositoryها
- ساختار Handlerها
- امنیت queryها
- URL validation
- ساختار فایل‌ها
- وابستگی‌های پروژه

لایه‌های بالاتر نباید بدون دلیل به implementation-specific APIهای SQLite مانند:

    db.conn

یا:

    db.execute()

وابسته شوند.

استثناهای low-level مانند:

    bot/database.py
    bot/sqlite_backend.py

بخشی از implementation داخلی SQLite هستند و با Repository/Service code یکسان نیستند.

---

# امنیت

اطلاعات حساس نباید بدون دلیل در Git commit شوند.

مواردی مانند:

- `BOT_TOKEN`
- Secretها
- Credentialها
- فایل‌های دیتابیس واقعی
- تنظیمات خصوصی Deployment
- Cloudflare secrets
- API keys

باید خارج از Repository یا در Secret Management مناسب نگهداری شوند.

فایل `.gitignore` برای جلوگیری از commit شدن فایل‌های محیطی و دیتابیس‌های محلی تنظیم شده است.

---

# قوانین توسعه

هنگام توسعه پروژه:

- معماری ماژولار حفظ شود.
- منطق جدید مستقیماً داخل `bot.py` اضافه نشود مگر در موارد مربوط به Bootstrap و راه‌اندازی.
- Handlerها مسئول دریافت ورودی و کنترل Flow باشند.
- منطق کسب‌وکار در Serviceها قرار گیرد.
- عملیات داده در Repositoryها یا Backendهای مربوطه متمرکز باشد.
- لایه‌های بالاتر به SQLite-specific API وابسته نشوند.
- ثابت‌های مشترک در `constants.py` نگهداری شوند.
- تنظیمات محیطی از `config.py` دریافت شوند.
- Secretها داخل Repository قرار نگیرند.
- تغییرات معماری فقط در صورت نیاز واقعی انجام شوند.
- تغییرات جدید نباید رفتارهای موجود MVP را بدون دلیل تغییر دهند.
- تست‌های جدید باید با معماری ماژولار فعلی هماهنگ باشند.
- تغییرات Cloudflare و Webhook نباید بدون بررسی جریان فعلی Telegram اعمال شوند.
- Backend جدید باید contract مربوط به `DatabaseBackend` را رعایت کند.
- منطق Repository نباید به Backend خاصی وابسته شود.
- Migrationهای دیتابیس باید idempotent و قابل تکرار باشند.
- عملیات حساس دیتابیس باید از Transaction مناسب استفاده کنند.

---

# اصول Persistence

در بخش‌های application-level پروژه:

    Handler
        ↓
    Service
        ↓
    Repository
        ↓
    DatabaseBackend

نباید به شکل زیر عمل شود:

    Handler
        ↓
    SQLite connection

یا:

    Service
        ↓
    db.conn.execute(...)

پیاده‌سازی SQLite در پایین‌ترین لایه نگهداری می‌شود.

این جداسازی برای مهاجرت آینده به D1 و همچنین تست‌پذیری بهتر پروژه ضروری است.

---

# وضعیت MVP

ArzanKadeh AI در حال توسعه است و معماری پروژه برای رشد تدریجی طراحی شده است.

تمرکز فعلی روی:

- پایداری هسته ربات
- معماری ماژولار
- صحت دیتابیس
- Repository abstraction
- Database Backend abstraction
- جستجوی محلی
- تجربه کاربری Telegram
- تست‌پذیری
- امنیت تنظیمات
- آماده‌سازی Cloudflare
- آماده‌سازی Webhook
- حفظ سازگاری SQLite تا زمان تکمیل Backend جدید

است.

---

# مسیر توسعه آینده

قابلیت‌های آینده می‌توانند شامل موارد زیر باشند:

- Telegram Webhook کامل
- Cloudflare Worker integration
- Cloudflare D1 Backend
- Telegram Mini App کامل
- AI Search پیشرفته
- سیستم تبلیغات پیشرفته‌تر
- امکانات بیشتر برای فروشندگان
- Analytics پیشرفته
- سیستم سفارش و پیگیری کامل‌تر
- قابلیت‌های بیشتر برای مقایسه محصولات
- زیرساخت مقیاس‌پذیرتر
- Persistent FSM مناسب محیط Webhook
- قابلیت‌های Background Task مناسب محیط Deployment جدید

این قابلیت‌ها باید روی معماری موجود توسعه داده شوند و از تغییرات غیرضروری در هسته پروژه جلوگیری شود.

---

# پشتیبانی

برای پشتیبانی و ارتباط با تیم پروژه:

    @awlism

---

# License

 این پروژه در حال توسعه است و شرایط استفاده و License نهایی آن در مراحل بعدی مشخص خواهد شد.