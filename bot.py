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
import re
from dataclasses import dataclass
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

# Numeric Telegram chat id of the main admin (@awlism), used to actually
# deliver support/report/ad-request DMs. The Bot API cannot message an
# arbitrary @username directly (Telegram privacy rules only allow it once
# that user has started a chat with the bot) -- so delivery needs the
# real numeric id, read from .env, never hardcoded. If unset, requests
# are still recorded normally in the database; only the live DM to the
# admin is skipped (logged instead), so nothing ever crashes or silently
# loses a user's request.
_admin_chat_id_raw = os.getenv("ADMIN_CHAT_ID", "").strip()
try:
    ADMIN_CHAT_ID: Optional[int] = int(_admin_chat_id_raw) if _admin_chat_id_raw else None
except ValueError:
    ADMIN_CHAT_ID = None
ADMIN_USERNAME = "@awlism"  # public display only, not a secret

PAGE_SIZE_CATEGORIES = 10
PAGE_SIZE_LIST = 8
TOP_LIST_LIMIT = 10
SUPPORT_MESSAGE_MAX_LEN = 100

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
    # ------------------------------------------------------------------
    # Referral / seller growth system.
    # These two tables are additive-only (CREATE TABLE IF NOT EXISTS) and
    # do not touch any existing table, so applying this on a database that
    # already has data is safe (no ALTER TABLE, no data migration needed).
    #
    # `referrals` is the "Referral Event" from the architecture:
    #   Referral (seller.id used directly as the referral code)
    #     -> Referral Event  (one row per successfully-attributed new user)
    #     -> Reward Rules    (REFERRAL_REWARD_RULES constant, see below)
    #     -> Reward          (referral_rewards table, reserved for later)
    #
    # UNIQUE(referred_user_id) guarantees a given user can be attributed to
    # at most ONE seller, ONE time, ever -- this is what prevents double
    # counting / repeated referral credit for the same user.
    # ------------------------------------------------------------------
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
    # Reserved for future automated rewards (5/20/50/100 referral
    # milestones -> badge / boost / featured / special-seller). No code
    # path writes to this table yet; it only exists now so that adding
    # real rewards later never requires a schema migration.
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
    # ------------------------------------------------------------------
    # Buyer/Seller UX overhaul (roles, favorites-for-sellers, unified
    # requests inbox, audit log). All additive/new tables -- nothing here
    # touches an existing table's structure, so this is safe to apply on
    # top of an existing database with real data.
    #
    # `favorites` (existing table, untouched) already stores PRODUCT
    # favorites. Sellers get their OWN separate table on purpose (per
    # spec: "برای محصول و فروشگاه Favorite جداگانه در دیتابیس طراحی شود")
    # rather than overloading `favorites` with a nullable/polymorphic
    # entity_type column, which would have required an ALTER + backfill
    # of the existing table.
    # ------------------------------------------------------------------
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
    # Unified inbox for "📋 درخواست‌های من": support requests and
    # advertising requests (moderation reports stay in the existing
    # `reports` table -- it already has its own status field and admin
    # workflow; `list_my_requests()` merges both sources for display).
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
    # Simple, append-only audit trail for sensitive/important actions.
    # Never store tokens/secrets/passwords in `details`.
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
]

# ------------------------------------------------------------------------
# Lightweight, additive-only "migrations" for columns added to EXISTING
# tables after they may already have been created (and may already hold
# real data) on a running deployment. `CREATE TABLE IF NOT EXISTS` alone
# does NOT add new columns to a table that already exists, so any new
# column introduced after the initial release must go through here.
#
# This keeps SQLite usable today while staying friendly to a future
# migration to PostgreSQL: every entry is a plain, idempotent, additive
# ALTER TABLE ... ADD COLUMN with a safe default, never a destructive
# change, and never a rename/drop.
# ------------------------------------------------------------------------
COLUMN_MIGRATIONS = [
    # (table, column, "SQL type + default", used for...)
    ("users", "active_mode", "TEXT NOT NULL DEFAULT 'buyer'"),
    ("users", "has_seen_compare_intro", "INTEGER NOT NULL DEFAULT 0"),
    ("sellers", "logo_url", "TEXT"),
    ("sellers", "telegram_support", "TEXT"),
    ("sellers", "location_text", "TEXT"),
    ("sellers", "coverage_area", "TEXT"),
    ("sellers", "phone", "TEXT"),
    # WhatsApp is fully independent of phone/Instagram/Telegram -- its own
    # column, own URL builder, own click-tracking event (whatsapp_click).
    ("sellers", "whatsapp", "TEXT"),
    # Seller-controlled visibility toggle ("📊 وضعیت فروشگاه": فعال/غیرفعال).
    # Defaults to 1 (active) so every existing seller row stays visible
    # exactly as before this migration -- purely additive/safe.
    ("sellers", "is_active", "INTEGER NOT NULL DEFAULT 1"),
]


async def ensure_column(table: str, column: str, sql_type_and_default: str) -> None:
    """Add `column` to `table` if it doesn't already exist. Idempotent and
    safe to run on every startup, on a brand-new database or an existing
    one with real data."""
    cur = await db.conn.execute(f"PRAGMA table_info({table});")
    rows = await cur.fetchall()
    await cur.close()
    existing_columns = {row[1] for row in rows}  # row[1] = column name
    if column in existing_columns:
        return
    await db.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type_and_default};")
    logger.info("Migrated: added column %s.%s", table, column)


async def run_column_migrations() -> None:
    for table, column, sql_type_and_default in COLUMN_MIGRATIONS:
        await ensure_column(table, column, sql_type_and_default)
    await db.conn.commit()

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
]


async def init_schema() -> None:
    for stmt in SCHEMA_STATEMENTS:
        await db.conn.execute(stmt)
    for stmt in INDEX_STATEMENTS:
        await db.conn.execute(stmt)
    await db.conn.commit()
    await run_column_migrations()


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


def whatsapp_url(number: Optional[str]) -> Optional[str]:
    """Builds a wa.me deep link from a phone number. Completely
    independent of `phone`/`instagram`/`telegram` -- callers must pass
    the seller's OWN `whatsapp` column, never `phone`.

    Strips everything except digits (spaces, dashes, parentheses, a
    leading '+' or Iran's international-dial prefix '00'), so
    "+98 912 345 6789", "0098912-345-6789" and "989123456789" all
    resolve to the same wa.me link.
    """
    if not number:
        return None
    digits = re.sub(r"\D", "", number.strip())
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    if not digits:
        return None
    return f"https://wa.me/{digits}"


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


async def log_audit(
    actor_user_id: Optional[int],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    details: Optional[str] = None,
) -> None:
    """Append-only audit trail for sensitive/important actions (product
    create/edit/delete, report approve/reject, support/ad request
    resolution, ...). NEVER pass tokens, secrets, or full user messages
    containing sensitive data into `details` -- keep it to short,
    human-readable summaries. Like log_event, this must never break the
    caller's actual action if logging itself fails."""
    try:
        await db.execute(
            """INSERT INTO audit_log (actor_user_id, action, entity_type, entity_id, details, created_at)
               VALUES (?, ?, ?, ?, ?, ?);""",
            (actor_user_id, action, entity_type, entity_id, details, now_iso()),
        )
    except Exception as exc:  # noqa: BLE001 - audit logging must never break the flow
        logger.error("Failed to write audit log entry '%s': %s", action, exc)


async def send_admin_dm(bot: Bot, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> bool:
    """Best-effort DM to the main admin (@awlism). The Bot API cannot
    message an arbitrary @username directly, so this needs the real
    numeric ADMIN_CHAT_ID from .env. If it's not configured, or sending
    fails for any reason (admin blocked the bot, network hiccup, ...),
    this is logged and swallowed -- the caller's request is ALWAYS still
    saved in the database regardless, so nothing is ever lost, only the
    live notification is best-effort."""
    if not ADMIN_CHAT_ID:
        logger.warning("ADMIN_CHAT_ID is not configured; skipping admin DM: %.80s", text)
        return False
    try:
        await bot.send_message(ADMIN_CHAT_ID, text, reply_markup=reply_markup)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to DM admin: %s", exc)
        return False


# ======================================================================
# 9.5 REFERRAL / SELLER GROWTH SYSTEM
# ======================================================================
# Deep-link format used everywhere in this section:
#   https://t.me/<bot_username>?start=shop_<seller_id>
# aiogram delivers this to handle_start() as message.text == "/start shop_123".
#
# Reward milestones are declared here as a plain constant (NOT written to
# any table yet) so the thresholds/labels are visible to the user as soon
# as this system launches, without activating any real reward yet. When
# real automated rewards are built, they read this same list and write
# into the already-existing `referral_rewards` table -- no schema change,
# no rewrite of the counting logic below.
REFERRAL_REWARD_RULES = [
    (5, "⭐ امتیاز"),
    (20, "🔥 Boost رایگان"),
    (50, "⭐ Featured چندروزه"),
    (100, "🏆 فروشنده ویژه"),
]

REFERRAL_DEEP_LINK_RE = re.compile(r"^shop_(\d+)$")


def build_referral_link(bot_username: str, seller_id: int) -> str:
    return f"https://t.me/{bot_username}?start=shop_{seller_id}"


async def get_referral_count(seller_id: int) -> int:
    row = await db.fetchone(
        "SELECT COUNT(*) AS c FROM referrals WHERE seller_id = ?;", (seller_id,)
    )
    return row["c"] if row else 0


def next_referral_milestone(count: int):
    """Returns (threshold, reward_label) for the next milestone not yet
    reached, or None if every currently-defined milestone is reached."""
    for threshold, label in REFERRAL_REWARD_RULES:
        if count < threshold:
            return threshold, label
    return None


async def record_referral_if_new(seller_id: int, referred_user_id: int) -> bool:
    """Attribute `referred_user_id` to `seller_id`'s referral link.

    Returns True if a new referral was recorded, False if this user was
    already attributed to some seller before (UNIQUE(referred_user_id)
    enforces this at the database level too -- this is belt-and-suspenders
    so we never even attempt a doomed INSERT, and never raise to the
    caller either way).
    """
    try:
        existing = await db.fetchone(
            "SELECT id FROM referrals WHERE referred_user_id = ?;", (referred_user_id,)
        )
        if existing:
            return False
        await db.execute(
            """INSERT INTO referrals (seller_id, referred_user_id, source, created_at)
               VALUES (?, ?, 'deep_link', ?);""",
            (seller_id, referred_user_id, now_iso()),
        )
        return True
    except Exception as exc:  # noqa: BLE001 - a referral glitch must never break /start
        logger.error("Failed to record referral for seller %s: %s", seller_id, exc)
        return False


async def get_sellers_owned_by_user(user_id: int) -> list:
    return await db.fetchall(
        """SELECT id, name FROM sellers
           WHERE created_by_user_id = ? OR owner_user_id = ?
           ORDER BY id DESC;""",
        (user_id, user_id),
    )


async def referral_stats_text(bot_username: str, seller_id: int, seller_name: str) -> str:
    count = await get_referral_count(seller_id)
    link = build_referral_link(bot_username, seller_id)
    milestone = next_referral_milestone(count)
    lines = [
        f"🎁 لینک اختصاصی فروشگاه «{seller_name}»",
        "",
        "این لینک را در استوری اینستاگرام یا کانال تلگرامت منتشر کن تا افراد بیشتری فروشگاهت را پیدا کنند.",
        "",
        f"🔗 لینک اختصاصی فروشگاه:\n{link}",
        "",
        "📊 آمار معرفی:",
        f"👥 کاربران معرفی‌شده: {count}",
    ]
    if milestone:
        threshold, label = milestone
        lines.append(f"🏁 مرحله بعدی: {threshold} معرفی ← {label}")
    return "\n".join(lines)


# ======================================================================
# 9.5 ROLES (Buyer / Seller / Admin)
# ======================================================================
# A user's role is DERIVED, not stored as a fixed enum: "seller" simply
# means "owns or created at least one seller record". `active_mode`
# (users.active_mode) only decides which of the two panels a dual-role
# user is currently looking at -- it is a UI preference, never a
# permission check by itself.
VALID_MODES = ("buyer", "seller")


async def user_has_any_seller(user_id: int) -> bool:
    row = await db.fetchone(
        "SELECT 1 FROM sellers WHERE owner_user_id = ? OR created_by_user_id = ? LIMIT 1;",
        (user_id, user_id),
    )
    return row is not None


async def get_active_mode(user_id: int) -> str:
    """Returns 'buyer' or 'seller'. A user with no seller at all is
    ALWAYS 'buyer', regardless of whatever is stored (defends against a
    stale flag from before their last seller was removed/rejected)."""
    has_seller = await user_has_any_seller(user_id)
    if not has_seller:
        return "buyer"
    row = await db.fetchone("SELECT active_mode FROM users WHERE id = ?;", (user_id,))
    mode = row["active_mode"] if row and row["active_mode"] in VALID_MODES else "buyer"
    return mode


async def set_active_mode(user_id: int, mode: str) -> None:
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid mode: {mode}")
    await db.execute(
        "UPDATE users SET active_mode = ?, updated_at = ? WHERE id = ?;",
        (mode, now_iso(), user_id),
    )


# ======================================================================
# 9.6 SELLER FAVORITES (separate storage from product favorites)
# ======================================================================
async def is_seller_favorite(user_id: int, seller_id: int) -> bool:
    row = await db.fetchone(
        "SELECT 1 FROM seller_favorites WHERE user_id = ? AND seller_id = ?;",
        (user_id, seller_id),
    )
    return row is not None


async def toggle_seller_favorite(user_id: int, seller_id: int) -> bool:
    """Returns the new state: True if now favorited, False if removed."""
    if await is_seller_favorite(user_id, seller_id):
        await db.execute(
            "DELETE FROM seller_favorites WHERE user_id = ? AND seller_id = ?;",
            (user_id, seller_id),
        )
        return False
    try:
        await db.execute(
            "INSERT INTO seller_favorites (user_id, seller_id, created_at) VALUES (?, ?, ?);",
            (user_id, seller_id, now_iso()),
        )
    except Exception:  # noqa: BLE001 - duplicate insert race, treat as already-favorited
        pass
    return True


async def count_seller_favorites(seller_id: int) -> int:
    row = await db.fetchone(
        "SELECT COUNT(*) AS c FROM seller_favorites WHERE seller_id = ?;", (seller_id,)
    )
    return row["c"] if row else 0


# ======================================================================
# 9.7 COMPARE (2-product session selection)
# ======================================================================
COMPARE_MAX_ITEMS = 2
COMPARE_INTRO_TEXT = (
    "⚖️ مقایسه چیه؟\n"
    "دو محصول رو کنار هم بذار تا راحت‌تر انتخاب کنی. ✨"
)


def compare_add(selection: list, product_id: int) -> tuple:
    """Pure logic for adding a product to the (max 2-item) compare
    selection. Returns (new_selection, message_key) where message_key is
    one of: 'added_need_one_more', 'added_ready', 'already_full',
    'already_in_selection'."""
    selection = list(selection)
    if product_id in selection:
        return selection, "already_in_selection"
    if len(selection) >= COMPARE_MAX_ITEMS:
        return selection, "already_full"
    selection.append(product_id)
    if len(selection) == COMPARE_MAX_ITEMS:
        return selection, "added_ready"
    return selection, "added_need_one_more"


# In-memory per-user compare selection. Deliberately NOT stored in
# FSMContext data: almost every navigation handler calls `state.clear()`
# as a safety net against stray FSM flows, which would also wipe FSM
# data and silently lose the user's in-progress comparison every time
# they browsed to an unrelated screen. It's also not persisted to SQLite
# because a comparison-in-progress is inherently short-lived UI state,
# not something that needs to survive a bot restart. Keyed by internal
# user_id (not telegram_id).
_compare_sessions: dict = {}


def get_compare_selection(user_id: int) -> list:
    return list(_compare_sessions.get(user_id, []))


def set_compare_selection(user_id: int, selection: list) -> None:
    _compare_sessions[user_id] = list(selection)


def clear_compare_selection(user_id: int) -> None:
    _compare_sessions.pop(user_id, None)


async def has_seen_compare_intro(user_id: int) -> bool:
    row = await db.fetchone(
        "SELECT has_seen_compare_intro FROM users WHERE id = ?;", (user_id,)
    )
    return bool(row and row["has_seen_compare_intro"])


async def mark_compare_intro_seen(user_id: int) -> None:
    await db.execute(
        "UPDATE users SET has_seen_compare_intro = 1, updated_at = ? WHERE id = ?;",
        (now_iso(), user_id),
    )


# ======================================================================
# 9.8 REQUESTS ("📋 درخواست‌های من") + RATE LIMITING
# ======================================================================
# request_type values: 'support', 'ad'
# (moderation reports live in the existing `reports` table and are
# merged into the "my requests" view for display -- see list_my_requests)
REQUEST_STATUS_LABELS = {
    "PENDING": "🟡 در حال بررسی",
    "REJECTED": "🔴 رد شد",
    "APPROVED": "🟢 تأیید شد",
    "COORDINATING": "🔵 در حال هماهنگی",
}


async def has_open_request(user_id: int, request_type: str, topic: Optional[str] = None) -> bool:
    """Anti-spam: is there already an unresolved request of this
    type/topic for this user? Used to block duplicate support/ad
    requests until the previous one is resolved."""
    if topic:
        row = await db.fetchone(
            """SELECT 1 FROM requests
               WHERE user_id = ? AND request_type = ? AND topic = ? AND status = 'PENDING'
               LIMIT 1;""",
            (user_id, request_type, topic),
        )
    else:
        row = await db.fetchone(
            """SELECT 1 FROM requests
               WHERE user_id = ? AND request_type = ? AND status = 'PENDING'
               LIMIT 1;""",
            (user_id, request_type),
        )
    return row is not None


async def has_open_report(user_id: int, seller_id: Optional[int], product_id: Optional[int]) -> bool:
    if seller_id is not None:
        row = await db.fetchone(
            "SELECT 1 FROM reports WHERE user_id=? AND seller_id=? AND status='PENDING' LIMIT 1;",
            (user_id, seller_id),
        )
    else:
        row = await db.fetchone(
            "SELECT 1 FROM reports WHERE user_id=? AND product_id=? AND status='PENDING' LIMIT 1;",
            (user_id, product_id),
        )
    return row is not None


async def create_request(
    user_id: int,
    request_type: str,
    topic: Optional[str] = None,
    message: Optional[str] = None,
    seller_id: Optional[int] = None,
) -> int:
    now = now_iso()
    cur = await db.execute(
        """INSERT INTO requests (user_id, request_type, topic, message, seller_id, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?);""",
        (user_id, request_type, topic, message, seller_id, now, now),
    )
    return cur.lastrowid


async def list_my_requests(user_id: int, limit: int = 20) -> list:
    """Merges `requests` (support/ad) and `reports` (moderation) into one
    chronological list for the "📋 درخواست‌های من" screen. Each item is a
    plain dict with a normalized shape so the renderer doesn't care which
    table it came from."""
    requests_rows = await db.fetchall(
        "SELECT * FROM requests WHERE user_id = ? ORDER BY created_at DESC LIMIT ?;",
        (user_id, limit),
    )
    report_rows = await db.fetchall(
        "SELECT * FROM reports WHERE user_id = ? ORDER BY created_at DESC LIMIT ?;",
        (user_id, limit),
    )

    items = []
    for r in requests_rows:
        label = {"support": "🛟 پشتیبانی", "ad": "📢 درخواست تبلیغات"}.get(r["request_type"], r["request_type"])
        status = r["status"] if r["status"] in REQUEST_STATUS_LABELS else "PENDING"
        items.append({
            "kind": "request",
            "id": r["id"],
            "title": r["topic"] or label,
            "created_at": r["created_at"],
            "status_label": REQUEST_STATUS_LABELS[status],
        })
    for r in report_rows:
        status = r["status"] if r["status"] in REQUEST_STATUS_LABELS else "PENDING"
        target = "فروشگاه" if r["seller_id"] else "محصول"
        items.append({
            "kind": "report",
            "id": r["id"],
            "title": f"🚨 گزارش {target}",
            "created_at": r["created_at"],
            "status_label": REQUEST_STATUS_LABELS[status],
        })

    items.sort(key=lambda x: x["created_at"], reverse=True)
    return items[:limit]


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
    b.button(text=f"{EMOJI_COMPARE} مقایسه", callback_data="comparelist")
    b.button(text=f"{EMOJI_REGISTER_SELLER} ثبت فروشگاه من", callback_data="registerseller")
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


class SupportStates(StatesGroup):
    waiting_text = State()


class ShopEditStates(StatesGroup):
    waiting_value = State()


class ProductAddStates(StatesGroup):
    waiting_name = State()
    waiting_description = State()
    waiting_price = State()
    waiting_old_price = State()
    waiting_image_url = State()


class ProductEditStates(StatesGroup):
    waiting_value = State()


class WhatsAppEditStates(StatesGroup):
    waiting_number = State()


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
# 12.5 SEARCH ENGINE — LocalQueryParser (local, free, no external API)
# ======================================================================
# Architecture (as required):
#
#     User Query -> QueryParser -> StructuredQuery -> SearchEngine
#                 -> Ranking -> Results
#
# `QueryParser` is a small interface/contract. `LocalQueryParser` is the
# only implementation today: pure Python, regex + dictionary based, no
# network calls, no paid API, nothing external at all. `SearchEngine`
# only ever talks to the `QueryParser` interface, never to
# `LocalQueryParser` directly -- so a future `AIQueryParser` (calling an
# external AI model) can be added later as a drop-in replacement:
#
#     search_engine = SearchEngine(AIQueryParser())
#
# without touching SearchEngine, the ranking logic, or any handler.
# ------------------------------------------------------------------


@dataclass
class StructuredQuery:
    """The output of any QueryParser. Every field is optional -- a parser
    is allowed to leave anything it isn't confident about as None, and
    SearchEngine will simply not filter on that field."""

    raw_query: str
    keyword: Optional[str] = None
    category: Optional[str] = None
    city: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    color: Optional[str] = None
    gender: Optional[str] = None

    def has_any_extracted_field(self) -> bool:
        """True only if the parser extracted something MORE than a bare
        keyword (category/city/price/color/gender). A keyword-only result
        is deliberately NOT treated as "structured": plain_keyword_search
        already covers product name+description+seller name+description+
        category name for a single term, which is STRICTLY broader than
        the structured path's name/description-only match. Routing a bare
        keyword through the structured pipeline would only narrow the
        results for no benefit, so bare-keyword queries go straight to
        the plain fallback instead.
        """
        return any([
            self.category, self.city,
            self.min_price is not None, self.max_price is not None,
            self.color, self.gender,
        ])

    def simplified(self) -> "StructuredQuery":
        """Drop the most restrictive fields (price, city) but keep the
        core intent (keyword/category), used as a middle fallback step
        between a full structured search and the raw-text plain search."""
        return StructuredQuery(raw_query=self.raw_query, keyword=self.keyword, category=self.category)


class QueryParser:
    """Contract every query parser must follow. SearchEngine depends on
    this interface only -- see module docstring above."""

    def parse(self, raw_query: str) -> StructuredQuery:  # pragma: no cover - interface
        raise NotImplementedError


# ------------------------------------------------------------------
# LocalQueryParser building blocks (all pure functions -> easy to unit
# test without a database or network connection).
# ------------------------------------------------------------------
_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_ASCII_DIGITS = "0123456789"
_PUNCTUATION_CHARS = "،؛؟!.,:;()[]{}«»\"'؟?/\\"

_DIGIT_LETTER_MAP = {
    **{ch: _ASCII_DIGITS[i] for i, ch in enumerate(_PERSIAN_DIGITS)},
    **{ch: _ASCII_DIGITS[i] for i, ch in enumerate(_ARABIC_DIGITS)},
    "ي": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "إ": "ا", "أ": "ا",
}


def normalize_persian_text(text: str) -> str:
    """Unifies Arabic/Persian digits and letter variants, strips ZWNJ and
    punctuation, and collapses whitespace. This alone fixes a large chunk
    of "typo"/spelling-variant issues (١٢٣ vs ۱۲۳ vs 123, ي vs ی, ك vs ک,
    "می‌خوام" vs "می خوام", ...)."""
    if not text:
        return ""
    out = []
    for ch in text:
        if ch in _DIGIT_LETTER_MAP:
            out.append(_DIGIT_LETTER_MAP[ch])
        elif ch == "\u200c" or ch in _PUNCTUATION_CHARS:
            out.append(" ")
        else:
            out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()


ALT_CITY_SPELLINGS = {
    "تهرون": "تهران",
    "اصفون": "اصفهان",
    "اهوازو": "اهواز",
}

CATEGORY_SYNONYMS = {
    "گوشی موبایل": "موبایل",
    "گوشی": "موبایل",
    "لپ تاپ": "لپ‌تاپ",
    "لپتاپ": "لپ‌تاپ",
    "کفشو": "کفش",
}

_GENDER_WORD_MAP = {
    "مردونه": "مردانه", "مردانه": "مردانه",
    "زنونه": "زنانه", "زنانه": "زنانه",
    "دخترونه": "دخترانه", "دخترانه": "دخترانه",
    "پسرونه": "پسرانه", "پسرانه": "پسرانه",
    "بچگونه": "بچگانه", "بچگانه": "بچگانه",
}

_COLOR_WORDS = [
    "سفید", "مشکی", "قرمز", "آبی", "سبز", "زرد", "صورتی", "بنفش",
    "طلایی", "نقره‌ای", "قهوه‌ای", "خاکستری", "نارنجی", "کرم",
]

_STOPWORDS = [
    "می خوام", "میخوام", "میخواستم", "می خواستم", "دنبال", "برای من",
    "برام", "لطفا", "لطفاً", "میخوام که", "هست", "دارید", "دارین",
    "کنید", "میشه", "می شه", "یه", "یک", "رو", "را", "ممنون",
    "تو", "در", "توی", "داخل", "تومان", "تومن", "چی", "چیزی",
]

# Reuse the SAME data the bot already seeds the database with (CITY_NAMES
# and CATEGORY_TREE, defined in section 6 above) so the parser can never
# drift out of sync with what actually exists in the database.
_NORMALIZED_CITY_NAMES = sorted(
    {normalize_persian_text(name) for name in CITY_NAMES}, key=len, reverse=True
)

_ALL_CATEGORY_NAMES = [_main_name for _main_emoji, _main_name, _subs in CATEGORY_TREE] + [
    _sub_name
    for _main_emoji, _main_name, _subs in CATEGORY_TREE
    for _sub_emoji, _sub_name in _subs
]
_SORTED_CATEGORY_NAMES = sorted(
    {normalize_persian_text(name) for name in _ALL_CATEGORY_NAMES}, key=len, reverse=True
)

_NORMALIZED_COLOR_WORDS = sorted(
    {normalize_persian_text(w) for w in _COLOR_WORDS}, key=len, reverse=True
)

# Stopwords are split into multi-word PHRASES (removed via word-boundary
# regex -- safe because a multi-word phrase can't accidentally be a
# substring of an unrelated single word) and single-word TOKENS (removed
# via exact token match after splitting on whitespace). This matters:
# a naive text.replace("یک", " ") would also mangle unrelated words that
# merely CONTAIN "یک" as a substring, e.g. "نزدیک" (nearby) or "شیک"
# (stylish/chic) -- both plausible words in a real shopping query.
_NORMALIZED_STOPWORDS = sorted(
    {normalize_persian_text(w) for w in _STOPWORDS if w.strip()}, key=len, reverse=True
)
_STOPWORD_PHRASES = sorted(
    (w for w in _NORMALIZED_STOPWORDS if " " in w), key=len, reverse=True
)
_STOPWORD_TOKENS = {w for w in _NORMALIZED_STOPWORDS if " " not in w}

_PRICE_UNIT_RE = r"(\d+(?:\.\d+)?)\s*(میلیون|هزار)?"
_PRICE_RANGE_RE = re.compile(rf"بین\s+{_PRICE_UNIT_RE}\s+تا\s+{_PRICE_UNIT_RE}")
_PRICE_MAX_RE = re.compile(rf"(?:زیر|کمتر از|کمتر|حداکثر|تا)\s+{_PRICE_UNIT_RE}")
_PRICE_MIN_RE = re.compile(rf"(?:بالای|بیشتر از|بیشتر|حداقل|از)\s+{_PRICE_UNIT_RE}")


def _remove_stopwords(text: str) -> str:
    """Word-boundary-safe stopword removal: multi-word phrases first
    (regex \\b...\\b, safe since spaces disambiguate them), then
    single-word tokens via exact post-split matching -- never a blind
    substring replace, so real words are never corrupted."""
    for phrase in _STOPWORD_PHRASES:
        text = re.sub(rf"\b{re.escape(phrase)}\b", " ", text)
    tokens = [t for t in text.split() if t not in _STOPWORD_TOKENS]
    return " ".join(tokens)


def _convert_number_unit(num_str: str, unit: Optional[str]) -> float:
    value = float(num_str)
    if unit == "میلیون":
        value *= 1_000_000
    elif unit == "هزار":
        value *= 1_000
    return value


def _extract_price(text: str):
    """Returns (min_price, max_price, remaining_text). Only ASCII-digit,
    already-normalized text should be passed in."""
    match = _PRICE_RANGE_RE.search(text)
    if match:
        v1 = _convert_number_unit(match.group(1), match.group(2))
        v2 = _convert_number_unit(match.group(3), match.group(4))
        min_price, max_price = (v1, v2) if v1 <= v2 else (v2, v1)
        text = text[:match.start()] + " " + text[match.end():]
        return min_price, max_price, text

    match = _PRICE_MAX_RE.search(text)
    if match:
        max_price = _convert_number_unit(match.group(1), match.group(2))
        text = text[:match.start()] + " " + text[match.end():]
        return None, max_price, text

    match = _PRICE_MIN_RE.search(text)
    if match:
        min_price = _convert_number_unit(match.group(1), match.group(2))
        text = text[:match.start()] + " " + text[match.end():]
        return min_price, None, text

    return None, None, text


class LocalQueryParser(QueryParser):
    """Fully local, free, deterministic natural-language-ish parser for
    Persian shopping queries. No network calls, no API keys, no external
    services of any kind -- everything here is regex + dictionary
    lookups against data already in this file."""

    def parse(self, raw_query: str) -> StructuredQuery:
        original = (raw_query or "").strip()
        text = normalize_persian_text(original)

        for alt, canonical in ALT_CITY_SPELLINGS.items():
            text = text.replace(normalize_persian_text(alt), normalize_persian_text(canonical))
        for alt, canonical in sorted(CATEGORY_SYNONYMS.items(), key=lambda kv: -len(kv[0])):
            text = text.replace(normalize_persian_text(alt), normalize_persian_text(canonical))

        min_price, max_price, text = _extract_price(text)

        city = None
        for city_name in _NORMALIZED_CITY_NAMES:
            if city_name and city_name in text:
                city = city_name
                text = text.replace(city_name, " ")
                break

        gender = None
        for alt, canonical in sorted(_GENDER_WORD_MAP.items(), key=lambda kv: -len(kv[0])):
            norm_alt = normalize_persian_text(alt)
            if norm_alt in text:
                gender = canonical
                text = text.replace(norm_alt, " ")
                break

        color = None
        for c in _NORMALIZED_COLOR_WORDS:
            if c and c in text:
                color = c
                text = text.replace(c, " ")
                break

        category = None
        for cat_name in _SORTED_CATEGORY_NAMES:
            if cat_name and cat_name in text:
                category = cat_name
                text = text.replace(cat_name, " ")
                break

        text = _remove_stopwords(text)

        keyword = re.sub(r"\s+", " ", text).strip() or None

        return StructuredQuery(
            raw_query=original,
            keyword=keyword,
            category=category,
            city=city,
            min_price=min_price,
            max_price=max_price,
            color=color,
            gender=gender,
        )


def build_search_summary(sq: StructuredQuery) -> str:
    parts = [p for p in (sq.keyword, sq.category, sq.gender, sq.color) if p]
    first_line = " • ".join(parts) if parts else sq.raw_query
    lines = [f"{EMOJI_SEARCH} جستجو برای:", first_line]
    if sq.min_price is not None and sq.max_price is not None:
        lines.append(f"بین {format_price(sq.min_price)} تا {format_price(sq.max_price)}")
    elif sq.max_price is not None:
        lines.append(f"تا {format_price(sq.max_price)}")
    elif sq.min_price is not None:
        lines.append(f"از {format_price(sq.min_price)}")
    if sq.city:
        lines.append(f"{EMOJI_CITY} {sq.city}")
    return "\n".join(lines)


def score_search_candidate(row, sq: StructuredQuery, resolved_category_ids: set, resolved_city_id) -> float:
    """Pure ranking function -- takes a dict-like row (works with both a
    plain dict in tests and a real aiosqlite.Row at runtime) and returns
    a relevance score. Combines: category match, keyword-in-name,
    keyword-in-description, city match, price fit, rating, review_count,
    views -- exactly the factors requested."""
    score = 0.0
    name = row["name"] or ""
    description = row["description"] or ""

    if resolved_category_ids and row["category_id"] in resolved_category_ids:
        score += 30
    if sq.keyword:
        if sq.keyword in name:
            score += 25
        elif sq.keyword in description:
            score += 10
    for term in (sq.color, sq.gender):
        if term and (term in name or term in description):
            score += 8

    if resolved_city_id and row["seller_city_id"] == resolved_city_id:
        score += 15

    price = row["price"]
    if price is not None:
        if sq.min_price is not None and price < sq.min_price:
            score -= 20
        if sq.max_price is not None and price > sq.max_price:
            score -= 20
        elif sq.min_price is not None or sq.max_price is not None:
            score += 10

    rating = row["rating"] or 0
    review_count = row["review_count"] or 0
    views = row["views"] or 0
    score += min(rating, 5) * 2
    score += min(review_count, 50) * 0.1
    score += min(views, 500) * 0.01
    return score


async def resolve_category_ids(name: Optional[str]) -> set:
    if not name:
        return set()
    like = f"%{name.strip()}%"
    rows = await db.fetchall(
        "SELECT id, parent_id FROM categories WHERE name LIKE ? LIMIT 5;", (like,)
    )
    ids = set()
    for r in rows:
        ids.add(r["id"])
        if r["parent_id"] is None:
            children = await db.fetchall(
                "SELECT id FROM categories WHERE parent_id = ?;", (r["id"],)
            )
            ids.update(c["id"] for c in children)
    return ids


async def resolve_city_id(name: Optional[str]):
    if not name:
        return None
    like = f"%{name.strip()}%"
    row = await db.fetchone("SELECT id FROM cities WHERE name LIKE ? LIMIT 1;", (like,))
    return row["id"] if row else None


async def plain_keyword_search(query: str, limit: int = 20) -> list:
    """The ORIGINAL search query, unchanged, kept as the universal
    fallback: if the parser can't structure a query, or a structured
    search finds nothing, this always still works with zero external
    dependencies."""
    like = f"%{query}%"
    return await db.fetchall(
        """SELECT DISTINCT p.* FROM products p
           JOIN sellers s ON s.id = p.seller_id
           LEFT JOIN categories c ON c.id = p.category_id
           WHERE p.name LIKE ? OR p.description LIKE ?
              OR s.name LIKE ? OR s.description LIKE ?
              OR c.name LIKE ?
           ORDER BY p.views DESC LIMIT ?;""",
        (like, like, like, like, like, limit),
    )


class SearchEngine:
    """Depends only on the QueryParser interface -- swapping
    LocalQueryParser for a future AIQueryParser requires no change here."""

    def __init__(self, parser: QueryParser):
        self.parser = parser

    async def _structured_search(self, sq: StructuredQuery, limit: int = 30) -> list:
        resolved_category_ids = await resolve_category_ids(sq.category)
        resolved_city_id = await resolve_city_id(sq.city)

        conditions = []
        params: list = []

        if resolved_category_ids:
            placeholders = ",".join("?" for _ in resolved_category_ids)
            conditions.append(f"p.category_id IN ({placeholders})")
            params.extend(resolved_category_ids)
        if resolved_city_id:
            conditions.append("s.city_id = ?")
            params.append(resolved_city_id)

        for term in (sq.keyword, sq.color, sq.gender):
            if term:
                like = f"%{term}%"
                conditions.append("(p.name LIKE ? OR p.description LIKE ?)")
                params.extend([like, like])

        if sq.max_price is not None:
            conditions.append("(p.price IS NOT NULL AND p.price <= ?)")
            params.append(sq.max_price)
        if sq.min_price is not None:
            conditions.append("(p.price IS NOT NULL AND p.price >= ?)")
            params.append(sq.min_price)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = (
            "SELECT p.*, s.name AS seller_name, s.city_id AS seller_city_id "
            "FROM products p JOIN sellers s ON s.id = p.seller_id "
            f"WHERE {where_clause} ORDER BY p.views DESC LIMIT 200;"
        )
        rows = await db.fetchall(query, params)
        scored = [
            (score_search_candidate(r, sq, resolved_category_ids, resolved_city_id), r)
            for r in rows
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [r for _score, r in scored[:limit]]

    async def search(self, raw_query: str):
        """Returns (structured_query, results, mode) where mode is
        "structured" (LocalQueryParser understood something and it
        matched) or "plain" (full fallback to the original LIKE search)."""
        structured = self.parser.parse(raw_query)

        if structured.has_any_extracted_field():
            results = await self._structured_search(structured)
            if results:
                return structured, results, "structured"

            simplified = structured.simplified()
            if simplified != structured and simplified.has_any_extracted_field():
                results = await self._structured_search(simplified)
                if results:
                    return simplified, results, "structured"

        plain_results = await plain_keyword_search(raw_query)
        return structured, plain_results, "plain"


# Module-level singleton. Swapping to AIQueryParser in the future is a
# one-line change here -- nothing else in the file needs to know.
search_engine = SearchEngine(LocalQueryParser())


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


async def _render_search_results(message: Message, header: str, products: list) -> None:
    b = InlineKeyboardBuilder()
    for p in products[:PAGE_SIZE_LIST]:
        b.row(InlineKeyboardButton(
            text=f"{EMOJI_PRODUCT} {p['name']} - {format_price(p['price'])}",
            callback_data=f"product:{p['id']}",
        ))
    kb_add_back(b, "main")
    await message.answer(header, reply_markup=b.as_markup())


async def _render_no_results(message: Message, text: str) -> None:
    b = InlineKeyboardBuilder()
    kb_add_back(b, "main")
    await message.answer(text, reply_markup=b.as_markup())


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

    structured, products, mode = await search_engine.search(query)
    await log_event(user_id, "search", "local_smart" if mode == "structured" else "query", None)

    if not products:
        await _render_no_results(message, f"🔎 نتیجه‌ای برای «{query}» پیدا نشد.")
        return

    if mode == "structured":
        header = build_search_summary(structured) + "\n\nنتایج:"
    else:
        header = f"🔎 نتایج جستجو برای «{query}»:"
    await _render_search_results(message, header, products)


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
    await _render_seller_detail(callback, seller_id)


async def _render_seller_detail(callback: CallbackQuery, seller_id: int) -> None:
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

    is_owner = user_id in (seller["owner_user_id"], seller["created_by_user_id"])
    is_active = bool(seller["is_active"]) if seller["is_active"] is not None else True
    if not is_active:
        lines.append("\n🔴 این فروشگاه موقتاً غیرفعال است و فعلاً امکان ارتباط جدید ندارد.")

    b = InlineKeyboardBuilder()
    ig = instagram_url(seller["instagram"])
    tg = telegram_url(seller["telegram"])
    site = website_url(seller["website"])
    wa = whatsapp_url(seller["whatsapp"])
    support_tg = telegram_url(seller["telegram_support"])
    # Instagram / Telegram / WhatsApp are independent contact channels and
    # a plain url= button gives Telegram no way to tell the bot a tap
    # happened, so click-tracking (instagram_click/telegram_click/
    # whatsapp_click) uses callback_data instead; the handler logs the
    # event and then opens the link via answer(url=...). Only channels
    # the seller actually filled in are ever shown, AND only while the
    # store is active for anyone other than its own owner -- this is the
    # single choke-point every path to a seller (list, product card,
    # search, referral link, review, claim) funnels through, so this one
    # check is what makes "فعال/غیرفعال" actually respected everywhere a
    # buyer could reach out to the seller.
    show_contacts = is_active or is_owner
    if show_contacts:
        if ig:
            b.row(InlineKeyboardButton(text="📸 اینستاگرام", callback_data=f"igclick:{seller_id}"))
        if tg:
            b.row(InlineKeyboardButton(text="✈️ تلگرام", callback_data=f"tgclick:{seller_id}"))
        if wa:
            b.row(InlineKeyboardButton(text="🟢 واتساپ", callback_data=f"waclick:{seller_id}"))
        if site:
            b.row(InlineKeyboardButton(text=f"{EMOJI_LINK} وبسایت", url=site))
        if support_tg:
            b.row(InlineKeyboardButton(text="💬 پشتیبانی فروشگاه", url=support_tg))

    is_fav = await is_seller_favorite(user_id, seller_id)
    fav_text = "💔 حذف از علاقه‌مندی‌ها" if is_fav else "❤️ ذخیره فروشگاه"
    fav_cb = f"sunfav:{seller_id}" if is_fav else f"sfav:{seller_id}"
    b.row(InlineKeyboardButton(text=fav_text, callback_data=fav_cb))

    if seller["status"] == "UNCLAIMED":
        b.row(InlineKeyboardButton(text=f"{EMOJI_CLAIM} درخواست مالکیت فروشگاه", callback_data=f"claim:{seller_id}"))
    b.row(InlineKeyboardButton(text="⭐ ثبت نظر", callback_data=f"reviewstart:seller:{seller_id}"))
    b.row(InlineKeyboardButton(text=f"{EMOJI_REPORT} گزارش", callback_data=f"report:seller:{seller_id}"))

    if is_owner:
        wa_label = "🟢 ویرایش واتساپ" if wa else "🟢 افزودن واتساپ"
        b.row(InlineKeyboardButton(text=wa_label, callback_data=f"waedit:{seller_id}"))

    kb_add_back(b, "sellers:0")

    await safe_edit(callback, "\n".join(lines), b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("sfav:"))
async def handle_seller_favorite_add(callback: CallbackQuery) -> None:
    seller_id = parse_int(callback.data.split(":")[1])
    if seller_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    user_id = await ensure_user(callback.from_user)
    seller = await db.fetchone("SELECT id FROM sellers WHERE id = ?;", (seller_id,))
    if not seller:
        await callback.answer("⚠️ این فروشگاه یافت نشد.", show_alert=True)
        return
    await toggle_seller_favorite(user_id, seller_id)
    await log_event(user_id, "favorite_add", "seller", seller_id)
    await callback.answer("❤️ ذخیره شد! هر وقت خواستی از بخش علاقه‌مندی‌ها پیداش می‌کنی.", show_alert=True)
    await _render_seller_detail(callback, seller_id)


@router.callback_query(F.data.startswith("sunfav:"))
async def handle_seller_favorite_remove(callback: CallbackQuery) -> None:
    seller_id = parse_int(callback.data.split(":")[1])
    if seller_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    user_id = await ensure_user(callback.from_user)
    await toggle_seller_favorite(user_id, seller_id)
    await callback.answer("از علاقه‌مندی‌ها حذف شد 💔")
    await _render_seller_detail(callback, seller_id)


@router.callback_query(F.data.startswith("igclick:"))
async def handle_instagram_click(callback: CallbackQuery) -> None:
    seller_id = parse_int(callback.data.split(":")[1])
    user_id = await ensure_user(callback.from_user)
    seller = await db.fetchone("SELECT instagram FROM sellers WHERE id = ?;", (seller_id,))
    link = instagram_url(seller["instagram"]) if seller else None
    if not link:
        await callback.answer("⚠️ این لینک در دسترس نیست.", show_alert=True)
        return
    await log_event(user_id, "instagram_click", "seller", seller_id)
    await callback.answer(url=link)


@router.callback_query(F.data.startswith("tgclick:"))
async def handle_telegram_click(callback: CallbackQuery) -> None:
    seller_id = parse_int(callback.data.split(":")[1])
    user_id = await ensure_user(callback.from_user)
    seller = await db.fetchone("SELECT telegram FROM sellers WHERE id = ?;", (seller_id,))
    link = telegram_url(seller["telegram"]) if seller else None
    if not link:
        await callback.answer("⚠️ این لینک در دسترس نیست.", show_alert=True)
        return
    await log_event(user_id, "telegram_click", "seller", seller_id)
    await callback.answer(url=link)


@router.callback_query(F.data.startswith("waclick:"))
async def handle_whatsapp_click(callback: CallbackQuery) -> None:
    seller_id = parse_int(callback.data.split(":")[1])
    user_id = await ensure_user(callback.from_user)
    seller = await db.fetchone("SELECT whatsapp FROM sellers WHERE id = ?;", (seller_id,))
    link = whatsapp_url(seller["whatsapp"]) if seller else None
    if not link:
        await callback.answer("⚠️ این لینک در دسترس نیست.", show_alert=True)
        return
    await log_event(user_id, "whatsapp_click", "seller", seller_id)
    await callback.answer(url=link)


@router.callback_query(F.data.startswith("waedit:"))
async def handle_whatsapp_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    seller_id = parse_int(callback.data.split(":")[1])
    if seller_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    user_id = await ensure_user(callback.from_user)
    seller = await db.fetchone(
        "SELECT id, owner_user_id, created_by_user_id FROM sellers WHERE id = ?;", (seller_id,)
    )
    if not seller or user_id not in (seller["owner_user_id"], seller["created_by_user_id"]):
        await callback.answer("⚠️ این عملیات فقط برای صاحب فروشگاه در دسترس است.", show_alert=True)
        return
    await state.update_data(whatsapp_seller_id=seller_id)
    await state.set_state(WhatsAppEditStates.waiting_number)
    b = InlineKeyboardBuilder()
    kb_add_back(b, f"seller:{seller_id}")
    await safe_edit(
        callback,
        "🟢 شماره واتساپ فروشگاه رو با کد کشور بفرست (مثلاً 989123456789 یا 09123456789):",
        b.as_markup(),
    )
    await callback.answer()


@router.message(StateFilter(WhatsAppEditStates.waiting_number))
async def handle_whatsapp_edit_value(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    data = await state.get_data()
    seller_id = data.get("whatsapp_seller_id")
    await state.clear()
    if not seller_id:
        await message.answer("⚠️ فرآیند منقضی شده. دوباره از صفحه فروشگاه تلاش کن.")
        return

    user_id = await ensure_user(message.from_user)
    seller = await db.fetchone(
        "SELECT id, owner_user_id, created_by_user_id, name FROM sellers WHERE id = ?;", (seller_id,)
    )
    if not seller or user_id not in (seller["owner_user_id"], seller["created_by_user_id"]):
        await message.answer("⚠️ این عملیات فقط برای صاحب فروشگاه در دسترس است.")
        return

    raw_number = (message.text or "").strip()
    if not whatsapp_url(raw_number):
        await message.answer("⚠️ شماره معتبر نیست. لطفاً فقط شماره همراه با کد کشور بفرست.")
        return

    await db.execute(
        "UPDATE sellers SET whatsapp = ?, updated_at = ? WHERE id = ?;",
        (raw_number, now_iso(), seller_id),
    )
    await log_audit(user_id, "seller_whatsapp_updated", "seller", seller_id)

    b = InlineKeyboardBuilder()
    kb_add_back(b, f"seller:{seller_id}")
    await message.answer(f"✅ شماره واتساپ «{seller['name']}» ذخیره شد.", reply_markup=b.as_markup())


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
    b.row(InlineKeyboardButton(text=f"{EMOJI_COMPARE} افزودن به مقایسه", callback_data=f"comparestart:{product_id}"))
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
        await log_event(user_id, "favorite_add", "product", product_id)
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

    user_id = await ensure_user(callback.from_user)
    seller_id = target_id if target_type == "seller" else None
    product_id = target_id if target_type == "product" else None
    if await has_open_report(user_id, seller_id, product_id):
        await callback.answer("گزارش قبلی شما برای همین مورد هنوز در حال بررسی است.", show_alert=True)
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


async def _save_report(user_id: int, data: dict, description: Optional[str], bot: Optional[Bot] = None) -> None:
    target_type = data.get("report_target_type")
    target_id = data.get("report_target_id")
    reason_code = data.get("report_reason")
    seller_id = target_id if target_type == "seller" else None
    product_id = target_id if target_type == "product" else None

    cur = await db.execute(
        """INSERT INTO reports (user_id, seller_id, product_id, reason, description, status, created_at)
           VALUES (?, ?, ?, ?, ?, 'PENDING', ?);""",
        (user_id, seller_id, product_id, reason_code, description, now_iso()),
    )
    report_id = cur.lastrowid
    await log_event(user_id, "report", target_type, target_id)
    await log_audit(user_id, "report_created", target_type, target_id, details=reason_code)

    if bot is not None:
        target_label = "فروشگاه" if seller_id else "محصول"
        b = InlineKeyboardBuilder()
        b.row(
            InlineKeyboardButton(text="🟢 تأیید گزارش", callback_data=f"adminreport:approve:{report_id}"),
            InlineKeyboardButton(text="🔴 رد گزارش", callback_data=f"adminreport:reject:{report_id}"),
        )
        await send_admin_dm(
            bot,
            f"🚨 گزارش جدید ({target_label} #{target_id})\nدلیل: {REPORT_REASONS.get(reason_code, reason_code)}\n"
            f"توضیح: {description or '—'}",
            reply_markup=b.as_markup(),
        )


@router.callback_query(F.data == "reportskip", StateFilter(ReportStates.waiting_description))
async def handle_report_skip(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await ensure_user(callback.from_user)
    data = await state.get_data()
    await state.clear()
    await _save_report(user_id, data, None, bot=callback.bot)
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
    await _save_report(user_id, data, (message.text or "").strip(), bot=message.bot)
    await message.answer("گزارش شما ثبت شد. ممنون که به امن‌تر شدن ارزانکده کمک می‌کنی.")


@router.callback_query(F.data.startswith("adminreport:"))
async def handle_admin_report_decision(callback: CallbackQuery) -> None:
    """Admin-only. Gated by ADMIN_CHAT_ID (not by any in-app "admin role"
    table, since this project has none yet) -- if ADMIN_CHAT_ID isn't
    configured, this action is refused for everyone rather than left open."""
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return
    _, action, report_id_str = parts
    report_id = parse_int(report_id_str)
    if report_id is None or action not in ("approve", "reject"):
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return

    admin_user_id = await ensure_user(callback.from_user)
    if not ADMIN_CHAT_ID or callback.from_user.id != ADMIN_CHAT_ID:
        await callback.answer("⛔️ این عملیات فقط برای ادمین در دسترس است.", show_alert=True)
        return

    report = await db.fetchone("SELECT * FROM reports WHERE id = ?;", (report_id,))
    if not report:
        await callback.answer("⚠️ این گزارش یافت نشد.", show_alert=True)
        return

    new_status = "APPROVED" if action == "approve" else "REJECTED"
    await db.execute("UPDATE reports SET status = ? WHERE id = ?;", (new_status, report_id))
    await log_audit(admin_user_id, f"report_{action}d", "report", report_id)

    if action == "approve":
        await notify_user(
            report["user_id"], "نتیجه گزارش شما",
            "✅ گزارشت بررسی و تأیید شد. ممنون که به امن‌تر شدن ارزانکده کمک می‌کنی.",
        )
    else:
        await notify_user(
            report["user_id"], "نتیجه گزارش شما",
            "🚫 گزارشت بررسی شد.\nبعد از بررسی، مورد گزارش‌شده نیاز به اقدام نداشت.",
        )

    await callback.answer(f"وضعیت گزارش #{report_id} به‌روزرسانی شد.")
    try:
        await callback.message.edit_text(f"{callback.message.text}\n\n— تصمیم ثبت شد: {REQUEST_STATUS_LABELS[new_status]}")
    except TelegramBadRequest:
        pass


# ======================================================================
# 19.5 REQUESTS ("📋 درخواست‌های من")
# ======================================================================
@router.callback_query(F.data == "myrequests")
async def handle_my_requests(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await ensure_user(callback.from_user)
    items = await list_my_requests(user_id)

    b = InlineKeyboardBuilder()
    if not items:
        text = "📋 <b>درخواست‌های من</b>\n\nهنوز درخواستی ثبت نکرده‌اید."
    else:
        lines = ["📋 <b>درخواست‌های من</b>", ""]
        for item in items:
            lines.append(f"{item['title']} — {item['status_label']}\n{item['created_at'][:10]}")
        text = "\n\n".join(lines)
    kb_add_back(b, "account")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


# ======================================================================
# 19.6 SUPPORT ("🛟 پشتیبانی ارزانکده")
# ======================================================================
SUPPORT_TOPICS_BUYER = {
    "buy": "🛍️ مشکل خرید",
    "shop": "🏪 مشکل فروشگاه",
    "tech": "⚙️ مشکل فنی",
    "report": "🚨 گزارش مشکل",
    "other": "📝 سایر موارد ضروری",
}
SUPPORT_TOPICS_SELLER = {
    "shop_account": "🏪 مشکل حساب/فروشندگی",
    "ads": "📢 هماهنگی/پرداخت تبلیغات",
    "tech": "⚙️ مشکل فنی ارزانکده",
    "other": "📝 سایر موارد ضروری",
}


@router.callback_query(F.data.startswith("supportstart:"))
async def handle_support_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    audience = callback.data.split(":", 1)[1]
    topics = SUPPORT_TOPICS_SELLER if audience == "seller" else SUPPORT_TOPICS_BUYER
    b = InlineKeyboardBuilder()
    for code, label in topics.items():
        b.row(InlineKeyboardButton(text=label, callback_data=f"supporttopic:{audience}:{code}"))
    kb_add_back(b, "account")
    await safe_edit(callback, "🛟 موضوع مشکلت رو انتخاب کن:", b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("supporttopic:"))
async def handle_support_topic(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return
    _, audience, code = parts
    topics = SUPPORT_TOPICS_SELLER if audience == "seller" else SUPPORT_TOPICS_BUYER
    if code not in topics:
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return

    user_id = await ensure_user(callback.from_user)
    if await has_open_request(user_id, "support", topic=topics[code]):
        await callback.answer(
            "درخواست پشتیبانی قبلی‌ات برای همین موضوع هنوز تعیین تکلیف نشده.", show_alert=True
        )
        return

    await state.update_data(support_topic=topics[code])
    await state.set_state(SupportStates.waiting_text)
    b = InlineKeyboardBuilder()
    await safe_edit(
        callback,
        f"دلیل انتخابی: {topics[code]}\n\n"
        f"✍️ در یک جمله برامون بنویس چه مشکلی پیش اومده.\nحداکثر {SUPPORT_MESSAGE_MAX_LEN} حرف 👇",
        b.as_markup(),
    )
    await callback.answer()


@router.message(StateFilter(SupportStates.waiting_text))
async def handle_support_text(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    user_id = await ensure_user(message.from_user)
    data = await state.get_data()
    topic = data.get("support_topic")
    await state.clear()
    if not topic:
        await message.answer("⚠️ فرآیند پشتیبانی منقضی شده. لطفاً دوباره تلاش کن.")
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ لطفاً یک متن معتبر بفرست.")
        return
    if len(text) > SUPPORT_MESSAGE_MAX_LEN:
        text = text[:SUPPORT_MESSAGE_MAX_LEN]

    request_id = await create_request(user_id, "support", topic=topic, message=text)
    await log_audit(user_id, "support_request_created", "request", request_id, details=topic)
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🟢 تأیید درخواست", callback_data=f"adminreq:approve:{request_id}"),
        InlineKeyboardButton(text="🔴 رد درخواست", callback_data=f"adminreq:reject:{request_id}"),
    )
    await send_admin_dm(
        message.bot,
        f"🛟 درخواست پشتیبانی جدید\nموضوع: {topic}\nپیام: {text}\n(کاربر داخلی #{user_id})",
        reply_markup=b.as_markup(),
    )
    await message.answer(
        "✅ درخواستت برای تیم پشتیبانی ارزانکده ارسال شد.\n"
        "تا وقتی که بررسی نشده، گفت‌وگوی مستقیم باز نمی‌شود؛ بعد از تأیید، ادامه‌ی گفت‌وگو فعال می‌شود."
    )


@router.callback_query(F.data.startswith("adminreq:"))
async def handle_admin_request_decision(callback: CallbackQuery) -> None:
    """Admin-only, same gating as handle_admin_report_decision. Covers
    the `requests` table (support + ad requests)."""
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return
    _, action, request_id_str = parts
    request_id = parse_int(request_id_str)
    if request_id is None or action not in ("approve", "reject"):
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return

    admin_user_id = await ensure_user(callback.from_user)
    if not ADMIN_CHAT_ID or callback.from_user.id != ADMIN_CHAT_ID:
        await callback.answer("⛔️ این عملیات فقط برای ادمین در دسترس است.", show_alert=True)
        return

    req = await db.fetchone("SELECT * FROM requests WHERE id = ?;", (request_id,))
    if not req:
        await callback.answer("⚠️ این درخواست یافت نشد.", show_alert=True)
        return

    new_status = "APPROVED" if action == "approve" else "REJECTED"
    await db.execute(
        "UPDATE requests SET status = ?, updated_at = ? WHERE id = ?;", (new_status, now_iso(), request_id)
    )
    await log_audit(admin_user_id, f"request_{action}d", "request", request_id)

    if req["request_type"] == "support":
        if action == "approve":
            await notify_user(
                req["user_id"], "درخواست پشتیبانی",
                "✅ درخواست پشتیبانی‌ات تأیید شد. تیم ارزانکده به‌زودی باهات در ارتباط خواهد بود.",
            )
        else:
            await notify_user(
                req["user_id"], "درخواست پشتیبانی",
                "درخواست پشتیبانی‌ات بررسی شد. اگر همچنان مشکل داری، دوباره از منو درخواست بده.",
            )
    else:  # ad
        if action == "approve":
            await notify_user(
                req["user_id"], "درخواست تبلیغات",
                "✅ درخواست تبلیغاتت تأیید شد. تیم ارزانکده برای هماهنگی قیمت و پرداخت باهات تماس می‌گیره.",
            )
        else:
            await notify_user(
                req["user_id"], "درخواست تبلیغات",
                "درخواست تبلیغاتت فعلاً امکان‌پذیر نیست. برای جزئیات بیشتر با پشتیبانی در ارتباط باش.",
            )

    await callback.answer(f"وضعیت درخواست #{request_id} به‌روزرسانی شد.")
    try:
        await callback.message.edit_text(f"{callback.message.text}\n\n— تصمیم ثبت شد: {REQUEST_STATUS_LABELS[new_status]}")
    except TelegramBadRequest:
        pass


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
    """Role-aware entry point: renders the Buyer panel or Seller panel
    depending on the user's current active_mode. A user with no seller
    at all always sees the Buyer panel, full stop -- see get_active_mode()."""
    await state.clear()
    user_id = await ensure_user(callback.from_user)
    mode = await get_active_mode(user_id)
    if mode == "seller":
        await _render_seller_panel(callback, user_id)
    else:
        await _render_buyer_panel(callback, user_id)
    await callback.answer()


def _mode_switch_button(current_mode: str) -> InlineKeyboardButton:
    if current_mode == "buyer":
        return InlineKeyboardButton(text="🏪 حالت فروشندگی", callback_data="setmode:seller")
    return InlineKeyboardButton(text="👤 حالت خرید", callback_data="setmode:buyer")


@router.callback_query(F.data.startswith("setmode:"))
async def handle_set_mode(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    mode = callback.data.split(":", 1)[1]
    if mode not in VALID_MODES:
        await callback.answer("⚠️ حالت نامعتبر است.", show_alert=True)
        return
    user_id = await ensure_user(callback.from_user)
    if mode == "seller" and not await user_has_any_seller(user_id):
        await callback.answer("⚠️ شما هنوز فروشگاهی ثبت نکرده‌اید.", show_alert=True)
        return
    await set_active_mode(user_id, mode)
    if mode == "seller":
        await _render_seller_panel(callback, user_id)
    else:
        await _render_buyer_panel(callback, user_id)
    await callback.answer()


async def _render_buyer_panel(callback: CallbackQuery, user_id: int) -> None:
    has_seller = await user_has_any_seller(user_id)
    lines = [f"{EMOJI_ACCOUNT} <b>حساب من</b>", "", "👤 حالت خرید"]
    b = InlineKeyboardBuilder()
    if has_seller:
        b.row(_mode_switch_button("buyer"))
    b.row(InlineKeyboardButton(text=f"{EMOJI_FAVORITES} علاقه‌مندی‌ها", callback_data="favorites:0"))
    b.row(InlineKeyboardButton(text=f"{EMOJI_COMPARE} مقایسه", callback_data="comparelist"))
    b.row(InlineKeyboardButton(text="💬 پیام‌های من", callback_data="notifications"))
    b.row(InlineKeyboardButton(text="📋 درخواست‌های من", callback_data="myrequests"))
    b.row(InlineKeyboardButton(text="🛟 پشتیبانی ارزانکده", callback_data="supportstart:buyer"))
    b.row(InlineKeyboardButton(text="👤 پروفایل من", callback_data="myprofile"))
    kb_add_back(b, "main")
    await safe_edit(callback, "\n".join(lines), b.as_markup())


async def _render_seller_panel(callback: CallbackQuery, user_id: int) -> None:
    lines = [f"{EMOJI_ACCOUNT} <b>حساب من</b>", "", "🏪 حالت فروشندگی"]
    b = InlineKeyboardBuilder()
    b.row(_mode_switch_button("seller"))
    b.row(InlineKeyboardButton(text="📊 وضعیت فروشگاه", callback_data="storestatus"))
    b.row(InlineKeyboardButton(text="🏪 فروشگاه من", callback_data="myshop"))
    b.row(InlineKeyboardButton(text="📦 محصولات", callback_data="myproducts"))
    b.row(InlineKeyboardButton(text=f"{EMOJI_ADS} تبلیغات", callback_data="ads"))
    b.row(InlineKeyboardButton(text="📈 آمار", callback_data="mystats"))
    b.row(InlineKeyboardButton(text="🎁 لینک معرفی فروشگاهم", callback_data="reflist"))
    b.row(InlineKeyboardButton(text="📋 درخواست‌های من", callback_data="myrequests"))
    b.row(InlineKeyboardButton(text="🛟 پشتیبانی ارزانکده", callback_data="supportstart:seller"))
    kb_add_back(b, "main")
    await safe_edit(callback, "\n".join(lines), b.as_markup())


async def resolve_single_seller_or_show_picker(
    callback: CallbackQuery, user_id: int, target_prefix: str, title: str
) -> Optional[int]:
    """If the user owns exactly one seller, returns its id immediately.
    If they own several, renders a picker (callback_data f"{target_prefix}:{id}")
    and returns None -- the caller must stop and let the picker screen's
    own handler re-invoke the actual target. If they own none, answers
    with an alert and returns None."""
    sellers = await get_sellers_owned_by_user(user_id)
    if not sellers:
        await callback.answer("⚠️ شما هنوز فروشگاهی ثبت نکرده‌اید.", show_alert=True)
        return None
    if len(sellers) == 1:
        return sellers[0]["id"]
    b = InlineKeyboardBuilder()
    for s in sellers:
        b.row(InlineKeyboardButton(text=f"{EMOJI_SELLERS} {s['name']}", callback_data=f"{target_prefix}:{s['id']}"))
    kb_add_back(b, "account")
    await safe_edit(callback, title, b.as_markup())
    await callback.answer()
    return None


async def _check_seller_ownership(user_id: int, seller_id: int) -> Optional[dict]:
    seller = await db.fetchone("SELECT * FROM sellers WHERE id = ?;", (seller_id,))
    if not seller:
        return None
    if user_id not in (seller["owner_user_id"], seller["created_by_user_id"]):
        return None
    return seller


# ------------------------------------------------------------------
# 👤 پروفایل من (buyer profile: name + city only)
# ------------------------------------------------------------------
@router.callback_query(F.data == "myprofile")
async def handle_my_profile(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await ensure_user(callback.from_user)
    user = await db.fetchone(
        """SELECT u.*, c.name AS city_name FROM users u
           LEFT JOIN cities c ON c.id = u.city_id WHERE u.id = ?;""",
        (user_id,),
    )
    name = " ".join(filter(None, [user["first_name"], user["last_name"]])) or "کاربر ارزانکده"
    text = f"👤 <b>پروفایل من</b>\n\nنام: {name}\n"
    if user["username"]:
        text += f"نام کاربری: @{user['username']}\n"
    text += f"{EMOJI_CITY} شهر من: {user['city_name'] or 'ثبت نشده'}\n"
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📍 تغییر شهر", callback_data="setcity"))
    kb_add_back(b, "account")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


async def _count_events(event_type: str, entity_type: str, entity_id: int) -> int:
    row = await db.fetchone(
        "SELECT COUNT(*) AS c FROM events WHERE event_type=? AND entity_type=? AND entity_id=?;",
        (event_type, entity_type, entity_id),
    )
    return row["c"] if row else 0


# ------------------------------------------------------------------
# 📊 وضعیت فروشگاه
# ------------------------------------------------------------------
@router.callback_query(F.data == "storestatus")
async def handle_store_status(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await ensure_user(callback.from_user)
    seller_id = await resolve_single_seller_or_show_picker(
        callback, user_id, "storestat", "کدوم فروشگاهت رو می‌خوای ببینی؟"
    )
    if seller_id:
        await _render_store_status(callback, seller_id)


@router.callback_query(F.data.startswith("storestat:"))
async def handle_store_status_picked(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    seller_id = parse_int(callback.data.split(":")[1])
    user_id = await ensure_user(callback.from_user)
    if seller_id is None or not await _check_seller_ownership(user_id, seller_id):
        await callback.answer("⚠️ شما به این فروشگاه دسترسی ندارید.", show_alert=True)
        return
    await _render_store_status(callback, seller_id)


async def _render_store_status(callback: CallbackQuery, seller_id: int) -> None:
    seller = await db.fetchone("SELECT * FROM sellers WHERE id = ?;", (seller_id,))
    if not seller:
        await callback.answer("⚠️ این فروشگاه یافت نشد.", show_alert=True)
        return
    is_active = bool(seller["is_active"]) if seller["is_active"] is not None else True
    fav_count = await count_seller_favorites(seller_id)
    ig_clicks = await _count_events("instagram_click", "seller", seller_id)
    tg_clicks = await _count_events("telegram_click", "seller", seller_id)
    wa_clicks = await _count_events("whatsapp_click", "seller", seller_id)
    row = await db.fetchone(
        "SELECT COALESCE(SUM(views), 0) AS total FROM products WHERE seller_id = ?;", (seller_id,)
    )
    active_label = "🟢 فعال" if is_active else "🔴 غیرفعال"
    text = (
        f"🏪 <b>وضعیت فروشگاهت</b>\n\n"
        f"وضعیت فعلی: {active_label}\n\n"
        f"👀 بازدید فروشگاه: {seller['views']}\n"
        f"❤️ ذخیره‌ها: {fav_count}\n"
        f"📦 بازدید محصولات: {row['total']}\n"
        f"📸 کلیک Instagram: {ig_clicks}\n"
        f"✈️ کلیک Telegram: {tg_clicks}\n"
        f"🟢 کلیک WhatsApp: {wa_clicks}\n"
    )
    b = InlineKeyboardBuilder()
    toggle_label = "🔴 غیرفعال کردن فروشگاه" if is_active else "🟢 فعال کردن فروشگاه"
    b.row(InlineKeyboardButton(text=toggle_label, callback_data=f"storetoggle:{seller_id}"))
    kb_add_back(b, "account")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("storetoggle:"))
async def handle_store_toggle_active(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    seller_id = parse_int(callback.data.split(":")[1])
    if seller_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    user_id = await ensure_user(callback.from_user)
    seller = await _check_seller_ownership(user_id, seller_id)
    if not seller:
        await callback.answer("⚠️ شما به این فروشگاه دسترسی ندارید.", show_alert=True)
        return

    current_active = bool(seller["is_active"]) if seller["is_active"] is not None else True
    new_active = not current_active
    await db.execute(
        "UPDATE sellers SET is_active = ?, updated_at = ? WHERE id = ?;",
        (1 if new_active else 0, now_iso(), seller_id),
    )
    await log_audit(user_id, "store_activated" if new_active else "store_deactivated", "seller", seller_id)
    await callback.answer("🟢 فروشگاهت فعال شد." if new_active else "🔴 فروشگاهت غیرفعال شد.")
    await _render_store_status(callback, seller_id)


# ------------------------------------------------------------------
# 🏪 فروشگاه من (editor)
# ------------------------------------------------------------------
SHOP_EDITABLE_FIELDS = {
    "name": "🏷️ نام فروشگاه",
    "description": "📝 معرفی کوتاه فروشگاه",
    "logo_url": "🖼️ لینک تصویر/لوگوی فروشگاه",
    "instagram": "📸 آیدی اینستاگرام (بدون @)",
    "telegram": "📢 آیدی کانال/ربات تلگرام (بدون @)",
    "telegram_support": "💬 آیدی تلگرام پشتیبانی فروشگاه (بدون @)",
    "whatsapp": "🟢 شماره واتساپ",
    "website": "🌐 آدرس وبسایت",
    "phone": "📞 شماره تماس",
    "location_text": "📍 لوکیشن (آدرس یا توضیح مکان)",
    "coverage_area": "🗺️ محدوده کاری",
}


@router.callback_query(F.data == "myshop")
async def handle_my_shop(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await ensure_user(callback.from_user)
    seller_id = await resolve_single_seller_or_show_picker(
        callback, user_id, "shopview", "کدوم فروشگاهت رو می‌خوای مدیریت کنی؟"
    )
    if seller_id:
        await _render_shop_view(callback, seller_id)


@router.callback_query(F.data.startswith("shopview:"))
async def handle_shop_view_picked(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    seller_id = parse_int(callback.data.split(":")[1])
    user_id = await ensure_user(callback.from_user)
    if seller_id is None or not await _check_seller_ownership(user_id, seller_id):
        await callback.answer("⚠️ شما به این فروشگاه دسترسی ندارید.", show_alert=True)
        return
    await _render_shop_view(callback, seller_id)


async def _render_shop_view(callback: CallbackQuery, seller_id: int) -> None:
    seller = await db.fetchone(
        """SELECT s.*, c.name AS city_name FROM sellers s
           LEFT JOIN cities c ON c.id = s.city_id WHERE s.id = ?;""",
        (seller_id,),
    )
    if not seller:
        await callback.answer("⚠️ این فروشگاه یافت نشد.", show_alert=True)
        return

    has_contact = any([seller["instagram"], seller["telegram"], seller["whatsapp"]])
    lines = [
        f"🏪 <b>{seller['name']}</b>",
        "",
        seller["description"] or "بدون توضیحات",
        "",
        f"📸 اینستاگرام: {seller['instagram'] or '—'}",
        f"📢 کانال/ربات تلگرام: {seller['telegram'] or '—'}",
        f"💬 پشتیبانی تلگرام: {seller['telegram_support'] or '—'}",
        f"🟢 واتساپ: {seller['whatsapp'] or '—'}",
        f"🌐 وبسایت: {seller['website'] or '—'}",
        f"📞 تلفن: {seller['phone'] or '—'}",
        f"📍 لوکیشن: {seller['location_text'] or '—'}",
        f"🗺️ محدوده کاری: {seller['coverage_area'] or '—'}",
        f"🏙️ شهر: {seller['city_name'] or '—'}",
    ]
    if not has_contact:
        lines.append(
            "\n⚠️ حداقل یکی از اینستاگرام، تلگرام یا واتساپ رو تکمیل کن تا خریدارها بتونن باهات در ارتباط باشن."
        )

    b = InlineKeyboardBuilder()
    for field, label in SHOP_EDITABLE_FIELDS.items():
        b.button(text=label, callback_data=f"shopedit:{seller_id}:{field}")
    b.button(text="🏙️ شهر", callback_data=f"shopcity:{seller_id}")
    b.adjust(2)
    kb_add_back(b, "account")
    await safe_edit(callback, "\n".join(lines), b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("shopedit:"))
async def handle_shop_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return
    seller_id, field = parse_int(parts[1]), parts[2]
    if seller_id is None or field not in SHOP_EDITABLE_FIELDS:
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return
    user_id = await ensure_user(callback.from_user)
    if not await _check_seller_ownership(user_id, seller_id):
        await callback.answer("⚠️ شما به این فروشگاه دسترسی ندارید.", show_alert=True)
        return
    await state.update_data(shop_edit_seller_id=seller_id, shop_edit_field=field)
    await state.set_state(ShopEditStates.waiting_value)
    b = InlineKeyboardBuilder()
    await safe_edit(callback, f"{SHOP_EDITABLE_FIELDS[field]} رو بفرست:", b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("shopcity:"))
async def handle_shop_city_start(callback: CallbackQuery, state: FSMContext) -> None:
    seller_id = parse_int(callback.data.split(":")[1])
    if seller_id is None:
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return
    user_id = await ensure_user(callback.from_user)
    if not await _check_seller_ownership(user_id, seller_id):
        await callback.answer("⚠️ شما به این فروشگاه دسترسی ندارید.", show_alert=True)
        return
    await state.update_data(shop_edit_seller_id=seller_id, shop_edit_field="city")
    await state.set_state(ShopEditStates.waiting_value)
    cities = await db.fetchall("SELECT id, name FROM cities ORDER BY name;")
    b = InlineKeyboardBuilder()
    for c in cities:
        b.button(text=c["name"], callback_data=f"pickcity:{c['id']}")
    b.adjust(3)
    kb_add_back(b, f"shopview:{seller_id}")
    await safe_edit(callback, f"{EMOJI_CITY} شهر فروشگاه رو انتخاب کن:", b.as_markup())
    await callback.answer()


@router.message(StateFilter(ShopEditStates.waiting_value))
async def handle_shop_edit_value(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    data = await state.get_data()
    seller_id, field = data.get("shop_edit_seller_id"), data.get("shop_edit_field")
    await state.clear()
    if not seller_id or field not in SHOP_EDITABLE_FIELDS:
        await message.answer("⚠️ فرآیند ویرایش منقضی شده. لطفاً دوباره تلاش کن.")
        return

    user_id = await ensure_user(message.from_user)
    seller = await _check_seller_ownership(user_id, seller_id)
    if not seller:
        await message.answer("⚠️ شما به این فروشگاه دسترسی ندارید.")
        return

    value = (message.text or "").strip()
    if field == "name" and not value:
        await message.answer("⚠️ نام فروشگاه نمی‌تواند خالی باشد.")
        return
    value_to_store = value or None

    # `field` is validated against the fixed SHOP_EDITABLE_FIELDS whitelist
    # above BEFORE this f-string is ever built -- never derived from raw
    # user input, so this is safe (see ensure_column() for the same pattern).
    await db.execute(
        f"UPDATE sellers SET {field} = ?, updated_at = ? WHERE id = ?;",
        (value_to_store, now_iso(), seller_id),
    )
    await log_audit(user_id, "shop_field_updated", "seller", seller_id, details=field)
    await message.answer("✅ به‌روزرسانی شد.")

    # "اگر فروشنده Telegram را انتخاب کرد: هر دو فیلد Telegram اجباری باشند."
    if field == "telegram" and value_to_store and not seller["telegram_support"]:
        await state.update_data(shop_edit_seller_id=seller_id, shop_edit_field="telegram_support")
        await state.set_state(ShopEditStates.waiting_value)
        await message.answer(
            "چون کانال/ربات تلگرام رو وارد کردی، آیدی تلگرام پشتیبانی هم لازمه:\n"
            f"{SHOP_EDITABLE_FIELDS['telegram_support']} رو بفرست:"
        )


# ------------------------------------------------------------------
# 📦 محصولات (list with per-card ✏️/🗑️, add, edit, delete-with-confirm)
# ------------------------------------------------------------------
@router.callback_query(F.data == "myproducts")
async def handle_my_products(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await ensure_user(callback.from_user)
    seller_id = await resolve_single_seller_or_show_picker(
        callback, user_id, "prodlist", "کدوم فروشگاهت رو می‌خوای مدیریت کنی؟"
    )
    if seller_id:
        await _render_product_list(callback, seller_id)


@router.callback_query(F.data.startswith("prodlist:"))
async def handle_product_list_picked(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    seller_id = parse_int(callback.data.split(":")[1])
    user_id = await ensure_user(callback.from_user)
    if seller_id is None or not await _check_seller_ownership(user_id, seller_id):
        await callback.answer("⚠️ شما به این فروشگاه دسترسی ندارید.", show_alert=True)
        return
    await _render_product_list(callback, seller_id)


_STOCK_LABELS = {"AVAILABLE": "موجود", "OUT_OF_STOCK": "ناموجود", "PREORDER": "پیش‌فروش"}


async def _render_product_list(callback: CallbackQuery, seller_id: int) -> None:
    products = await db.fetchall(
        "SELECT * FROM products WHERE seller_id = ? ORDER BY created_at DESC;", (seller_id,)
    )
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ افزودن محصول", callback_data=f"prodadd:{seller_id}"))
    if not products:
        text = (
            "📦 محصولاتت رو اینجا مدیریت کن\n"
            "هر محصولی داری اضافه کن تا مشتری‌ها راحت‌تر پیداش کنن. ✨\n\n"
            "هنوز محصولی اضافه نکردی."
        )
    else:
        text = "📦 محصولاتت رو اینجا مدیریت کن\nهر محصولی داری اضافه کن تا مشتری‌ها راحت‌تر پیداش کنن. ✨"
        for p in products:
            stock = _STOCK_LABELS.get(p["stock_status"], p["stock_status"])
            b.row(InlineKeyboardButton(
                text=f"🛍️ {p['name']} — {format_price(p['price'])} ({stock})",
                callback_data=f"product:{p['id']}",
            ))
            b.row(
                InlineKeyboardButton(text="✏️ ویرایش", callback_data=f"prodedit:{p['id']}"),
                InlineKeyboardButton(text="🗑️ حذف", callback_data=f"proddel:{p['id']}"),
            )
    kb_add_back(b, "account")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("prodadd:"))
async def handle_product_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    seller_id = parse_int(callback.data.split(":")[1])
    if seller_id is None:
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return
    user_id = await ensure_user(callback.from_user)
    if not await _check_seller_ownership(user_id, seller_id):
        await callback.answer("⚠️ شما به این فروشگاه دسترسی ندارید.", show_alert=True)
        return
    await state.update_data(prodadd_seller_id=seller_id)
    await state.set_state(ProductAddStates.waiting_name)
    b = InlineKeyboardBuilder()
    await safe_edit(callback, "نام محصول رو بفرست:", b.as_markup())
    await callback.answer()


@router.message(StateFilter(ProductAddStates.waiting_name))
async def handle_product_add_name(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("⚠️ نام نمی‌تواند خالی باشد. دوباره بفرست:")
        return
    await state.update_data(prodadd_name=name)
    await state.set_state(ProductAddStates.waiting_description)
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="رد کردن", callback_data="prodaddskip:description"))
    await message.answer("توضیح کوتاه محصول (اختیاری):", reply_markup=b.as_markup())


@router.message(StateFilter(ProductAddStates.waiting_description))
async def handle_product_add_description(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    await state.update_data(prodadd_description=(message.text or "").strip() or None)
    await state.set_state(ProductAddStates.waiting_price)
    await message.answer(f"{EMOJI_PRICE} قیمت محصول رو بفرست (فقط عدد، تومان):")


@router.message(StateFilter(ProductAddStates.waiting_price))
async def handle_product_add_price(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    price = parse_int((message.text or "").strip().replace(",", ""))
    if price is None or price < 0:
        await message.answer("⚠️ لطفاً فقط عدد قیمت رو بفرست (مثلاً 250000):")
        return
    await state.update_data(prodadd_price=price)
    await state.set_state(ProductAddStates.waiting_old_price)
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="رد کردن", callback_data="prodaddskip:old_price"))
    await message.answer("قیمت قبل از تخفیف (اختیاری):", reply_markup=b.as_markup())


@router.message(StateFilter(ProductAddStates.waiting_old_price))
async def handle_product_add_old_price(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    old_price = parse_int((message.text or "").strip().replace(",", ""))
    await state.update_data(prodadd_old_price=old_price)
    await state.set_state(ProductAddStates.waiting_image_url)
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="رد کردن", callback_data="prodaddskip:image_url"))
    await message.answer("لینک تصویر محصول (اختیاری):", reply_markup=b.as_markup())


@router.message(StateFilter(ProductAddStates.waiting_image_url))
async def handle_product_add_image(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    await state.update_data(prodadd_image_url=(message.text or "").strip() or None)
    await _finish_product_add(message.from_user, state, message=message)


@router.callback_query(F.data.startswith("prodaddskip:"))
async def handle_product_add_skip(callback: CallbackQuery, state: FSMContext) -> None:
    field = callback.data.split(":", 1)[1]
    if field == "old_price":
        await state.update_data(prodadd_old_price=None)
        await state.set_state(ProductAddStates.waiting_image_url)
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="رد کردن", callback_data="prodaddskip:image_url"))
        await safe_edit(callback, "لینک تصویر محصول (اختیاری):", b.as_markup())
        await callback.answer()
    elif field == "image_url":
        await state.update_data(prodadd_image_url=None)
        await _finish_product_add(callback.from_user, state, callback=callback)
    else:
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)


async def _finish_product_add(
    tg_user, state: FSMContext, callback: Optional[CallbackQuery] = None, message: Optional[Message] = None
) -> None:
    user_id = await ensure_user(tg_user)
    data = await state.get_data()
    await state.clear()
    seller_id, name = data.get("prodadd_seller_id"), data.get("prodadd_name")

    if not seller_id or not name:
        text = "⚠️ اطلاعات محصول ناقص است. لطفاً دوباره از «📦 محصولات» تلاش کن."
        if callback:
            await safe_edit(callback, text, InlineKeyboardBuilder().as_markup())
        elif message:
            await message.answer(text)
        return

    now = now_iso()
    cur = await db.execute(
        """INSERT INTO products (seller_id, name, description, price, old_price, image_url,
               stock_status, rating, review_count, views, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'AVAILABLE', 0, 0, 0, ?, ?);""",
        (
            seller_id, name, data.get("prodadd_description"), data.get("prodadd_price"),
            data.get("prodadd_old_price"), data.get("prodadd_image_url"), now, now,
        ),
    )
    product_id = cur.lastrowid
    await log_audit(user_id, "product_created", "product", product_id, details=name)

    text = f"✅ محصول «{name}» اضافه شد."
    b = InlineKeyboardBuilder()
    kb_add_back(b, "myproducts")
    if callback:
        await safe_edit(callback, text, b.as_markup())
        await callback.answer()
    elif message:
        await message.answer(text, reply_markup=b.as_markup())


PRODUCT_EDITABLE_FIELDS = {
    "name": "🏷️ نام محصول",
    "description": "📝 توضیحات محصول",
    "price": f"{EMOJI_PRICE} قیمت (فقط عدد)",
    "old_price": "💸 قیمت قبل از تخفیف (فقط عدد، یا «حذف» برای پاک کردن)",
    "image_url": "🖼️ لینک تصویر محصول",
}


@router.callback_query(F.data.startswith("prodedit:"))
async def handle_product_edit_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    product_id = parse_int(callback.data.split(":")[1])
    if product_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    product = await db.fetchone("SELECT * FROM products WHERE id = ?;", (product_id,))
    if not product:
        await callback.answer("⚠️ این محصول یافت نشد.", show_alert=True)
        return
    user_id = await ensure_user(callback.from_user)
    if not await _check_seller_ownership(user_id, product["seller_id"]):
        await callback.answer("⚠️ شما به این محصول دسترسی ندارید.", show_alert=True)
        return

    b = InlineKeyboardBuilder()
    for field, label in PRODUCT_EDITABLE_FIELDS.items():
        b.button(text=label, callback_data=f"prodfield:{product_id}:{field}")
    b.button(text="📦 وضعیت موجودی", callback_data=f"prodstock:{product_id}")
    b.adjust(2)
    kb_add_back(b, "myproducts")
    await safe_edit(callback, f"✏️ ویرایش «{product['name']}»\nکدوم بخش رو می‌خوای تغییر بدی؟", b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("prodfield:"))
async def handle_product_field_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return
    product_id, field = parse_int(parts[1]), parts[2]
    if product_id is None or field not in PRODUCT_EDITABLE_FIELDS:
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return
    product = await db.fetchone("SELECT * FROM products WHERE id = ?;", (product_id,))
    user_id = await ensure_user(callback.from_user)
    if not product or not await _check_seller_ownership(user_id, product["seller_id"]):
        await callback.answer("⚠️ شما به این محصول دسترسی ندارید.", show_alert=True)
        return
    await state.update_data(prodedit_product_id=product_id, prodedit_field=field)
    await state.set_state(ProductEditStates.waiting_value)
    b = InlineKeyboardBuilder()
    await safe_edit(callback, f"{PRODUCT_EDITABLE_FIELDS[field]} رو بفرست:", b.as_markup())
    await callback.answer()


@router.message(StateFilter(ProductEditStates.waiting_value))
async def handle_product_field_edit_value(message: Message, state: FSMContext) -> None:
    if await restart_requested(message, state):
        return
    data = await state.get_data()
    product_id, field = data.get("prodedit_product_id"), data.get("prodedit_field")
    await state.clear()
    if not product_id or field not in PRODUCT_EDITABLE_FIELDS:
        await message.answer("⚠️ فرآیند ویرایش منقضی شده. لطفاً دوباره تلاش کن.")
        return

    product = await db.fetchone("SELECT * FROM products WHERE id = ?;", (product_id,))
    user_id = await ensure_user(message.from_user)
    if not product or not await _check_seller_ownership(user_id, product["seller_id"]):
        await message.answer("⚠️ شما به این محصول دسترسی ندارید.")
        return

    raw = (message.text or "").strip()
    if field in ("price", "old_price"):
        if field == "old_price" and raw in ("حذف", "-", "0", ""):
            value = None
        else:
            value = parse_int(raw.replace(",", ""))
            if value is None or value < 0:
                await message.answer("⚠️ لطفاً فقط عدد بفرست:")
                return
    elif field == "name":
        if not raw:
            await message.answer("⚠️ نام نمی‌تواند خالی باشد:")
            return
        value = raw
    else:
        value = raw or None

    # `field` is validated against the fixed PRODUCT_EDITABLE_FIELDS
    # whitelist above BEFORE this f-string is built -- never derived from
    # raw user input (same safe pattern as ensure_column()/shop editing).
    await db.execute(
        f"UPDATE products SET {field} = ?, updated_at = ? WHERE id = ?;",
        (value, now_iso(), product_id),
    )
    await log_audit(user_id, "product_updated", "product", product_id, details=field)
    await message.answer("✅ محصول به‌روزرسانی شد.")


@router.callback_query(F.data.startswith("prodstock:"))
async def handle_product_stock_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    product_id = parse_int(callback.data.split(":")[1])
    if product_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    product = await db.fetchone("SELECT * FROM products WHERE id = ?;", (product_id,))
    user_id = await ensure_user(callback.from_user)
    if not product or not await _check_seller_ownership(user_id, product["seller_id"]):
        await callback.answer("⚠️ شما به این محصول دسترسی ندارید.", show_alert=True)
        return
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ موجود", callback_data=f"prodstockset:{product_id}:AVAILABLE"))
    b.row(InlineKeyboardButton(text="⛔️ ناموجود", callback_data=f"prodstockset:{product_id}:OUT_OF_STOCK"))
    b.row(InlineKeyboardButton(text="⏳ پیش‌فروش", callback_data=f"prodstockset:{product_id}:PREORDER"))
    kb_add_back(b, f"prodedit:{product_id}")
    await safe_edit(callback, "وضعیت موجودی رو انتخاب کن:", b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("prodstockset:"))
async def handle_product_stock_set(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return
    product_id, status = parse_int(parts[1]), parts[2]
    if product_id is None or status not in _STOCK_LABELS:
        await callback.answer("⚠️ درخواست نامعتبر است.", show_alert=True)
        return
    product = await db.fetchone("SELECT * FROM products WHERE id = ?;", (product_id,))
    user_id = await ensure_user(callback.from_user)
    if not product or not await _check_seller_ownership(user_id, product["seller_id"]):
        await callback.answer("⚠️ شما به این محصول دسترسی ندارید.", show_alert=True)
        return
    await db.execute(
        "UPDATE products SET stock_status = ?, updated_at = ? WHERE id = ?;", (status, now_iso(), product_id)
    )
    await log_audit(user_id, "product_updated", "product", product_id, details="stock_status")
    await callback.answer("✅ وضعیت موجودی به‌روزرسانی شد.")


@router.callback_query(F.data.startswith("proddel:"))
async def handle_product_delete_confirm_screen(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    product_id = parse_int(callback.data.split(":")[1])
    if product_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    product = await db.fetchone("SELECT * FROM products WHERE id = ?;", (product_id,))
    user_id = await ensure_user(callback.from_user)
    if not product or not await _check_seller_ownership(user_id, product["seller_id"]):
        await callback.answer("⚠️ شما به این محصول دسترسی ندارید.", show_alert=True)
        return
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="❌ نه، برگرد", callback_data="proddelno"))
    b.row(InlineKeyboardButton(text="🗑️ آره، حذفش کن", callback_data=f"proddelyes:{product_id}"))
    await safe_edit(
        callback,
        f"🗑️ حذف «{product['name']}»؟\nمطمئنی می‌خوای این محصول رو حذف کنی؟",
        b.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "proddelno")
async def handle_product_delete_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("باشه، چیزی حذف نشد 🙂")
    await handle_my_products(callback, state)


@router.callback_query(F.data.startswith("proddelyes:"))
async def handle_product_delete_confirmed(callback: CallbackQuery, state: FSMContext) -> None:
    product_id = parse_int(callback.data.split(":")[1])
    if product_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    product = await db.fetchone("SELECT * FROM products WHERE id = ?;", (product_id,))
    user_id = await ensure_user(callback.from_user)
    if not product or not await _check_seller_ownership(user_id, product["seller_id"]):
        await callback.answer("⚠️ شما به این محصول دسترسی ندارید.", show_alert=True)
        return
    await db.execute("DELETE FROM products WHERE id = ?;", (product_id,))
    await log_audit(user_id, "product_deleted", "product", product_id, details=product["name"])
    await callback.answer("🗑️ محصول حذف شد.")
    await handle_my_products(callback, state)


# ------------------------------------------------------------------
# 📈 آمار (aggregate + per-product)
# ------------------------------------------------------------------
@router.callback_query(F.data == "mystats")
async def handle_my_stats(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await ensure_user(callback.from_user)
    seller_id = await resolve_single_seller_or_show_picker(
        callback, user_id, "statshome", "کدوم فروشگاهت رو می‌خوای ببینی؟"
    )
    if seller_id:
        await _render_stats_home(callback, seller_id)


@router.callback_query(F.data.startswith("statshome:"))
async def handle_stats_home_picked(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    seller_id = parse_int(callback.data.split(":")[1])
    user_id = await ensure_user(callback.from_user)
    if seller_id is None or not await _check_seller_ownership(user_id, seller_id):
        await callback.answer("⚠️ شما به این فروشگاه دسترسی ندارید.", show_alert=True)
        return
    await _render_stats_home(callback, seller_id)


async def _render_stats_home(callback: CallbackQuery, seller_id: int) -> None:
    products = await db.fetchall(
        "SELECT * FROM products WHERE seller_id = ? ORDER BY views DESC;", (seller_id,)
    )
    seller = await db.fetchone("SELECT * FROM sellers WHERE id = ?;", (seller_id,))
    fav_count = await count_seller_favorites(seller_id)
    total_product_views = sum(p["views"] for p in products)
    active_products = sum(1 for p in products if p["stock_status"] == "AVAILABLE")
    request_row = await db.fetchone("SELECT COUNT(*) AS c FROM requests WHERE seller_id = ?;", (seller_id,))
    text = (
        f"📈 <b>آمار فروشگاه</b>\n\n"
        f"👀 بازدید فروشگاه: {seller['views']}\n"
        f"❤️ ذخیره فروشگاه: {fav_count}\n"
        f"📦 مجموع بازدید محصولات: {total_product_views}\n"
        f"🛍️ تعداد محصولات: {len(products)}\n"
        f"✅ محصولات موجود (فعال): {active_products}\n"
        f"📋 تعداد درخواست‌های ثبت‌شده: {request_row['c'] if request_row else 0}\n"
    )
    if products:
        text += "\nبرای دیدن آمار هر محصول، روی اسمش بزن:"
    b = InlineKeyboardBuilder()
    for p in products[:PAGE_SIZE_LIST]:
        b.row(InlineKeyboardButton(text=f"📊 {p['name']}", callback_data=f"statsprod:{p['id']}"))
    kb_add_back(b, "account")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("statsprod:"))
async def handle_stats_product(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    product_id = parse_int(callback.data.split(":")[1])
    if product_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    product = await db.fetchone("SELECT * FROM products WHERE id = ?;", (product_id,))
    user_id = await ensure_user(callback.from_user)
    if not product or not await _check_seller_ownership(user_id, product["seller_id"]):
        await callback.answer("⚠️ شما به این محصول دسترسی ندارید.", show_alert=True)
        return
    fav_row = await db.fetchone("SELECT COUNT(*) AS c FROM favorites WHERE product_id = ?;", (product_id,))
    # Instagram/Telegram/WhatsApp click buttons currently live on the
    # SELLER card, not per product, so per-product click counts are
    # always 0 in the current schema. Shown anyway for the exact field
    # list the spec asked for, with an honest 0 rather than omitting it.
    text = (
        f"📊 <b>{product['name']}</b>\n\n"
        f"👀 بازدید: {product['views']}\n"
        f"❤️ ذخیره: {fav_row['c']}\n"
        f"📸 کلیک Instagram: 0\n"
        f"✈️ کلیک Telegram: 0\n"
        f"🟢 کلیک WhatsApp: 0\n"
    )
    b = InlineKeyboardBuilder()
    kb_add_back(b, "mystats")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "reflist")
async def handle_referral_list(callback: CallbackQuery) -> None:
    user_id = await ensure_user(callback.from_user)
    sellers = await get_sellers_owned_by_user(user_id)
    if not sellers:
        await callback.answer("⚠️ شما هنوز فروشگاهی ثبت نکرده‌اید.", show_alert=True)
        return
    if len(sellers) == 1:
        await _render_referral_stats(callback, sellers[0]["id"])
        return
    b = InlineKeyboardBuilder()
    for s in sellers:
        b.row(InlineKeyboardButton(text=f"{EMOJI_SELLERS} {s['name']}", callback_data=f"refstats:{s['id']}"))
    kb_add_back(b, "account")
    await safe_edit(callback, "کدوم فروشگاهت رو می‌خوای ببینی؟", b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("refstats:"))
async def handle_referral_stats(callback: CallbackQuery) -> None:
    seller_id = parse_int(callback.data.split(":")[1])
    if seller_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    await _render_referral_stats(callback, seller_id)


async def _render_referral_stats(callback: CallbackQuery, seller_id: int) -> None:
    user_id = await ensure_user(callback.from_user)
    seller = await db.fetchone(
        "SELECT id, name, owner_user_id, created_by_user_id FROM sellers WHERE id = ?;",
        (seller_id,),
    )
    if not seller:
        await callback.answer("⚠️ این فروشگاه یافت نشد.", show_alert=True)
        return
    if seller["owner_user_id"] != user_id and seller["created_by_user_id"] != user_id:
        await callback.answer("⚠️ شما به این فروشگاه دسترسی ندارید.", show_alert=True)
        return

    me = await callback.bot.get_me()
    text = await referral_stats_text(me.username, seller["id"], seller["name"])
    b = InlineKeyboardBuilder()
    kb_add_back(b, "account")
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

    if current_state == ShopEditStates.waiting_value.state:
        data = await state.get_data()
        if data.get("shop_edit_field") == "city":
            seller_id = data.get("shop_edit_seller_id")
            await state.clear()
            seller = await _check_seller_ownership(user_id, seller_id) if seller_id else None
            if not seller:
                await callback.answer("⚠️ شما به این فروشگاه دسترسی ندارید.", show_alert=True)
                return
            await db.execute(
                "UPDATE sellers SET city_id = ?, updated_at = ? WHERE id = ?;", (city_id, now_iso(), seller_id)
            )
            await log_audit(user_id, "shop_field_updated", "seller", seller_id, details="city")
            await callback.answer(f"شهر فروشگاه به {city['name']} تغییر کرد ✅")
            await _render_shop_view(callback, seller_id)
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


@router.callback_query(F.data == "compare")
async def handle_compare_legacy_redirect(callback: CallbackQuery, state: FSMContext) -> None:
    """Old callback_data kept working (in case it's cached in an old
    message's keyboard) -- just forwards to the real comparelist screen."""
    await handle_compare_list(callback, state)


@router.callback_query(F.data == "comparelist")
async def handle_compare_list(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = await ensure_user(callback.from_user)

    if not await has_seen_compare_intro(user_id):
        await mark_compare_intro_seen(user_id)
        b = InlineKeyboardBuilder()
        kb_add_back(b, "main")
        await safe_edit(callback, COMPARE_INTRO_TEXT, b.as_markup())
        await callback.answer()
        return

    selection = get_compare_selection(user_id)
    if not selection:
        b = InlineKeyboardBuilder()
        kb_add_back(b, "main")
        await safe_edit(
            callback,
            f"{EMOJI_COMPARE} هنوز محصولی برای مقایسه انتخاب نکردی.\n\nاز روی صفحه هر محصول، دکمه «افزودن به مقایسه» رو بزن.",
            b.as_markup(),
        )
        await callback.answer()
        return

    products = []
    for pid in selection:
        row = await db.fetchone(
            """SELECT p.*, s.name AS seller_name FROM products p
               JOIN sellers s ON s.id = p.seller_id WHERE p.id = ?;""",
            (pid,),
        )
        if row:
            products.append(row)

    if len(products) < len(selection):
        # A previously-selected product was removed/deleted since being added.
        set_compare_selection(user_id, [p["id"] for p in products])

    if len(products) < COMPARE_MAX_ITEMS:
        b = InlineKeyboardBuilder()
        for p in products:
            b.row(InlineKeyboardButton(text=f"❌ حذف {p['name']}", callback_data=f"comparedrop:{p['id']}"))
        kb_add_back(b, "main")
        await safe_edit(
            callback,
            f"{EMOJI_COMPARE} یک محصول دیگر انتخاب کن.\n\nانتخاب فعلی:\n" + "\n".join(f"• {p['name']}" for p in products),
            b.as_markup(),
        )
        await callback.answer()
        return

    a, b_ = products[0], products[1]
    lines = [
        f"{EMOJI_COMPARE} <b>مقایسه دو محصول</b>",
        "",
        f"🛍️ <b>{a['name']}</b>  ⚔️  <b>{b_['name']}</b>",
        f"{EMOJI_PRICE} {format_price(a['price'])}  |  {format_price(b_['price'])}",
        f"{EMOJI_RATING} {a['rating']:.1f} ({a['review_count']} نظر)  |  {b_['rating']:.1f} ({b_['review_count']} نظر)",
        f"🏪 {a['seller_name']}  |  {b_['seller_name']}",
    ]
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=f"🛍️ {a['name']}", callback_data=f"product:{a['id']}"))
    kb.row(InlineKeyboardButton(text=f"🛍️ {b_['name']}", callback_data=f"product:{b_['id']}"))
    kb.row(InlineKeyboardButton(text="🔄 شروع مقایسه جدید", callback_data="comparereset"))
    kb_add_back(kb, "main")
    await safe_edit(callback, "\n".join(lines), kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("comparestart:"))
async def handle_compare_start(callback: CallbackQuery) -> None:
    product_id = parse_int(callback.data.split(":")[1])
    if product_id is None:
        await callback.answer("⚠️ شناسه نامعتبر است.", show_alert=True)
        return
    product = await db.fetchone("SELECT id FROM products WHERE id = ?;", (product_id,))
    if not product:
        await callback.answer("⚠️ این محصول یافت نشد.", show_alert=True)
        return

    user_id = await ensure_user(callback.from_user)
    if not await has_seen_compare_intro(user_id):
        await mark_compare_intro_seen(user_id)
        await callback.answer(COMPARE_INTRO_TEXT, show_alert=True)

    selection = get_compare_selection(user_id)
    new_selection, outcome = compare_add(selection, product_id)
    set_compare_selection(user_id, new_selection)

    if outcome == "already_in_selection":
        await callback.answer("این محصول قبلاً به مقایسه اضافه شده.", show_alert=True)
    elif outcome == "already_full":
        await callback.answer("مقایسه همزمان فقط برای ۲ محصول امکان‌پذیره.", show_alert=True)
    elif outcome == "added_ready":
        await log_event(user_id, "compare_add", "product", product_id)
        await callback.answer("✅ اضافه شد! حالا می‌تونی مقایسه رو ببینی.", show_alert=True)
    else:
        await log_event(user_id, "compare_add", "product", product_id)
        await callback.answer("✅ اضافه شد! یک محصول دیگه هم انتخاب کن.", show_alert=True)


@router.callback_query(F.data.startswith("comparedrop:"))
async def handle_compare_drop(callback: CallbackQuery, state: FSMContext) -> None:
    product_id = parse_int(callback.data.split(":")[1])
    user_id = await ensure_user(callback.from_user)
    if product_id is not None:
        selection = [pid for pid in get_compare_selection(user_id) if pid != product_id]
        set_compare_selection(user_id, selection)
    await callback.answer()
    await handle_compare_list(callback, state)


@router.callback_query(F.data == "comparereset")
async def handle_compare_reset(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = await ensure_user(callback.from_user)
    clear_compare_selection(user_id)
    await callback.answer("مقایسه پاک شد.")
    await handle_compare_list(callback, state)


AD_TYPES = {
    "featured_product": {
        "label": "🔥 نمایش ویژه محصول",
        "what": "محصول انتخابی‌ات در بالای لیست دسته‌بندی و نتایج جستجوی مرتبط نمایش داده می‌شود.",
        "where": "در صفحه دسته‌بندی محصول و نتایج جستجوهای مرتبط.",
        "why": "دیده شدن بیشتر یعنی بازدید و شانس فروش بیشتر برای همان محصول.",
        "pay_for": "بابت مدت‌زمان نمایش ویژه (روزانه) پرداخت می‌کنی.",
    },
    "featured_seller": {
        "label": "⭐ نمایش ویژه فروشگاه",
        "what": "فروشگاهت در بخش «فروشندگان برتر» و لیست فروشگاه‌ها بالاتر نمایش داده می‌شود.",
        "where": "در «فروشندگان برتر» و لیست عمومی فروشگاه‌ها.",
        "why": "بازدیدکننده‌های بیشتری قبل از دیدن رقبا، فروشگاهت رو می‌بینن.",
        "pay_for": "بابت مدت‌زمان نمایش ویژه (روزانه) پرداخت می‌کنی.",
    },
    "regional_ad": {
        "label": "📍 تبلیغ منطقه‌ای",
        "what": "فروشگاه/محصولت به‌طور خاص برای کاربرانی که همون شهر/منطقه رو انتخاب کردن نمایش ویژه می‌گیره.",
        "where": "در بخش «نزدیک من» و نتایج مرتبط با همون شهر.",
        "why": "برای کسب‌وکارهای محلی، مشتری‌های واقعاً نزدیک‌تر رو هدف می‌گیره.",
        "pay_for": "بابت مدت‌زمان نمایش ویژه در همون منطقه پرداخت می‌کنی.",
    },
    "intro_feature": {
        "label": "🏠 معرفی ویژه",
        "what": "معرفی کامل‌تر فروشگاهت (با توضیح بیشتر) در بخش‌های معرفی‌شده‌ی ربات قرار می‌گیره.",
        "where": "در بخش‌های کشف محتوا مثل «انتخاب ارزانکده».",
        "why": "برای فروشگاه‌های تازه‌کار، دیده شدن اولیه رو سریع‌تر می‌کنه.",
        "pay_for": "بابت یک بار معرفی ویژه (نه نمایش مستمر) پرداخت می‌کنی.",
    },
}


@router.callback_query(F.data == "ads")
async def handle_ads(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await ensure_user(callback.from_user)
    text = (
        f"{EMOJI_ADS} <b>تبلیغات در ارزانکده</b>\n\n"
        "این تبلیغات مخصوص دیده شدن بیشتر داخل مارکت‌پلیس و ربات ارزانکده است "
        "(نه تبلیغ کانال). روی هر گزینه بزن تا دقیقاً ببینی شامل چی می‌شه."
    )
    b = InlineKeyboardBuilder()
    for code, info in AD_TYPES.items():
        b.row(InlineKeyboardButton(text=info["label"], callback_data=f"adtype:{code}"))
    kb_add_back(b, "account")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("adtype:"))
async def handle_ad_type_detail(callback: CallbackQuery) -> None:
    code = callback.data.split(":", 1)[1]
    info = AD_TYPES.get(code)
    if not info:
        await callback.answer("⚠️ این نوع تبلیغ یافت نشد.", show_alert=True)
        return
    text = (
        f"{info['label']}\n\n"
        f"❓ این تبلیغ دقیقاً چیست؟\n{info['what']}\n\n"
        f"📍 کجا نمایش داده می‌شود؟\n{info['where']}\n\n"
        f"✨ چه چیزی باعث بیشتر دیده شدن می‌شود؟\n{info['why']}\n\n"
        f"💰 فروشنده بابت چه چیزی پول می‌دهد؟\n{info['pay_for']}\n\n"
        "هیچ قیمتی در این مرحله حدس زده نمی‌شود؛ برای قیمت و هماهنگی پرداخت با پشتیبانی ارزانکده در ارتباط باش."
    )
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💬 درخواست این تبلیغ", callback_data=f"adconfirm:{code}"))
    kb_add_back(b, "ads")
    await safe_edit(callback, text, b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("adconfirm:"))
async def handle_ad_confirm(callback: CallbackQuery) -> None:
    code = callback.data.split(":", 1)[1]
    info = AD_TYPES.get(code)
    if not info:
        await callback.answer("⚠️ این نوع تبلیغ یافت نشد.", show_alert=True)
        return

    user_id = await ensure_user(callback.from_user)
    if await has_open_request(user_id, "ad", topic=info["label"]):
        await callback.answer("درخواست تبلیغاتی قبلی‌ات برای همین نوع هنوز تعیین تکلیف نشده.", show_alert=True)
        return

    sellers = await get_sellers_owned_by_user(user_id)
    seller_id = sellers[0]["id"] if sellers else None

    request_id = await create_request(user_id, "ad", topic=info["label"], seller_id=seller_id)
    await log_audit(user_id, "ad_request_created", "request", request_id, details=code)

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🟢 تأیید درخواست", callback_data=f"adminreq:approve:{request_id}"),
        InlineKeyboardButton(text="🔴 رد درخواست", callback_data=f"adminreq:reject:{request_id}"),
    )
    await send_admin_dm(
        callback.bot,
        f"📢 درخواست تبلیغات جدید\nنوع: {info['label']}\n(کاربر داخلی #{user_id}"
        + (f"، فروشگاه #{seller_id}" if seller_id else "") + ")",
        reply_markup=b.as_markup(),
    )

    b2 = InlineKeyboardBuilder()
    kb_add_back(b2, "account")
    await safe_edit(
        callback,
        f"✅ درخواست «{info['label']}» ثبت شد.\n\n"
        "💬 برای قیمت و هماهنگی پرداخت با پشتیبانی ارزانکده در ارتباط باش.\n"
        "می‌تونی وضعیت درخواستت رو از «📋 درخواست‌های من» پیگیری کنی.",
        b2.as_markup(),
    )
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
async def handle_register_skip(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
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
        await _finish_register_seller(callback.from_user, state, bot, callback=callback)
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
async def handle_register_website(message: Message, state: FSMContext, bot: Bot) -> None:
    if await restart_requested(message, state):
        return
    await state.update_data(seller_website=(message.text or "").strip())
    await _finish_register_seller(message.from_user, state, bot, message=message)


async def _finish_register_seller(
    tg_user,
    state: FSMContext,
    bot: Bot,
    callback: Optional[CallbackQuery] = None,
    message: Optional[Message] = None,
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
    cur = await db.execute(
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
    seller_id = cur.lastrowid

    # Referral / growth system: give the seller their shareable link right
    # away, per the "🎁 فروشگاهت در ارزانکده ثبت شد!" flow.
    me = await bot.get_me()
    referral_block = await referral_stats_text(me.username, seller_id, name)
    text = "🎁 فروشگاهت در ارزانکده ثبت شد!\n\n" + referral_block

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
    user_id = await ensure_user(message.from_user)
    await _handle_referral_deep_link(message, user_id)
    await send_main_menu(message)


async def _handle_referral_deep_link(message: Message, user_id: int) -> None:
    """Parses an optional '/start shop_<seller_id>' deep-link payload and
    attributes the visit as a referral. Never raises -- a malformed or
    missing payload just means "no referral", /start still works exactly
    as before."""
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        return
    match = REFERRAL_DEEP_LINK_RE.match(parts[1].strip())
    if not match:
        return
    seller_id = int(match.group(1))

    seller = await db.fetchone("SELECT id, owner_user_id FROM sellers WHERE id = ?;", (seller_id,))
    if not seller:
        return
    if seller["owner_user_id"] == user_id:
        return  # a seller visiting their own link is not a referral

    recorded = await record_referral_if_new(seller_id, user_id)
    if recorded and seller["owner_user_id"]:
        await notify_user(
            seller["owner_user_id"],
            "🎉 معرفی جدید",
            "یک کاربر جدید از طریق لینک اختصاصی فروشگاه شما وارد ارزانکده شد!",
            ntype="referral",
        )


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
# BACKUP
# ======================================================================
BACKUP_DIR = os.getenv("BACKUP_DIR", "backups")
BACKUP_KEEP_COUNT = int(os.getenv("BACKUP_KEEP_COUNT", "7") or "7")
BACKUP_INTERVAL_HOURS = float(os.getenv("BACKUP_INTERVAL_HOURS", "24") or "24")


def backup_filename(when: Optional[datetime] = None) -> str:
    when = when or datetime.now(timezone.utc)
    return f"backup_{when.strftime('%Y-%m-%d')}.db"


def prune_old_backups(backup_dir: str = BACKUP_DIR, keep: int = BACKUP_KEEP_COUNT) -> list:
    """Deletes the oldest backup_*.db files beyond `keep`, sorted by
    filename (safe because backup_filename() is YYYY-MM-DD, so
    alphabetical order == chronological order). Returns the list of
    deleted filenames. Never raises -- a pruning failure must not affect
    the backup that was just taken."""
    deleted = []
    try:
        if not os.path.isdir(backup_dir) or keep <= 0:
            return deleted
        files = sorted(f for f in os.listdir(backup_dir) if f.startswith("backup_") and f.endswith(".db"))
        for f in files[:-keep] if len(files) > keep else []:
            os.remove(os.path.join(backup_dir, f))
            deleted.append(f)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to prune old backups: %s", exc)
    return deleted


async def backup_database() -> Optional[str]:
    """Creates a safe, internally-consistent SQLite backup using SQLite's
    own `VACUUM INTO` (a proper hot-backup mechanism -- safe to run even
    while the bot is actively reading/writing, unlike a raw file copy
    which could catch a write mid-transaction). Then prunes old backups
    beyond BACKUP_KEEP_COUNT. Never raises: a failed backup is logged and
    must never crash or interrupt the running bot."""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        path = os.path.join(BACKUP_DIR, backup_filename())
        if os.path.exists(path):
            os.remove(path)  # VACUUM INTO refuses to overwrite an existing file
        await db.execute("VACUUM INTO ?;", (path,))
        logger.info("Database backup created: %s", path)
        prune_old_backups()
        return path
    except Exception as exc:  # noqa: BLE001 - a failed backup must never crash the bot
        logger.error("Database backup failed: %s", exc)
        return None


async def periodic_backup_task() -> None:
    """Background task: takes one backup immediately, then one every
    BACKUP_INTERVAL_HOURS. Started once in main() and naturally stops
    when the bot process exits."""
    await backup_database()
    while True:
        await asyncio.sleep(BACKUP_INTERVAL_HOURS * 3600)
        await backup_database()


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

    backup_task = asyncio.create_task(periodic_backup_task())

    try:
        logger.info("Bot is running.")
        await dp.start_polling(bot)
    finally:
        backup_task.cancel()
        await on_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
