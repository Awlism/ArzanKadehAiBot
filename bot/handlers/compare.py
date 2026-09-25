# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Product comparison handlers
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..database import db
from ..keyboards import kb_add_back
from ..repositories import (
    COMPARE_INTRO_TEXT,
    COMPARE_MAX_ITEMS,
    clear_compare_selection,
    compare_add,
    get_compare_selection,
    has_seen_compare_intro,
    mark_compare_intro_seen,
    set_compare_selection,
)
from ..utils import (
    ensure_user,
    format_price,
    log_event,
    now_iso,
    parse_int,
    safe_edit,
)


router = Router(name="compare")


@router.callback_query(F.data == "compare")
async def handle_compare_legacy_redirect(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """
    Keep the old callback_data working in case it exists
    in an already-sent Telegram message.
    """
    await handle_compare_list(
        callback,
        state,
    )


@router.callback_query(F.data == "comparelist")
async def handle_compare_list(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    user_id = await ensure_user(
        callback.from_user
    )

    if not await has_seen_compare_intro(user_id):
        await mark_compare_intro_seen(user_id)

        builder = InlineKeyboardBuilder()
        kb_add_back(
            builder,
            "main",
        )

        await safe_edit(
            callback,
            COMPARE_INTRO_TEXT,
            builder.as_markup(),
        )

        await callback.answer()
        return

    selection = get_compare_selection(
        user_id
    )

    if not selection:
        builder = InlineKeyboardBuilder()
        kb_add_back(
            builder,
            "main",
        )

        await safe_edit(
            callback,
            (
                "⚖️ هنوز محصولی برای مقایسه "
                "انتخاب نکردی.\n\n"
                "از روی صفحه هر محصول، دکمه "
                "«افزودن به مقایسه» رو بزن."
            ),
            builder.as_markup(),
        )

        await callback.answer()
        return

    products = []

    for product_id in selection:
        row = await db.fetchone(
            """
            SELECT
                p.*,
                s.name AS seller_name
            FROM products p
            JOIN sellers s
                ON s.id = p.seller_id
            WHERE p.id = ?;
            """,
            (product_id,),
        )

        if row:
            products.append(row)

    if len(products) < len(selection):
        set_compare_selection(
            user_id,
            [
                product["id"]
                for product in products
            ],
        )

    if len(products) < COMPARE_MAX_ITEMS:
        builder = InlineKeyboardBuilder()

        for product in products:
            builder.row(
                InlineKeyboardButton(
                    text=(
                        f"❌ حذف "
                        f"{product['name']}"
                    ),
                    callback_data=(
                        f"comparedrop:{product['id']}"
                    ),
                )
            )

        kb_add_back(
            builder,
            "main",
        )

        selected_names = "\n".join(
            f"• {product['name']}"
            for product in products
        )

        await safe_edit(
            callback,
            (
                "⚖️ یک محصول دیگر انتخاب کن."
                "\n\n"
                "انتخاب فعلی:"
                f"\n{selected_names}"
            ),
            builder.as_markup(),
        )

        await callback.answer()
        return

    first_product = products[0]
    second_product = products[1]

    lines = [
        "⚖️ <b>مقایسه دو محصول</b>",
        "",
        (
            f"🛍️ <b>{first_product['name']}</b>"
            "  ⚔️  "
            f"<b>{second_product['name']}</b>"
        ),
        (
            f"💰 "
            f"{format_price(first_product['price'])}"
            "  |  "
            f"{format_price(second_product['price'])}"
        ),
        (
            "⭐ "
            f"{first_product['rating']:.1f}"
            f" ({first_product['review_count']} نظر)"
            "  |  "
            f"{second_product['rating']:.1f}"
            f" ({second_product['review_count']} نظر)"
        ),
        (
            f"🏪 {first_product['seller_name']}"
            "  |  "
            f"{second_product['seller_name']}"
        ),
    ]

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=(
                f"🛍️ {first_product['name']}"
            ),
            callback_data=(
                f"product:{first_product['id']}"
            ),
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=(
                f"🛍️ {second_product['name']}"
            ),
            callback_data=(
                f"product:{second_product['id']}"
            ),
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🔄 شروع مقایسه جدید",
            callback_data="comparereset",
        )
    )

    kb_add_back(
        builder,
        "main",
    )

    await safe_edit(
        callback,
        "\n".join(lines),
        builder.as_markup(),
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("comparestart:")
)
async def handle_compare_start(
    callback: CallbackQuery,
) -> None:
    product_id = parse_int(
        callback.data.split(":")[1]
    )

    if product_id is None:
        await callback.answer(
            "⚠️ شناسه نامعتبر است.",
            show_alert=True,
        )
        return

    product = await db.fetchone(
        """
        SELECT id
        FROM products
        WHERE id = ?;
        """,
        (product_id,),
    )

    if not product:
        await callback.answer(
            "⚠️ این محصول یافت نشد.",
            show_alert=True,
        )
        return

    user_id = await ensure_user(
        callback.from_user
    )

    if not await has_seen_compare_intro(
        user_id
    ):
        await mark_compare_intro_seen(
            user_id
        )

        await callback.answer(
            COMPARE_INTRO_TEXT,
            show_alert=True,
        )

    selection = get_compare_selection(
        user_id
    )

    new_selection, outcome = compare_add(
        selection,
        product_id,
    )

    set_compare_selection(
        user_id,
        new_selection,
    )

    if outcome == "already_in_selection":
        await callback.answer(
            "این محصول قبلاً به مقایسه اضافه شده.",
            show_alert=True,
        )

    elif outcome == "already_full":
        await callback.answer(
            "مقایسه همزمان فقط برای ۲ محصول امکان‌پذیره.",
            show_alert=True,
        )

    elif outcome == "added_ready":
        await log_event(
            user_id,
            "compare_add",
            "product",
            product_id,
        )

        await callback.answer(
            "✅ اضافه شد! حالا می‌تونی مقایسه رو ببینی.",
            show_alert=True,
        )

    else:
        await log_event(
            user_id,
            "compare_add",
            "product",
            product_id,
        )

        await callback.answer(
            "✅ اضافه شد! یک محصول دیگه هم انتخاب کن.",
            show_alert=True,
        )


@router.callback_query(
    F.data.startswith("comparedrop:")
)
async def handle_compare_drop(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    product_id = parse_int(
        callback.data.split(":")[1]
    )

    user_id = await ensure_user(
        callback.from_user
    )

    if product_id is not None:
        selection = [
            selected_id
            for selected_id in get_compare_selection(
                user_id
            )
            if selected_id != product_id
        ]

        set_compare_selection(
            user_id,
            selection,
        )

    await callback.answer()

    await handle_compare_list(
        callback,
        state,
    )


@router.callback_query(
    F.data == "comparereset"
)
async def handle_compare_reset(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    user_id = await ensure_user(
        callback.from_user
    )

    clear_compare_selection(
        user_id
    )

    await callback.answer(
        "مقایسه پاک شد."
    )

    await handle_compare_list(
        callback,
        state,
    )