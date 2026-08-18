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


# =========================================================
# СОСТОЯНИЯ АНКЕТЫ
# =========================================================

class ProfileStates(StatesGroup):
    name = State()
    age = State()
    city = State()
    gender = State()
    looking_for = State()
    photo = State()
    bio = State()


# =========================================================
# ГЛАВНОЕ МЕНЮ
# =========================================================

def main_menu(has_profile: bool = True) -> InlineKeyboardMarkup:
    if not has_profile:
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
                        text="ℹ️ Как это работает",
                        callback_data="info",
                    )
                ],
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔎 Найти партнёра",
                    callback_data="dating:start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❤️ Симпатии",
                    callback_data="likes:show",
                ),
                InlineKeyboardButton(
                    text="👤 Моя анкета",
                    callback_data="profile:me",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Изменить анкету",
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


# =========================================================
# ПОЛ
# =========================================================

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


# =========================================================
# КОГО ИЩЕТ
# =========================================================

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


# =========================================================
# КНОПКИ АНКЕТЫ
# =========================================================

def dating_keyboard(target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❤️",
                    callback_data=f"dating:like:{target_id}",
                ),
                InlineKeyboardButton(
                    text="❌",
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


# =========================================================
# ТЕКСТ АНКЕТЫ
# =========================================================

def profile_text(data: dict) -> str:
    name = html.quote(str(data.get("name", "")))
    age = data.get("age", "")
    city = html.quote(str(data.get("city", "")))
    gender = html.quote(str(data.get("gender", "")))
    looking_for = html.quote(
        str(data.get("looking_for", ""))
    )
    bio = html.quote(
        str(data.get("bio", ""))
    )

    return (
        f"👤 <b>{name}, {age}</b>\n"
        f"📍 {city}\n"
        f"🚻 {gender}\n"
        f"❤️ Ищет: {looking_for}\n\n"
        f"📝 {bio}"
    )


# =========================================================
# ПОКАЗ СЛЕДУЮЩЕЙ АНКЕТЫ
# =========================================================

async def send_next_profile(
    message: Message,
    user_id: int,
    db: Storage,
) -> None:
    profile = await db.get_next_profile(user_id)

    if not profile:
        await message.answer(
            "😔 <b>Пока новых анкет нет.</b>\n\n"
            "Загляни позже.",
            reply_markup=main_menu(True),
        )
        return

    data = dict(profile)

    text = profile_text(data)

    keyboard = dating_keyboard(
        int(data["user_id"])
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


# =========================================================
# START
# =========================================================

@router.message(CommandStart())
async def cmd_start(
    message: Message,
    db: Storage,
) -> None:
    user = message.from_user

    if user is None:
        return

    await db.track_user(
        user.id,
        user.username,
    )

    profile = await db.get_profile(
        user.id
    )

    if profile:
        await message.answer(
            "🔐 <b>Secret Match</b>\n\n"
            "Приватные знакомства без лишнего шума.\n\n"
            "Выбери действие:",
            reply_markup=main_menu(True),
        )
    else:
        await message.answer(
            "🔐 <b>Secret Match</b>\n\n"
            "Приватные знакомства для совершеннолетних.\n"
            "Создай анкету и найди человека с похожими интересами.\n\n"
            "🔒 Личные данные не показываются в анкете.",
            reply_markup=main_menu(False),
        )


# =========================================================
# HELP
# =========================================================

@router.message(Command("help"))
async def cmd_help(
    message: Message,
) -> None:
    await message.answer(
        "🔐 <b>Secret Match</b>\n\n"
        "❤️ Создай анкету.\n"
        "🔎 Просматривай подходящие анкеты.\n"
        "❤️ Ставь симпатию.\n"
        "❌ Пропускай.\n"
        "🚫 Блокируй пользователей.\n"
        "💕 При взаимной симпатии вы узнаете друг о друге."
    )


# =========================================================
# INFO
# =========================================================

@router.callback_query(
    F.data == "info"
)
async def show_info(
    callback: CallbackQuery,
) -> None:
    await callback.answer()

    await callback.message.answer(
        "🔐 <b>Как работает Secret Match</b>\n\n"
        "1️⃣ Создаёшь анкету.\n"
        "2️⃣ Выбираешь, кого хочешь найти.\n"
        "3️⃣ Смотришь анкеты.\n"
        "4️⃣ ❤️ — если человек понравился.\n"
        "5️⃣ ❌ — если хочешь пропустить.\n"
        "6️⃣ 💕 При взаимной симпатии бот сообщит вам обоим.\n\n"
        "🔒 Используй только свои фотографии "
        "и не публикуй личные данные.",
        reply_markup=main_menu(False),
    )


# =========================================================
# СОЗДАНИЕ АНКЕТЫ
# =========================================================

@router.callback_query(
    F.data == "profile:create"
)
async def create_profile(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()

    await state.clear()

    await state.set_state(
        ProfileStates.name
    )

    await callback.message.answer(
        "❤️ <b>Создание анкеты</b>\n\n"
        "👤 Как тебя зовут?"
    )


# =========================================================
# РЕДАКТИРОВАНИЕ
# =========================================================

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
            "👤 У тебя пока нет анкеты.",
            reply_markup=main_menu(False),
        )
        return

    await state.clear()

    await state.set_state(
        ProfileStates.name
    )

    await callback.message.answer(
        "✏️ <b>Изменение анкеты</b>\n\n"
        "👤 Введи новое имя:"
    )


# =========================================================
# ИМЯ
# =========================================================

@router.message(
    ProfileStates.name
)
async def profile_name(
    message: Message,
    state: FSMContext,
) -> None:
    name = (
        message.text or ""
    ).strip()

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

    await state.update_data(
        name=name
    )

    await state.set_state(
        ProfileStates.age
    )

    await message.answer(
        f"👋 <b>{html.quote(name)}</b>\n\n"
        "🎂 Сколько тебе лет?"
    )


# =========================================================
# ВОЗРАСТ
# =========================================================

@router.message(
    ProfileStates.age
)
async def profile_age(
    message: Message,
    state: FSMContext,
) -> None:
    text = (
        message.text or ""
    ).strip()

    if not text.isdigit():
        await message.answer(
            "🎂 Напиши возраст цифрами.\n\n"
            "Например: <b>22</b>"
        )
        return

    age = int(text)

    if age < 18:
        await message.answer(
            "🔞 Сервис предназначен "
            "только для пользователей 18+."
        )
        return

    if age > 100:
        await message.answer(
            "Проверь возраст."
        )
        return

    await state.update_data(
        age=age
    )

    await state.set_state(
        ProfileStates.city
    )

    await message.answer(
        "📍 В каком ты городе?"
    )


# =========================================================
# ГОРОД
# =========================================================

@router.message(
    ProfileStates.city
)
async def profile_city(
    message: Message,
    state: FSMContext,
) -> None:
    city = (
        message.text or ""
    ).strip()

    if not city:
        await message.answer(
            "Напиши город."
        )
        return

    if len(city) > 50:
        await message.answer(
            "Название города слишком длинное."
        )
        return

    await state.update_data(
        city=city
    )

    await state.set_state(
        ProfileStates.gender
    )

    await message.answer(
        "🚻 <b>Кто ты?</b>",
        reply_markup=gender_keyboard(),
    )


# =========================================================
# ПОЛ
# =========================================================

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
        "❤️ <b>Кого хочешь найти?</b>",
        reply_markup=looking_keyboard(),
    )


# =========================================================
# КОГО ИЩЕТ
# =========================================================

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
        "📸 <b>Теперь отправь фотографию.</b>\n\n"
        "Лучше выбрать фото, где хорошо видно лицо."
    )


# =========================================================
# ФОТО
# =========================================================

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
        "🔥 <b>Фото получил.</b>\n\n"
        "📝 Напиши немного о себе.\n\n"
        "Например: характер, интересы, "
        "что ищешь."
    )


@router.message(
    ProfileStates.photo
)
async def profile_photo_wrong(
    message: Message,
) -> None:
    await message.answer(
        "📸 Отправь именно фотографию."
    )


# =========================================================
# ОПИСАНИЕ
# =========================================================

@router.message(
    ProfileStates.bio
)
async def profile_bio(
    message: Message,
    state: FSMContext,
    db: Storage,
) -> None:
    bio = (
        message.text or ""
    ).strip()

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
        "✅ <b>Анкета готова.</b>\n\n"
        "Теперь можно начинать.",
        reply_markup=main_menu(True),
    )


# =========================================================
# МОЯ АНКЕТА
# =========================================================

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
            reply_markup=main_menu(False),
        )
        return

    data = dict(profile)

    text = profile_text(data)

    if data.get("photo_file_id"):
        await callback.message.answer_photo(
            photo=data["photo_file_id"],
            caption=text,
            reply_markup=main_menu(True),
        )
    else:
        await callback.message.answer(
            text,
            reply_markup=main_menu(True),
        )


# =========================================================
# УДАЛЕНИЕ АНКЕТЫ
# =========================================================

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
                    text="🗑 Да, удалить",
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
        "Анкета и история симпатий будут удалены.",
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
        "👌 Отмена.",
        reply_markup=main_menu(True),
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
        "🗑 <b>Анкета удалена.</b>\n\n"
        "Ты можешь создать новую анкету.",
        reply_markup=main_menu(False),
    )


# =========================================================
# НАЧАТЬ ЗНАКОМСТВА
# =========================================================

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
            reply_markup=main_menu(False),
        )
        return

    await send_next_profile(
        callback.message,
        callback.from_user.id,
        db,
    )


# =========================================================
# LIKE / SKIP / BLOCK
# =========================================================

@router.callback_query(
    F.data.startswith("dating:")
)
async def dating_action(
    callback: CallbackQuery,
    db: Storage,
) -> None:
    parts = (
        callback.data or ""
    ).split(":")

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

    # -----------------------------------------------------
    # BLOCK
    # -----------------------------------------------------

    if action == "block":
        await db.block_user(
            user_id,
            target_id,
        )

        await callback.message.answer(
            "🚫 <b>Пользователь заблокирован.</b>"
        )

        await send_next_profile(
            callback.message,
            user_id,
            db,
        )

        return

    # -----------------------------------------------------
    # LIKE / SKIP
    # -----------------------------------------------------

    if action not in (
        "like",
        "skip",
    ):
        return

    mutual = await db.swipe(
        user_id=user_id,
        target_id=target_id,
        action=action,
    )

    # -----------------------------------------------------
    # SKIP
    # -----------------------------------------------------

    if action == "skip":
        await send_next_profile(
            callback.message,
            user_id,
            db,
        )
        return

    # -----------------------------------------------------
    # MUTUAL LIKE
    # -----------------------------------------------------

    if mutual:
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
            "Вы понравились друг другу. ❤️\n\n"
            "Теперь можете начать общение.",
            reply_markup=keyboard,
        )

        try:
            if user_username:
                text = (
                    "💕 <b>Взаимная симпатия!</b>\n\n"
                    f"@{html.quote(user_username)} "
                    "тоже поставил(а) тебе ❤️"
                )
            else:
                text = (
                    "💕 <b>Взаимная симпатия!</b>\n\n"
                    "Вы понравились друг другу. ❤️"
                )

            await callback.bot.send_message(
                target_id,
                text,
            )

        except Exception:
            pass

    # -----------------------------------------------------
    # обычный LIKE
    # -----------------------------------------------------

    else:
        try:
            sender_username = (
                await db.get_username(
                    user_id
                )
            )

            if sender_username:
                text = (
                    "❤️ <b>Тебе поставили симпатию!</b>\n\n"
                    f"@{html.quote(sender_username)} "
                    "заинтересовался твоей анкетой."
                )
            else:
                text = (
                    "❤️ <b>Тебе поставили симпатию!</b>\n\n"
                    "Кто-то заинтересовался твоей анкетой."
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


# =========================================================
# МОИ СИМПАТИИ
# =========================================================

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
            "❤️ <b>Пока симпатий нет.</b>\n\n"
            "Начни знакомиться — всё впереди.",
            reply_markup=main_menu(True),
        )
        return

    await callback.message.answer(
        f"❤️ <b>Твои симпатии</b>\n\n"
        f"Количество: {len(likes)}"
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


# =========================================================
# МЕНЮ
# =========================================================

@router.callback_query(
    F.data == "dating:menu"
)
async def dating_menu(
    callback: CallbackQuery,
    db: Storage,
) -> None:
    await callback.answer()

    profile = await db.get_profile(
        callback.from_user.id
    )

    await callback.message.answer(
        "🔐 <b>Secret Match</b>",
        reply_markup=main_menu(
            bool(profile)
        ),
    )
