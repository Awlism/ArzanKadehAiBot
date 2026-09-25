# -*- coding: utf-8 -*-
"""
ArzanKadeh AI
FSM States
"""

from aiogram.fsm.state import State, StatesGroup


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


class GeneralAdStates(StatesGroup):
    waiting_title = State()
    waiting_description = State()
    waiting_image_url = State()
    waiting_link = State()


class AdminAdSettingStates(StatesGroup):
    waiting_price = State()
    waiting_duration = State()
    waiting_placement = State()


class AdminSearchStates(StatesGroup):
    waiting_user_query = State()