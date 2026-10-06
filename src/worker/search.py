# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Worker-side local search engine and search handlers.

This module intentionally does not import aiogram, sqlite,
aiosqlite, or the legacy bot package.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import re
import time
from typing import Any, Optional

from worker.state import (
    clear_state,
    ensure_state_table,
    get_state,
    set_state,
)


SEARCH_STATE = "search"
PAGE_SIZE = 8

SEARCH_MAX_QUERY_LENGTH = 120
SEARCH_MAX_QUERY_TOKENS = 12
SEARCH_MAX_REPEATED_CHARACTERS = 8

SEARCH_MAX_CANDIDATES = 200
SEARCH_RESULT_LIMIT = 30
SELLER_SEARCH_LIMIT = 10

TYPO_MIN_TOKEN_LENGTH = 4
TYPO_MAX_TOKEN_LENGTH = 32
TYPO_MAX_DISTANCE = 1
TYPO_MAX_FUZZY_TOKENS = 6
TYPO_MAX_COMPARISONS = 1200

SEARCH_CACHE_TTL_SECONDS = 15 * 60
SEARCH_CACHE_MAX_USERS = 1000


_search_result_cache: dict[int, dict[str, Any]] = {}


_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_ASCII_DIGITS = "0123456789"

_PUNCTUATION_CHARS = (
    "،؛؟!.,:;()[]{}«»\"'؟?/\\"
)

_DIGIT_LETTER_MAP = {
    **{
        char: _ASCII_DIGITS[index]
        for index, char in enumerate(
            _PERSIAN_DIGITS
        )
    },
    **{
        char: _ASCII_DIGITS[index]
        for index, char in enumerate(
            _ARABIC_DIGITS
        )
    },
    "ي": "ی",
    "ك": "ک",
    "ة": "ه",
    "ۀ": "ه",
    "إ": "ا",
    "أ": "ا",
}


def normalize_persian_text(
    text: str,
) -> str:
    if not text:
        return ""

    output: list[str] = []

    for char in text:
        if char in _DIGIT_LETTER_MAP:
            output.append(
                _DIGIT_LETTER_MAP[char]
            )
        elif (
            char == "\u200c"
            or char in _PUNCTUATION_CHARS
        ):
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


GENDER_WORD_MAP = {
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


COLOR_WORDS = [
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


STOPWORDS = [
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


_NORMALIZED_COLOR_WORDS = sorted(
    {
        normalize_persian_text(
            word
        )
        for word in COLOR_WORDS
    },
    key=len,
    reverse=True,
)


_NORMALIZED_STOPWORDS = sorted(
    {
        normalize_persian_text(word)
        for word in STOPWORDS
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


_PRICE_UNIT_RE = (
    r"(\d+(?:\.\d+)?)\s*(میلیون|هزار)?"
)


_PRICE_RANGE_RE = re.compile(
    rf"بین\s+{_PRICE_UNIT_RE}\s+تا\s+{_PRICE_UNIT_RE}"
)


_PRICE_MAX_RE = re.compile(
    rf"(?:زیر|کمتر از|کمتر|حداکثر|تا)\s+"
    rf"{_PRICE_UNIT_RE}"
)


_PRICE_MIN_RE = re.compile(
    rf"(?:بالای|بیشتر از|بیشتر|حداقل|از)\s+"
    rf"{_PRICE_UNIT_RE}"
)


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
            (
                self.category,
                self.city,
                self.min_price is not None,
                self.max_price is not None,
                self.color,
                self.gender,
            )
        )


def _now() -> float:
    return time.monotonic()


def _html(
    value: Any,
) -> str:
    if value is None:
        return ""

    return escape(
        str(value),
        quote=False,
    )


def _tokenize(
    text: str,
) -> list[str]:
    normalized = normalize_persian_text(
        text
    )

    if not normalized:
        return []

    return [
        token
        for token in normalized.split()
        if token
    ]


def _validate_search_query(
    raw_query: str,
) -> tuple[
    bool,
    str,
    Optional[str],
]:
    query = (
        raw_query or ""
    ).strip()

    if not query:
        return (
            False,
            "",
            "⚠️ لطفاً یک متن معتبر برای جستجو بفرست.",
        )

    if len(query) > SEARCH_MAX_QUERY_LENGTH:
        return (
            False,
            "",
            (
                "⚠️ متن جستجو خیلی طولانیه.\n"
                f"حداکثر {SEARCH_MAX_QUERY_LENGTH} "
                "کاراکتر مجازه."
            ),
        )

    normalized = normalize_persian_text(
        query
    )

    if not normalized:
        return (
            False,
            "",
            "⚠️ متن جستجو باید شامل حروف یا عدد باشه.",
        )

    tokens = normalized.split()

    if len(tokens) > SEARCH_MAX_QUERY_TOKENS:
        return (
            False,
            "",
            (
                "⚠️ عبارت جستجو خیلی شلوغه.\n"
                f"حداکثر {SEARCH_MAX_QUERY_TOKENS} "
                "کلمه وارد کن."
            ),
        )

    compact_alnum = "".join(
        char
        for char in normalized
        if char.isalnum()
    )

    if not compact_alnum:
        return (
            False,
            "",
            "⚠️ لطفاً یک عبارت واقعی برای جستجو وارد کن.",
        )

    repeated = re.search(
        rf"(.)\1{{{SEARCH_MAX_REPEATED_CHARACTERS - 1},}}",
        compact_alnum,
    )

    if repeated:
        return (
            False,
            "",
            "⚠️ عبارت جستجو معتبر نیست.",
        )

    return (
        True,
        normalized,
        None,
    )


def _remove_stopwords(
    text: str,
) -> str:
    for phrase in _STOPWORD_PHRASES:
        text = re.sub(
            rf"\b{re.escape(phrase)}\b",
            " ",
            text,
        )

    return " ".join(
        token
        for token in text.split()
        if token not in _STOPWORD_TOKENS
    )


def _convert_number_unit(
    value: str,
    unit: Optional[str],
) -> float:
    number = float(value)

    if unit == "میلیون":
        number *= 1_000_000
    elif unit == "هزار":
        number *= 1_000

    return number


def _extract_price(
    text: str,
) -> tuple[
    Optional[float],
    Optional[float],
    str,
]:
    match = _PRICE_RANGE_RE.search(
        text
    )

    if match:
        first = _convert_number_unit(
            match.group(1),
            match.group(2),
        )
        second = _convert_number_unit(
            match.group(3),
            match.group(4),
        )

        minimum = min(
            first,
            second,
        )
        maximum = max(
            first,
            second,
        )

        text = (
            text[:match.start()]
            + " "
            + text[match.end():]
        )

        return (
            minimum,
            maximum,
            text,
        )

    match = _PRICE_MAX_RE.search(
        text
    )

    if match:
        maximum = _convert_number_unit(
            match.group(1),
            match.group(2),
        )

        text = (
            text[:match.start()]
            + " "
            + text[match.end():]
        )

        return (
            None,
            maximum,
            text,
        )

    match = _PRICE_MIN_RE.search(
        text
    )

    if match:
        minimum = _convert_number_unit(
            match.group(1),
            match.group(2),
        )

        text = (
            text[:match.start()]
            + " "
            + text[match.end():]
        )

        return (
            minimum,
            None,
            text,
        )

    return (
        None,
        None,
        text,
    )


async def _category_names(
    db: Any,
) -> list[str]:
    rows = await db.fetchall(
        """
        SELECT name
        FROM categories
        ORDER BY id;
        """
    )

    return [
        normalize_persian_text(
            row["name"]
        )
        for row in rows
        if row.get("name")
    ]


async def _city_names(
    db: Any,
) -> list[str]:
    rows = await db.fetchall(
        """
        SELECT name
        FROM cities
        ORDER BY id;
        """
    )

    return [
        normalize_persian_text(
            row["name"]
        )
        for row in rows
        if row.get("name")
    ]


class LocalQueryParser:
    async def parse(
        self,
        db: Any,
        raw_query: str,
    ) -> StructuredQuery:
        original = (
            raw_query or ""
        ).strip()

        text = normalize_persian_text(
            original
        )

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

        minimum, maximum, text = _extract_price(
            text
        )

        city = None

        for city_name in sorted(
            await _city_names(db),
            key=len,
            reverse=True,
        ):
            if city_name and city_name in text:
                city = city_name
                text = text.replace(
                    city_name,
                    " ",
                )
                break

        gender = None

        for alt, canonical in sorted(
            GENDER_WORD_MAP.items(),
            key=lambda item: -len(item[0]),
        ):
            normalized_alt = normalize_persian_text(
                alt
            )

            if normalized_alt in text:
                gender = canonical
                text = text.replace(
                    normalized_alt,
                    " ",
                )
                break

        color = None

        for color_name in _NORMALIZED_COLOR_WORDS:
            if color_name in text:
                color = color_name
                text = text.replace(
                    color_name,
                    " ",
                )
                break

        category = None

        for category_name in sorted(
            set(await _category_names(db)),
            key=len,
            reverse=True,
        ):
            if category_name and category_name in text:
                category = category_name
                text = text.replace(
                    category_name,
                    " ",
                )
                break

        text = _remove_stopwords(
            text
        )

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
            min_price=minimum,
            max_price=maximum,
            color=color,
            gender=gender,
        )


def _keyword_tokens(
    structured: StructuredQuery,
) -> list[str]:
    if not structured.keyword:
        return []

    seen: set[str] = set()
    tokens: list[str] = []

    for token in _tokenize(
        structured.keyword
    ):
        if token in _STOPWORD_TOKENS:
            continue

        if token in seen:
            continue

        seen.add(token)
        tokens.append(token)

    return tokens


def _field_match_score(
    tokens: list[str],
    text: str,
    *,
    exact_phrase_score: float,
    token_score: float,
    all_tokens_bonus: float,
    partial_token_score: float = 0.0,
) -> float:
    if not tokens or not text:
        return 0.0

    normalized = normalize_persian_text(
        text
    )

    if not normalized:
        return 0.0

    score = 0.0

    phrase = " ".join(tokens)

    if phrase and phrase in normalized:
        score += exact_phrase_score

    text_tokens = set(
        _tokenize(normalized)
    )

    matched = 0

    for token in tokens:
        if token in text_tokens:
            score += token_score
            matched += 1
            continue

        if token in normalized:
            score += partial_token_score
            matched += 1

    if matched == len(tokens):
        score += all_tokens_bonus

    return score


def _levenshtein_distance(
    left: str,
    right: str,
    max_distance: int = TYPO_MAX_DISTANCE,
) -> int:
    if left == right:
        return 0

    if not left:
        return len(right)

    if not right:
        return len(left)

    if abs(
        len(left) - len(right)
    ) > max_distance:
        return max_distance + 1

    if len(left) > len(right):
        left, right = right, left

    previous = list(
        range(len(left) + 1)
    )

    for row_index, right_char in enumerate(
        right,
        start=1,
    ):
        current = [row_index]
        row_min = current[0]

        for col_index, left_char in enumerate(
            left,
            start=1,
        ):
            insertion = (
                current[col_index - 1]
                + 1
            )
            deletion = (
                previous[col_index]
                + 1
            )
            substitution = (
                previous[col_index - 1]
                + (left_char != right_char)
            )

            value = min(
                insertion,
                deletion,
                substitution,
            )

            current.append(value)
            row_min = min(
                row_min,
                value,
            )

        if row_min > max_distance:
            return max_distance + 1

        previous = current

    return previous[-1]


def _is_typo_match(
    query_token: str,
    candidate_token: str,
) -> bool:
    if (
        len(query_token)
        < TYPO_MIN_TOKEN_LENGTH
        or len(candidate_token)
        < TYPO_MIN_TOKEN_LENGTH
    ):
        return False

    if (
        len(query_token)
        > TYPO_MAX_TOKEN_LENGTH
        or len(candidate_token)
        > TYPO_MAX_TOKEN_LENGTH
    ):
        return False

    if query_token == candidate_token:
        return False

    if abs(
        len(query_token)
        - len(candidate_token)
    ) > TYPO_MAX_DISTANCE:
        return False

    return (
        _levenshtein_distance(
            query_token,
            candidate_token,
        )
        <= TYPO_MAX_DISTANCE
    )


def _fuzzy_token_score(
    query_tokens: list[str],
    text: str,
) -> float:
    if not query_tokens or not text:
        return 0.0

    text_tokens = _tokenize(text)

    if not text_tokens:
        return 0.0

    score = 0.0
    comparisons = 0
    fuzzy_tokens = 0

    for query_token in query_tokens:
        if fuzzy_tokens >= TYPO_MAX_FUZZY_TOKENS:
            break

        if not (
            TYPO_MIN_TOKEN_LENGTH
            <= len(query_token)
            <= TYPO_MAX_TOKEN_LENGTH
        ):
            continue

        for candidate_token in text_tokens:
            if (
                comparisons
                >= TYPO_MAX_COMPARISONS
            ):
                return score

            if not (
                TYPO_MIN_TOKEN_LENGTH
                <= len(candidate_token)
                <= TYPO_MAX_TOKEN_LENGTH
            ):
                continue

            comparisons += 1

            if _is_typo_match(
                query_token,
                candidate_token,
            ):
                score += 7.0
                fuzzy_tokens += 1
                break

    return score


def _row_fuzzy_score(
    row: dict[str, Any],
    query_tokens: list[str],
) -> float:
    if not query_tokens:
        return 0.0

    score = 0.0

    fields = (
        (
            row["name"] or "",
            1.0,
        ),
        (
            row["category_name"] or "",
            0.8,
        ),
        (
            row["seller_name"] or "",
            0.7,
        ),
        (
            row["description"] or "",
            0.3,
        ),
    )

    for value, weight in fields:
        score += (
            _fuzzy_token_score(
                query_tokens,
                value,
            )
            * weight
        )

    return score


def _score_product(
    row: dict[str, Any],
    structured: StructuredQuery,
    category_ids: set[int],
    city_id: int | None,
) -> float:
    score = 0.0

    name = normalize_persian_text(
        row["name"] or ""
    )
    description = normalize_persian_text(
        row["description"] or ""
    )
    seller_name = normalize_persian_text(
        row["seller_name"] or ""
    )
    category_name = normalize_persian_text(
        row["category_name"] or ""
    )

    tokens = _keyword_tokens(
        structured
    )

    if (
        category_ids
        and row["category_id"]
        in category_ids
    ):
        score += 35

    if structured.category:
        score += _field_match_score(
            [structured.category],
            category_name,
            exact_phrase_score=8,
            token_score=4,
            all_tokens_bonus=3,
            partial_token_score=2,
        )

    if tokens:
        score += _field_match_score(
            tokens,
            name,
            exact_phrase_score=32,
            token_score=13,
            all_tokens_bonus=18,
            partial_token_score=5,
        )

        score += _field_match_score(
            tokens,
            description,
            exact_phrase_score=8,
            token_score=4,
            all_tokens_bonus=6,
            partial_token_score=2,
        )

        score += _field_match_score(
            tokens,
            seller_name,
            exact_phrase_score=7,
            token_score=4,
            all_tokens_bonus=5,
            partial_token_score=2,
        )

    for term in (
        structured.color,
        structured.gender,
    ):
        if not term:
            continue

        normalized_term = normalize_persian_text(
            term
        )

        if normalized_term in name:
            score += 10

        if normalized_term in description:
            score += 4

    if city_id is not None:
        if row["city_id"] == city_id:
            score += 15

    score += min(
        float(row["rating"] or 0),
        5.0,
    ) * 1.5

    score += min(
        int(row["views"] or 0),
        10000,
    ) / 10000

    return score


async def _category_ids_for_name(
    db: Any,
    category_name: Optional[str],
) -> set[int]:
    if not category_name:
        return set()

    rows = await db.fetchall(
        """
        SELECT id
        FROM categories
        WHERE name = ?;
        """,
        (
            category_name,
        ),
    )

    return {
        int(row["id"])
        for row in rows
    }


async def _city_id_for_name(
    db: Any,
    city_name: Optional[str],
) -> int | None:
    if not city_name:
        return None

    row = await db.fetchone(
        """
        SELECT id
        FROM cities
        WHERE name = ?
        LIMIT 1;
        """,
        (
            city_name,
        ),
    )

    if row is None:
        return None

    return int(
        row["id"]
    )


async def _structured_search(
    db: Any,
    structured: StructuredQuery,
) -> list[dict[str, Any]]:
    category_ids = (
        await _category_ids_for_name(
            db,
            structured.category,
        )
    )

    city_id = (
        await _city_id_for_name(
            db,
            structured.city,
        )
    )

    conditions = [
        "COALESCE(s.is_active, 1) = 1"
    ]
    params: list[Any] = []

    if category_ids:
        placeholders = ",".join(
            "?"
            for _ in category_ids
        )

        conditions.append(
            f"p.category_id IN ({placeholders})"
        )

        params.extend(
            sorted(category_ids)
        )

    if city_id is not None:
        conditions.append(
            "s.city_id = ?"
        )
        params.append(
            city_id
        )

    if structured.min_price is not None:
        conditions.append(
            "p.price >= ?"
        )
        params.append(
            structured.min_price
        )

    if structured.max_price is not None:
        conditions.append(
            "p.price <= ?"
        )
        params.append(
            structured.max_price
        )

    tokens = _keyword_tokens(
        structured
    )

    if tokens:
        token_conditions = []

        for token in tokens:
            like = f"%{token}%"

            token_conditions.append(
                """
                (
                    p.name LIKE ?
                    OR p.description LIKE ?
                    OR s.name LIKE ?
                    OR c.name LIKE ?
                )
                """
            )

            params.extend(
                [
                    like,
                    like,
                    like,
                    like,
                ]
            )

        conditions.append(
            "("
            + " AND ".join(
                token_conditions
            )
            + ")"
        )

    where_clause = " AND ".join(
        conditions
    )

    rows = await db.fetchall(
        f"""
        SELECT
            p.*,
            s.name AS seller_name,
            s.city_id AS city_id,
            c.name AS category_name,
            city.name AS city_name
        FROM products p
        JOIN sellers s
            ON s.id = p.seller_id
        LEFT JOIN categories c
            ON c.id = p.category_id
        LEFT JOIN cities city
            ON city.id = s.city_id
        WHERE {where_clause}
        ORDER BY
            p.rating DESC,
            p.views DESC,
            p.id DESC
        LIMIT ?;
        """,
        params + [
            SEARCH_MAX_CANDIDATES
        ],
    )

    scored = []

    for row in rows:
        score = _score_product(
            row,
            structured,
            category_ids,
            city_id,
        )

        if score <= 0:
            continue

        scored.append(
            (
                score,
                row,
            )
        )

    scored.sort(
        key=lambda pair: (
            pair[0],
            float(
                pair[1]["rating"]
                or 0
            ),
            int(
                pair[1]["views"]
                or 0
            ),
            int(
                pair[1]["id"]
                or 0
            ),
        ),
        reverse=True,
    )

    return [
        row
        for _score, row in scored[
            :SEARCH_RESULT_LIMIT
        ]
    ]


async def _plain_search(
    db: Any,
    structured: StructuredQuery,
) -> list[dict[str, Any]]:
    tokens = _keyword_tokens(
        structured
    )

    if not tokens:
        return []

    conditions = []
    params: list[Any] = []

    for token in tokens:
        like = f"%{token}%"

        conditions.append(
            """
            (
                p.name LIKE ?
                OR p.description LIKE ?
                OR s.name LIKE ?
                OR c.name LIKE ?
            )
            """
        )

        params.extend(
            [
                like,
                like,
                like,
                like,
            ]
        )

    params.append(
        SEARCH_MAX_CANDIDATES
    )

    rows = await db.fetchall(
        """
        SELECT
            p.*,
            s.name AS seller_name,
            s.city_id AS city_id,
            c.name AS category_name,
            city.name AS city_name
        FROM products p
        JOIN sellers s
            ON s.id = p.seller_id
        LEFT JOIN categories c
            ON c.id = p.category_id
        LEFT JOIN cities city
            ON city.id = s.city_id
        WHERE
            COALESCE(s.is_active, 1) = 1
            AND (
                %s
            )
        ORDER BY
            p.rating DESC,
            p.views DESC,
            p.id DESC
        LIMIT ?;
        """
        % " AND ".join(
            conditions
        ),
        params,
    )

    return rows[
        :SEARCH_RESULT_LIMIT
    ]


async def _fuzzy_search(
    db: Any,
    structured: StructuredQuery,
) -> list[dict[str, Any]]:
    tokens = _keyword_tokens(
        structured
    )

    if not tokens:
        return []

    params = [
        SEARCH_MAX_CANDIDATES
    ]

    rows = await db.fetchall(
        """
        SELECT
            p.*,
            s.name AS seller_name,
            s.city_id AS city_id,
            c.name AS category_name,
            city.name AS city_name
        FROM products p
        JOIN sellers s
            ON s.id = p.seller_id
        LEFT JOIN categories c
            ON c.id = p.category_id
        LEFT JOIN cities city
            ON city.id = s.city_id
        WHERE
            COALESCE(s.is_active, 1) = 1
        ORDER BY
            p.rating DESC,
            p.views DESC,
            p.id DESC
        LIMIT ?;
        """,
        params,
    )

    scored = []

    for row in rows:
        score = _row_fuzzy_score(
            row,
            tokens,
        )

        if score <= 0:
            continue

        scored.append(
            (
                score,
                row,
            )
        )

    scored.sort(
        key=lambda pair: (
            pair[0],
            float(
                pair[1]["rating"]
                or 0
            ),
            int(
                pair[1]["views"]
                or 0
            ),
            int(
                pair[1]["id"]
                or 0
            ),
        ),
        reverse=True,
    )

    return [
        row
        for _score, row in scored[
            :SEARCH_RESULT_LIMIT
        ]
    ]


async def _search_products(
    db: Any,
    raw_query: str,
) -> tuple[
    StructuredQuery,
    list[dict[str, Any]],
    str,
]:
    parser = LocalQueryParser()

    structured = await parser.parse(
        db,
        raw_query,
    )

    if structured.has_any_extracted_field():
        rows = await _structured_search(
            db,
            structured,
        )

        if rows:
            return (
                structured,
                rows,
                "structured",
            )

    rows = await _plain_search(
        db,
        structured,
    )

    if rows:
        return (
            structured,
            rows,
            "plain",
        )

    rows = await _fuzzy_search(
        db,
        structured,
    )

    return (
        structured,
        rows,
        "fuzzy" if rows else "plain",
    )


def _seller_score(
    row: dict[str, Any],
    tokens: list[str],
) -> float:
    score = 0.0

    fields = (
        (
            row["name"] or "",
            20.0,
        ),
        (
            row["description"] or "",
            6.0,
        ),
        (
            row["city_name"] or "",
            4.0,
        ),
    )

    for value, weight in fields:
        normalized = normalize_persian_text(
            value
        )

        for token in tokens:
            if token in normalized:
                score += weight

    score += min(
        float(row["rating"] or 0),
        5.0,
    ) * 1.5

    score += min(
        int(row["views"] or 0),
        10000,
    ) / 10000

    return score


async def _search_sellers(
    db: Any,
    raw_query: str,
) -> list[dict[str, Any]]:
    normalized = normalize_persian_text(
        raw_query
    )

    tokens = [
        token
        for token in _tokenize(
            normalized
        )
        if token
        not in _STOPWORD_TOKENS
    ]

    if not tokens:
        return []

    conditions = []
    params: list[Any] = []

    for token in tokens:
        like = f"%{token}%"

        conditions.append(
            """
            (
                s.name LIKE ?
                OR s.description LIKE ?
                OR c.name LIKE ?
            )
            """
        )

        params.extend(
            [
                like,
                like,
                like,
            ]
        )

    params.append(
        SEARCH_MAX_CANDIDATES
    )

    rows = await db.fetchall(
        """
        SELECT
            s.*,
            c.name AS city_name
        FROM sellers s
        LEFT JOIN cities c
            ON c.id = s.city_id
        WHERE
            COALESCE(s.is_active, 1) = 1
            AND (
                %s
            )
        LIMIT ?;
        """
        % " OR ".join(
            conditions
        ),
        params,
    )

    scored = []

    for row in rows:
        score = _seller_score(
            row,
            tokens,
        )

        if score <= 0:
            continue

        scored.append(
            (
                score,
                row,
            )
        )

    scored.sort(
        key=lambda pair: (
            pair[0],
            float(
                pair[1]["rating"]
                or 0
            ),
            int(
                pair[1]["views"]
                or 0
            ),
            int(
                pair[1]["id"]
                or 0
            ),
        ),
        reverse=True,
    )

    return [
        row
        for _score, row in scored[
            :SELLER_SEARCH_LIMIT
        ]
    ]


def _format_price(
    value: Any,
) -> str:
    if value is None:
        return "قیمت نامشخص"

    try:
        number = float(value)
    except (
        TypeError,
        ValueError,
    ):
        return str(value)

    if number.is_integer():
        return (
            f"{int(number):,} تومان"
        )

    return (
        f"{number:,.2f} تومان"
    )


def _search_summary(
    structured: StructuredQuery,
) -> str:
    parts = [
        part
        for part in (
            structured.keyword,
            structured.category,
            structured.gender,
            structured.color,
        )
        if part
    ]

    first = (
        " • ".join(
            _html(part)
            for part in parts
        )
        if parts
        else _html(
            structured.raw_query
        )
    )

    lines = [
        "🔎 جستجو برای:",
        first,
    ]

    if (
        structured.min_price is not None
        and structured.max_price is not None
    ):
        lines.append(
            "بین "
            f"{_html(_format_price(structured.min_price))} "
            "تا "
            f"{_html(_format_price(structured.max_price))}"
        )
    elif structured.max_price is not None:
        lines.append(
            "تا "
            f"{_html(_format_price(structured.max_price))}"
        )
    elif structured.min_price is not None:
        lines.append(
            "از "
            f"{_html(_format_price(structured.min_price))}"
        )

    if structured.city:
        lines.append(
            "📍 "
            f"{_html(structured.city)}"
        )

    return "\n".join(lines)


def _cleanup_cache(
    now: Optional[float] = None,
) -> None:
    if now is None:
        now = _now()

    expired = [
        user_id
        for user_id, entry
        in _search_result_cache.items()
        if (
            now
            - entry["created_at"]
            > SEARCH_CACHE_TTL_SECONDS
        )
    ]

    for user_id in expired:
        _search_result_cache.pop(
            user_id,
            None,
        )

    if (
        len(_search_result_cache)
        <= SEARCH_CACHE_MAX_USERS
    ):
        return

    overflow = (
        len(_search_result_cache)
        - SEARCH_CACHE_MAX_USERS
    )

    oldest = sorted(
        _search_result_cache.items(),
        key=lambda item:
            item[1]["created_at"],
    )[:overflow]

    for user_id, _entry in oldest:
        _search_result_cache.pop(
            user_id,
            None,
        )


def _pagination(
    base: str,
    page: int,
    has_next: bool,
) -> list[dict[str, Any]]:
    row: list[dict[str, Any]] = []

    if page > 0:
        row.append(
            {
                "text": "◀️ قبلی",
                "callback_data": (
                    f"{base}:{page - 1}"
                ),
            }
        )

    if has_next:
        row.append(
            {
                "text": "بعدی ▶️",
                "callback_data": (
                    f"{base}:{page + 1}"
                ),
            }
        )

    return row


def _back_keyboard(
    callback_data: str = "main",
) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🔙 بازگشت",
                    "callback_data": callback_data,
                }
            ]
        ]
    }


def _result_keyboard(
    products: list[dict[str, Any]],
    sellers: list[dict[str, Any]],
    page: int,
) -> dict[str, Any]:
    rows: list[
        list[dict[str, Any]]
    ] = []

    offset = page * PAGE_SIZE

    page_products = products[
        offset:
        offset + PAGE_SIZE
    ]

    if page == 0 and sellers:
        rows.append(
            [
                {
                    "text": "🏪 فروشگاه‌های مرتبط",
                    "callback_data": "main",
                }
            ]
        )

        for seller in sellers:
            badge = (
                "🟢"
                if str(
                    seller["status"]
                ).upper()
                == "CLAIMED"
                else "⚪"
            )

            city = (
                str(
                    seller["city_name"]
                    or ""
                ).strip()
            )

            suffix = (
                f" • {_html(city)}"
                if city
                else ""
            )

            rows.append(
                [
                    {
                        "text": (
                            "🏪 "
                            f"{badge} "
                            f"{_html(seller['name'])}"
                            f"{suffix}"
                        ),
                        "callback_data": (
                            f"seller:{seller['id']}"
                        ),
                    }
                ]
            )

        if products:
            rows.append(
                [
                    {
                        "text": "📦 محصولات مرتبط",
                        "callback_data": "main",
                    }
                ]
            )

    for product in page_products:
        rows.append(
            [
                {
                    "text": (
                        "🛍️ "
                        f"{_html(product['name'])}"
                        " - "
                        f"{_html(_format_price(product['price']))}"
                    ),
                    "callback_data": (
                        f"product:{product['id']}"
                    ),
                }
            ]
        )

    has_next = (
        offset + PAGE_SIZE
        < len(products)
    )

    pagination = _pagination(
        "searchpage",
        page,
        has_next,
    )

    if pagination:
        rows.append(
            pagination
        )

    rows.append(
        [
            {
                "text": "🔙 بازگشت",
                "callback_data": "main",
            }
        ]
    )

    return {
        "inline_keyboard": rows,
    }


async def _ensure_user(
    db: Any,
    telegram_user: dict[str, Any],
) -> dict[str, Any]:
    telegram_id = telegram_user.get(
        "id"
    )

    try:
        telegram_id = int(
            telegram_id
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "Telegram user id is invalid."
        ) from exc

    if telegram_id < 1:
        raise ValueError(
            "Telegram user id is invalid."
        )

    now = (
        __import__(
            "datetime"
        )
        .datetime.now(
            __import__(
                "datetime"
            ).timezone.utc
        )
        .isoformat(
            timespec="seconds"
        )
    )

    await db.execute(
        """
        INSERT INTO users (
            telegram_id,
            username,
            first_name,
            last_name,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id)
        DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            updated_at = excluded.updated_at;
        """,
        (
            telegram_id,
            (
                str(
                    telegram_user.get(
                        "username"
                    )
                ).strip()
                if telegram_user.get(
                    "username"
                ) is not None
                else None
            ),
            (
                str(
                    telegram_user.get(
                        "first_name"
                    )
                ).strip()
                if telegram_user.get(
                    "first_name"
                ) is not None
                else None
            ),
            (
                str(
                    telegram_user.get(
                        "last_name"
                    )
                ).strip()
                if telegram_user.get(
                    "last_name"
                ) is not None
                else None
            ),
            now,
            now,
        ),
    )

    row = await db.fetchone(
        """
        SELECT *
        FROM users
        WHERE telegram_id = ?
        LIMIT 1;
        """,
        (
            telegram_id,
        ),
    )

    if row is None:
        raise RuntimeError(
            "Failed to create or load user."
        )

    return row


async def _answer_callback(
    telegram: Any,
    callback_query: dict[str, Any],
    text: Optional[str] = None,
    show_alert: bool = False,
) -> None:
    callback_id = callback_query.get(
        "id"
    )

    if not callback_id:
        return

    await telegram.answer_callback_query(
        str(callback_id),
        text=text,
        show_alert=show_alert,
    )


async def _edit_callback(
    telegram: Any,
    callback_query: dict[str, Any],
    text: str,
    reply_markup: Optional[
        dict[str, Any]
    ] = None,
) -> bool:
    message = callback_query.get(
        "message"
    )

    if not isinstance(
        message,
        dict,
    ):
        return False

    chat = message.get(
        "chat"
    )

    if not isinstance(
        chat,
        dict,
    ):
        return False

    chat_id = chat.get(
        "id"
    )
    message_id = message.get(
        "message_id"
    )

    if (
        chat_id is None
        or message_id is None
    ):
        return False

    await telegram.edit_message_text(
        int(chat_id),
        int(message_id),
        text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )

    return True


async def _send(
    telegram: Any,
    message: dict[str, Any],
    text: str,
    reply_markup: Optional[
        dict[str, Any]
    ] = None,
) -> None:
    chat = message.get(
        "chat"
    )

    if not isinstance(
        chat,
        dict,
    ):
        return

    chat_id = chat.get(
        "id"
    )

    if chat_id is None:
        return

    await telegram.send_message(
        int(chat_id),
        text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


async def handle_search_start(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    user = callback_query.get(
        "from"
    )

    if not isinstance(
        user,
        dict,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    try:
        row = await _ensure_user(
            db,
            user,
        )
    except (
        ValueError,
        RuntimeError,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    await ensure_state_table(
        db
    )

    await set_state(
        db,
        int(row["id"]),
        SEARCH_STATE,
        {},
    )

    await _edit_callback(
        telegram,
        callback_query,
        (
            "🔎 دنبال چه چیزی می‌گردی؟\n\n"
            "متن جستجو را بفرست:"
        ),
        _back_keyboard(
            "main"
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


async def handle_search_message(
    db: Any,
    telegram: Any,
    message: dict[str, Any],
) -> bool:
    user = message.get(
        "from"
    )

    if not isinstance(
        user,
        dict,
    ):
        return False

    try:
        row = await _ensure_user(
            db,
            user,
        )
    except (
        ValueError,
        RuntimeError,
    ):
        return False

    user_id = int(
        row["id"]
    )

    await ensure_state_table(
        db
    )

    state = await get_state(
        db,
        user_id,
    )

    if (
        state is None
        or state.get("state")
        != SEARCH_STATE
    ):
        return False

    query = str(
        message.get(
            "text",
            "",
        )
        or ""
    ).strip()

    if query == "/start":
        await clear_state(
            db,
            user_id,
        )
        return True

    valid, normalized, error = (
        _validate_search_query(
            query
        )
    )

    if not valid:
        await _send(
            telegram,
            message,
            error
            or "⚠️ عبارت جستجو معتبر نیست.",
        )
        return True

    await clear_state(
        db,
        user_id,
    )

    structured, products, mode = (
        await _search_products(
            db,
            normalized,
        )
    )

    sellers = await _search_sellers(
        db,
        normalized,
    )

    await db.execute(
        """
        INSERT INTO events (
            user_id,
            event_type,
            entity_type,
            entity_id,
            created_at
        )
        VALUES (?, ?, ?, ?, ?);
        """,
        (
            user_id,
            "search",
            (
                "local_smart"
                if mode
                in {
                    "structured",
                    "fuzzy",
                }
                else "query"
            ),
            None,
            __import__(
                "datetime"
            )
            .datetime.now(
                __import__(
                    "datetime"
                ).timezone.utc
            )
            .isoformat(
                timespec="seconds"
            ),
        ),
    )

    if not products and not sellers:
        await _send(
            telegram,
            message,
            (
                "🔎 نتیجه‌ای برای "
                f"«{_html(normalized)}» پیدا نشد."
            ),
            _back_keyboard(
                "main"
            ),
        )
        return True

    if mode == "structured":
        header = (
            _search_summary(
                structured
            )
            + "\n\nنتایج:"
        )
    elif mode == "fuzzy":
        header = (
            "🔎 نتایج نزدیک به "
            f"«{_html(normalized)}»:"
        )
    else:
        header = (
            "🔎 نتایج جستجو برای "
            f"«{_html(normalized)}»:"
        )

    if sellers and not products:
        header += (
            "\n\n🏪 فروشگاه‌های مرتبط:"
        )

    now = _now()

    _cleanup_cache(
        now
    )

    _search_result_cache[
        user_id
    ] = {
        "header": header,
        "products": products,
        "sellers": sellers,
        "created_at": now,
    }

    _cleanup_cache(
        now
    )

    await _send(
        telegram,
        message,
        header,
        _result_keyboard(
            products,
            sellers,
            0,
        ),
    )

    return True


async def handle_search_page(
    db: Any,
    telegram: Any,
    callback_query: dict[str, Any],
) -> None:
    user = callback_query.get(
        "from"
    )

    if not isinstance(
        user,
        dict,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    try:
        row = await _ensure_user(
            db,
            user,
        )
    except (
        ValueError,
        RuntimeError,
    ):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ اطلاعات کاربر نامعتبر است.",
            True,
        )
        return

    raw_data = str(
        callback_query.get(
            "data",
            "",
        )
    )

    parts = raw_data.split(
        ":",
        1,
    )

    if len(parts) != 2:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ صفحه نامعتبر است.",
            True,
        )
        return

    try:
        page = int(
            parts[1]
        )
    except (
        TypeError,
        ValueError,
    ):
        page = -1

    if page < 0:
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ صفحه نامعتبر است.",
            True,
        )
        return

    user_id = int(
        row["id"]
    )

    now = _now()

    _cleanup_cache(
        now
    )

    cached = _search_result_cache.get(
        user_id
    )

    if cached is None:
        await _answer_callback(
            telegram,
            callback_query,
            (
                "⚠️ نتایج جستجو منقضی شده. "
                "دوباره جستجو کن."
            ),
            True,
        )
        return

    if (
        now
        - cached["created_at"]
        > SEARCH_CACHE_TTL_SECONDS
    ):
        _search_result_cache.pop(
            user_id,
            None,
        )

        await _answer_callback(
            telegram,
            callback_query,
            (
                "⚠️ نتایج جستجو منقضی شده. "
                "دوباره جستجو کن."
            ),
            True,
        )
        return

    products = cached[
        "products"
    ]
    sellers = cached[
        "sellers"
    ]

    if (
        page * PAGE_SIZE
        >= len(products)
        and not (
            page == 0
            and sellers
        )
    ):
        await _answer_callback(
            telegram,
            callback_query,
            "⚠️ این صفحه وجود ندارد.",
            True,
        )
        return

    await _edit_callback(
        telegram,
        callback_query,
        cached["header"],
        _result_keyboard(
            products,
            sellers,
            page,
        ),
    )

    await _answer_callback(
        telegram,
        callback_query,
    )


__all__ = [
    "handle_search_start",
    "handle_search_message",
    "handle_search_page",
]