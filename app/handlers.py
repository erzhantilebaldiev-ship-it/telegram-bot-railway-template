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
    name = State()
    age = State()
    city = State()
    gender = State()
    looking_for = State()
    photo = State()
    bio = State()


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


def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👨 Парень",
                    callback_data="gender:male",
                ),
                InlineKeyboardButton(
                    text="👩 Девушка",
                    callback_data="gender:female",
                ),
            ]
        ]
    )


def looking_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👨 Парней",
                    callback_data="looking:male",
                ),
                InlineKeyboardButton(
                    text="👩 Девушек",
                    callback_data="looking:female",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❤️ Неважно",
                    callback_data="looking:any",
                )
            ],
        ]
    )


def profile_text(data: dict) -> str:
    return (
        "👤 <b>Твоя анкета</b>\n\n"
        f"Имя: <b>{html.quote(str(data['name']))}</b>\n"
        f"Возраст: <b>{data['age']}</b>\n"
        f"Город: <b>{html.quote(str(data['city']))}</b>\n"
        f"Пол: <b>{html.quote(str(data['gender']))}</b>\n"
        f"Ищет: <b>{html.quote(str(data['looking_for']))}</b>\n\n"
        f"📝 {html.quote(str(data['bio']))}"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, db: Storage) -> None:
    user = message.from_user

    if user is not None:
        await db.track_user(user.id, user.username)

    await message.answer(
        "❤️ <b>Добро пожаловать в Dating Bot!</b>\n\n"
        "Здесь ты можешь познакомиться с интересными людьми.\n\n"
        "Создай свою анкету 👇",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>Помощь</b>\n\n"
        "❤️ Создай анкету и начинай знакомиться.\n"
        "👤 В разделе «Моя анкета» можно посмотреть свои данные."
    )


@router.callback_query(F.data == "profile:create")
async def create_profile(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(ProfileStates.name)

    await callback.message.answer(
        "❤️ <b>Создаём твою анкету</b>\n\n"
        "👤 Как тебя зовут?"
    )


@router.message(ProfileStates.name)
async def profile_name(
    message: Message,
    state: FSMContext,
) -> None:
    name = (message.text or "").strip()

    if not name:
        await message.answer("Напиши своё имя 🙂")
        return

    if len(name) > 30:
        await message.answer("Имя слишком длинное. Напиши короче 🙂")
        return

    await state.update_data(name=name)
    await state.set_state(ProfileStates.age)

    await message.answer(
        f"Приятно познакомиться, <b>{html.quote(name)}</b>! 👋\n\n"
        "🎂 Сколько тебе лет?"
    )


@router.message(ProfileStates.age)
async def profile_age(
    message: Message,
    state: FSMContext,
) -> None:
    text = (message.text or "").strip()

    if not text.isdigit():
        await message.answer(
            "🎂 Напиши возраст цифрами.\n\n"
            "Например: <b>22</b>"
        )
        return

    age = int(text)

    if age < 18:
        await message.answer(
            "Извини, бот предназначен для пользователей от 18 лет."
        )
        return

    if age > 100:
        await message.answer("Проверь возраст и попробуй ещё раз 🙂")
        return

    await state.update_data(age=age)
    await state.set_state(ProfileStates.city)

    await message.answer(
        "📍 Отлично!\n\n"
        "Из какого ты города?"
    )


@router.message(ProfileStates.city)
async def profile_city(
    message: Message,
    state: FSMContext,
) -> None:
    city = (message.text or "").strip()

    if not city:
        await message.answer("Напиши название своего города 🙂")
        return

    if len(city) > 50:
        await message.answer("Название города слишком длинное.")
        return

    await state.update_data(city=city)
    await state.set_state(ProfileStates.gender)

    await message.answer(
        "🚻 Кто ты?",
        reply_markup=gender_keyboard(),
    )


@router.callback_query(
    ProfileStates.gender,
    F.data.startswith("gender:")
)
async def profile_gender(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()

    gender_map = {
        "gender:male": "Парень",
        "gender:female": "Девушка",
    }

    gender = gender_map.get(callback.data)

    if not gender:
        return

    await state.update_data(gender=gender)
    await state.set_state(ProfileStates.looking_for)

    await callback.message.answer(
        "❤️ Кого ты хочешь найти?",
        reply_markup=looking_keyboard(),
    )


@router.callback_query(
    ProfileStates.looking_for,
    F.data.startswith("looking:")
)
async def profile_looking(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()

    looking_map = {
        "looking:male": "Парней",
        "looking:female": "Девушек",
        "looking:any": "Неважно",
    }

    looking_for = looking_map.get(callback.data)

    if not looking_for:
        return

    await state.update_data(looking_for=looking_for)
    await state.set_state(ProfileStates.photo)

    await callback.message.answer(
        "📸 Теперь отправь своё фото.\n\n"
        "Лучше отправить обычное фото, где хорошо видно твоё лицо."
    )


@router.message(ProfileStates.photo, F.photo)
async def profile_photo(
    message: Message,
    state: FSMContext,
) -> None:
    photo = message.photo[-1]

    await state.update_data(photo_file_id=photo.file_id)
    await state.set_state(ProfileStates.bio)

    await message.answer(
        "🔥 Фото получил!\n\n"
        "✍️ Теперь расскажи немного о себе.\n\n"
        "Например: чем занимаешься, что любишь, какой у тебя характер."
    )


@router.message(ProfileStates.photo)
async def profile_photo_wrong(
    message: Message,
) -> None:
    await message.answer(
        "📸 Пожалуйста, отправь именно фотографию."
    )


@router.message(ProfileStates.bio)
async def profile_bio(
    message: Message,
    state: FSMContext,
    db: Storage,
) -> None:
    bio = (message.text or "").strip()

    if not bio:
        await message.answer("Напиши пару слов о себе 🙂")
        return

    if len(bio) > 500:
        await message.answer(
            "Описание слишком длинное. Максимум 500 символов."
        )
        return

    data = await state.get_data()
    user = message.from_user

    if user is None:
        await state.clear()
        return

    await db.save_profile(
        user_id=user.id,
        name=data["name"],
        age=data["age"],
        city=data["city"],
        gender=data["gender"],
        looking_for=data["looking_for"],
        photo_file_id=data.get("photo_file_id"),
        bio=bio,
    )

    await state.clear()

    final_data = {
        **data,
        "bio": bio,
    }

    await message.answer(
        "🎉 <b>Анкета готова!</b>\n\n"
        + profile_text(final_data),
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "profile:me")
async def my_profile(
    callback: CallbackQuery,
    db: Storage,
) -> None:
    await callback.answer()

    user = callback.from_user
    profile = await db.get_profile(user.id)

    if not profile:
        await callback.message.answer(
            "👤 У тебя пока нет анкеты.\n\n"
            "Нажми ❤️ «Создать анкету»."
        )
        return

    data = dict(profile)

    text = profile_text(data)

    if data.get("photo_file_id"):
        await callback.message.answer_photo(
            photo=data["photo_file_id"],
            caption=text,
        )
    else:
        await callback.message.answer(
            text,
            reply_markup=main_menu(),
        )
