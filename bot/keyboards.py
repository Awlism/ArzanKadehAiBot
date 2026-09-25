# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Keyboard builders
"""

from aiogram.types import InlineKeyboardMarkup
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
    EMOJI_NOTIFICATIONS,
    EMOJI_PICKS,
    EMOJI_REGISTER_SELLER,
    EMOJI_SEARCH,
    EMOJI_SELLERS,
    EMOJI_TOP_SELLERS,
)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(
        text=f"{EMOJI_SEARCH} جستجو",
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
        text=f"{EMOJI_PICKS} پیشنهادها",
        callback_data="picks",
    )
    builder.button(
        text=f"{EMOJI_NEAR_ME} نزدیک من",
        callback_data="nearme",
    )
    builder.button(
        text=f"{EMOJI_TOP_SELLERS} برترین فروشگاه‌ها",
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
        text=f"{EMOJI_REGISTER_SELLER} ثبت فروشگاه",
        callback_data="registerseller",
    )
    builder.button(
        text=f"{EMOJI_ADS} تبلیغات",
        callback_data="publicads",
    )
    builder.button(
        text=f"{EMOJI_ACCOUNT} حساب کاربری",
        callback_data="account",
    )
    builder.button(
        text=f"{EMOJI_NOTIFICATIONS} اعلان‌ها",
        callback_data="notifications",
    )
    builder.button(
        text=f"{EMOJI_MAIN_MENU} منوی اصلی",
        callback_data="main_menu",
    )

    builder.adjust(2)

    return builder.as_markup()


def back_keyboard(
    callback_data: str = "main_menu",
    text: str = "🔙 بازگشت",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(
        text=text,
        callback_data=callback_data,
    )

    return builder.as_markup()


def pagination_keyboard(
    previous_callback: str | None = None,
    next_callback: str | None = None,
    back_callback: str = "main_menu",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if previous_callback:
        builder.button(
            text="⬅️ قبلی",
            callback_data=previous_callback,
        )

    if next_callback:
        builder.button(
            text="بعدی ➡️",
            callback_data=next_callback,
        )

    builder.button(
        text="🔙 بازگشت",
        callback_data=back_callback,
    )

    builder.adjust(2)

    return builder.as_markup()


def confirm_keyboard(
    confirm_callback: str,
    cancel_callback: str = "main_menu",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(
        text="✅ تأیید",
        callback_data=confirm_callback,
    )
    builder.button(
        text="❌ لغو",
        callback_data=cancel_callback,
    )

    builder.adjust(2)

    return builder.as_markup()


def restart_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(
        text="🔄 شروع دوباره",
        callback_data="restart_button",
    )

    return builder.as_markup()