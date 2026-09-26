# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Local search engine and search handlers
"""

import re
import time
from dataclasses import dataclass
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StateFilter
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..constants import (
    EMOJI_CITY,
    EMOJI_PRODUCT,
    EMOJI_SEARCH,
    PAGE_SIZE_LIST,
)
from ..database import CATEGORY_TREE, CITY_NAMES, db
from ..keyboards import kb_add_back, kb_pagination_row
from ..states import SearchStates
from ..utils import (
    ensure_user,
    format_price,
    log_event,
    parse_int,
    restart_requested,
    safe_edit,
)


router = Router(name="search")


# ======================================================================
# LOCAL SEARCH ENGINE
# ======================================================================

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_ASCII_DIGITS = "0123456789"

_PUNCTUATION_CHARS = "،؛؟!.,:;()[]{}«»\"'؟?/\\"

_DIGIT_LETTER_MAP = {
    **{
        ch: _ASCII_DIGITS[i]
        for i, ch in enumerate(_PERSIAN_DIGITS)
    },
    **{
        ch: _ASCII_DIGITS[i]
        for i, ch in enumerate(_ARABIC_DIGITS)
    },
    "ي": "ی",
    "ك": "ک",
    "ة": "ه",
    "ۀ": "ه",
    "إ": "ا",
    "أ": "ا",
}


def normalize_persian_text(text: str) -> str:
    if not text:
        return ""

    output = []

    for char in text:
        if char in _DIGIT_LETTER_MAP:
            output.append(_DIGIT_LETTER_MAP[char])
        elif char == "\u200c" or char in _PUNCTUATION_CHARS:
            output.append(" ")
        else:
            output.append(char)

    return re.sub(
        r"\s+",
        " ",
        "".join(output),
    ).strip()


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
    "مردونه": "مردانه",
    "مردانه": "مردانه",
    "زنونه": "زنانه",
    "زنانه": "زنانه",
    "دخترونه": "دخترانه",
    "دخترانه": "دخترانه",
    "پسرونه": "پسرانه",
    "پسرانه": "پسرانه",
    "بچگونه": "بچگانه",
    "بچگانه": "بچگانه",
}


_COLOR_WORDS = [
    "سفید",
    "مشکی",
    "قرمز",
    "آبی",
    "سبز",
    "زرد",
    "صورتی",
    "بنفش",
    "طلایی",
    "نقره‌ای",
    "قهوه‌ای",
    "خاکستری",
    "نارنجی",
    "کرم",
]


_STOPWORDS = [
    "می خوام",
    "میخوام",
    "میخواستم",
    "می خواستم",
    "دنبال",
    "برای من",
    "برام",
    "لطفا",
    "لطفاً",
    "میخوام که",
    "هست",
    "دارید",
    "دارین",
    "کنید",
    "میشه",
    "می شه",
    "یه",
    "یک",
    "رو",
    "را",
    "ممنون",
    "تو",
    "در",
    "توی",
    "داخل",
    "تومان",
    "تومن",
    "چی",
    "چیزی",
]


_NORMALIZED_CITY_NAMES = sorted(
    {
        normalize_persian_text(name)
        for name in CITY_NAMES
    },
    key=len,
    reverse=True,
)


_ALL_CATEGORY_NAMES = (
    [
        main_name
        for _main_emoji, main_name, _subs in CATEGORY_TREE
    ]
    + [
        sub_name
        for _main_emoji, _main_name, subs in CATEGORY_TREE
        for _sub_emoji, sub_name in subs
    ]
)


_SORTED_CATEGORY_NAMES = sorted(
    {
        normalize_persian_text(name)
        for name in _ALL_CATEGORY_NAMES
    },
    key=len,
    reverse=True,
)


_NORMALIZED_COLOR_WORDS = sorted(
    {
        normalize_persian_text(word)
        for word in _COLOR_WORDS
    },
    key=len,
    reverse=True,
)


_NORMALIZED_STOPWORDS = sorted(
    {
        normalize_persian_text(word)
        for word in _STOPWORDS
        if word.strip()
    },
    key=len,
    reverse=True,
)


_STOPWORD_PHRASES = sorted(
    (
        word
        for word in _NORMALIZED_STOPWORDS
        if " " in word
    ),
    key=len,
    reverse=True,
)


_STOPWORD_TOKENS = {
    word
    for word in _NORMALIZED_STOPWORDS
    if " " not in word
}


_PRICE_UNIT_RE = r"(\d+(?:\.\d+)?)\s*(میلیون|هزار)?"

_PRICE_RANGE_RE = re.compile(
    rf"بین\s+{_PRICE_UNIT_RE}\s+تا\s+{_PRICE_UNIT_RE}"
)

_PRICE_MAX_RE = re.compile(
    rf"(?:زیر|کمتر از|کمتر|حداکثر|تا)\s+{_PRICE_UNIT_RE}"
)

_PRICE_MIN_RE = re.compile(
    rf"(?:بالای|بیشتر از|بیشتر|حداقل|از)\s+{_PRICE_UNIT_RE}"
)


def _remove_stopwords(text: str) -> str:
    for phrase in _STOPWORD_PHRASES:
        text = re.sub(
            rf"\b{re.escape(phrase)}\b",
            " ",
            text,
        )

    tokens = [
        token
        for token in text.split()
        if token not in _STOPWORD_TOKENS
    ]

    return " ".join(tokens)


def _convert_number_unit(
    num_str: str,
    unit: Optional[str],
) -> float:
    value = float(num_str)

    if unit == "میلیون":
        value *= 1_000_000
    elif unit == "هزار":
        value *= 1_000

    return value


def _extract_price(text: str):
    match = _PRICE_RANGE_RE.search(text)

    if match:
        value_1 = _convert_number_unit(
            match.group(1),
            match.group(2),
        )
        value_2 = _convert_number_unit(
            match.group(3),
            match.group(4),
        )

        min_price, max_price = (
            (value_1, value_2)
            if value_1 <= value_2
            else (value_2, value_1)
        )

        text = (
            text[:match.start()]
            + " "
            + text[match.end():]
        )

        return min_price, max_price, text

    match = _PRICE_MAX_RE.search(text)

    if match:
        max_price = _convert_number_unit(
            match.group(1),
            match.group(2),
        )

        text = (
            text[:match.start()]
            + " "
            + text[match.end():]
        )

        return None, max_price, text

    match = _PRICE_MIN_RE.search(text)

    if match:
        min_price = _convert_number_unit(
            match.group(1),
            match.group(2),
        )

        text = (
            text[:match.start()]
            + " "
            + text[match.end():]
        )

        return min_price, None, text

    return None, None, text


@dataclass
class StructuredQuery:
    raw_query: str
    keyword: Optional[str] = None
    category: Optional[str] = None
    city: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    color: Optional[str] = None
    gender: Optional[str] = None

    def has_any_extracted_field(self) -> bool:
        return any(
            [
                self.category,
                self.city,
                self.min_price is not None,
                self.max_price is not None,
                self.color,
                self.gender,
            ]
        )

    def simplified(self) -> "StructuredQuery":
        return StructuredQuery(
            raw_query=self.raw_query,
            keyword=self.keyword,
            category=self.category,
        )


class QueryParser:
    def parse(
        self,
        raw_query: str,
    ) -> StructuredQuery:
        raise NotImplementedError


class LocalQueryParser(QueryParser):
    def parse(
        self,
        raw_query: str,
    ) -> StructuredQuery:
        original = (raw_query or "").strip()
        text = normalize_persian_text(original)

        for alt, canonical in ALT_CITY_SPELLINGS.items():
            text = text.replace(
                normalize_persian_text(alt),
                normalize_persian_text(canonical),
            )

        for alt, canonical in sorted(
            CATEGORY_SYNONYMS.items(),
            key=lambda item: -len(item[0]),
        ):
            text = text.replace(
                normalize_persian_text(alt),
                normalize_persian_text(canonical),
            )

        min_price, max_price, text = _extract_price(text)

        city = None

        for city_name in _NORMALIZED_CITY_NAMES:
            if city_name and city_name in text:
                city = city_name
                text = text.replace(
                    city_name,
                    " ",
                )
                break

        gender = None

        for alt, canonical in sorted(
            _GENDER_WORD_MAP.items(),
            key=lambda item: -len(item[0]),
        ):
            normalized_alt = normalize_persian_text(alt)

            if normalized_alt in text:
                gender = canonical
                text = text.replace(
                    normalized_alt,
                    " ",
                )
                break

        color = None

        for color_name in _NORMALIZED_COLOR_WORDS:
            if color_name and color_name in text:
                color = color_name
                text = text.replace(
                    color_name,
                    " ",
                )
                break

        category = None

        for category_name in _SORTED_CATEGORY_NAMES:
            if category_name and category_name in text:
                category = category_name
                text = text.replace(
                    category_name,
                    " ",
                )
                break

        text = _remove_stopwords(text)

        keyword = (
            re.sub(
                r"\s+",
                " ",
                text,
            ).strip()
            or None
        )

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


def build_search_summary(
    structured_query: StructuredQuery,
) -> str:
    parts = [
        part
        for part in (
            structured_query.keyword,
            structured_query.category,
            structured_query.gender,
            structured_query.color,
        )
        if part
    ]

    first_line = (
        " • ".join(parts)
        if parts
        else structured_query.raw_query
    )

    lines = [
        f"{EMOJI_SEARCH} جستجو برای:",
        first_line,
    ]

    if (
        structured_query.min_price is not None
        and structured_query.max_price is not None
    ):
        lines.append(
            "بین "
            f"{format_price(structured_query.min_price)} "
            "تا "
            f"{format_price(structured_query.max_price)}"
        )

    elif structured_query.max_price is not None:
        lines.append(
            f"تا {format_price(structured_query.max_price)}"
        )

    elif structured_query.min_price is not None:
        lines.append(
            f"از {format_price(structured_query.min_price)}"
        )

    if structured_query.city:
        lines.append(
            f"{EMOJI_CITY} {structured_query.city}"
        )

    return "\n".join(lines)


def score_search_candidate(
    row,
    structured_query: StructuredQuery,
    resolved_category_ids: set,
    resolved_city_id,
) -> float:
    score = 0.0

    name = row["name"] or ""
    description = row["description"] or ""

    if (
        resolved_category_ids
        and row["category_id"] in resolved_category_ids
    ):
        score += 30

    if structured_query.keyword:
        if structured_query.keyword in name:
            score += 25
        elif structured_query.keyword in description:
            score += 10

    for term in (
        structured_query.color,
        structured_query.gender,
    ):
        if term and (
            term in name
            or term in description
        ):
            score += 8

    if (
        resolved_city_id
        and row["seller_city_id"] == resolved_city_id
    ):
        score += 15

    price = row["price"]

    if price is not None:
        if (
            structured_query.min_price is not None
            and price < structured_query.min_price
        ):
            score -= 20

        if (
            structured_query.max_price is not None
            and price > structured_query.max_price
        ):
            score -= 20

        elif (
            structured_query.min_price is not None
            or structured_query.max_price is not None
        ):
            score += 10

    rating = row["rating"] or 0
    review_count = row["review_count"] or 0
    views = row["views"] or 0

    score += min(rating, 5) * 2
    score += min(review_count, 50) * 0.1
    score += min(views, 500) * 0.01

    return score


async def resolve_category_ids(
    name: Optional[str],
) -> set:
    if not name:
        return set()

    like = f"%{name.strip()}%"

    rows = await db.fetchall(
        """
        SELECT id, parent_id
        FROM categories
        WHERE name LIKE ?
        LIMIT 5;
        """,
        (like,),
    )

    ids = set()

    for row in rows:
        ids.add(row["id"])

        if row["parent_id"] is None:
            children = await db.fetchall(
                """
                SELECT id
                FROM categories
                WHERE parent_id = ?;
                """,
                (row["id"],),
            )

            ids.update(
                child["id"]
                for child in children
            )

    return ids


async def resolve_city_id(
    name: Optional[str],
):
    if not name:
        return None

    like = f"%{name.strip()}%"

    row = await db.fetchone(
        """
        SELECT id
        FROM cities
        WHERE name LIKE ?
        LIMIT 1;
        """,
        (like,),
    )

    return row["id"] if row else None


async def plain_keyword_search(
    query: str,
    limit: int = 20,
) -> list:
    like = f"%{query}%"

    return await db.fetchall(
        """
        SELECT DISTINCT p.*
        FROM products p
        JOIN sellers s
            ON s.id = p.seller_id
        LEFT JOIN categories c
            ON c.id = p.category_id
        WHERE p.name LIKE ?
           OR p.description LIKE ?
           OR s.name LIKE ?
           OR s.description LIKE ?
           OR c.name LIKE ?
        ORDER BY p.views DESC
        LIMIT ?;
        """,
        (
            like,
            like,
            like,
            like,
            like,
            limit,
        ),
    )


class SearchEngine:
    def __init__(
        self,
        parser: QueryParser,
    ):
        self.parser = parser

    async def _structured_search(
        self,
        structured_query: StructuredQuery,
        limit: int = 30,
    ) -> list:
        resolved_category_ids = (
            await resolve_category_ids(
                structured_query.category
            )
        )

        resolved_city_id = await resolve_city_id(
            structured_query.city
        )

        conditions = []
        params: list = []

        if resolved_category_ids:
            placeholders = ",".join(
                "?"
                for _ in resolved_category_ids
            )

            conditions.append(
                f"p.category_id IN ({placeholders})"
            )

            params.extend(
                resolved_category_ids
            )

        if resolved_city_id:
            conditions.append(
                "s.city_id = ?"
            )
            params.append(
                resolved_city_id
            )

        for term in (
            structured_query.keyword,
            structured_query.color,
            structured_query.gender,
        ):
            if term:
                like = f"%{term}%"

                conditions.append(
                    """
                    (
                        p.name LIKE ?
                        OR p.description LIKE ?
                    )
                    """
                )

                params.extend(
                    [
                        like,
                        like,
                    ]
                )

        if structured_query.max_price is not None:
            conditions.append(
                """
                (
                    p.price IS NOT NULL
                    AND p.price <= ?
                )
                """
            )
            params.append(
                structured_query.max_price
            )

        if structured_query.min_price is not None:
            conditions.append(
                """
                (
                    p.price IS NOT NULL
                    AND p.price >= ?
                )
                """
            )
            params.append(
                structured_query.min_price
            )

        where_clause = (
            " AND ".join(conditions)
            if conditions
            else "1=1"
        )

        query = (
            "SELECT p.*, "
            "s.name AS seller_name, "
            "s.city_id AS seller_city_id "
            "FROM products p "
            "JOIN sellers s "
            "ON s.id = p.seller_id "
            f"WHERE {where_clause} "
            "ORDER BY p.views DESC "
            "LIMIT 200;"
        )

        rows = await db.fetchall(
            query,
            params,
        )

        scored = [
            (
                score_search_candidate(
                    row,
                    structured_query,
                    resolved_category_ids,
                    resolved_city_id,
                ),
                row,
            )
            for row in rows
        ]

        scored.sort(
            key=lambda pair: pair[0],
            reverse=True,
        )

        return [
            row
            for _score, row in scored[:limit]
        ]

    async def search(
        self,
        raw_query: str,
    ):
        structured = self.parser.parse(
            raw_query
        )

        if structured.has_any_extracted_field():
            results = await self._structured_search(
                structured
            )

            if results:
                return (
                    structured,
                    results,
                    "structured",
                )

            simplified = structured.simplified()

            if (
                simplified != structured
                and simplified.has_any_extracted_field()
            ):
                results = await self._structured_search(
                    simplified
                )

                if results:
                    return (
                        simplified,
                        results,
                        "structured",
                    )

        plain_results = await plain_keyword_search(
            raw_query
        )

        return (
            structured,
            plain_results,
            "plain",
        )


search_engine = SearchEngine(
    LocalQueryParser()
)


# ======================================================================
# SEARCH HANDLERS
# ======================================================================

@router.callback_query(F.data == "search")
async def handle_search_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await ensure_user(
        callback.from_user
    )

    await state.set_state(
        SearchStates.waiting_query
    )

    builder = InlineKeyboardBuilder()
    kb_add_back(
        builder,
        "main",
    )

    await safe_edit(
        callback,
        (
            f"{EMOJI_SEARCH} دنبال چه چیزی می‌گردی؟"
            "\n\n"
            "متن جستجو را بفرست:"
        ),
        builder.as_markup(),
    )

    await callback.answer()


def _cleanup_search_cache(
    now: Optional[float] = None,
) -> None:
    if now is None:
        now = time.monotonic()

    expired_users = [
        user_id
        for user_id, entry in _search_result_cache.items()
        if now - entry["created_at"] > SEARCH_CACHE_TTL_SECONDS
    ]

    for user_id in expired_users:
        _search_result_cache.pop(
            user_id,
            None,
        )

    if len(_search_result_cache) <= SEARCH_CACHE_MAX_USERS:
        return

    overflow = (
        len(_search_result_cache)
        - SEARCH_CACHE_MAX_USERS
    )

    oldest_users = sorted(
        _search_result_cache.items(),
        key=lambda item: item[1]["created_at"],
    )[:overflow]

    for user_id, _entry in oldest_users:
        _search_result_cache.pop(
            user_id,
            None,
        )


SEARCH_CACHE_TTL_SECONDS = 15 * 60
SEARCH_CACHE_MAX_USERS = 1000

_search_result_cache: dict[int, dict] = {}


async def _render_search_results(
    target,
    header: str,
    products: list,
    page: int = 0,
) -> None:
    offset = page * PAGE_SIZE_LIST

    page_products = products[
        offset:offset + PAGE_SIZE_LIST
    ]

    has_next = (
        offset + PAGE_SIZE_LIST
        < len(products)
    )

    builder = InlineKeyboardBuilder()

    for product in page_products:
        builder.row(
            InlineKeyboardButton(
                text=(
                    f"{EMOJI_PRODUCT} "
                    f"{product['name']} - "
                    f"{format_price(product['price'])}"
                ),
                callback_data=(
                    f"product:{product['id']}"
                ),
            )
        )

    kb_pagination_row(
        builder,
        "searchpage",
        page,
        has_next,
    )

    kb_add_back(
        builder,
        "main",
    )

    if isinstance(target, CallbackQuery):
        await safe_edit(
            target,
            header,
            builder.as_markup(),
        )
        await target.answer()
    else:
        await target.answer(
            header,
            reply_markup=builder.as_markup(),
        )


async def _render_no_results(
    message: Message,
    text: str,
) -> None:
    builder = InlineKeyboardBuilder()

    kb_add_back(
        builder,
        "main",
    )

    await message.answer(
        text,
        reply_markup=builder.as_markup(),
    )


@router.message(
    StateFilter(SearchStates.waiting_query)
)
async def handle_search_query(
    message: Message,
    state: FSMContext,
) -> None:
    if await restart_requested(
        message,
        state,
    ):
        return

    user_id = await ensure_user(
        message.from_user
    )

    query = (
        message.text or ""
    ).strip()

    await state.clear()

    if not query:
        await message.answer(
            "⚠️ لطفاً یک متن معتبر برای جستجو بفرست."
        )
        return

    structured, products, mode = (
        await search_engine.search(query)
    )

    await log_event(
        user_id,
        "search",
        (
            "local_smart"
            if mode == "structured"
            else "query"
        ),
        None,
    )

    if not products:
        await _render_no_results(
            message,
            (
                f"🔎 نتیجه‌ای برای "
                f"«{query}» پیدا نشد."
            ),
        )
        return

    if mode == "structured":
        header = (
            build_search_summary(structured)
            + "\n\nنتایج:"
        )
    else:
        header = (
            f"🔎 نتایج جستجو برای "
            f"«{query}»:"
        )

    now = time.monotonic()

    _cleanup_search_cache(
        now
    )

    _search_result_cache[user_id] = {
        "header": header,
        "products": products,
        "created_at": now,
    }

    _cleanup_search_cache(
        now
    )

    await _render_search_results(
        message,
        header,
        products,
        page=0,
    )


@router.callback_query(
    F.data.startswith("searchpage:")
)
async def handle_search_page(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    page = parse_int(
        callback.data.split(":")[1]
    )

    if page is None or page < 0:
        await callback.answer(
            "⚠️ صفحه نامعتبر است.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(
        callback.from_user
    )

    now = time.monotonic()

    _cleanup_search_cache(
        now
    )

    cached = _search_result_cache.get(
        user_id
    )

    if not cached:
        await callback.answer(
            "⚠️ نتایج جستجو منقضی شده. "
            "دوباره جستجو کن.",
            show_alert=True,
        )
        return

    if now - cached["created_at"] > SEARCH_CACHE_TTL_SECONDS:
        _search_result_cache.pop(
            user_id,
            None,
        )

        await callback.answer(
            "⚠️ نتایج جستجو منقضی شده. "
            "دوباره جستجو کن.",
            show_alert=True,
        )
        return

    if page * PAGE_SIZE_LIST >= len(cached["products"]):
        await callback.answer(
            "⚠️ این صفحه وجود ندارد.",
            show_alert=True,
        )
        return

    await _render_search_results(
        callback,
        cached["header"],
        cached["products"],
        page=page,
    )