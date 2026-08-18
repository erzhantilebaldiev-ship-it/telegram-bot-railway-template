from __future__ import annotations

from datetime import date, time

from aiogram import F, Router, html
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from db import Storage


router = Router(name="meetups")


# =========================================================
# СОСТОЯНИЯ СОЗДАНИЯ СХОДКИ
# =========================================================

class MeetupStates(StatesGroup):
    place = State()
    date = State()
    time = State()
    max_people = State()
    description = State()


# =========================================================
# ГЛАВНОЕ МЕНЮ
# =========================================================

def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📍 Сходки",
                    callback_data="meetups:list",
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Создать сходку",
                    callback_data="meetup:create",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 Мои сходки",
                    callback_data="meetups:mine",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 Правила",
                    callback_data="rules",
                )
            ],
        ]
    )


def back_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="menu",
                )
            ]
        ]
    )


# =========================================================
# КАРТОЧКА СХОДКИ
# =========================================================

def meetup_keyboard(
    meetup_id: int,
    joined: bool = False,
) -> InlineKeyboardMarkup:

    buttons = []

    if not joined:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🙋 Участвовать",
                    callback_data=f"meetup:join:{meetup_id}",
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="👥 Участники",
                callback_data=f"meetup:members:{meetup_id}",
            )
        ]
    )

    buttons.append(
        [
            InlineKeyboardButton(
                text="📍 Место",
                callback_data=f"meetup:place:{meetup_id}",
            )
        ]
    )

    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="meetups:list",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


def meetup_text(data: dict) -> str:
    meetup_date = data["meetup_date"]
    meetup_time = data["meetup_time"]

    if hasattr(meetup_date, "strftime"):
        meetup_date = meetup_date.strftime("%d.%m.%Y")

    if hasattr(meetup_time, "strftime"):
        meetup_time = meetup_time.strftime("%H:%M")

    return (
        "📍 <b>СХОДКА</b>\n\n"
        f"📌 <b>Место:</b> "
        f"{html.quote(str(data['place']))}\n"
        f"📅 <b>Дата:</b> {meetup_date}\n"
        f"🕐 <b>Время:</b> {meetup_time}\n"
        f"👥 <b>Участники:</b> "
        f"{data['member_count']}/{data['max_people']}\n\n"
        f"📝 <b>Описание:</b>\n"
        f"{html.quote(str(data['description']))}"
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

    if user is not None:
        await db.track_user(
            user.id,
            user.username,
        )

    await message.answer(
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Здесь люди собираются для совместного "
        "отдыха, прогулок, игр и общения.\n\n"
        "🔞 Возраст: 18–28 лет.",
        reply_markup=main_menu(),
    )


# =========================================================
# ГЛАВНОЕ МЕНЮ
# =========================================================

@router.callback_query(
    F.data == "menu"
)
async def menu(
    callback: CallbackQuery,
) -> None:

    await callback.answer()

    await callback.message.answer(
        "🏠 <b>Главное меню</b>",
        reply_markup=main_menu(),
    )


# =========================================================
# ПРАВИЛА
# =========================================================

@router.callback_query(
    F.data == "rules"
)
async def rules(
    callback: CallbackQuery,
) -> None:

    await callback.answer()

    text = (
        "📜 <b>ПРАВИЛА СХОДОК</b>\n\n"
        "🔞 Участие только с 18 до 28 лет.\n\n"
        "🚫 Запрещены наркотики и любые запрещённые вещества.\n\n"
        "🚫 Запрещена продажа товаров и услуг.\n\n"
        "🚫 Запрещены сексуальные услуги и предложения.\n\n"
        "🚫 Никаких драк, угроз и агрессии.\n\n"
        "🤝 Уважай других участников.\n\n"
        "🔒 Не распространяй чужие личные данные "
        "и фотографии без разрешения.\n\n"
        "🎮 Сходки предназначены для общения, "
        "прогулок, игр и совместного времяпровождения.\n\n"
        "⚠️ Создатель сходки является её организатором "
        "и администратором группы."
    )

    await callback.message.answer(
        text,
        reply_markup=back_menu_keyboard(),
    )


# =========================================================
# СПИСОК СХОДОК
# =========================================================

@router.callback_query(
    F.data == "meetups:list"
)
async def meetups_list(
    callback: CallbackQuery,
    db: Storage,
) -> None:

    await callback.answer()

    await db.close_expired_meetups()

    meetups = await db.get_active_meetups()

    if not meetups:
        await callback.message.answer(
            "📍 <b>Сейчас активных сходок нет.</b>\n\n"
            "Можешь создать свою.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="➕ Создать сходку",
                            callback_data="meetup:create",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню",
                            callback_data="menu",
                        )
                    ],
                ]
            ),
        )
        return

    await callback.message.answer(
        "📍 <b>АКТИВНЫЕ СХОДКИ</b>\n\n"
        "Выбери интересующую тебя:",
    )

    for meetup in meetups:
        meetup_id = meetup["meetup_id"]

        meetup_date = meetup["meetup_date"]
        meetup_time = meetup["meetup_time"]

        if hasattr(meetup_date, "strftime"):
            meetup_date = meetup_date.strftime("%d.%m")

        if hasattr(meetup_time, "strftime"):
            meetup_time = meetup_time.strftime("%H:%M")

        text = (
            f"📍 <b>{html.quote(str(meetup['place']))}</b>\n"
            f"📅 {meetup_date}  🕐 {meetup_time}\n"
            f"👥 {meetup['member_count']}/{meetup['max_people']}"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Открыть",
                        callback_data=f"meetup:view:{meetup_id}",
                    )
                ]
            ]
        )

        await callback.message.answer(
            text,
            reply_markup=keyboard,
        )


# =========================================================
# ПРОСМОТР СХОДКИ
# =========================================================

@router.callback_query(
    F.data.startswith("meetup:view:")
)
async def meetup_view(
    callback: CallbackQuery,
    db: Storage,
) -> None:

    await callback.answer()

    try:
        meetup_id = int(
            callback.data.split(":")[2]
        )
    except (ValueError, IndexError):
        await callback.message.answer(
            "❌ Ошибка сходки."
        )
        return

    meetup = await db.get_meetup(
        meetup_id
    )

    if not meetup:
        await callback.message.answer(
            "❌ Эта сходка уже недоступна.",
            reply_markup=main_menu(),
        )
        return

    members = await db.get_meetup_members(
        meetup_id
    )

    user_id = callback.from_user.id

    joined = any(
        member["user_id"] == user_id
        for member in members
    )

    data = dict(meetup)

    await callback.message.answer(
        meetup_text(data),
        reply_markup=meetup_keyboard(
            meetup_id,
            joined=joined,
        ),
    )


# =========================================================
# СОЗДАНИЕ СХОДКИ
# =========================================================

@router.callback_query(
    F.data == "meetup:create"
)
async def meetup_create(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    await callback.answer()

    await state.clear()
    await state.set_state(
        MeetupStates.place
    )

    await callback.message.answer(
        "➕ <b>Создание сходки</b>\n\n"
        "📍 Напиши место проведения.\n\n"
        "Например:\n"
        "• Парк\n"
        "• Площадь\n"
        "• Анкара Парк"
    )


# =========================================================
# МЕСТО
# =========================================================

@router.message(
    MeetupStates.place
)
async def meetup_place(
    message: Message,
    state: FSMContext,
) -> None:

    place = (
        message.text or ""
    ).strip()

    if not place:
        await message.answer(
            "📍 Напиши место."
        )
        return

    if len(place) > 150:
        await message.answer(
            "📍 Название места слишком длинное."
        )
        return

    await state.update_data(
        place=place
    )

    await state.set_state(
        MeetupStates.date
    )

    await message.answer(
        "📅 Введи дату встречи.\n\n"
        "Формат:\n"
        "<b>25.08.2026</b>"
    )


# =========================================================
# ДАТА
# =========================================================

@router.message(
    MeetupStates.date
)
async def meetup_date(
    message: Message,
    state: FSMContext,
) -> None:

    text = (
        message.text or ""
    ).strip()

    try:
        day, month, year = map(
            int,
            text.split(".")
        )

        meetup_date = date(
            year,
            month,
            day,
        )

    except (ValueError, TypeError):
        await message.answer(
            "📅 Неверный формат.\n\n"
            "Используй:\n"
            "<b>25.08.2026</b>"
        )
        return

    if meetup_date < date.today():
        await message.answer(
            "📅 Нельзя создать сходку на прошедшую дату."
        )
        return

    await state.update_data(
        meetup_date=meetup_date
    )

    await state.set_state(
        MeetupStates.time
    )

    await message.answer(
        "🕐 Введи время.\n\n"
        "Например:\n"
        "<b>19:00</b>"
    )


# =========================================================
# ВРЕМЯ
# =========================================================

@router.message(
    MeetupStates.time
)
async def meetup_time(
    message: Message,
    state: FSMContext,
) -> None:

    text = (
        message.text or ""
    ).strip()

    try:
        hour, minute = map(
            int,
            text.split(":")
        )

        meetup_time = time(
            hour,
            minute,
        )

    except (ValueError, TypeError):
        await message.answer(
            "🕐 Неверный формат.\n\n"
            "Используй:\n"
            "<b>19:00</b>"
        )
        return

    await state.update_data(
        meetup_time=meetup_time
    )

    await state.set_state(
        MeetupStates.max_people
    )

    await message.answer(
        "👥 Сколько максимум людей может участвовать?\n\n"
        "Напиши число от <b>2</b> до <b>100</b>."
    )


# =========================================================
# ЛИМИТ
# =========================================================

@router.message(
    MeetupStates.max_people
)
async def meetup_max_people(
    message: Message,
    state: FSMContext,
) -> None:

    text = (
        message.text or ""
    ).strip()

    if not text.isdigit():
        await message.answer(
            "👥 Введи число.\n\n"
            "Например: <b>10</b>"
        )
        return

    max_people = int(text)

    if max_people < 2 or max_people > 100:
        await message.answer(
            "👥 Можно указать от 2 до 100 участников."
        )
        return

    await state.update_data(
        max_people=max_people
    )

    await state.set_state(
        MeetupStates.description
    )

    await message.answer(
        "📝 Напиши короткое описание сходки.\n\n"
        "Например:\n"
        "<i>Прогулка по городу, музыка, игры и просто хорошо проведём вечер.</i>"
    )


# =========================================================
# ОПИСАНИЕ И СОЗДАНИЕ
# =========================================================

@router.message(
    MeetupStates.description
)
async def meetup_description(
    message: Message,
    state: FSMContext,
    db: Storage,
) -> None:

    description = (
        message.text or ""
    ).strip()

    if len(description) > 500:
        await message.answer(
            "📝 Максимум 500 символов."
        )
        return

    user = message.from_user

    if user is None:
        return

    data = await state.get_data()

    meetup_id = await db.create_meetup(
        creator_id=user.id,
        place=data["place"],
        meetup_date=data["meetup_date"],
        meetup_time=data["meetup_time"],
        max_people=data["max_people"],
        description=description,
    )

    await state.clear()

    meetup = await db.get_meetup(
        meetup_id
    )

    if not meetup:
        await message.answer(
            "❌ Не удалось создать сходку.",
            reply_markup=main_menu(),
        )
        return

    await message.answer(
        "🎉 <b>Сходка создана!</b>\n\n"
        "Ты автоматически стал её организатором.",
        reply_markup=main_menu(),
    )

    await message.answer(
        meetup_text(dict(meetup)),
        reply_markup=meetup_keyboard(
            meetup_id,
            joined=True,
        ),
    )


# =========================================================
# ВСТУПЛЕНИЕ
# =========================================================

@router.callback_query(
    F.data.startswith("meetup:join:")
)
async def meetup_join(
    callback: CallbackQuery,
    db: Storage,
) -> None:

    await callback.answer()

    try:
        meetup_id = int(
            callback.data.split(":")[2]
        )
    except (ValueError, IndexError):
        return

    user_id = callback.from_user.id

    await db.track_user(
        user_id,
        callback.from_user.username,
    )

    success, text = await db.join_meetup(
        meetup_id,
        user_id,
    )

    await callback.message.answer(
        (
            "✅ <b>Ты присоединился!</b>\n\n"
            if success
            else f"ℹ️ <b>{html.quote(text)}</b>"
        )
    )

    meetup = await db.get_meetup(
        meetup_id
    )

    if meetup:
        members = await db.get_meetup_members(
            meetup_id
        )

        joined = any(
            member["user_id"] == user_id
            for member in members
        )

        await callback.message.answer(
            meetup_text(dict(meetup)),
            reply_markup=meetup_keyboard(
                meetup_id,
                joined=joined,
            ),
        )


# =========================================================
# УЧАСТНИКИ
# =========================================================

@router.callback_query(
    F.data.startswith("meetup:members:")
)
async def meetup_members(
    callback: CallbackQuery,
    db: Storage,
) -> None:

    await callback.answer()

    try:
        meetup_id = int(
            callback.data.split(":")[2]
        )
    except (ValueError, IndexError):
        return

    meetup = await db.get_meetup(
        meetup_id
    )

    if not meetup:
        await callback.message.answer(
            "❌ Сходка недоступна."
        )
        return

    members = await db.get_meetup_members(
        meetup_id
    )

    lines = [
        "👥 <b>УЧАСТНИКИ</b>\n"
    ]

    for index, member in enumerate(
        members,
        start=1,
    ):
        username = member["username"]

        if username:
            name = f"@{html.quote(username)}"
        else:
            name = "Участник"

        if member["user_id"] == meetup["creator_id"]:
            name += " 👑"

        lines.append(
            f"{index}. {name}"
        )

    await callback.message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data=f"meetup:view:{meetup_id}",
                    )
                ]
            ]
        ),
    )


# =========================================================
# МЕСТО
# =========================================================

@router.callback_query(
    F.data.startswith("meetup:place:")
)
async def meetup_place_view(
    callback: CallbackQuery,
    db: Storage,
) -> None:

    await callback.answer()

    try:
        meetup_id = int(
            callback.data.split(":")[2]
        )
    except (ValueError, IndexError):
        return

    meetup = await db.get_meetup(
        meetup_id
    )

    if not meetup:
        await callback.message.answer(
            "❌ Сходка недоступна."
        )
        return

    await callback.message.answer(
        "📍 <b>Место встречи</b>\n\n"
        f"{html.quote(str(meetup['place']))}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data=f"meetup:view:{meetup_id}",
                    )
                ]
            ]
        ),
    )


# =========================================================
# МОИ СХОДКИ
# =========================================================

@router.callback_query(
    F.data == "meetups:mine"
)
async def my_meetups(
    callback: CallbackQuery,
    db: Storage,
) -> None:

    await callback.answer()

    await db.close_expired_meetups()

    meetups = await db.get_user_meetups(
        callback.from_user.id
    )

    if not meetups:
        await callback.message.answer(
            "👥 <b>У тебя пока нет активных сходок.</b>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="➕ Создать сходку",
                            callback_data="meetup:create",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню",
                            callback_data="menu",
                        )
                    ],
                ]
            ),
        )
        return

    await callback.message.answer(
        "👥 <b>МОИ СХОДКИ</b>"
    )

    for meetup in meetups:
        meetup_id = meetup["meetup_id"]

        meetup_date = meetup["meetup_date"]
        meetup_time = meetup["meetup_time"]

        if hasattr(meetup_date, "strftime"):
            meetup_date = meetup_date.strftime("%d.%m")

        if hasattr(meetup_time, "strftime"):
            meetup_time = meetup_time.strftime("%H:%M")

        text = (
            f"📍 <b>{html.quote(str(meetup['place']))}</b>\n"
            f"📅 {meetup_date}  🕐 {meetup_time}\n"
            f"👥 {meetup['member_count']}/{meetup['max_people']}"
        )

        await callback.message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Открыть",
                            callback_data=f"meetup:view:{meetup_id}",
                        )
                    ]
                ]
            ),
        )
