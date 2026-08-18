from __future__ import annotations

from aiogram import F, Router, html
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from db import Storage


router = Router(name="dating")


class ProfileStates(StatesGroup):
    waiting_name = State()
    waiting_age = State()


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❤️ Создать анкету",
                    callback_data="profile:create",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👤 Моя анкета",
                    callback_data="profile:me",
                )
            ],
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message, db: Storage) -> None:
    user = message.from_user

    if user is not None:
        await db.track_user(user.id, user.username)

    await message.answer(
        "❤️ <b>Добро пожаловать в Dating Bot!</b>\n\n"
        "Здесь ты можешь познакомиться с интересными людьми.\n\n"
        "Сначала создай свою анкету 👇",
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "profile:create")
async def create_profile(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()

    await state.set_state(ProfileStates.waiting_name)

    await callback.message.answer(
        "👤 <b>Создаём твою анкету</b>\n\n"
        "Как тебя зовут?"
    )


@router.message(ProfileStates.waiting_name)
async def profile_name(
    message: Message,
    state: FSMContext,
) -> None:
    name = (message.text or "").strip()

    if not name:
        await message.answer("Пожалуйста, напиши своё имя 🙂")
        return

    if len(name) > 30:
        await message.answer("Имя слишком длинное. Напиши короче 🙂")
        return

    await state.update_data(name=name)
    await state.set_state(ProfileStates.waiting_age)

    await message.answer(
        f"Приятно познакомиться, <b>{html.quote(name)}</b>! 👋\n\n"
        "🎂 Сколько тебе лет?"
    )


@router.message(ProfileStates.waiting_age)
async def profile_age(
    message: Message,
    state: FSMContext,
) -> None:
    text = (message.text or "").strip()

    if not text.isdigit():
        await message.answer(
            "Напиши возраст цифрами, например: <b>22</b>"
        )
        return

    age = int(text)

    if age < 18:
        await message.answer(
            "Извини, этот бот предназначен для пользователей от 18 лет."
        )
        return

    if age > 100:
        await message.answer(
            "Проверь возраст и введи корректное число 🙂"
        )
        return

    data = await state.get_data()
    name = data.get("name", "Пользователь")

    await state.clear()

    await message.answer(
        f"Отлично, <b>{html.quote(name)}</b>! 🎉\n\n"
        f"Тебе {age} лет.\n\n"
        "Следующий этап анкеты добавим дальше."
    )


@router.callback_query(F.data == "profile:me")
async def my_profile(callback: CallbackQuery) -> None:
    await callback.answer()

    await callback.message.answer(
        "👤 <b>Моя анкета</b>\n\n"
        "Ты ещё не создал анкету.\n"
        "Нажми «❤️ Создать анкету»."
    )
