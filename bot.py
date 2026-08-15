# -*- coding: utf-8 -*-
"""
ArzanKadeh AI (ارزانکده AI)
============================
یک محل کشف قابل‌اعتماد، زیبا و ساده برای کسب‌وکارهای ایرانی.

Single-file Telegram bot built with aiogram 3.x + aiosqlite.

Run:
    python bot.py

Environment (.env):
    BOT_TOKEN=xxxxx
    DATABASE_PATH=arzan_kadeh.db   (optional)
"""

# ======================================================================
# 1. IMPORTS
# ======================================================================
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Sequence

import aiosqlite
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ======================================================================
# 2. CONFIGURATION
# ======================================================================
load_dotenv()

BOT_TOKEN: Optional[str] = os.getenv("BOT_TOKEN")
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "arzan_kadeh.db")
# Optional, OFF by default. When enabled, inserts a small set of obviously
# labeled DEMO seller/products so the bot is not empty during local testing.
# Demo rows are always prefixed with "DEMO -" / "[DEMO]" so they can never
# be mistaken for real data, and re-running startup never duplicates them.
SEED_DEMO_DATA: bool = os.getenv("SEED_DEMO_DATA", "false").strip().lower() == "true"

PAGE_SIZE_CATEGORIES = 10
PAGE_SIZE_LIST = 8
TOP_LIST_LIMIT = 10

# ======================================================================
# 3. LOGGING
# ======================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("arzankadeh")

# ======================================================================
# 4. DATABASE
# ======================================================================
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

    async def execute(self, query: str, params: Sequence = ()) -> aiosqlite.Cursor:
        cur = await self.conn.execute(query, params)
        await self.conn.commit()
        return cur

    async def fetchone(self, query: str, params: Sequence = ()) -> Optional[aiosqlite.Row]:
        cur = await self.conn.execute(query, params)
        row = await cur.fetchone()
        await cur.close()
        return row

    async def fetchall(self, query: str, params: Sequence = ()) -> list:
        cur = await self.conn.execute(query, params)
        rows = await cur.fetchall()
        await cur.close()
        return rows


db = Database(DATABASE_PATH)

# ======================================================================
# 5. DATABASE SCHEMA
# ======================================================================
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
]


async def init_schema() -> None:
    for stmt in SCHEMA_STATEMENTS:
        await db.conn.execute(stmt)
    for stmt in INDEX_STATEMENTS:
        await db.conn.execute(stmt)
    await db.conn.commit()


# ======================================================================
# 6. SEED DATA
# ======================================================================
CITY_NAMES = [
    "تهران", "کرج", "مشهد", "اصفهان", "شیراز", "تبریز", "قم", "اهواز",
    "رشت", "کرمان", "ارومیه", "یزد", "کرمانشاه", "همدان", "بندرعباس",
    "قزوین", "اراک", "زنجان", "سنندج", "ساری", "گرگان", "اردبیل",
    "بوشهر", "خرم‌آباد", "آبادان",
]

# Each entry: (main_emoji, main_name, [(sub_emoji, sub_name), ...])
CATEGORY_TREE = [
    ("👗", "مد و پوشاک", [
        ("👩", "زنانه"), ("👨", "مردانه"), ("🧒", "بچگانه"), ("👟", "کفش"),
        ("👜", "کیف"), ("🩲", "لباس زیر"), ("👚", "لباس خانگی"),
        ("🏃", "لباس ورزشی"), ("✨", "لباس مجلسی"), ("☀️", "لباس تابستانی"),
        ("🧥", "لباس زمستانی"), ("🧣", "شال و روسری"), ("💍", "اکسسوری و زیورآلات"),
    ]),
    ("💄", "زیبایی و آرایشی", [
        ("💄", "آرایشی"), ("🧴", "مراقبت پوست"), ("💇", "مراقبت مو"),
        ("🌸", "عطر و ادکلن"), ("🧼", "محصولات بهداشتی"), ("💅", "ناخن"),
        ("🪞", "ابزار زیبایی"),
    ]),
    ("💇", "سالن و خدمات زیبایی", [
        ("💇", "آرایشگاه"), ("💅", "ناخن"), ("👁️", "مژه و ابرو"),
        ("💇‍♀️", "مو"), ("💄", "میکاپ"), ("💆", "ماساژ"), ("🧖", "اسپا"),
        ("✨", "خدمات زیبایی تخصصی"),
    ]),
    ("💎", "طلا و جواهر", [
        ("🥇", "طلا"), ("🥈", "نقره"), ("💎", "جواهر"), ("📿", "بدلیجات"),
        ("⌚", "ساعت"), ("💠", "سنگ‌های قیمتی"),
    ]),
    ("📱", "موبایل و دیجیتال", [
        ("📱", "موبایل"), ("🔌", "لوازم جانبی"), ("💻", "لپ‌تاپ"),
        ("🖥️", "کامپیوتر"), ("🎮", "کنسول و بازی"), ("🎧", "صوتی و تصویری"),
        ("📷", "دوربین"), ("⌚", "لوازم هوشمند"),
    ]),
    ("🏠", "خانه و آشپزخانه", [
        ("🪴", "دکوراسیون"), ("🍳", "آشپزخانه"), ("⚡", "لوازم برقی"),
        ("🛏️", "کالای خواب"), ("🛋️", "مبلمان"), ("🌱", "گل و گیاه"),
        ("🏠", "لوازم خانه"), ("🧹", "نظافت و شست‌وشو"),
    ]),
    ("🧸", "کودک و نوزاد", [
        ("👕", "لباس کودک"), ("🧸", "اسباب‌بازی"), ("🍼", "لوازم نوزاد"),
        ("🛒", "کالسکه و صندلی"), ("🧼", "مراقبت کودک"), ("🎀", "سیسمونی"),
    ]),
    ("🥗", "خوراکی و نوشیدنی", [
        ("☕", "قهوه"), ("🍵", "چای"), ("🍫", "شکلات"), ("🍰", "شیرینی"),
        ("🎂", "کیک"), ("🥜", "خشکبار"), ("🌶️", "ادویه"), ("🥤", "نوشیدنی"),
        ("🥫", "محصولات خانگی"), ("🍱", "غذاهای آماده"),
    ]),
    ("🎨", "صنایع دستی و هنری", [
        ("🧶", "صنایع دستی"), ("🖌️", "نقاشی"), ("🧵", "بافتنی"),
        ("🖼️", "محصولات هنری"), ("🏺", "سفال و سرامیک"), ("🪵", "چوب و رزین"),
        ("📿", "زیورآلات دست‌ساز"),
    ]),
    ("🎁", "هدیه", [
        ("🎉", "هدایای مناسبتی"), ("🎂", "هدیه تولد"), ("❤️", "هدیه عاشقانه"),
        ("🏢", "هدیه سازمانی"), ("🎁", "باکس هدیه"), ("🧶", "هدایای دست‌ساز"),
    ]),
    ("🌱", "گل و گیاه", [
        ("🌹", "گل طبیعی"), ("🌸", "گل مصنوعی"), ("🪴", "گیاه آپارتمانی"),
        ("🏺", "گلدان"), ("💐", "باکس گل"), ("🌿", "تراریوم"),
    ]),
    ("🏋️", "ورزش", [
        ("👕", "پوشاک ورزشی"), ("👟", "کفش ورزشی"), ("🏋️", "تجهیزات ورزشی"),
        ("💪", "بدنسازی"), ("🧘", "یوگا و فیتنس"), ("⚽", "ورزش‌های توپی"),
        ("🏕️", "کمپینگ"),
    ]),
    ("🚗", "خودرو و موتور", [
        ("🚗", "لوازم خودرو"), ("🏍️", "لوازم موتور"), ("⚙️", "قطعات"),
        ("🔧", "لوازم جانبی"), ("🛠️", "خدمات خودرو"), ("🏍️", "خدمات موتور"),
        ("🛞", "تایر و رینگ"),
    ]),
    ("📚", "کتاب و آموزش", [
        ("📖", "کتاب"), ("🎓", "دوره آموزشی"), ("✏️", "لوازم تحریر"),
        ("🌐", "آموزش زبان"), ("🧠", "آموزش مهارت"), ("🎸", "آموزش موسیقی"),
        ("📚", "آموزش کنکور و مدرسه"),
    ]),
    ("🛠️", "خدمات", [
        ("🔧", "خدمات فنی"), ("💻", "خدمات آنلاین"), ("🎓", "خدمات آموزشی"),
        ("💬", "مشاوره"), ("📷", "عکاسی"), ("🎬", "تولید محتوا"),
        ("📱", "مدیریت شبکه‌های اجتماعی"), ("📢", "تبلیغات"),
        ("🏠", "خدمات منزل"), ("🛠️", "تعمیرات"), ("🎉", "برگزاری مراسم"),
        ("🚚", "حمل‌ونقل"), ("🧰", "سایر خدمات"),
    ]),
    ("🐾", "حیوانات خانگی", [
        ("🥩", "غذا"), ("🐾", "لوازم حیوانات"), ("🐕", "پوشاک حیوانات"),
        ("🧼", "بهداشت حیوانات"), ("🩺", "خدمات حیوانات"), ("🏠", "لوازم نگهداری"),
    ]),
    ("📦", "محصولات وارداتی", [
        ("👗", "پوشاک وارداتی"), ("💄", "آرایشی وارداتی"), ("🍫", "خوراکی وارداتی"),
        ("📱", "دیجیتال وارداتی"), ("🏠", "لوازم خانه وارداتی"),
        ("📦", "سایر محصولات وارداتی"),
    ]),
    ("🏡", "املاک", [
        ("🏠", "فروش مسکونی"), ("🔑", "اجاره مسکونی"), ("🏢", "فروش تجاری"),
        ("🏬", "اجاره تجاری"), ("🌳", "زمین"), ("🏡", "ویلا"),
        ("🏢", "دفتر کار"), ("📦", "سایر املاک"),
    ]),
]


async def seed_cities() -> None:
    row = await db.fetchone("SELECT COUNT(*) AS c FROM cities;")
    if row["c"] > 0:
        return
    now = now_iso()
    for name in CITY_NAMES:
        await db.conn.execute(
            "INSERT OR IGNORE INTO cities (name) VALUES (?);", (name,)
        )
    await db.conn.commit()
    logger.info("Seeded %d cities.", len(CITY_NAMES))


async def seed_categories() -> None:
    row = await db.fetchone("SELECT COUNT(*) AS c FROM categories;")
    if row["c"] > 0:
        return
    for main_emoji, main_name, subs in CATEGORY_TREE:
        cur = await db.conn.execute(
            "INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, NULL);",
            (main_name, main_emoji),
        )
        parent_id = cur.lastrowid
        for sub_emoji, sub_name in subs:
            await db.conn.execute(
                "INSERT INTO categories (name, emoji, parent_id) VALUES (?, ?, ?);",
                (sub_name, sub_emoji, parent_id),
            )
    await db.conn.commit()
    logger.info("Seeded categories tree (%d main categories).", len(CATEGORY_TREE))


DEMO_SELLER_NAME = "DEMO - فروشگاه نمونه"
DEMO_PRODUCT_NAME = "DEMO - محصول نمونه"


async def seed_demo_data() -> None:
    """Optional, OFF by default (SEED_DEMO_DATA=true to enable).

    All demo rows are unmistakably prefixed with 'DEMO -' / '[DEMO]' so they
    can never be confused with real seller/product data, and this function
    is idempotent: it checks for the demo seller by name before inserting.
    """
    if not SEED_DEMO_DATA:
        return

    existing = await db.fetchone(
        "SELECT id FROM sellers WHERE name = ?;", (DEMO_SELLER_NAME,)
    )
    if existing:
        return

    city = await db.fetchone("SELECT id FROM cities WHERE name = 'تهران';")
    category = await db.fetchone(
        "SELECT id FROM categories WHERE parent_id IS NOT NULL ORDER BY id LIMIT 1;"
    )
    now = now_iso()

    cur = await db.conn.execute(
        """INSERT INTO sellers (name, description, city_id, status, rating,
               review_count, views, created_at, updated_at)
           VALUES (?, ?, ?, 'UNCLAIMED', 0, 0, 0, ?, ?);""",
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
        """INSERT INTO products (seller_id, category_id, name, description, price,
               stock_status, rating, review_count, views, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'AVAILABLE', 0, 0, 0, ?, ?);""",
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
    logger.info("Seeded DEMO data (clearly labeled, SEED_DEMO_DATA=true).")


# ======================================================================
# 7. EMOJI / CATEGORY DEFINITIONS (constants used across the file)
# ======================================================================
EMOJI_MAIN_MENU = "🛍️"
EMOJI_SEARCH = "🔎"
EMOJI_SELLERS = "🏪"
EMOJI_CATEGORIES = "📂"
EMOJI_HOT = "🔥"
EMOJI_NEW_TODAY = "🆕"
EMOJI_PICKS = "✨"
EMOJI_NEAR_ME = "📍"
EMOJI_TOP_SELLERS = "⭐"
EMOJI_FAVORITES = "❤️"
EMOJI_GIFT_LIST = "🎁"
EMOJI_COMPARE = "⚖️"
EMOJI_NOTIFICATIONS = "🔔"
EMOJI_REGISTER_SELLER = "➕"
EMOJI_ADS = "📢"
EMOJI_ACCOUNT = "👤"
EMOJI_BACK = "🔙"
EMOJI_CLAIMED = "🟢"
EMOJI_UNCLAIMED = "⚪"
EMOJI_REPORT = "🚩"
EMOJI_PRODUCT = "🛍️"
EMOJI_PRICE = "💰"
EMOJI_CITY = "📍"
EMOJI_RATING = "⭐"
EMOJI_LINK = "🔗"
EMOJI_VIEW = "👁"
EMOJI_CLAIM = "👤"
EMOJI_STAR = "⭐"

REPORT_REASONS = {
    "scam": "🚨 کلاهبرداری",
    "wrong_info": "ℹ️ اطلاعات اشتباه",
    "inappropriate": "🚫 محتوای نامناسب",
    "illegal": "⚠️ فروش کالای غیرمجاز",
    "other": "📝 سایر",
}

# ======================================================================
# 8. UTILITY FUNCTIONS
# ======================================================================
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def format_price(price: Optional[float]) -> str:
    if price is None:
        return "نامشخص"
    try:
        return f"{price:,.0f} تومان"
    except (TypeError, ValueError):
        return "نامشخص"


def status_badge(status: str) -> str:
    if status == "CLAIMED":
        return f"{EMOJI_CLAIMED} تأییدشده"
    return f"{EMOJI_UNCLAIMED} معرفی‌شده"


def instagram_url(username: Optional[str]) -> Optional[str]:
    if not username:
        return None
    clean = username.strip().lstrip("@")
    return f"https://instagram.com/{clean}" if clean else None


def telegram_url(username: Optional[str]) -> Optional[str]:
    if not username:
        return None
    clean = username.strip().lstrip("@")
    return f"https://t.me/{clean}" if clean else None


def website_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    clean = url.strip()
    if not clean:
        return None
    if not clean.startswith("http://") and not clean.startswith("https://"):
        clean = "https://" + clean
    return clean


async def safe_edit(callback: CallbackQuery, text: str, kb: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            pass
        else:
            logger.warning("edit_text failed, sending new message instead: %s", exc)
            await callback.message.answer(text, reply_markup=kb)


async def ensure_user(tg_user) -> int:
    """Idempotent upsert of the Telegram user. Returns internal user id."""
    row = await db.fetchone(
        "SELECT id FROM users WHERE telegram_id = ?;", (tg_user.id,)
    )
    now = now_iso()
    if row:
        await db.execute(
            """UPDATE users SET username=?, first_name=?, last_name=?, updated_at=?
               WHERE telegram_id=?;""",
            (tg_user.username, tg_user.first_name, tg_user.last_name, now, tg_user.id),
        )
        return row["id"]
    cur = await db.execute(
        """INSERT INTO users (telegram_id, username, first_name, last_name, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?);""",
        (tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name, now, now),
    )
    return cur.lastrowid


# ======================================================================
# 9. ANALYTICS HELPERS
# ======================================================================
async def log_event(
    user_id: Optional[int],
    event_type: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
) -> None:
    try:
        await db.execute(
            """INSERT INTO events (user_id, event_type, entity_type, entity_id, created_at)
               VALUES (?, ?, ?, ?, ?);""",
            (user_id, event_type, entity_type, entity_id, now_iso()),
        )
    except Exception as exc:  # noqa: BLE001 - analytics must never break the flow
        logger.error("Failed to log event '%s': %s", event_type, exc)


async def notify_user(user_id: int, title: str, message: str, ntype: str = "info") -> None:
    try:
        await db.execute(
            """INSERT INTO notifications (user_id, title, message, notification_type, is_read, created_at)
               VALUES (?, ?, ?, ?, 0, ?);""",
            (user_id, title, message, ntype, now_iso()),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create notification: %s", exc)


# ======================================================================
# 10. KEYBOARDS
# ======================================================================
def kb_add_back(builder: InlineKeyboardBuilder, callback_data: str, text: str = f"{EMOJI_BACK} بازگشت") -> None:
    builder.row(InlineKeyboardButton(text=text, callback_data=callback_data))


def kb_pagination_row(builder: InlineKeyboardBuilder, base_callback: str, page: int, has_next: bool) -> None:
    row = []
    if page > 0:
        row.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"{base_callback}:{page-1}"))
    if has_next:
        row.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"{base_callback}:{page+1}"))
    if row:
        builder.row(*row)


# ======================================================================
# 11. MAIN MENU
# ======================================================================
def main_menu_text() -> str:
    return (
        f"{EMOJI_MAIN_MENU} <b>به ارزانکده خوش اومدی!</b>\n\n"
        "یک محل ساده برای پیدا کردن فروشگاه‌ها، محصولات و خدمات ایرانی.\n\n"
        "یکی از گزینه‌های زیر رو انتخاب کن 👇"
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{EMOJI_SEARCH} جستجوی محصول", callback_data="search")
    b.button(text=f"{EMOJI_SELLERS} فروشگاه‌ها", callback_data="sellers:0")
    b.button(text=f"{EMOJI_CATEGORIES} دسته‌بندی‌ها", callback_data="cat:0:0")
    b.button(text=f"{EMOJI_HOT} داغ‌ترین‌ها", callback_data="hot")
    b.button(text=f"{EMOJI_NEW_TODAY} جدیدهای امروز", callback_data="newtoday")
    b.button(text=f"{EMOJI_PICKS} انتخاب ارزانکده", callback_data="picks")
    b.button(text=f"{EMOJI_NEAR_ME} نزدیک من", callback_data="nearme")
    b.button(text=f"{EMOJI_TOP_SELLERS} فروشندگان برتر", callback_data="topsellers")
    b.button(text=f"{EMOJI_FAVORITES} علاقه‌مندی‌ها", callback_data="favorites:0")
    b.button(text=f"{EMOJI_GIFT_LIST} فهرست هدیه", callback_data="giftlist")
    b.button(text=f"{EMOJI_COMPARE} مقایسه", callback_data="compare")
    b.button(text=f"{EMOJI_NOTIFICATIONS} اعلان‌ها", callback_data="notifications")
    b.button(text=f"{EMOJI_REGISTER_SELLER} ثبت فروشگاه من", callback_data="registerseller")
    b.button(text=f"{EMOJI_ADS} تبلیغات", callback_data="ads")
    b.button(text=f"{EMOJI_ACCOUNT} حساب کاربری", callback_data="account")
    b.adjust(2)
    return b.as_markup()


async def send_main_menu(target) -> None:
    if isinstance(target, CallbackQuery):
        await safe_edit(target, main_menu_text(), main_menu_keyboard())
    else:
        await target.answer(main_menu_text(), reply_markup=main_menu_keyboard())


async def restart_requested(message: Message, state: FSMContext) -> bool:
    """Guard used at the top of every FSM text-input handler.

    If the user sends /start while in the middle of a multi-step flow
    (search, review, report, seller registration, ...), cancel the flow
    and show the main menu instead of consuming "/start" as flow input.
    This prevents a state-specific handler from ever trapping the user.
    Returns True if it handled the message (caller must return immediately).
    """
    if (message.text or "").strip() == "/start":
        await state.clear()
        await ensure_user(message.from_user)
        await send_main_menu(message)
        return True
    return False


# ======================================================================
# FSM STATES
# ======================================================================
class SearchStates(StatesGroup):
    waiting_query = State()


class RegisterSellerStates(StatesGroup):
    name = State()
    description = State()
    city = State()
    instagram = State()
    telegram = State()
    website = State()


class ReviewStates(StatesGroup):
    waiting_rating = State()
    waiting_text = State()


class ReportStates(StatesGroup):
    waiting_description = State()


# ======================================================================
# ROUTER
# ======================================================================
router = Router()

# ======================================================================
# 12. CATEGORY SYSTEM
# ======================================================================
@router.callback_query(F.data.startswith("cat:"))
async def handle_category(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":")
    cat_id = parse_int(parts[1]) if len(parts) > 1 else None
    page = parse_int(parts[2]) if len(parts) > 2 else 0
    if cat_id is None or page is None:
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return

    user_id = await ensure_user(callback.from_user)

    if cat_id == 0:
        # Root categories list
        rows = await db.fetchall(
            "SELECT id, name, emoji FROM categories WHERE parent_id IS NULL ORDER BY id;"
        )
        offset = page * PAGE_SIZE_CATEGORIES
        page_rows = rows[offset: offset + PAGE_SIZE_CATEGORIES]
        has_next = offset + PAGE_SIZE_CATEGORIES < len(rows)

        b = InlineKeyboardBuilder()
        for r in page_rows:
            b.row(InlineKeyboardButton(
                text=f"{r['emoji']} {r['name']}", callback_data=f"cat:{r['id']}:0"
            ))
        kb_pagination_row(b, "cat:0", page, has_next)
        kb_add_back(b, "main")
        await safe_edit(callback, f"{EMOJI_CATEGORIES} <b>دسته‌بندی‌ها</b>\n\nیک دسته را انتخاب کن:", b.as_markup())
        await callback.answer()
        return

    category = await db.fetchone("SELECT * FROM categories WHERE id = ?;", (cat_id,))
    if not category:
        await callback.answer("⚠️ این دسته‌بندی یافت نشد.", show_alert=True)
        return

    await log_event(user_id, "category_click", "category", cat_id)

    children = await db.fetchall(
        "SELECT id, name, emoji FROM categories WHERE parent_id = ? ORDER BY id;", (cat_id,)
    )

    back_target = f"cat:{category['parent_id']}:0" if category["parent_id"] else "cat:0:0"

    if children:
        offset = page * PAGE_SIZE_CATEGORIES
        page_rows = children[offset: offset + PAGE_SIZE_CATEGORIES]
        has_next = offset + PAGE_SIZE_CATEGORIES < len(children)

        b = InlineKeyboardBuilder()
        for r in page_rows:
            b.row(InlineKeyboardButton(
                text=f"{r['emoji']} {r['name']}", callback_data=f"cat:{r['id']}:0"
            ))
        kb_pagination_row(b, f"cat:{cat_id}", page, has_next)
        kb_add_back(b, back_target)
        text = f"{category['emoji']} <b>{category['name']}</b>\n\nیک زیردسته را انتخاب کن:"
        await safe_edit(callback, text, b.as_markup())
        await callback.answer()
        return

    # Leaf category -> show products
    products = await db.fetchall(
        """SELECT p.*, s.name AS seller_name FROM products p
           JOIN sellers s ON s.id = p.seller_id
           WHERE p.category_id = ? ORDER BY p.views DESC, p.id DESC;""",
        (cat_id,),
    )

    if not products:
        b = InlineKeyboardBuilder()
        kb_add_back(b, back_target)
        text = (
            f"{category['emoji']} <b>{category['name']}</b>\n\n"
            f"📦 فعلاً محصولی در این دسته ثبت نشده."
        )
        await safe_edit(callback, text, b.as_markup())
        await callback.answer()
        return

    offset = page * PAGE_SIZE_LIST
    page_rows = products[offset: offset + PAGE_SIZE_LIST]
    has_next = offset + PAGE_SIZE_LIST < len(products)

    b = InlineKeyboardBuilder()
    for p in page_rows:
        b.row(InlineKeyboardButton(
            text=f"{EMOJI_PRODUCT} {p['name']} - {format_price(p['price'])}",
            callback_data=f"product:{p['id']}",
        ))
    kb_pagination_row(b, f"cat:{cat_id}", page, has_next)
    kb_add_back(b, back_target)
    text = f"{category['emoji']} <b>{category['name']}</b>\n\nمحصولات این دسته:"
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


# ======================================================================
# 13. SEARCH
# ======================================================================
@router.callback_query(F.data == "search")
async def handle_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    await ensure_user(callback.from_user)
    await state.set_state(SearchStates.waiting_query)
    b = InlineKeyboardBuilder()
    kb_add_back(b, "main")
    await safe_edit(callback, f"{EMOJI_SEARCH} دنبال چه چیزی می‌گردی؟\n\nمتن جستجو را بفرست:", b.as_markup())
    await callback.answer()


@router.message(StateFilter(SearchStates.waiting_query))
async def handle_search_query(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    user_id = await ensure_user(message.from_user)
    query = (message.text or "").strip()
    await state.clear()

    if not query:
        await message.answer("⚠️ لطفاً یک متن معتبر برای جستجو بفرست.")
        return

    like = f"%{query}%"
    products = await db.fetchall(
        """SELECT DISTINCT p.* FROM products p
           JOIN sellers s ON s.id = p.seller_id
           LEFT JOIN categories c ON c.id = p.category_id
           WHERE p.name LIKE ? OR p.description LIKE ?
              OR s.name LIKE ? OR s.description LIKE ?
              OR c.name LIKE ?
           ORDER BY p.views DESC LIMIT 20;""",
        (like, like, like, like, like),
    )

    await log_event(user_id, "search", "query", None)

    if not products:
        b = InlineKeyboardBuilder()
        kb_add_back(b, "main")
        await message.answer(f"🔎 نتیجه‌ای برای «{query}» پیدا نشد.", reply_markup=b.as_markup())
        return

    b = InlineKeyboardBuilder()
    for p in products[:PAGE_SIZE_LIST]:
        b.row(InlineKeyboardButton(
            text=f"{EMOJI_PRODUCT} {p['name']} - {format_price(p['price'])}",
            callback_data=f"product:{p['id']}",
        ))
    kb_add_back(b, "main")
    await message.answer(f"🔎 نتایج جستجو برای «{query}»:", reply_markup=b.as_markup())


# ======================================================================
# 14. SELLERS
# ======================================================================
@router.callback_query(F.data.startswith("sellers:"))
async def handle_sellers_list(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    page = parse_int(callback.data.split(":")[1]) or 0
    await ensure_user(callback.from_user)

    sellers = await db.fetchall(
        "SELECT * FROM sellers ORDER BY rating DESC, views DESC, id DESC;"
    )

    if not sellers:
        b = InlineKeyboardBuilder()
        kb_add_back(b, "main")
        await safe_edit(callback, f"{EMOJI_SELLERS} فعلاً فروشگاهی ثبت نشده است.", b.as_markup())
        await callback.answer()
        return

    offset = page * PAGE_SIZE_LIST
    page_rows = sellers[offset: offset + PAGE_SIZE_LIST]
    has_next = offset + PAGE_SIZE_LIST < len(sellers)

    b = InlineKeyboardBuilder()
    for s in page_rows:
        badge = "🟢" if s["status"] == "CLAIMED" else "⚪"
        b.row(InlineKeyboardButton(text=f"{EMOJI_SELLERS} {badge} {s['name']}", callback_data=f"seller:{s['id']}"))
    kb_pagination_row(b, "sellers", page, has_next)
    kb_add_back(b, "main")
    await safe_edit(callback, f"{EMOJI_SELLERS} <b>فروشگاه‌ها</b>", b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("seller:"))
async def handle_seller_detail(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    seller_id = parse_int(callback.data.split(":")[1])
    if seller_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return

    user_id = await ensure_user(callback.from_user)
    seller = await db.fetchone(
        """SELECT s.*, c.name AS city_name FROM sellers s
           LEFT JOIN cities c ON c.id = s.city_id WHERE s.id = ?;""",
        (seller_id,),
    )
    if not seller:
        await callback.answer("⚠️ این فروشگاه یافت نشد.", show_alert=True)
        return

    await db.execute("UPDATE sellers SET views = views + 1 WHERE id = ?;", (seller_id,))
    await log_event(user_id, "view_seller", "seller", seller_id)

    lines = [
        f"{EMOJI_SELLERS} <b>{seller['name']}</b>",
        "",
        seller["description"] or "بدون توضیحات",
        "",
        f"{EMOJI_CITY} {seller['city_name'] or 'نامشخص'}",
        f"{EMOJI_RATING} {seller['rating']:.1f} ({seller['review_count']} نظر)",
        status_badge(seller["status"]),
    ]
    if seller["status"] == "UNCLAIMED":
        lines.append("\nاین صفحه هنوز توسط صاحب کسب‌وکار تأیید نشده است.")

    b = InlineKeyboardBuilder()
    ig = instagram_url(seller["instagram"])
    tg = telegram_url(seller["telegram"])
    site = website_url(seller["website"])
    if ig:
        b.row(InlineKeyboardButton(text="📸 اینستاگرام", url=ig))
    if tg:
        b.row(InlineKeyboardButton(text="✈️ تلگرام", url=tg))
    if site:
        b.row(InlineKeyboardButton(text=f"{EMOJI_LINK} وبسایت", url=site))

    if seller["status"] == "UNCLAIMED":
        b.row(InlineKeyboardButton(text=f"{EMOJI_CLAIM} درخواست مالکیت فروشگاه", callback_data=f"claim:{seller_id}"))
    b.row(InlineKeyboardButton(text="⭐ ثبت نظر", callback_data=f"reviewstart:seller:{seller_id}"))
    b.row(InlineKeyboardButton(text=f"{EMOJI_REPORT} گزارش", callback_data=f"report:seller:{seller_id}"))
    kb_add_back(b, "sellers:0")

    await safe_edit(callback, "\n".join(lines), b.as_markup())
    await callback.answer()


# ======================================================================
# SELLER CLAIMS
# ======================================================================
@router.callback_query(F.data.startswith("claim:"))
async def handle_claim(callback: CallbackQuery) -> None:
    seller_id = parse_int(callback.data.split(":")[1])
    if seller_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    user_id = await ensure_user(callback.from_user)

    seller = await db.fetchone("SELECT id FROM sellers WHERE id = ?;", (seller_id,))
    if not seller:
        await callback.answer("⚠️ این فروشگاه یافت نشد.", show_alert=True)
        return

    existing = await db.fetchone(
        "SELECT id FROM seller_claims WHERE seller_id=? AND user_id=? AND status='PENDING';",
        (seller_id, user_id),
    )
    if existing:
        await callback.answer("شما قبلاً برای این فروشگاه درخواست داده‌اید.", show_alert=True)
        return

    now = now_iso()
    await db.execute(
        """INSERT INTO seller_claims (seller_id, user_id, status, created_at, updated_at)
           VALUES (?, ?, 'PENDING', ?, ?);""",
        (seller_id, user_id, now, now),
    )
    await log_event(user_id, "claim_request", "seller", seller_id)
    await callback.answer("درخواست مالکیت شما ثبت شد و در انتظار بررسی است.", show_alert=True)


# ======================================================================
# 15. PRODUCTS
# ======================================================================
@router.callback_query(F.data.startswith("product:"))
async def handle_product_detail(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _render_product_detail(callback)


async def _render_product_detail(callback: CallbackQuery) -> None:
    product_id = parse_int(callback.data.split(":")[1])
    if product_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return

    user_id = await ensure_user(callback.from_user)
    product = await db.fetchone(
        """SELECT p.*, s.name AS seller_name, s.status AS seller_status,
                  c.name AS city_name
           FROM products p
           JOIN sellers s ON s.id = p.seller_id
           LEFT JOIN cities c ON c.id = s.city_id
           WHERE p.id = ?;""",
        (product_id,),
    )
    if not product:
        await callback.answer("⚠️ این محصول یافت نشد.", show_alert=True)
        return

    await db.execute("UPDATE products SET views = views + 1 WHERE id = ?;", (product_id,))
    await log_event(user_id, "view_product", "product", product_id)

    is_fav = await db.fetchone(
        "SELECT id FROM favorites WHERE user_id=? AND product_id=?;", (user_id, product_id)
    )

    lines = [
        f"{EMOJI_PRODUCT} <b>{product['name']}</b>",
        "",
        product["description"] or "بدون توضیحات",
        "",
        f"{EMOJI_PRICE} {format_price(product['price'])}",
        f"🏪 {product['seller_name']}",
        f"{EMOJI_CITY} {product['city_name'] or 'نامشخص'}",
        f"{EMOJI_RATING} {product['rating']:.1f} ({product['review_count']} نظر)",
        status_badge(product["seller_status"]),
    ]
    if product["stock_status"] == "OUT_OF_STOCK":
        lines.append("⛔️ ناموجود")

    b = InlineKeyboardBuilder()
    fav_text = "💔 حذف از علاقه‌مندی‌ها" if is_fav else "❤️ افزودن به علاقه‌مندی‌ها"
    fav_cb = f"unfavorite:{product_id}" if is_fav else f"favorite:{product_id}"
    b.row(InlineKeyboardButton(text=fav_text, callback_data=fav_cb))
    b.row(InlineKeyboardButton(text=f"{EMOJI_SELLERS} فروشگاه", callback_data=f"seller:{product['seller_id']}"))
    b.row(InlineKeyboardButton(text="⭐ ثبت نظر", callback_data=f"reviewstart:product:{product_id}"))
    b.row(InlineKeyboardButton(text=f"{EMOJI_REPORT} گزارش", callback_data=f"report:product:{product_id}"))
    back_cb = f"cat:{product['category_id']}:0" if product["category_id"] else "cat:0:0"
    kb_add_back(b, back_cb)

    await safe_edit(callback, "\n".join(lines), b.as_markup())
    await callback.answer()


# ======================================================================
# 16. FAVORITES
# ======================================================================
@router.callback_query(F.data.startswith("favorite:"))
async def handle_favorite_add(callback: CallbackQuery) -> None:
    product_id = parse_int(callback.data.split(":")[1])
    if product_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    user_id = await ensure_user(callback.from_user)

    product = await db.fetchone("SELECT id FROM products WHERE id = ?;", (product_id,))
    if not product:
        await callback.answer("⚠️ این محصول یافت نشد.", show_alert=True)
        return

    try:
        await db.execute(
            "INSERT INTO favorites (user_id, product_id, created_at) VALUES (?, ?, ?);",
            (user_id, product_id, now_iso()),
        )
        await log_event(user_id, "favorite", "product", product_id)
    except aiosqlite.IntegrityError:
        pass

    await callback.answer("به علاقه‌مندی‌ها اضافه شد ❤️")
    await _render_product_detail(callback)


@router.callback_query(F.data.startswith("unfavorite:"))
async def handle_favorite_remove(callback: CallbackQuery) -> None:
    product_id = parse_int(callback.data.split(":")[1])
    if product_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    user_id = await ensure_user(callback.from_user)
    await db.execute(
        "DELETE FROM favorites WHERE user_id=? AND product_id=?;", (user_id, product_id)
    )
    await callback.answer("از علاقه‌مندی‌ها حذف شد 💔")
    await _render_product_detail(callback)


@router.callback_query(F.data.startswith("favorites:"))
async def handle_favorites_list(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    page = parse_int(callback.data.split(":")[1]) or 0
    user_id = await ensure_user(callback.from_user)

    products = await db.fetchall(
        """SELECT p.* FROM favorites f
           JOIN products p ON p.id = f.product_id
           WHERE f.user_id = ? ORDER BY f.created_at DESC;""",
        (user_id,),
    )

    if not products:
        b = InlineKeyboardBuilder()
        kb_add_back(b, "main")
        await safe_edit(callback, f"{EMOJI_FAVORITES} هنوز محصولی به علاقه‌مندی‌ها اضافه نکردی.", b.as_markup())
        await callback.answer()
        return

    offset = page * PAGE_SIZE_LIST
    page_rows = products[offset: offset + PAGE_SIZE_LIST]
    has_next = offset + PAGE_SIZE_LIST < len(products)

    b = InlineKeyboardBuilder()
    for p in page_rows:
        b.row(InlineKeyboardButton(text=f"{EMOJI_PRODUCT} {p['name']}", callback_data=f"product:{p['id']}"))
    kb_pagination_row(b, "favorites", page, has_next)
    kb_add_back(b, "main")
    await safe_edit(callback, f"{EMOJI_FAVORITES} <b>علاقه‌مندی‌ها</b>", b.as_markup())
    await callback.answer()


# ======================================================================
# 17. REVIEWS
# ======================================================================
@router.callback_query(F.data.startswith("reviewstart:"))
async def handle_review_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, target_type, target_id_str = callback.data.split(":")
    target_id = parse_int(target_id_str)
    if target_id is None or target_type not in ("seller", "product"):
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return

    await state.update_data(review_target_type=target_type, review_target_id=target_id)
    await state.set_state(ReviewStates.waiting_rating)

    b = InlineKeyboardBuilder()
    for n in range(1, 6):
        b.row(InlineKeyboardButton(text="⭐" * n, callback_data=f"reviewrate:{n}"))
    kb_add_back(b, f"{target_type}:{target_id}")
    await safe_edit(callback, "امتیاز خودت رو انتخاب کن:", b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("reviewrate:"), StateFilter(ReviewStates.waiting_rating))
async def handle_review_rate(callback: CallbackQuery, state: FSMContext) -> None:
    rating = parse_int(callback.data.split(":")[1])
    if rating is None or not (1 <= rating <= 5):
        await callback.answer("⚠️ امتیاز نامعتبر است.", show_alert=True)
        return

    await state.update_data(review_rating=rating)
    await state.set_state(ReviewStates.waiting_text)
    await safe_edit(callback, "متن نظرت رو بنویس و بفرست:", InlineKeyboardBuilder().as_markup())
    await callback.answer()


@router.message(StateFilter(ReviewStates.waiting_text))
async def handle_review_text(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    user_id = await ensure_user(message.from_user)
    data = await state.get_data()
    target_type = data.get("review_target_type")
    target_id = data.get("review_target_id")
    rating = data.get("review_rating")
    await state.clear()

    if not target_type or not target_id or not rating:
        await message.answer("⚠️ فرآیند ثبت نظر منقضی شده. لطفاً دوباره تلاش کن.")
        return

    seller_id = target_id if target_type == "seller" else None
    product_id = target_id if target_type == "product" else None

    dup_query = "SELECT id FROM reviews WHERE user_id=? AND "
    dup_query += "seller_id=?" if target_type == "seller" else "product_id=?"
    existing = await db.fetchone(dup_query + ";", (user_id, target_id))
    if existing:
        await message.answer("شما قبلاً برای این مورد نظر ثبت کرده‌اید.")
        return

    await db.execute(
        """INSERT INTO reviews (user_id, seller_id, product_id, rating, text, created_at)
           VALUES (?, ?, ?, ?, ?, ?);""",
        (user_id, seller_id, product_id, rating, (message.text or "").strip(), now_iso()),
    )

    if target_type == "seller":
        await db.execute(
            """UPDATE sellers SET rating = (SELECT AVG(rating) FROM reviews WHERE seller_id=?),
               review_count = (SELECT COUNT(*) FROM reviews WHERE seller_id=?) WHERE id=?;""",
            (target_id, target_id, target_id),
        )
    else:
        await db.execute(
            """UPDATE products SET rating = (SELECT AVG(rating) FROM reviews WHERE product_id=?),
               review_count = (SELECT COUNT(*) FROM reviews WHERE product_id=?) WHERE id=?;""",
            (target_id, target_id, target_id),
        )

    await log_event(user_id, "review", target_type, target_id)
    await message.answer("✅ ممنون! نظر شما با موفقیت ثبت شد.")


# ======================================================================
# 18. CLAIMS (helper handlers already above under section "SELLER CLAIMS")
# ======================================================================

# ======================================================================
# 19. REPORTS
# ======================================================================
@router.callback_query(F.data.startswith("report:"))
async def handle_report_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    _, target_type, target_id_str = callback.data.split(":")
    target_id = parse_int(target_id_str)
    if target_id is None or target_type not in ("seller", "product"):
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return

    b = InlineKeyboardBuilder()
    for code, label in REPORT_REASONS.items():
        b.row(InlineKeyboardButton(text=label, callback_data=f"reportreason:{target_type}:{target_id}:{code}"))
    kb_add_back(b, f"{target_type}:{target_id}")
    await safe_edit(callback, "دلیل گزارش رو انتخاب کن:", b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("reportreason:"))
async def handle_report_reason(callback: CallbackQuery, state: FSMContext) -> None:
    _, target_type, target_id_str, reason_code = callback.data.split(":")
    target_id = parse_int(target_id_str)
    if target_id is None or reason_code not in REPORT_REASONS:
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return

    await state.update_data(
        report_target_type=target_type, report_target_id=target_id, report_reason=reason_code
    )
    await state.set_state(ReportStates.waiting_description)

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="رد کردن توضیحات", callback_data="reportskip"))
    await safe_edit(callback, "اگر توضیح بیشتری داری بنویس، یا رد کن:", b.as_markup())
    await callback.answer()


async def _save_report(user_id: int, data: dict, description: Optional[str]) -> None:
    target_type = data.get("report_target_type")
    target_id = data.get("report_target_id")
    reason_code = data.get("report_reason")
    seller_id = target_id if target_type == "seller" else None
    product_id = target_id if target_type == "product" else None

    await db.execute(
        """INSERT INTO reports (user_id, seller_id, product_id, reason, description, status, created_at)
           VALUES (?, ?, ?, ?, ?, 'PENDING', ?);""",
        (user_id, seller_id, product_id, reason_code, description, now_iso()),
    )
    await log_event(user_id, "report", target_type, target_id)


@router.callback_query(F.data == "reportskip", StateFilter(ReportStates.waiting_description))
async def handle_report_skip(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await ensure_user(callback.from_user)
    data = await state.get_data()
    await state.clear()
    await _save_report(user_id, data, None)
    b = InlineKeyboardBuilder()
    kb_add_back(b, "main")
    await safe_edit(
        callback,
        "گزارش شما ثبت شد. ممنون که به امن‌تر شدن ارزانکده کمک می‌کنی.",
        b.as_markup(),
    )
    await callback.answer()


@router.message(StateFilter(ReportStates.waiting_description))
async def handle_report_description(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    user_id = await ensure_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    await _save_report(user_id, data, (message.text or "").strip())
    await message.answer("گزارش شما ثبت شد. ممنون که به امن‌تر شدن ارزانکده کمک می‌کنی.")


# ======================================================================
# 20. NOTIFICATIONS
# ======================================================================
@router.callback_query(F.data == "notifications")
async def handle_notifications(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _render_notifications(callback)


async def _render_notifications(callback: CallbackQuery) -> None:
    user_id = await ensure_user(callback.from_user)
    rows = await db.fetchall(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 20;",
        (user_id,),
    )
    if not rows:
        b = InlineKeyboardBuilder()
        kb_add_back(b, "main")
        await safe_edit(callback, f"{EMOJI_NOTIFICATIONS} اعلان جدیدی نداری.", b.as_markup())
        await callback.answer()
        return

    b = InlineKeyboardBuilder()
    lines = [f"{EMOJI_NOTIFICATIONS} <b>اعلان‌ها</b>", ""]
    for n in rows:
        mark = "✅" if n["is_read"] else "🆕"
        lines.append(f"{mark} <b>{n['title']}</b>\n{n['message'] or ''}")
        if not n["is_read"]:
            b.row(InlineKeyboardButton(text=f"خواندم: {n['title'][:20]}", callback_data=f"notifread:{n['id']}"))
    kb_add_back(b, "main")
    await safe_edit(callback, "\n\n".join(lines), b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("notifread:"))
async def handle_notification_read(callback: CallbackQuery) -> None:
    notif_id = parse_int(callback.data.split(":")[1])
    if notif_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    await db.execute("UPDATE notifications SET is_read = 1 WHERE id = ?;", (notif_id,))
    await callback.answer("علامت خوانده شد ✅")
    await _render_notifications(callback)


# ======================================================================
# 21. ACCOUNT
# ======================================================================
@router.callback_query(F.data == "account")
async def handle_account(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await ensure_user(callback.from_user)
    user = await db.fetchone(
        """SELECT u.*, c.name AS city_name FROM users u
           LEFT JOIN cities c ON c.id = u.city_id WHERE u.id = ?;""",
        (user_id,),
    )
    name = " ".join(filter(None, [user["first_name"], user["last_name"]])) or "کاربر ارزانکده"
    text = f"{EMOJI_ACCOUNT} <b>حساب کاربری</b>\n\nنام: {name}\n"
    if user["username"]:
        text += f"نام کاربری: @{user['username']}\n"
    text += (
        f"شهر: {user['city_name'] or 'ثبت نشده'}\n"
        f"عضویت از: {user['created_at'][:10]}\n"
    )
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📍 تغییر شهر", callback_data="setcity"))
    kb_add_back(b, "main")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "setcity")
async def handle_set_city(callback: CallbackQuery) -> None:
    cities = await db.fetchall("SELECT id, name FROM cities ORDER BY name;")
    b = InlineKeyboardBuilder()
    for c in cities:
        b.button(text=c["name"], callback_data=f"pickcity:{c['id']}")
    b.adjust(3)
    kb_add_back(b, "account")
    await safe_edit(callback, f"{EMOJI_CITY} شهر خودت رو انتخاب کن:", b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("pickcity:"))
async def handle_pick_city(callback: CallbackQuery, state: FSMContext) -> None:
    city_id = parse_int(callback.data.split(":")[1])
    if city_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    city = await db.fetchone("SELECT id, name FROM cities WHERE id = ?;", (city_id,))
    if not city:
        await callback.answer("⚠️ این شهر یافت نشد.", show_alert=True)
        return

    current_state = await state.get_state()
    user_id = await ensure_user(callback.from_user)

    if current_state == RegisterSellerStates.city.state:
        await state.update_data(seller_city_id=city_id)
        await state.set_state(RegisterSellerStates.instagram)
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="رد کردن", callback_data="regskip:instagram"))
        await safe_edit(callback, "آیدی اینستاگرام فروشگاه (اختیاری):", b.as_markup())
        await callback.answer()
        return

    await db.execute(
        "UPDATE users SET city_id=?, updated_at=? WHERE id=?;", (city_id, now_iso(), user_id)
    )
    await callback.answer(f"شهر شما به {city['name']} تغییر کرد ✅")
    await handle_account(callback, state=state)


# ======================================================================
# NEAR ME
# ======================================================================
@router.callback_query(F.data == "nearme")
async def handle_near_me(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await ensure_user(callback.from_user)
    user = await db.fetchone("SELECT city_id FROM users WHERE id = ?;", (user_id,))

    if not user or not user["city_id"]:
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="📍 انتخاب شهر", callback_data="setcity"))
        kb_add_back(b, "main")
        await safe_edit(callback, "برای این بخش ابتدا باید شهر خودت رو انتخاب کنی.", b.as_markup())
        await callback.answer()
        return

    city = await db.fetchone("SELECT name FROM cities WHERE id = ?;", (user["city_id"],))
    sellers = await db.fetchall(
        "SELECT id, name, status FROM sellers WHERE city_id = ? ORDER BY rating DESC LIMIT 10;",
        (user["city_id"],),
    )

    b = InlineKeyboardBuilder()
    if not sellers:
        text = f"{EMOJI_NEAR_ME} شهر انتخاب‌شده: {city['name']}\n\nفعلاً فروشگاهی در این شهر ثبت نشده."
    else:
        text = f"{EMOJI_NEAR_ME} شهر انتخاب‌شده: {city['name']}\n\nفروشگاه‌های این شهر:"
        for s in sellers:
            badge = "🟢" if s["status"] == "CLAIMED" else "⚪"
            b.row(InlineKeyboardButton(text=f"{EMOJI_SELLERS} {badge} {s['name']}", callback_data=f"seller:{s['id']}"))
    kb_add_back(b, "main")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


# ======================================================================
# HOT / NEW TODAY / PICKS / TOP SELLERS / GIFT LIST / COMPARE
# ======================================================================
@router.callback_query(F.data == "hot")
async def handle_hot(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await ensure_user(callback.from_user)
    products = await db.fetchall(
        "SELECT * FROM products ORDER BY views DESC, rating DESC LIMIT ?;", (TOP_LIST_LIMIT,)
    )
    b = InlineKeyboardBuilder()
    if not products:
        text = f"{EMOJI_HOT} هنوز محصولی برای نمایش وجود ندارد."
    else:
        text = f"{EMOJI_HOT} <b>داغ‌ترین‌ها</b>"
        for p in products:
            b.row(InlineKeyboardButton(text=f"{EMOJI_PRODUCT} {p['name']}", callback_data=f"product:{p['id']}"))
    kb_add_back(b, "main")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "newtoday")
async def handle_new_today(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await ensure_user(callback.from_user)
    products = await db.fetchall(
        "SELECT * FROM products WHERE date(created_at) = date('now') ORDER BY created_at DESC LIMIT ?;",
        (TOP_LIST_LIMIT,),
    )
    b = InlineKeyboardBuilder()
    if not products:
        text = f"{EMOJI_NEW_TODAY} امروز محصول جدیدی ثبت نشده."
    else:
        text = f"{EMOJI_NEW_TODAY} <b>جدیدهای امروز</b>"
        for p in products:
            b.row(InlineKeyboardButton(text=f"{EMOJI_PRODUCT} {p['name']}", callback_data=f"product:{p['id']}"))
    kb_add_back(b, "main")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "picks")
async def handle_picks(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await ensure_user(callback.from_user)
    products = await db.fetchall(
        "SELECT * FROM products ORDER BY rating DESC, review_count DESC, views DESC LIMIT ?;",
        (TOP_LIST_LIMIT,),
    )
    b = InlineKeyboardBuilder()
    if not products:
        text = f"{EMOJI_PICKS} فعلاً پیشنهادی برای نمایش وجود ندارد."
    else:
        text = f"{EMOJI_PICKS} <b>انتخاب ارزانکده</b>"
        for p in products:
            b.row(InlineKeyboardButton(text=f"{EMOJI_PRODUCT} {p['name']}", callback_data=f"product:{p['id']}"))
    kb_add_back(b, "main")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "topsellers")
async def handle_top_sellers(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await ensure_user(callback.from_user)
    sellers = await db.fetchall(
        "SELECT * FROM sellers ORDER BY rating DESC, review_count DESC, views DESC LIMIT ?;",
        (TOP_LIST_LIMIT,),
    )
    b = InlineKeyboardBuilder()
    if not sellers:
        text = f"{EMOJI_TOP_SELLERS} فعلاً فروشنده‌ای برای نمایش وجود ندارد."
    else:
        text = f"{EMOJI_TOP_SELLERS} <b>فروشندگان برتر</b>"
        for s in sellers:
            b.row(InlineKeyboardButton(text=f"{EMOJI_SELLERS} {s['name']}", callback_data=f"seller:{s['id']}"))
    kb_add_back(b, "main")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "giftlist")
async def handle_gift_list(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await ensure_user(callback.from_user)
    gift_main = await db.fetchone("SELECT id FROM categories WHERE name='هدیه' AND parent_id IS NULL;")
    products = []
    if gift_main:
        cat_ids = [gift_main["id"]] + [
            r["id"] for r in await db.fetchall("SELECT id FROM categories WHERE parent_id=?;", (gift_main["id"],))
        ]
        placeholders = ",".join("?" for _ in cat_ids)
        products = await db.fetchall(
            f"SELECT * FROM products WHERE category_id IN ({placeholders}) ORDER BY rating DESC LIMIT ?;",
            (*cat_ids, TOP_LIST_LIMIT),
        )
    b = InlineKeyboardBuilder()
    if not products:
        text = f"{EMOJI_GIFT_LIST} هنوز محصولی برای فهرست هدیه نداریم."
    else:
        text = f"{EMOJI_GIFT_LIST} <b>فهرست هدیه</b>"
        for p in products:
            b.row(InlineKeyboardButton(text=f"{EMOJI_PRODUCT} {p['name']}", callback_data=f"product:{p['id']}"))
    kb_add_back(b, "main")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "compare")
async def handle_compare(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await ensure_user(callback.from_user)
    b = InlineKeyboardBuilder()
    kb_add_back(b, "main")
    await safe_edit(callback, f"{EMOJI_COMPARE} قابلیت مقایسه در نسخه بعدی فعال می‌شود.", b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "ads")
async def handle_ads(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await ensure_user(callback.from_user)
    text = (
        f"{EMOJI_ADS} <b>تبلیغات در ارزانکده</b>\n\n"
        "فروشگاه، محصول یا برند خودت را بیشتر دیده شو.\n\n"
        "در نسخه فعلی ثبت و پرداخت تبلیغات فعال نیست."
    )
    b = InlineKeyboardBuilder()
    kb_add_back(b, "main")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


# ======================================================================
# 22. ADVERTISING (see handle_ads above) / REGISTER SELLER
# ======================================================================
@router.callback_query(F.data == "registerseller")
async def handle_register_seller_start(callback: CallbackQuery, state: FSMContext) -> None:
    await ensure_user(callback.from_user)
    await state.set_state(RegisterSellerStates.name)
    b = InlineKeyboardBuilder()
    kb_add_back(b, "main")
    await safe_edit(callback, f"{EMOJI_REGISTER_SELLER} نام فروشگاه رو بفرست:", b.as_markup())
    await callback.answer()


@router.message(StateFilter(RegisterSellerStates.name))
async def handle_register_name(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("⚠️ لطفاً یک نام معتبر بفرست.")
        return
    await state.update_data(seller_name=name)
    await state.set_state(RegisterSellerStates.description)
    await message.answer("توضیحات فروشگاه رو بفرست:")


@router.message(StateFilter(RegisterSellerStates.description))
async def handle_register_description(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    description = (message.text or "").strip()
    if not description:
        await message.answer("⚠️ لطفاً توضیحات معتبر بفرست.")
        return
    await state.update_data(seller_description=description)
    await state.set_state(RegisterSellerStates.city)
    cities = await db.fetchall("SELECT id, name FROM cities ORDER BY name;")
    b = InlineKeyboardBuilder()
    for c in cities:
        b.button(text=c["name"], callback_data=f"pickcity:{c['id']}")
    b.adjust(3)
    await message.answer(f"{EMOJI_CITY} شهر فروشگاه رو انتخاب کن:", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("regskip:"))
async def handle_register_skip(callback: CallbackQuery, state: FSMContext) -> None:
    field = callback.data.split(":")[1]
    if field == "instagram":
        await state.set_state(RegisterSellerStates.telegram)
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="رد کردن", callback_data="regskip:telegram"))
        await safe_edit(callback, "آیدی تلگرام فروشگاه (اختیاری):", b.as_markup())
    elif field == "telegram":
        await state.set_state(RegisterSellerStates.website)
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="رد کردن", callback_data="regskip:website"))
        await safe_edit(callback, "وبسایت فروشگاه (اختیاری):", b.as_markup())
    elif field == "website":
        await _finish_register_seller(callback.from_user, state, callback=callback)
    await callback.answer()


@router.message(StateFilter(RegisterSellerStates.instagram))
async def handle_register_instagram(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    await state.update_data(seller_instagram=(message.text or "").strip())
    await state.set_state(RegisterSellerStates.telegram)
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="رد کردن", callback_data="regskip:telegram"))
    await message.answer("آیدی تلگرام فروشگاه (اختیاری):", reply_markup=b.as_markup())


@router.message(StateFilter(RegisterSellerStates.telegram))
async def handle_register_telegram(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    await state.update_data(seller_telegram=(message.text or "").strip())
    await state.set_state(RegisterSellerStates.website)
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="رد کردن", callback_data="regskip:website"))
    await message.answer("وبسایت فروشگاه (اختیاری):", reply_markup=b.as_markup())


@router.message(StateFilter(RegisterSellerStates.website))
async def handle_register_website(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    await state.update_data(seller_website=(message.text or "").strip())
    await _finish_register_seller(message.from_user, state, message=message)


async def _finish_register_seller(
    tg_user, state: FSMContext, callback: Optional[CallbackQuery] = None, message: Optional[Message] = None
) -> None:
    user_id = await ensure_user(tg_user)
    data = await state.get_data()
    await state.clear()

    name = data.get("seller_name")
    description = data.get("seller_description")
    city_id = data.get("seller_city_id")

    if not name or not description or not city_id:
        text = "⚠️ اطلاعات ثبت فروشگاه ناقص است. لطفاً دوباره از منوی اصلی تلاش کن."
        if callback:
            await safe_edit(callback, text, InlineKeyboardBuilder().as_markup())
        elif message:
            await message.answer(text)
        return

    now = now_iso()
    await db.execute(
        """INSERT INTO sellers (name, description, city_id, instagram, telegram, website,
               status, rating, review_count, views, created_by_user_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'UNCLAIMED', 0, 0, 0, ?, ?, ?);""",
        (
            name,
            description,
            city_id,
            data.get("seller_instagram") or None,
            data.get("seller_telegram") or None,
            data.get("seller_website") or None,
            user_id,
            now,
            now,
        ),
    )

    text = "✅ فروشگاه شما با موفقیت ثبت شد و در وضعیت «معرفی‌شده» قرار دارد."
    b = InlineKeyboardBuilder()
    kb_add_back(b, "main")
    if callback:
        await safe_edit(callback, text, b.as_markup())
    elif message:
        await message.answer(text, reply_markup=b.as_markup())


# ======================================================================
# 23. FALLBACK HANDLERS
# ======================================================================
@router.callback_query(F.data == "main")
async def handle_main_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await ensure_user(callback.from_user)
    await send_main_menu(callback)
    await callback.answer()


@router.callback_query()
async def handle_unknown_callback(callback: CallbackQuery) -> None:
    logger.warning("Unknown callback_data received: %s", callback.data)
    await callback.answer("⚠️ این گزینه هنوز فعال نیست.", show_alert=True)


# ======================================================================
# START COMMAND
# ======================================================================
# NOTE: This MUST be registered before the generic `@router.message()`
# fallback below. aiogram dispatches to the FIRST handler whose filters
# match, and a bare @router.message() with no filter matches everything
# (including "/start"). If the fallback were registered first, it would
# permanently swallow /start and handle_start() would never run.
@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await ensure_user(message.from_user)
    await send_main_menu(message)


@router.message()
async def handle_unknown_message(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is not None:
        # A stray message while inside an FSM flow that has no dedicated handler.
        return
    await ensure_user(message.from_user)
    await send_main_menu(message)


# ======================================================================
# 24. STARTUP
# ======================================================================
async def on_startup() -> None:
    logger.info("ArzanKadeh AI starting...")
    await db.connect()
    await init_schema()
    await seed_cities()
    await seed_categories()
    await seed_demo_data()
    logger.info("Database initialized successfully.")


async def on_shutdown() -> None:
    await db.close()


# ======================================================================
# 25. MAIN
# ======================================================================
async def main() -> None:
    if not BOT_TOKEN:
        logger.error(
            "BOT_TOKEN is missing. Please create a .env file with BOT_TOKEN=<your token> and try again."
        )
        return

    await on_startup()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    try:
        logger.info("Bot is running.")
        await dp.start_polling(bot)
    finally:
        await on_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
