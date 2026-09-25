# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Shared constants
"""

# ---------------------------------------------------------------------------
# Roles / modes
# ---------------------------------------------------------------------------

ROLE_BUYER = "buyer"
ROLE_SELLER = "seller"
ROLE_ADMIN = "admin"

VALID_MODES = (
    ROLE_BUYER,
    ROLE_SELLER,
    ROLE_ADMIN,
)


# ---------------------------------------------------------------------------
# Seller states
# ---------------------------------------------------------------------------

SELLER_PENDING = "pending"
SELLER_APPROVED = "approved"
SELLER_REJECTED = "rejected"
SELLER_SUSPENDED = "suspended"

VALID_SELLER_STATES = (
    SELLER_PENDING,
    SELLER_APPROVED,
    SELLER_REJECTED,
    SELLER_SUSPENDED,
)


# ---------------------------------------------------------------------------
# General limits
# ---------------------------------------------------------------------------

PAGE_SIZE_CATEGORIES = 8
PAGE_SIZE_LIST = 8
TOP_LIST_LIMIT = 10

SUPPORT_MESSAGE_MAX_LEN = 4000


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

_UNSAFE_URL_CHARS = {
    "\n",
    "\r",
    "\t",
    " ",
    "<",
    ">",
    '"',
    "'",
    "`",
    "\\",
}

_DANGEROUS_URL_SCHEME_PREFIXES = (
    "javascript:",
    "data:",
    "vbscript:",
    "file:",
    "ftp:",
    "tg:",
)


# ---------------------------------------------------------------------------
# Seller/shop editable fields
# ---------------------------------------------------------------------------

SHOP_EDITABLE_FIELDS = {
    "name": "نام فروشگاه",
    "description": "توضیحات فروشگاه",
    "logo_url": "لینک لوگو",
    "instagram": "آیدی اینستاگرام",
    "telegram": "آیدی کانال/ربات تلگرام",
    "telegram_support": "آیدی تلگرام پشتیبانی",
    "whatsapp": "شماره واتساپ",
    "website": "وب‌سایت",
    "phone": "شماره تماس",
    "location_text": "آدرس / موقعیت",
    "coverage_area": "محدوده فعالیت",
}


# Explicit SQL statements.
#
# IMPORTANT:
# The field name must never come from raw user input.
# Callers must select one of these predefined statements by key.
# Values themselves are always passed through SQLite parameters.
SHOP_UPDATE_QUERIES = {
    "name": (
        "UPDATE sellers "
        "SET name = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
    "description": (
        "UPDATE sellers "
        "SET description = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
    "logo_url": (
        "UPDATE sellers "
        "SET logo_url = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
    "instagram": (
        "UPDATE sellers "
        "SET instagram = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
    "telegram": (
        "UPDATE sellers "
        "SET telegram = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
    "telegram_support": (
        "UPDATE sellers "
        "SET telegram_support = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
    "whatsapp": (
        "UPDATE sellers "
        "SET whatsapp = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
    "website": (
        "UPDATE sellers "
        "SET website = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
    "phone": (
        "UPDATE sellers "
        "SET phone = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
    "location_text": (
        "UPDATE sellers "
        "SET location_text = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
    "coverage_area": (
        "UPDATE sellers "
        "SET coverage_area = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
}


# ---------------------------------------------------------------------------
# Product editable fields
# ---------------------------------------------------------------------------

PRODUCT_EDITABLE_FIELDS = {
    "name": "نام محصول",
    "description": "توضیحات محصول",
    "price": "قیمت",
    "old_price": "قیمت قبلی",
    "image_url": "لینک تصویر",
}


PRODUCT_UPDATE_QUERIES = {
    "name": (
        "UPDATE products "
        "SET name = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
    "description": (
        "UPDATE products "
        "SET description = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
    "price": (
        "UPDATE products "
        "SET price = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
    "old_price": (
        "UPDATE products "
        "SET old_price = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
    "image_url": (
        "UPDATE products "
        "SET image_url = ?, updated_at = ? "
        "WHERE id = ?;"
    ),
}


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

EVENT_START = "start"
EVENT_SEARCH = "search"
EVENT_PRODUCT_VIEW = "product_view"
EVENT_SELLER_VIEW = "seller_view"
EVENT_FAVORITE_ADD = "favorite_add"
EVENT_FAVORITE_REMOVE = "favorite_remove"
EVENT_COMPARE_ADD = "compare_add"
EVENT_COMPARE_REMOVE = "compare_remove"
EVENT_ORDER_CREATE = "order_create"
EVENT_ORDER_STATUS = "order_status"
EVENT_CONTACT_SELLER = "contact_seller"
EVENT_SUPPORT = "support"
EVENT_AD_VIEW = "ad_view"
EVENT_AD_CLICK = "ad_click"


# ---------------------------------------------------------------------------
# Referral
# ---------------------------------------------------------------------------

REFERRAL_REWARD_INVITER = 1
REFERRAL_REWARD_INVITEE = 1

REFERRAL_DEEP_LINK_PREFIX = "ref_"


# ---------------------------------------------------------------------------
# Advertisement types
# ---------------------------------------------------------------------------

AD_TYPES = (
    "banner",
    "featured",
    "seller",
    "product",
)


# ---------------------------------------------------------------------------
# Generic status values
# ---------------------------------------------------------------------------

STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Miscellaneous UI text / markers
# ---------------------------------------------------------------------------

ADMIN_MODE_PLACEHOLDER_TEXT = "پنل مدیریت"


# ---------------------------------------------------------------------------
# Database / migration helpers
# ---------------------------------------------------------------------------

DATABASE_QUICK_CHECK_OK = "ok"


# ---------------------------------------------------------------------------
# Search / comparison
# ---------------------------------------------------------------------------

COMPARE_MAX_ITEMS = 4


# ---------------------------------------------------------------------------
# Pagination / navigation callback prefixes
# ---------------------------------------------------------------------------

CALLBACK_PREFIX_CATEGORY = "category:"
CALLBACK_PREFIX_PRODUCT = "product:"
CALLBACK_PREFIX_SELLER = "seller:"
CALLBACK_PREFIX_PAGE = "page:"
CALLBACK_PREFIX_COMPARE = "compare:"
CALLBACK_PREFIX_FAVORITE = "favorite:"
CALLBACK_PREFIX_REQUEST = "request:"
CALLBACK_PREFIX_AD = "ad:"