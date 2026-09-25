# -*- coding: utf-8 -*-

import logging
from typing import Optional, Sequence

import aiosqlite

from .config import DATABASE_PATH, SEED_DEMO_DATA


logger = logging.getLogger("arzankadeh")


class Database:
    """Small async wrapper around aiosqlite for this MVP."""

    def __init__(self, path: str):
        self.path = path
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA foreign_keys = ON;")
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    async def execute(
        self,
        query: str,
        params: Sequence = (),
    ) -> aiosqlite.Cursor:
        cur = await self.conn.execute(query, params)
        await self.conn.commit()
        return cur

    async def fetchone(
        self,
        query: str,
        params: Sequence = (),
    ) -> Optional[aiosqlite.Row]:
        cur = await self.conn.execute(query, params)
        row = await cur.fetchone()
        await cur.close()
        return row

    async def fetchall(
        self,
        query: str,
        params: Sequence = (),
    ) -> list:
        cur = await self.conn.execute(query, params)
        rows = await cur.fetchall()
        await cur.close()
        return rows


db = Database(DATABASE_PATH)


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE NOT NULL,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        city_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (city_id) REFERENCES cities(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS cities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        emoji TEXT NOT NULL DEFAULT '📁',
        parent_id INTEGER,
        FOREIGN KEY (parent_id) REFERENCES categories(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS sellers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        city_id INTEGER,
        instagram TEXT,
        telegram TEXT,
        website TEXT,
        status TEXT NOT NULL DEFAULT 'UNCLAIMED',
        rating REAL NOT NULL DEFAULT 0,
        review_count INTEGER NOT NULL DEFAULT 0,
        views INTEGER NOT NULL DEFAULT 0,
        owner_user_id INTEGER,
        created_by_user_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (city_id) REFERENCES cities(id),
        FOREIGN KEY (owner_user_id) REFERENCES users(id),
        FOREIGN KEY (created_by_user_id) REFERENCES users(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        category_id INTEGER,
        name TEXT NOT NULL,
        description TEXT,
        price REAL,
        old_price REAL,
        image_url TEXT,
        stock_status TEXT NOT NULL DEFAULT 'AVAILABLE',
        rating REAL NOT NULL DEFAULT 0,
        review_count INTEGER NOT NULL DEFAULT 0,
        views INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (seller_id) REFERENCES sellers(id),
        FOREIGN KEY (category_id) REFERENCES categories(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(user_id, product_id),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS seller_claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (seller_id) REFERENCES sellers(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        seller_id INTEGER,
        product_id INTEGER,
        rating INTEGER NOT NULL,
        text TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (seller_id) REFERENCES sellers(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        seller_id INTEGER,
        product_id INTEGER,
        reason TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL DEFAULT 'PENDING',
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (seller_id) REFERENCES sellers(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        event_type TEXT NOT NULL,
        entity_type TEXT,
        entity_id INTEGER,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        message TEXT,
        notification_type TEXT,
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        referred_user_id INTEGER NOT NULL UNIQUE,
        source TEXT NOT NULL DEFAULT 'deep_link',
        created_at TEXT NOT NULL,
        FOREIGN KEY (seller_id) REFERENCES sellers(id),
        FOREIGN KEY (referred_user_id) REFERENCES users(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS referral_rewards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        milestone INTEGER NOT NULL,
        reward_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        granted_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (seller_id) REFERENCES sellers(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS seller_favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        seller_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(user_id, seller_id),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (seller_id) REFERENCES sellers(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        request_type TEXT NOT NULL,
        topic TEXT,
        message TEXT,
        seller_id INTEGER,
        status TEXT NOT NULL DEFAULT 'PENDING',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (seller_id) REFERENCES sellers(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_user_id INTEGER,
        action TEXT NOT NULL,
        entity_type TEXT,
        entity_id INTEGER,
        details TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (actor_user_id) REFERENCES users(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        buyer_user_id INTEGER NOT NULL,
        seller_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        total_price INTEGER,
        status TEXT NOT NULL DEFAULT 'PENDING'
            CHECK (status IN ('PENDING', 'CONFIRMED', 'COMPLETED', 'CANCELLED')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (buyer_user_id) REFERENCES users(id),
        FOREIGN KEY (seller_id) REFERENCES sellers(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    );
    """,
]


COLUMN_MIGRATIONS = [
    ("users", "active_mode", "TEXT NOT NULL DEFAULT 'buyer'"),
    ("users", "has_seen_compare_intro", "INTEGER NOT NULL DEFAULT 0"),
    ("sellers", "logo_url", "TEXT"),
    ("sellers", "telegram_support", "TEXT"),
    ("sellers", "location_text", "TEXT"),
    ("sellers", "coverage_area", "TEXT"),
    ("sellers", "phone", "TEXT"),
    ("sellers", "whatsapp", "TEXT"),
    ("sellers", "is_active", "INTEGER NOT NULL DEFAULT 1"),
    ("users", "role_chosen", "INTEGER NOT NULL DEFAULT 0"),
    ("requests", "ad_kind", "TEXT"),
    ("requests", "ad_title", "TEXT"),
    ("requests", "ad_image_url", "TEXT"),
    ("requests", "ad_link", "TEXT"),
    ("requests", "ad_price", "INTEGER"),
    ("requests", "ad_duration_days", "INTEGER"),
    ("requests", "ad_placement", "TEXT"),
    ("requests", "ad_expires_at", "TEXT"),
]


INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories(parent_id);",
    "CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);",
    "CREATE INDEX IF NOT EXISTS idx_products_seller ON products(seller_id);",
    "CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_sellers_city ON sellers(city_id);",
    "CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_reviews_seller ON reviews(seller_id);",
    "CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews(product_id);",
    "CREATE INDEX IF NOT EXISTS idx_claims_seller ON seller_claims(seller_id);",
    "CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_referrals_seller ON referrals(seller_id);",
    "CREATE INDEX IF NOT EXISTS idx_referral_rewards_seller ON referral_rewards(seller_id);",
    "CREATE INDEX IF NOT EXISTS idx_seller_favorites_user ON seller_favorites(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_seller_favorites_seller ON seller_favorites(seller_id);",
    "CREATE INDEX IF NOT EXISTS idx_requests_user ON requests(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_type, entity_id);",
    "CREATE INDEX IF NOT EXISTS idx_orders_buyer ON orders(buyer_user_id);",
    "CREATE INDEX IF NOT EXISTS idx_orders_seller ON orders(seller_id);",
    "CREATE INDEX IF NOT EXISTS idx_orders_product ON orders(product_id);",
    "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);",
]


async def ensure_column(
    table: str,
    column: str,
    sql_type_and_default: str,
) -> None:
    cur = await db.conn.execute(f"PRAGMA table_info({table});")
    rows = await cur.fetchall()
    await cur.close()

    existing_columns = {row[1] for row in rows}

    if column in existing_columns:
        return

    await db.conn.execute(
        f"ALTER TABLE {table} ADD COLUMN {column} {sql_type_and_default};"
    )

    logger.info(
        "Migrated: added column %s.%s",
        table,
        column,
    )


async def run_column_migrations() -> None:
    for table, column, sql_type_and_default in COLUMN_MIGRATIONS:
        await ensure_column(
            table,
            column,
            sql_type_and_default,
        )

    await db.conn.commit()


async def init_schema() -> None:
    for stmt in SCHEMA_STATEMENTS:
        await db.conn.execute(stmt)

    for stmt in INDEX_STATEMENTS:
        await db.conn.execute(stmt)

    await db.conn.commit()
    await run_column_migrations()


CITY_NAMES = [
    "تهران",
    "کرج",
    "مشهد",
    "اصفهان",
    "شیراز",
    "تبریز",
    "قم",
    "اهواز",
    "رشت",
    "کرمان",
    "ارومیه",
    "یزد",
    "کرمانشاه",
    "همدان",
    "بندرعباس",
    "قزوین",
    "اراک",
    "زنجان",
    "سنندج",
    "ساری",
    "گرگان",
    "اردبیل",
    "بوشهر",
    "خرم‌آباد",
    "آبادان",
]


CATEGORY_TREE = [
    ("👗", "مد و پوشاک", [
        ("👩", "زنانه"),
        ("👨", "مردانه"),
        ("🧒", "بچگانه"),
        ("👟", "کفش"),
        ("👜", "کیف"),
        ("🩲", "لباس زیر"),
        ("👚", "لباس خانگی"),
        ("🏃", "لباس ورزشی"),
        ("✨", "لباس مجلسی"),
        ("☀️", "لباس تابستانی"),
        ("🧥", "لباس زمستانی"),
        ("🧣", "شال و روسری"),
        ("💍", "اکسسوری و زیورآلات"),
    ]),
    ("💄", "زیبایی و آرایشی", [
        ("💄", "آرایشی"),
        ("🧴", "مراقبت پوست"),
        ("💇", "مراقبت مو"),
        ("🌸", "عطر و ادکلن"),
        ("🧼", "محصولات بهداشتی"),
        ("💅", "ناخن"),
        ("🪞", "ابزار زیبایی"),
    ]),
    ("💇", "سالن و خدمات زیبایی", [
        ("💇", "آرایشگاه"),
        ("💅", "ناخن"),
        ("👁️", "مژه و ابرو"),
        ("💇‍♀️", "مو"),
        ("💄", "میکاپ"),
        ("💆", "ماساژ"),
        ("🧖", "اسپا"),
        ("✨", "خدمات زیبایی تخصصی"),
    ]),
    ("💎", "طلا و جواهر", [
        ("🥇", "طلا"),
        ("🥈", "نقره"),
        ("💎", "جواهر"),
        ("📿", "بدلیجات"),
        ("⌚", "ساعت"),
        ("💠", "سنگ‌های قیمتی"),
    ]),
    ("📱", "موبایل و دیجیتال", [
        ("📱", "موبایل"),
        ("🔌", "لوازم جانبی"),
        ("💻", "لپ‌تاپ"),
        ("🖥️", "کامپیوتر"),
        ("🎮", "کنسول و بازی"),
        ("🎧", "صوتی و تصویری"),
        ("📷", "دوربین"),
        ("⌚", "لوازم هوشمند"),
    ]),
    ("🏠", "خانه و آشپزخانه", [
        ("🪴", "دکوراسیون"),
        ("🍳", "آشپزخانه"),
        ("⚡", "لوازم برقی"),
        ("🛏️", "کالای خواب"),
        ("🛋️", "مبلمان"),
        ("🌱", "گل و گیاه"),
        ("🏠", "لوازم خانه"),
        ("🧹", "نظافت و شست‌وشو"),
    ]),
    ("🧸", "کودک و نوزاد", [
        ("👕", "لباس کودک"),
        ("🧸", "اسباب‌بازی"),
        ("🍼", "لوازم نوزاد"),
        ("🛒", "کالسکه و صندلی"),
        ("🧼", "مراقبت کودک"),
        ("🎀", "سیسمونی"),
    ]),
    ("🥗", "خوراکی و نوشیدنی", [
        ("☕", "قهوه"),
        ("🍵", "چای"),
        ("🍫", "شکلات"),
        ("🍰", "شیرینی"),
        ("🎂", "کیک"),
        ("🥜", "خشکبار"),
        ("🌶️", "ادویه"),
        ("🥤", "نوشیدنی"),
        ("🥫", "محصولات خانگی"),
        ("🍱", "غذاهای آماده"),
    ]),
    ("🎨", "صنایع دستی و هنری", [
        ("🧶", "صنایع دستی"),
        ("🖌️", "نقاشی"),
        ("🧵", "بافتنی"),
        ("🖼️", "محصولات هنری"),
        ("🏺", "سفال و سرامیک"),
        ("🪵", "چوب و رزین"),
        ("📿", "زیورآلات دست‌ساز"),
    ]),
    ("🎁", "هدیه", [
        ("🎉", "هدایای مناسبتی"),
        ("🎂", "هدیه تولد"),
        ("❤️", "هدیه عاشقانه"),
        ("🏢", "هدیه سازمانی"),
        ("🎁", "باکس هدیه"),
        ("🧶", "هدایای دست‌ساز"),
    ]),
    ("🌱", "گل و گیاه", [
        ("🌹", "گل طبیعی"),
        ("🌸", "گل مصنوعی"),
        ("🪴", "گیاه آپارتمانی"),
        ("🏺", "گلدان"),
        ("💐", "باکس گل"),
        ("🌿", "تراریوم"),
    ]),
    ("🏋️", "ورزش", [
        ("👕", "پوشاک ورزشی"),
        ("👟", "کفش ورزشی"),
        ("🏋️", "تجهیزات ورزشی"),
        ("💪", "بدنسازی"),
        ("🧘", "یوگا و فیتنس"),
        ("⚽", "ورزش‌های توپی"),
        ("🏕️", "کمپینگ"),
    ]),
    ("🚗", "خودرو و موتور", [
        ("🚗", "لوازم خودرو"),
        ("🏍️", "لوازم موتور"),
        ("⚙️", "قطعات"),
        ("🔧", "لوازم جانبی"),
        ("🛠️", "خدمات خودرو"),
        ("🏍️", "خدمات موتور"),
        ("🛞", "تایر و رینگ"),
    ]),
    ("📚", "کتاب و آموزش", [
        ("📖", "کتاب"),
        ("🎓", "دوره آموزشی"),
        ("✏️", "لوازم تحریر"),
        ("🌐", "آموزش زبان"),
        ("🧠", "آموزش مهارت"),
        ("🎸", "آموزش موسیقی"),
        ("📚", "آموزش کنکور و مدرسه"),
    ]),
    ("🛠️", "خدمات", [
        ("🔧", "خدمات فنی"),
        ("💻", "خدمات آنلاین"),
        ("🎓", "خدمات آموزشی"),
        ("💬", "مشاوره"),
        ("📷", "عکاسی"),
        ("🎬", "تولید محتوا"),
        ("📱", "مدیریت شبکه‌های اجتماعی"),
        ("📢", "تبلیغات"),
        ("🏠", "خدمات منزل"),
        ("🛠️", "تعمیرات"),
        ("🎉", "برگزاری مراسم"),
        ("🚚", "حمل‌ونقل"),
        ("🧰", "سایر خدمات"),
    ]),
    ("🐾", "حیوانات خانگی", [
        ("🥩", "غذا"),
        ("🐾", "لوازم حیوانات"),
        ("🐕", "پوشاک حیوانات"),
        ("🧼", "بهداشت حیوانات"),
        ("🩺", "خدمات حیوانات"),
        ("🏠", "لوازم نگهداری"),
    ]),
    ("📦", "محصولات وارداتی", [
        ("👗", "پوشاک وارداتی"),
        ("💄", "آرایشی وارداتی"),
        ("🍫", "خوراکی وارداتی"),
        ("📱", "دیجیتال وارداتی"),
        ("🏠", "لوازم خانه وارداتی"),
        ("📦", "سایر محصولات وارداتی"),
    ]),
    ("🏡", "املاک", [
        ("🏠", "فروش مسکونی"),
        ("🔑", "اجاره مسکونی"),
        ("🏢", "فروش تجاری"),
        ("🏬", "اجاره تجاری"),
        ("🌳", "زمین"),
        ("🏡", "ویلا"),
        ("🏢", "دفتر کار"),
        ("📦", "سایر املاک"),
    ]),
]


DEMO_SELLER_NAME = "DEMO - فروشگاه نمونه"
DEMO_PRODUCT_NAME = "DEMO - محصول نمونه"


async def seed_cities() -> None:
    row = await db.fetchone("SELECT COUNT(*) AS c FROM cities;")

    if row["c"] > 0:
        return

    for name in CITY_NAMES:
        await db.conn.execute(
            "INSERT OR IGNORE INTO cities (name) VALUES (?);",
            (name,),
        )

    await db.conn.commit()
    logger.info("Seeded %d cities.", len(CITY_NAMES))


async def seed_categories() -> None:
    row = await db.fetchone("SELECT COUNT(*) AS c FROM categories;")

    if row["c"] > 0:
        return

    for main_emoji, main_name, subs in CATEGORY_TREE:
        cur = await db.conn.execute(
            """
            INSERT INTO categories (name, emoji, parent_id)
            VALUES (?, ?, NULL);
            """,
            (main_name, main_emoji),
        )

        parent_id = cur.lastrowid

        for sub_emoji, sub_name in subs:
            await db.conn.execute(
                """
                INSERT INTO categories (name, emoji, parent_id)
                VALUES (?, ?, ?);
                """,
                (sub_name, sub_emoji, parent_id),
            )

    await db.conn.commit()
    logger.info(
        "Seeded categories tree (%d main categories).",
        len(CATEGORY_TREE),
    )


async def seed_demo_data() -> None:
    """Optional demo data, disabled unless SEED_DEMO_DATA=true."""

    if not SEED_DEMO_DATA:
        return

    existing = await db.fetchone(
        "SELECT id FROM sellers WHERE name = ?;",
        (DEMO_SELLER_NAME,),
    )

    if existing:
        return

    city = await db.fetchone(
        "SELECT id FROM cities WHERE name = 'تهران';"
    )

    category = await db.fetchone(
        """
        SELECT id
        FROM categories
        WHERE parent_id IS NOT NULL
        ORDER BY id
        LIMIT 1;
        """
    )

    now = _now_iso()

    cur = await db.conn.execute(
        """
        INSERT INTO sellers (
            name,
            description,
            city_id,
            status,
            rating,
            review_count,
            views,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, 'UNCLAIMED', 0, 0, 0, ?, ?);
        """,
        (
            DEMO_SELLER_NAME,
            "[DEMO] این یک فروشگاه نمایشی برای تست ربات است و واقعی نیست.",
            city["id"] if city else None,
            now,
            now,
        ),
    )

    demo_seller_id = cur.lastrowid

    await db.conn.execute(
        """
        INSERT INTO products (
            seller_id,
            category_id,
            name,
            description,
            price,
            stock_status,
            rating,
            review_count,
            views,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'AVAILABLE', 0, 0, 0, ?, ?);
        """,
        (
            demo_seller_id,
            category["id"] if category else None,
            DEMO_PRODUCT_NAME,
            "[DEMO] این یک محصول نمایشی برای تست ربات است و واقعی نیست.",
            100000,
            now,
            now,
        ),
    )

    await db.conn.commit()

    logger.info(
        "Seeded DEMO data (clearly labeled, SEED_DEMO_DATA=true)."
    )


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")