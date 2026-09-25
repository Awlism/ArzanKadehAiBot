# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Keyboard builders
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .constants import (
    EMOJI_ACCOUNT,
    EMOJI_ADS,
    EMOJI_BACK,
    EMOJI_CATEGORIES,
    EMOJI_COMPARE,
    EMOJI_FAVORITES,
    EMOJI_HOT,
    EMOJI_MAIN_MENU,
    EMOJI_NEAR_ME,
    EMOJI_NEW_TODAY,
    EMOJI_PICKS,
    EMOJI_REGISTER_SELLER,
    EMOJI_SEARCH,
    EMOJI_SELLERS,
    EMOJI_TOP_SELLERS,
)


def restart_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text="🔄 شروع دوباره",
        callback_data="restart_button",
    )


def kb_add_back(
    builder: InlineKeyboardBuilder,
    callback_data: str,
    text: str = f"{EMOJI_BACK} بازگشت",
) -> None:
    builder.row(
        InlineKeyboardButton(
            text=text,
            callback_data=callback_data,
        )
    )


def kb_pagination_row(
    builder: InlineKeyboardBuilder,
    base_callback: str,
    page: int,
    has_next: bool,
) -> None:
    row = []

    if page > 0:
        row.append(
            InlineKeyboardButton(
                text="◀️ قبلی",
                callback_data=f"{base_callback}:{page - 1}",
            )
        )

    if has_next:
        row.append(
            InlineKeyboardButton(
                text="بعدی ▶️",
                callback_data=f"{base_callback}:{page + 1}",
            )
        )

    if row:
        builder.row(*row)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(
        text=f"{EMOJI_SEARCH} جستجوی محصول",
        callback_data="search",
    )
    builder.button(
        text=f"{EMOJI_SELLERS} فروشگاه‌ها",
        callback_data="sellers:0",
    )
    builder.button(
        text=f"{EMOJI_CATEGORIES} دسته‌بندی‌ها",
        callback_data="cat:0:0",
    )
    builder.button(
        text=f"{EMOJI_HOT} داغ‌ترین‌ها",
        callback_data="hot",
    )
    builder.button(
        text=f"{EMOJI_NEW_TODAY} جدیدهای امروز",
        callback_data="newtoday",
    )
    builder.button(
        text=f"{EMOJI_PICKS} انتخاب ارزانکده",
        callback_data="picks",
    )
    builder.button(
        text=f"{EMOJI_NEAR_ME} نزدیک من",
        callback_data="nearme",
    )
    builder.button(
        text=f"{EMOJI_TOP_SELLERS} فروشندگان برتر",
        callback_data="topsellers",
    )
    builder.button(
        text=f"{EMOJI_FAVORITES} علاقه‌مندی‌ها",
        callback_data="favorites:0",
    )
    builder.button(
        text=f"{EMOJI_COMPARE} مقایسه",
        callback_data="comparelist",
    )
    builder.button(
        text=f"{EMOJI_REGISTER_SELLER} ثبت فروشگاه من",
        callback_data="registerseller",
    )
    builder.button(
        text="📢 تبلیغ در ارزانکده",
        callback_data="publicads",
    )
    builder.button(
        text=f"{EMOJI_ACCOUNT} حساب کاربری",
        callback_data="account",
    )

    builder.adjust(2)
    builder.row(restart_button())

    return builder.as_markup()