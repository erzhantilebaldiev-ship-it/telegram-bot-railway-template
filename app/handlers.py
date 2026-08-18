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
                    text="🔎 Знакомства",
                    callback_data="dating:start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❤️ Мои симпатии",
                    callback_data="likes:show",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👤 Моя анкета",
                    callback_data="profile:me",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Редактировать анкету",
                    callback_data="profile:edit",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑️ Удалить анкету",
                    callback_data="profile:delete",
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


def dating_keyboard(
    target_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❤️ Нравится",
                    callback_data=f"dating:like:{target_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Пропустить",
                    callback_data=f"dating:skip:{target_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Заблокировать",
                    callback_data=f"dating:block:{target_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Меню",
                    callback_data="dating:menu",
                )
            ],
        ]
    )


def profile_text(data: dict) -> str:
    return (
        f"👤 <b>{html.quote(str(data['name']))}, "
        f"{data['age']}</b>\n\n"
        f"📍 {html.quote(str(data['city']))}\n"
        f"🚻 {html.quote(str(data['gender']))}\n"
        f"❤️ Ищет: {html.quote(str(data['looking_for']))}\n\n"
        f"📝 {html.quote(str(data['bio']))}"
    )


async def send_next_profile(
    message: Message,
    user_id: int,
    db: Storage,
) -> None:
    profile = await db.get_next_profile(user_id)

    if not profile:
        await message.answer(
            "😔 <b>Новых анкет пока нет.</b>\n\n"
            "Попробуй зайти позже.",
            reply_markup=main_menu(),
        )
        return

    data = dict(profile)
    text = profile_text(data)

    keyboard = dating_keyboard(
        data["user_id"]
    )

    if data.get("photo_file_id"):
        await message.answer_photo(
            photo=data["photo_file_id"],
            caption=text,
            reply_markup=keyboard,
        )
    else:
        await message.answer(
            text,
            reply_markup=keyboard,
        )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    db: Storage,
) -> None:
    user = message.from_user

    if user is not None:
        await db.track_user(
            user.id,
            user.username,
        )

    await message.answer(
        "❤️ <b>Добро пожаловать!</b>\n\n"
        "Здесь можно знакомиться, "
        "ставить лайки и находить взаимную симпатию.\n\n"
        "Выбери действие:",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
async def cmd_help(
    message: Message,
) -> None:
    await message.answer(
        "ℹ️ <b>Как пользоваться ботом</b>\n\n"
        "👤 Создай анкету.\n"
        "🔎 Смотри анкеты других пользователей.\n"
        "❤️ Ставь лайки.\n"
        "❌ Пропускай.\n"
        "💕 При взаимном лайке вы узнаете друг о друге.\n"
        "💬 После взаимной симпатии можно написать человеку."
    )


# =========================
# СОЗДАНИЕ АНКЕТЫ
# =========================

@router.callback_query(
    F.data == "profile:create"
)
async def create_profile(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()

    await state.clear()
    await state.set_state(ProfileStates.name)

    await callback.message.answer(
        "❤️ <b>Создаём анкету</b>\n\n"
        "👤 Как тебя зовут?"
    )


@router.callback_query(
    F.data == "profile:edit"
)
async def edit_profile(
    callback: CallbackQuery,
    state: FSMContext,
    db: Storage,
) -> None:
    await callback.answer()

    profile = await db.get_profile(
        callback.from_user.id
    )

    if not profile:
        await callback.message.answer(
            "👤 У тебя ещё нет анкеты.",
            reply_markup=main_menu(),
        )
        return

    await state.clear()
    await state.set_state(ProfileStates.name)

    await callback.message.answer(
        "✏️ <b>Редактирование анкеты</b>\n\n"
        "👤 Введи новое имя:"
    )


@router.message(ProfileStates.name)
async def profile_name(
    message: Message,
    state: FSMContext,
) -> None:
    name = (message.text or "").strip()

    if not name:
        await message.answer(
            "Напиши имя 🙂"
        )
        return

    if len(name) > 30:
        await message.answer(
            "Имя слишком длинное."
        )
        return

    await state.update_data(name=name)
    await state.set_state(ProfileStates.age)

    await message.answer(
        f"👋 <b>{html.quote(name)}</b>\n\n"
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
            "🎂 Напиши возраст цифрами.\n"
            "Например: <b>22</b>"
        )
        return

    age = int(text)

    if age < 18:
        await message.answer(
            "Извини, бот предназначен "
            "для пользователей от 18 лет."
        )
        return

    if age > 100:
        await message.answer(
            "Проверь возраст."
        )
        return

    await state.update_data(age=age)
    await state.set_state(ProfileStates.city)

    await message.answer(
        "📍 Из какого ты города?"
    )


@router.message(ProfileStates.city)
async def profile_city(
    message: Message,
    state: FSMContext,
) -> None:
    city = (message.text or "").strip()

    if not city:
        await message.answer(
            "Напиши город."
        )
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

    gender = gender_map.get(
        callback.data
    )

    if not gender:
        return

    await state.update_data(
        gender=gender
    )

    await state.set_state(
        ProfileStates.looking_for
    )

    await callback.message.answer(
        "❤️ Кого хочешь найти?",
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

    looking_for = looking_map.get(
        callback.data
    )

    if not looking_for:
        return

    await state.update_data(
        looking_for=looking_for
    )

    await state.set_state(
        ProfileStates.photo
    )

    await callback.message.answer(
        "📸 Отправь своё фото."
    )


@router.message(
    ProfileStates.photo,
    F.photo,
)
async def profile_photo(
    message: Message,
    state: FSMContext,
) -> None:
    photo = message.photo[-1]

    await state.update_data(
        photo_file_id=photo.file_id
    )

    await state.set_state(
        ProfileStates.bio
    )

    await message.answer(
        "🔥 Фото получил!\n\n"
        "📝 Расскажи немного о себе."
    )


@router.message(ProfileStates.photo)
async def profile_photo_wrong(
    message: Message,
) -> None:
    await message.answer(
        "📸 Отправь именно фотографию."
    )


@router.message(ProfileStates.bio)
async def profile_bio(
    message: Message,
    state: FSMContext,
    db: Storage,
) -> None:
    bio = (message.text or "").strip()

    if not bio:
        await message.answer(
            "Напиши пару слов о себе."
        )
        return

    if len(bio) > 500:
        await message.answer(
            "Максимум 500 символов."
        )
        return

    user = message.from_user

    if user is None:
        return

    data = await state.get_data()

    await db.save_profile(
        user_id=user.id,
        name=data["name"],
        age=data["age"],
        city=data["city"],
        gender=data["gender"],
        looking_for=data["looking_for"],
        photo_file_id=data.get(
            "photo_file_id"
        ),
        bio=bio,
    )

    await state.clear()

    await message.answer(
        "🎉 <b>Анкета сохранена!</b>",
        reply_markup=main_menu(),
    )


# =========================
# МОЯ АНКЕТА
# =========================

@router.callback_query(
    F.data == "profile:me"
)
async def my_profile(
    callback: CallbackQuery,
    db: Storage,
) -> None:
    await callback.answer()

    profile = await db.get_profile(
        callback.from_user.id
    )

    if not profile:
        await callback.message.answer(
            "👤 У тебя пока нет анкеты.",
            reply_markup=main_menu(),
        )
        return

    data = dict(profile)
    text = profile_text(data)

    if data.get("photo_file_id"):
        await callback.message.answer_photo(
            photo=data["photo_file_id"],
            caption=text,
            reply_markup=main_menu(),
        )
    else:
        await callback.message.answer(
            text,
            reply_markup=main_menu(),
        )


# =========================
# УДАЛЕНИЕ АНКЕТЫ
# =========================

@router.callback_query(
    F.data == "profile:delete"
)
async def delete_profile_confirm(
    callback: CallbackQuery,
) -> None:
    await callback.answer()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑️ Да, удалить",
                    callback_data="profile:delete_yes",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="profile:delete_no",
                ),
            ]
        ]
    )

    await callback.message.answer(
        "⚠️ <b>Удалить анкету?</b>\n\n"
        "Анкета и история лайков будут удалены.",
        reply_markup=keyboard,
    )


@router.callback_query(
    F.data == "profile:delete_no"
)
async def delete_profile_no(
    callback: CallbackQuery,
) -> None:
    await callback.answer()

    await callback.message.answer(
        "👌 Хорошо.",
        reply_markup=main_menu(),
    )


@router.callback_query(
    F.data == "profile:delete_yes"
)
async def delete_profile_yes(
    callback: CallbackQuery,
    db: Storage,
) -> None:
    await callback.answer()

    await db.delete_profile(
        callback.from_user.id
    )

    await callback.message.answer(
        "🗑️ <b>Анкета удалена.</b>\n\n"
        "Если захочешь — можешь создать новую.",
        reply_markup=main_menu(),
    )


# =========================
# ЗНАКОМСТВА
# =========================

@router.callback_query(
    F.data == "dating:start"
)
async def dating_start(
    callback: CallbackQuery,
    db: Storage,
) -> None:
    await callback.answer()

    profile = await db.get_profile(
        callback.from_user.id
    )

    if not profile:
        await callback.message.answer(
            "👤 Сначала создай анкету.",
            reply_markup=main_menu(),
        )
        return

    await callback.message.answer(
        "🔎 <b>Начинаем знакомства!</b>"
    )

    await send_next_profile(
        callback.message,
        callback.from_user.id,
        db,
    )


@router.callback_query(
    F.data.startswith("dating:")
)
async def dating_action(
    callback: CallbackQuery,
    db: Storage,
) -> None:
    parts = callback.data.split(":")

    if len(parts) != 3:
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    action = parts[1]

    try:
        target_id = int(parts[2])
    except ValueError:
        await callback.answer(
            "Ошибка анкеты.",
            show_alert=True,
        )
        return

    user_id = callback.from_user.id

    await callback.answer()

    if action == "block":
        await db.block_user(
            user_id,
            target_id,
        )

        await callback.message.answer(
            "🚫 Пользователь заблокирован."
        )

        await send_next_profile(
            callback.message,
            user_id,
            db,
        )
        return

    if action not in ("like", "skip"):
        return

    mutual = await db.swipe(
        user_id=user_id,
        target_id=target_id,
        action=action,
    )

    if action == "skip":
        await callback.message.answer(
            "❌ Пропущено."
        )

    elif mutual:
        target_username = (
            await db.get_username(
                target_id
            )
        )

        user_username = (
            await db.get_username(
                user_id
            )
        )

        buttons = []

        if target_username:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text="💬 Написать",
                        url=f"https://t.me/{target_username}",
                    )
                ]
            )

        keyboard = (
            InlineKeyboardMarkup(
                inline_keyboard=buttons
            )
            if buttons
            else None
        )

        await callback.message.answer(
            "💕 <b>ВЗАИМНАЯ СИМПАТИЯ!</b>\n\n"
            "Вы понравились друг другу! 🎉\n\n"
            "Теперь можете начать общение.",
            reply_markup=keyboard,
        )

        try:
            if user_username:
                await callback.bot.send_message(
                    target_id,
                    "💕 <b>Взаимная симпатия!</b>\n\n"
                    f"@{html.quote(user_username)} "
                    "тоже поставил(а) тебе лайк! ❤️",
                )
            else:
                await callback.bot.send_message(
                    target_id,
                    "💕 <b>Взаимная симпатия!</b>\n\n"
                    "Вы понравились друг другу! ❤️",
                )
        except Exception:
            pass

    else:
        await callback.message.answer(
            "❤️ <b>Лайк поставлен!</b>\n\n"
            "Если человек тоже поставит тебе лайк — "
            "я сообщу о взаимной симпатии."
        )

        try:
            sender_username = (
                await db.get_username(
                    user_id
                )
            )

            if sender_username:
                text = (
                    "❤️ <b>Тебе поставили лайк!</b>\n\n"
                    f"@{html.quote(sender_username)} "
                    "заинтересовался твоей анкетой. 🔥"
                )
            else:
                text = (
                    "❤️ <b>Тебе поставили лайк!</b>\n\n"
                    "Кто-то заинтересовался твоей анкетой. 🔥"
                )

            await callback.bot.send_message(
                target_id,
                text,
            )

        except Exception:
            pass

    await send_next_profile(
        callback.message,
        user_id,
        db,
    )


# =========================
# МОИ СИМПАТИИ
# =========================

@router.callback_query(
    F.data == "likes:show"
)
async def show_likes(
    callback: CallbackQuery,
    db: Storage,
) -> None:
    await callback.answer()

    likes = await db.get_likes(
        callback.from_user.id
    )

    if not likes:
        await callback.message.answer(
            "❤️ <b>Пока тебе никто не поставил лайк.</b>\n\n"
            "Продолжай знакомиться — всё впереди!",
            reply_markup=main_menu(),
        )
        return

    await callback.message.answer(
        f"❤️ <b>Тебе поставили лайк:</b> "
        f"{len(likes)}"
    )

    for profile in likes[:20]:
        data = dict(profile)

        text = profile_text(data)

        username = await db.get_username(
            data["user_id"]
        )

        buttons = []

        if username:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text="💬 Написать",
                        url=f"https://t.me/{username}",
                    )
                ]
            )

        keyboard = (
            InlineKeyboardMarkup(
                inline_keyboard=buttons
            )
            if buttons
            else None
        )

        if data.get("photo_file_id"):
            await callback.message.answer_photo(
                photo=data["photo_file_id"],
                caption=text,
                reply_markup=keyboard,
            )
        else:
            await callback.message.answer(
                text,
                reply_markup=keyboard,
            )


@router.callback_query(
    F.data == "dating:menu"
)
async def dating_menu(
    callback: CallbackQuery,
) -> None:
    await callback.answer()

    await callback.message.answer(
        "🏠 <b>Главное меню</b>",
        reply_markup=main_menu(),
    )
