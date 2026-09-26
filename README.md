# ArzanKadeh AI (ارزانکده AI)

یک محل کشف قابل‌اعتماد، زیبا و ساده برای کسب‌وکارهای ایرانی — فروشگاه‌های اینستاگرامی، تلگرامی، کسب‌وکارهای خانگی، محلی، سالن‌های زیبایی، صنایع دستی، غذا، خدمات و محصولات.

ArzanKadeh AI یک ربات تلگرام MVP است که با aiogram 3.x، aiosqlite و معماری ماژولار پایتون ساخته شده است.

## ویژگی‌های پیاده‌سازی‌شده

- دسته‌بندی چندسطحی محصولات
- ناوبری مبتنی بر دیتابیس با `parent_id`
- جستجوی هوشمند محلی و رایگان با `LocalQueryParser`
- جستجوی ساختاریافته بر اساس قیمت، شهر، دسته‌بندی، رنگ و جنسیت
- Ranking نتایج بر اساس داده واقعی دیتابیس
- سیستم Referral برای فروشندگان
- صفحه فروشگاه و محصول
- وضعیت تأیید فروشگاه‌ها
- علاقه‌مندی‌ها
- امتیازدهی و نظرات
- گزارش تخلف
- درخواست مالکیت فروشگاه
- ثبت فروشگاه
- اعلان‌ها
- حساب کاربری
- انتخاب شهر
- بخش‌های داغ‌ترین‌ها، جدیدهای امروز و فروشندگان برتر
- مقایسه محصولات
- سیستم تبلیغات
- ثبت رویدادهای Analytics
- Fallback handler سراسری
- داده نمایشی اختیاری با `SEED_DEMO_DATA`

---

## معماری پروژه

پروژه از معماری ماژولار استفاده می‌کند و منطق ربات در یک فایل واحد قرار ندارد.

ساختار اصلی پروژه:

    .
    ├── bot.py
    ├── requirements.txt
    ├── .env.example
    ├── .gitignore
    ├── README.md
    ├── miniapp/
    │   └── index.html
    ├── bot/
    │   ├── __init__.py
    │   ├── config.py
    │   ├── constants.py
    │   ├── database.py
    │   ├── keyboards.py
    │   ├── repositories.py
    │   ├── states.py
    │   ├── utils.py
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
    │   └── services/
    │       ├── __init__.py
    │       ├── backups.py
    │       ├── notifications.py
    │       ├── referrals.py
    │       └── tasks.py
    └── tests/
        ├── _extract.py
        ├── test_schema_and_seed.py
        ├── test_category_navigation_logic.py
        ├── test_utils.py
        ├── test_static_analysis.py
        └── ...

---

## معماری منطقی

    Telegram
        │
        ▼
    Handlers
        │
        ├── Navigation
        ├── Products
        ├── Sellers
        ├── Search
        ├── Favorites
        ├── Compare
        ├── Orders
        └── ...
        │
        ▼
    Services
        │
        ▼
    Repositories
        │
        ▼
    Database
        │
        ▼
    SQLite

مسئولیت هر بخش از پروژه از بخش‌های دیگر جدا شده است تا توسعه، تست و نگهداری پروژه ساده‌تر باشد.

`navigation.py` مسئول جریان‌های اصلی ورود و ناوبری، انتخاب نقش، restart، referral deep-link و fallbackهای عمومی است.

---

## نصب

نیازمندی‌های پروژه در `requirements.txt` قرار دارند.

دستور نصب:

    pip install -r requirements.txt

سپس فایل محیطی را ایجاد کن:

    cp .env.example .env

مقادیر واقعی تنظیمات را داخل `.env` قرار بده.

---

## اجرا

برای اجرای فعلی ربات:

    python bot.py

در وضعیت فعلی، Backend ربات از polling تلگرام استفاده می‌کند و برای اجرای واقعی به `BOT_TOKEN` نیاز دارد.

مسیر Webhook و Cloudflare در معماری هدف پروژه در نظر گرفته شده‌اند، اما فعال‌سازی کامل Webhook زمانی نهایی محسوب می‌شود که Backend نیز برای دریافت Webhook به‌درستی پیکربندی شده باشد.

---

## تنظیمات محیطی

نمونه تنظیمات در `.env.example` قرار دارد.

    BOT_TOKEN=your_bot_token_here
    DATABASE_PATH=arzan_kadeh.db
    SEED_DEMO_DATA=false
    ADMIN_CHAT_ID=
    ADMIN_USERNAME=@awlism

### BOT_TOKEN

توکن اصلی ربات تلگرام است.

این مقدار باید در محیط اجرای واقعی تنظیم شود و نباید به‌عنوان Secret داخل کد یا فایل‌های عمومی پروژه قرار بگیرد.

### DATABASE_PATH

مسیر دیتابیس SQLite را مشخص می‌کند.

مقدار پیش‌فرض:

    arzan_kadeh.db

### SEED_DEMO_DATA

برای فعال‌کردن داده‌های نمایشی استفاده می‌شود.

حالت پیش‌فرض:

    SEED_DEMO_DATA=false

برای فعال‌کردن:

    SEED_DEMO_DATA=true

### ADMIN_CHAT_ID

آیدی عددی چت تلگرام مدیر است.

این مقدار باید Chat ID عددی باشد و username نیست.

اگر مقدار معتبر وجود نداشته باشد، قابلیت‌هایی که نیاز به ارسال مستقیم پیام مدیریتی دارند بدون ایجاد Crash از ارسال مستقیم صرف‌نظر می‌کنند.

### ADMIN_USERNAME

username عمومی مدیر برای نمایش در بخش‌های مرتبط با پشتیبانی و مدیریت است.

---

## دیتابیس

پروژه از `aiosqlite` برای دسترسی asynchronous به SQLite استفاده می‌کند.

از جدول‌های اصلی پروژه می‌توان به موارد زیر اشاره کرد:

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

Seed شهرها و دسته‌بندی‌ها به‌صورت idempotent طراحی شده‌اند تا اجرای مجدد برنامه باعث ایجاد رکوردهای تکراری نشود.

داده‌های Demo نیز اختیاری هستند و با `SEED_DEMO_DATA` کنترل می‌شوند.

---

## جستجوی هوشمند محلی

معماری جستجو به شکل زیر است:

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

### QueryParser

`QueryParser` یک contract مستقل برای تبدیل متن خام کاربر به Query ساختاریافته است.

### LocalQueryParser

پیاده‌سازی فعلی `QueryParser` است و بدون نیاز به API یا سرویس AI خارجی اجرا می‌شود.

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

### SearchEngine

`SearchEngine` به contract مربوط به `QueryParser` وابسته است و مستقیماً به `LocalQueryParser` وابستگی ندارد.

این ساختار اجازه می‌دهد در آینده QueryParserهای جدید، از جمله پیاده‌سازی‌های مبتنی بر AI، بدون بازنویسی منطق اصلی `SearchEngine` اضافه شوند.

### Ranking

نتایج بر اساس داده واقعی دیتابیس رتبه‌بندی می‌شوند.

معیارهای مورد استفاده می‌توانند شامل موارد زیر باشند:

- تطابق دسته‌بندی
- تطابق کلمات کلیدی
- شهر
- محدوده قیمت
- امتیاز
- تعداد نظرات
- بازدید

Search Engine نباید محصول یا نتیجه ساختگی ایجاد کند.

---

## سیستم Referral

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

## اعلان‌ها

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

## Telegram Mini App

پوشه `miniapp` در MVP فعلی شامل placeholder اولیه Telegram Mini App است.

ساختار:

    miniapp/
        └── index.html

Mini App به‌عنوان مسیر توسعه آینده نگهداری می‌شود و منطق اصلی ربات به آن وابسته نیست.

---

## Cloudflare

زیرساخت Cloudflare پروژه برای استقرار و مسیر Webhook در نظر گرفته شده است.

معماری هدف:

    Telegram
        │
        ▼
    Cloudflare
        │
        ▼
    Bot Backend

وضعیت فعلی:

- معماری Cloudflare/Webhook به‌عنوان مسیر استقرار هدف پروژه تعریف شده است.
- Backend فعلی همچنان با polling اجرا می‌شود.
- Webhook کامل Telegram هنوز مرحله نهایی پیاده‌سازی و فعال‌سازی را طی می‌کند.
- Secretها و تنظیمات Deployment مربوط به Cloudflare نباید داخل Repository قرار بگیرند.
- فعال‌سازی نهایی Webhook باید پس از آماده‌شدن کامل Backend انجام شود.

---

## امنیت

اطلاعات حساس نباید بدون دلیل در Git commit شوند.

مواردی مانند:

- BOT_TOKEN
- Secretها
- Credentialها
- فایل‌های دیتابیس واقعی
- تنظیمات خصوصی Deployment
- Secretهای Cloudflare

باید خارج از Repository یا در Secret Management مناسب نگهداری شوند.

فایل `.gitignore` برای جلوگیری از commit شدن فایل‌های محیطی و دیتابیس‌های محلی تنظیم شده است.

---

## تست‌ها

پوشه `tests` شامل تست‌های پروژه و بررسی‌های Static Analysis است.

بخش‌هایی مانند موارد زیر در تست‌ها پوشش داده می‌شوند:

- Database
- Schema
- Seed
- Navigation
- Utilities
- Repositoryها
- Serviceها
- Handlerها
- Static Analysis
- ساختار پروژه
- رفتارهای اصلی MVP

برای اجرای کامل تست‌ها:

    pytest tests -v

یا:

    python -m unittest discover -s tests -v

---

## GitHub Codespaces

در Codespaces ابتدا نیازمندی‌ها را نصب کن:

    pip install -r requirements.txt

سپس فایل محیطی را ایجاد کن:

    cp .env.example .env

مقادیر واقعی محیط اجرای ربات را داخل `.env` قرار بده.

برای اجرای ربات:

    python bot.py

برای اجرای تست‌ها:

    pytest tests -v

---

## توسعه

هنگام توسعه پروژه:

- معماری ماژولار حفظ شود.
- منطق جدید مستقیماً داخل `bot.py` اضافه نشود مگر در موارد مربوط به Bootstrap و راه‌اندازی.
- Handlerها مسئول دریافت ورودی و کنترل Flow باشند.
- منطق کسب‌وکار در Serviceها قرار گیرد.
- دسترسی به دیتابیس در Repositoryها یا لایه دیتابیس متمرکز باشد.
- ثابت‌های مشترک در `constants.py` نگهداری شوند.
- تنظیمات محیطی فقط از `config.py` دریافت شوند.
- Secretها داخل Repository قرار نگیرند.
- تغییرات معماری فقط در صورت نیاز واقعی انجام شوند.
- تغییرات جدید نباید رفتارهای موجود MVP را بدون دلیل تغییر دهند.
- تست‌های جدید باید با معماری ماژولار فعلی هماهنگ باشند.
- تغییرات Cloudflare و Webhook نباید بدون بررسی جریان فعلی Telegram اعمال شوند.

---

## وضعیت MVP

ArzanKadeh AI در حال توسعه است و معماری پروژه برای رشد تدریجی طراحی شده است.

تمرکز فعلی روی:

- پایداری هسته ربات
- ساختار ماژولار
- صحت دیتابیس
- جستجوی محلی
- تجربه کاربری Telegram
- تست‌پذیری
- امنیت تنظیمات
- آماده‌سازی زیرساخت Deployment
- اتصال صحیح به Cloudflare
- تکمیل مهاجرت از polling به Webhook

است.

---

## مسیر توسعه آینده

قابلیت‌های آینده می‌توانند شامل موارد زیر باشند:

- Webhook کامل Telegram
- توسعه بیشتر Cloudflare integration
- Telegram Mini App کامل
- AI Search پیشرفته
- سیستم تبلیغات پیشرفته‌تر
- امکانات بیشتر برای فروشندگان
- Analytics پیشرفته
- سیستم سفارش و پیگیری کامل‌تر
- قابلیت‌های بیشتر برای مقایسه محصولات
- زیرساخت مقیاس‌پذیرتر

این قابلیت‌ها باید روی معماری موجود توسعه داده شوند و از تغییرات غیرضروری در هسته پروژه جلوگیری شود.

---

## پشتیبانی

برای پشتیبانی و ارتباط با تیم پروژه:

    @awlism

---

## License

این پروژه در حال توسعه است و شرایط استفاده و License نهایی آن در مراحل بعدی مشخص خواهد شد.