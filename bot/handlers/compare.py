# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
Product comparison handlers
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..constants import COMPARE_MAX_ITEMS
from ..database import db
from ..keyboards import kb_add_back
from ..repositories import (
    COMPARE_INTRO_TEXT,
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
            WHERE p.id = ?
              AND COALESCE(s.is_active, 1) = 1;
            """,
            (product_id,),
        )

        if row:
            products.append(row)

    valid_product_ids = [
        product["id"]
        for product in products
    ]

    if len(products) != len(selection):
        set_compare_selection(
            user_id,
            valid_product_ids,
        )

    if not products:
        builder = InlineKeyboardBuilder()

        kb_add_back(
            builder,
            "main",
        )

        await safe_edit(
            callback,
            (
                "⚠️ محصولات انتخاب‌شده دیگر "
                "در دسترس نیستند.\n\n"
                "مقایسه پاک شد؛ می‌تونی دوباره "
                "محصولات جدید انتخاب کنی."
            ),
            builder.as_markup(),
        )

        await callback.answer()
        return

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

        remaining = (
            COMPARE_MAX_ITEMS
            - len(products)
        )

        await safe_edit(
            callback,
            (
                "⚖️ برای شروع مقایسه، "
                f"{remaining} محصول دیگه انتخاب کن."
                "\n\n"
                "انتخاب فعلی:"
                f"\n{selected_names}"
            ),
            builder.as_markup(),
        )

        await callback.answer()
        return

    builder = InlineKeyboardBuilder()

    lines = [
        "⚖️ <b>مقایسه محصولات</b>",
        "",
    ]

    for index, product in enumerate(
        products,
        start=1,
    ):
        lines.extend(
            [
                f"<b>{index}. {product['name']}</b>",
                (
                    f"💰 قیمت: "
                    f"{format_price(product['price'])}"
                ),
                (
                    "⭐ امتیاز: "
                    f"{product['rating']:.1f}"
                    f" ({product['review_count']} نظر)"
                ),
                (
                    f"🏪 فروشنده: "
                    f"{product['seller_name']}"
                ),
                "",
            ]
        )

        builder.row(
            InlineKeyboardButton(
                text=f"🛍️ {product['name']}",
                callback_data=(
                    f"product:{product['id']}"
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
        "\n".join(lines).strip(),
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
        SELECT
            p.id
        FROM products p
        JOIN sellers s
            ON s.id = p.seller_id
        WHERE p.id = ?
          AND COALESCE(s.is_active, 1) = 1;
        """,
        (product_id,),
    )

    if not product:
        await callback.answer(
            "⚠️ این محصول دیگر در دسترس نیست.",
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
            (
                "مقایسه همزمان فقط برای "
                f"{COMPARE_MAX_ITEMS} محصول امکان‌پذیره."
            ),
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
            (
                "✅ اضافه شد! حالا می‌تونی "
                "مقایسه رو ببینی."
            ),
            show_alert=True,
        )

    else:
        await log_event(
            user_id,
            "compare_add",
            "product",
            product_id,
        )

        remaining = (
            COMPARE_MAX_ITEMS
            - len(new_selection)
        )

        await callback.answer(
            (
                "✅ اضافه شد! "
                f"{remaining} محصول دیگه انتخاب کن."
            ),
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