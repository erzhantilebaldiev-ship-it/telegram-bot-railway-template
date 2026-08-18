from __future__ import annotations

from datetime import datetime, timedelta

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


router = Router(name="meetups")


# =========================================================
# СОСТОЯНИЯ
# =========================================================

class MeetupStates(StatesGroup):
    title = State()
    city = State()
    place = State()
    date = State()
    time = State()
    max_people = State()
    description = State()


# =========================================================
# КЛАВИАТУРЫ
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
                    callback_data="meetups:my",
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


def meetup_card_keyboard(
    meetup_id: int,
    is_member: bool = False,
    is_creator: bool = False,
) -> InlineKeyboardMarkup:

    rows = []

    if is_creator:
        rows.append(
            [
                InlineKeyboardButton(
                    text="👑 Управление",
                    callback_data=f"meetup:manage:{meetup_id}",
                )
            ]
        )

    elif is_member:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚪 Выйти",
                    callback_data=f"meetup:leave:{meetup_id}",
                )
            ]
        )

    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🙋 Участвовать",
                    callback_data=f"meetup:join:{meetup_id}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="👥 Участники",
                callback_data=f"meetup:members:{meetup_id}",
            )
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ К сходкам",
                callback_data="meetups:list",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def manage_keyboard(
    meetup_id: int,
) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👥 Участники",
                    callback_data=f"meetup:members:{meetup_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔗 Группа",
                    callback_data=f"meetup:group:{meetup_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏁 Завершить",
                    callback_data=f"meetup:close:{meetup_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"meetup:view:{meetup_id}",
                )
            ],
        ]
    )


# =========================================================
# ТЕКСТ КАРТОЧКИ
# =========================================================

def meetup_text(data: dict) -> str:
    member_count = int(
        data.get("member_count", 0)
    )

    max_people = int(
        data["max_people"]
    )

    free_places = max_people - member_count

    if free_places < 0:
        free_places = 0

    status = data.get(
        "status",
        "open",
    )

    if status == "open":
        status_text = "🟢 Открыта"
    elif status == "closed":
        status_text = "🔴 Завершена"
    else:
        status_text = "⚪ Неизвестно"

    description = (
        data.get("description")
        or "Без описания"
    )

    meetup_date = data["meetup_date"]
    meetup_time = data["meetup_time"]

    if hasattr(
        meetup_date,
        "strftime",
    ):
        date_text = meetup_date.strftime(
            "%d.%m.%Y"
        )
    else:
        date_text = str(meetup_date)

    if hasattr(
        meetup_time,
        "strftime",
    ):
        time_text = meetup_time.strftime(
            "%H:%M"
        )
    else:
        time_text = str(meetup_time)

    return (
        f"📍 <b>{html.quote(str(data['title']))}</b>\n\n"
        f"🏙 Город: <b>{html.quote(str(data['city']))}</b>\n"
        f"📌 Место: <b>{html.quote(str(data['place']))}</b>\n"
        f"📅 Дата: <b>{date_text}</b>\n"
        f"⏰ Время: <b>{time_text}</b>\n\n"
        f"👥 Участники: "
        f"<b>{member_count}/{max_people}</b>\n"
        f"🟢 Свободно мест: <b>{free_places}</b>\n"
        f"📊 Статус: {status_text}\n\n"
        f"📝 <b>Описание:</b>\n"
        f"{html.quote(str(description))}\n\n"
        f"🔞 <b>Возраст: 18–28 лет</b>"
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

    await message.answer(
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Здесь можно находить людей для совместного "
        "времяпровождения, прогулок, игр и сходок.\n\n"
        "🔞 Участие только для пользователей 18–28 лет.",
        reply_markup=main_menu(),
    )


# =========================================================
# /help
# =========================================================

@router.message(Command("help"))
async def cmd_help(
    message: Message,
) -> None:

    await message.answer(
        "ℹ️ <b>Помощь</b>\n\n"
        "Используй кнопки меню для навигации.",
        reply_markup=main_menu(),
    )


# =========================================================
# ГЛАВНОЕ МЕНЮ
# =========================================================

@router.callback_query(
    F.data == "menu"
)
async def open_menu(
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
async def show_rules(
    callback: CallbackQuery,
) -> None:

    await callback.answer()

    await callback.message.answer(
        "📜 <b>ПРАВИЛА СООБЩЕСТВА</b>\n\n"
        "🔞 <b>1. Возраст</b>\n"
        "Участие разрешено только пользователям "
        "от 18 до 28 лет.\n\n"
        "🤝 <b>2. Назначение</b>\n"
        "Сходки предназначены для общения, "
        "прогулок, игр, совместного времяпровождения "
        "и обычного отдыха.\n\n"
        "🚫 <b>3. Запрещено</b>\n"
        "• наркотики и запрещённые вещества;\n"
        "• продажа или передача запрещённых веществ;\n"
        "• сексуальные и интимные услуги за деньги;\n"
        "• продажа товаров и услуг через сходки;\n"
        "• угрозы, насилие и агрессия;\n"
        "• мошенничество;\n"
        "• незаконная деятельность.\n\n"
        "🛡 <b>4. Безопасность</b>\n"
        "Не передавай незнакомым людям пароли, "
        "коды подтверждения и другие личные данные.\n\n"
        "⚠️ <b>5. Ответственность</b>\n"
        "Каждый участник самостоятельно отвечает "
        "за своё поведение и соблюдение законодательства.\n\n"
        "👑 <b>6. Организатор</b>\n"
        "Создатель сходки является её организатором "
        "и администратором группы.\n\n"
        "❗ Нарушение правил может привести "
        "к блокировке участия в будущих сходках.",
        reply_markup=back_menu_keyboard(),
    )


# =========================================================
# СОЗДАНИЕ СХОДКИ
# =========================================================

@router.callback_query(
    F.data == "meetup:create"
)
async def create_meetup_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    await callback.answer()

    await state.clear()
    await state.set_state(
        MeetupStates.title
    )

    await callback.message.answer(
        "➕ <b>Создание сходки</b>\n\n"
        "Напиши название сходки.\n\n"
        "Например:\n"
        "🎮 Играем в настолки\n"
        "🌃 Вечерняя прогулка\n"
        "⚽ Играем в футбол"
    )


@router.message(
    MeetupStates.title
)
async def meetup_title(
    message: Message,
    state: FSMContext,
) -> None:

    title = (
        message.text or ""
    ).strip()

    if not title:
        await message.answer(
            "Напиши название сходки."
        )
        return

    if len(title) > 60:
        await message.answer(
            "Название слишком длинное.\n"
            "Максимум 60 символов."
        )
        return

    await state.update_data(
        title=title
    )

    await state.set_state(
        MeetupStates.city
    )

    await message.answer(
        "🏙 <b>Город</b>\n\n"
        "Напиши город проведения."
    )


@router.message(
    MeetupStates.city
)
async def meetup_city(
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
        MeetupStates.place
    )

    await message.answer(
        "📌 <b>Место</b>\n\n"
        "Напиши место встречи.\n\n"
        "Например:\n"
        "Парк Ататюрк\n"
        "Центральная площадь\n"
        "ТРЦ"
    )


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
            "Напиши место встречи."
        )
        return

    if len(place) > 150:
        await message.answer(
            "Описание места слишком длинное."
        )
        return

    await state.update_data(
        place=place
    )

    await state.set_state(
        MeetupStates.date
    )

    await message.answer(
        "📅 <b>Дата</b>\n\n"
        "Введи дату в формате:\n"
        "<b>25.08.2026</b>"
    )


@router.message(
    MeetupStates.date
)
async def meetup_date(
    message: Message,
    state: FSMContext,
) -> None:

    value = (
        message.text or ""
    ).strip()

    try:
        meetup_date = datetime.strptime(
            value,
            "%d.%m.%Y",
        ).date()

    except ValueError:
        await message.answer(
            "❌ Неверный формат.\n\n"
            "Используй:\n"
            "<b>25.08.2026</b>"
        )
        return

    if meetup_date < datetime.now().date():
        await message.answer(
            "❌ Нельзя выбрать прошедшую дату."
        )
        return

    await state.update_data(
        meetup_date=meetup_date
    )

    await state.set_state(
        MeetupStates.time
    )

    await message.answer(
        "⏰ <b>Время</b>\n\n"
        "Введи время в формате:\n"
        "<b>19:00</b>"
    )


@router.message(
    MeetupStates.time
)
async def meetup_time(
    message: Message,
    state: FSMContext,
) -> None:

    value = (
        message.text or ""
    ).strip()

    try:
        meetup_time = datetime.strptime(
            value,
            "%H:%M",
        ).time()

    except ValueError:
        await message.answer(
            "❌ Неверный формат.\n\n"
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
        "👥 <b>Количество участников</b>\n\n"
        "Сколько человек максимум может участвовать?\n\n"
        "Например: <b>10</b>"
    )


@router.message(
    MeetupStates.max_people
)
async def meetup_max_people(
    message: Message,
    state: FSMContext,
) -> None:

    value = (
        message.text or ""
    ).strip()

    if not value.isdigit():
        await message.answer(
            "Введи количество цифрами.\n"
            "Например: <b>10</b>"
        )
        return

    max_people = int(value)

    if max_people < 2:
        await message.answer(
            "Минимум 2 участника."
        )
        return

    if max_people > 100:
        await message.answer(
            "Максимум 100 участников."
        )
        return

    await state.update_data(
        max_people=max_people
    )

    await state.set_state(
        MeetupStates.description
    )

    await message.answer(
        "📝 <b>Описание</b>\n\n"
        "Расскажи, чем будете заниматься.\n\n"
        "Например:\n"
        "«Собираемся погулять, поиграть "
        "в футбол и потом посидеть вместе»"
    )


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

    if not description:
        await message.answer(
            "Напиши описание."
        )
        return

    if len(description) > 500:
        await message.answer(
            "Максимум 500 символов."
        )
        return

    user = message.from_user

    if user is None:
        return

    data = await state.get_data()

    meetup_date = data["meetup_date"]
    meetup_time = data["meetup_time"]

    start_datetime = datetime.combine(
        meetup_date,
        meetup_time,
    )

    ends_at = (
        start_datetime
        + timedelta(hours=24)
    )

    meetup_id = await db.create_meetup(
        creator_id=user.id,
        title=data["title"],
        city=data["city"],
        place=data["place"],
        meetup_date=meetup_date,
        meetup_time=meetup_time,
        description=description,
        max_people=data["max_people"],
        ends_at=ends_at,
    )

    await state.clear()

    meetup = await db.get_meetup(
        meetup_id
    )

    await message.answer(
        "🎉 <b>Сходка создана!</b>\n\n"
        "Ты автоматически являешься "
        "организатором и администратором.",
    )

    if meetup:
        data = dict(meetup)

        await message.answer(
            meetup_text(data),
            reply_markup=meetup_card_keyboard(
                meetup_id,
                is_member=True,
                is_creator=True,
            ),
        )


# =========================================================
# СПИСОК СХОДОК
# =========================================================

@router.callback_query(
    F.data == "meetups:list"
)
async def list_meetups(
    callback: CallbackQuery,
    db: Storage,
) -> None:

    await callback.answer()

    meetups = await db.get_open_meetups(
        limit=20
    )

    if not meetups:
        await callback.message.answer(
            "📍 <b>Сейчас открытых сходок нет.</b>\n\n"
            "Ты можешь создать первую.",
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
                            text="🏠 Меню",
                            callback_data="menu",
                        )
                    ],
                ]
            ),
        )
        return

    await callback.message.answer(
        "📍 <b>Открытые сходки</b>\n\n"
        "Выбери подходящую:"
    )

    for meetup in meetups:

        data = dict(meetup)

        meetup_id = data["meetup_id"]

        is_member = await db.is_member(
            meetup_id,
            callback.from_user.id,
        )

        is_creator = (
            data["creator_id"]
            == callback.from_user.id
        )

        await callback.message.answer(
            meetup_text(data),
            reply_markup=meetup_card_keyboard(
                meetup_id,
                is_member=is_member,
                is_creator=is_creator,
            ),
        )


# =========================================================
# ПРОСМОТР СХОДКИ
# =========================================================

@router.callback_query(
    F.data.startswith("meetup:view:")
)
async def view_meetup(
    callback: CallbackQuery,
    db: Storage,
) -> None:

    await callback.answer()

    try:
        meetup_id = int(
            callback.data.split(":")[2]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    meetup = await db.get_meetup(
        meetup_id
    )

    if not meetup:
        await callback.message.answer(
            "❌ Сходка не найдена.",
            reply_markup=main_menu(),
        )
        return

    data = dict(meetup)

    is_member = await db.is_member(
        meetup_id,
        callback.from_user.id,
    )

    is_creator = (
        data["creator_id"]
        == callback.from_user.id
    )

    await callback.message.answer(
        meetup_text(data),
        reply_markup=meetup_card_keyboard(
            meetup_id,
            is_member=is_member,
            is_creator=is_creator,
        ),
    )


# =========================================================
# ВСТУПЛЕНИЕ
# =========================================================

@router.callback_query(
    F.data.startswith("meetup:join:")
)
async def join_meetup(
    callback: CallbackQuery,
    db: Storage,
) -> None:

    try:
        meetup_id = int(
            callback.data.split(":")[2]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    user = callback.from_user

    await db.track_user(
        user.id,
        user.username,
    )

    meetup = await db.get_meetup(
        meetup_id
    )

    if not meetup:
        await callback.answer(
            "Сходка не найдена.",
            show_alert=True,
        )
        return

    data = dict(meetup)

    if data["status"] != "open":
        await callback.answer(
            "Эта сходка уже завершена.",
            show_alert=True,
        )
        return

    age = None

    # Возраст хранится пока не в отдельном профиле.
    # Поэтому здесь система не может определить возраст
    # автоматически. Проверка будет добавлена после
    # подключения профиля пользователя.

    member_count = int(
        data["member_count"]
    )

    if member_count >= int(
        data["max_people"]
    ):
        await callback.answer(
            "❌ Свободных мест нет.",
            show_alert=True,
        )
        return

    success = await db.join_meetup(
        meetup_id,
        user.id,
    )

    if not success:

        already = await db.is_member(
            meetup_id,
            user.id,
        )

        if already:
            await callback.answer(
                "Ты уже участвуешь.",
                show_alert=True,
            )
        else:
            await callback.answer(
                "Не удалось присоединиться.",
                show_alert=True,
            )

        return

    await callback.answer(
        "✅ Ты присоединился!"
    )

    updated = await db.get_meetup(
        meetup_id
    )

    if updated:
        updated_data = dict(updated)

        await callback.message.answer(
            "🙋 <b>Ты участвуешь в сходке!</b>\n\n"
            "Организатор увидит тебя в списке участников.",
            reply_markup=meetup_card_keyboard(
                meetup_id,
                is_member=True,
                is_creator=False,
            ),
        )


# =========================================================
# ВЫХОД
# =========================================================

@router.callback_query(
    F.data.startswith("meetup:leave:")
)
async def leave_meetup(
    callback: CallbackQuery,
    db: Storage,
) -> None:

    try:
        meetup_id = int(
            callback.data.split(":")[2]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    success = await db.leave_meetup(
        meetup_id,
        callback.from_user.id,
    )

    if not success:
        await callback.answer(
            "Ты не можешь выйти из этой сходки.",
            show_alert=True,
        )
        return

    await callback.answer(
        "Ты вышел из сходки."
    )

    await callback.message.answer(
        "🚪 <b>Ты вышел из сходки.</b>",
        reply_markup=main_menu(),
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

    try:
        meetup_id = int(
            callback.data.split(":")[2]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    meetup = await db.get_meetup(
        meetup_id
    )

    if not meetup:
        await callback.answer(
            "Сходка не найдена.",
            show_alert=True,
        )
        return

    members = await db.get_members(
        meetup_id
    )

    if not members:
        await callback.message.answer(
            "👥 Пока участников нет.",
            reply_markup=back_menu_keyboard(),
        )
        return

    lines = [
        "👥 <b>Участники сходки</b>\n"
    ]

    for index, member in enumerate(
        members,
        start=1,
    ):

        username = member.get(
            "username"
        )

        if username:
            name = f"@{html.quote(username)}"
        else:
            name = "Пользователь"

        if (
            member["user_id"]
            == meetup["creator_id"]
        ):
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
                        text="⬅️ К сходке",
                        callback_data=(
                            f"meetup:view:{meetup_id}"
                        ),
                    )
                ]
            ]
        ),
    )


# =========================================================
# МОИ СХОДКИ
# =========================================================

@router.callback_query(
    F.data == "meetups:my"
)
async def my_meetups(
    callback: CallbackQuery,
    db: Storage,
) -> None:

    await callback.answer()

    meetups = await db.get_my_meetups(
        callback.from_user.id,
        limit=20,
    )

    if not meetups:
        await callback.message.answer(
            "👥 <b>У тебя пока нет созданных сходок.</b>",
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
                            text="🏠 Меню",
                            callback_data="menu",
                        )
                    ],
                ]
            ),
        )
        return

    await callback.message.answer(
        "👥 <b>Твои сходки</b>"
    )

    for meetup in meetups:

        data = dict(meetup)

        meetup_id = data["meetup_id"]

        await callback.message.answer(
            meetup_text(data),
            reply_markup=meetup_card_keyboard(
                meetup_id,
                is_member=True,
                is_creator=True,
            ),
        )


# =========================================================
# УПРАВЛЕНИЕ СХОДКОЙ
# =========================================================

@router.callback_query(
    F.data.startswith("meetup:manage:")
)
async def manage_meetup(
    callback: CallbackQuery,
    db: Storage,
) -> None:

    try:
        meetup_id = int(
            callback.data.split(":")[2]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    meetup = await db.get_meetup(
        meetup_id
    )

    if not meetup:
        await callback.answer(
            "Сходка не найдена.",
            show_alert=True,
        )
        return

    if (
        meetup["creator_id"]
        != callback.from_user.id
    ):
        await callback.answer(
            "Только организатор может управлять сходкой.",
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.answer(
        "👑 <b>Управление сходкой</b>\n\n"
        "Ты являешься организатором.",
        reply_markup=manage_keyboard(
            meetup_id
        ),
    )


# =========================================================
# ГРУППА
# =========================================================

@router.callback_query(
    F.data.startswith("meetup:group:")
)
async def meetup_group(
    callback: CallbackQuery,
    db: Storage,
) -> None:

    try:
        meetup_id = int(
            callback.data.split(":")[2]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    meetup = await db.get_meetup(
        meetup_id
    )

    if not meetup:
        await callback.answer(
            "Сходка не найдена.",
            show_alert=True,
        )
        return

    if (
        meetup["creator_id"]
        != callback.from_user.id
    ):
        await callback.answer(
            "Только организатор может управлять группой.",
            show_alert=True,
        )
        return

    if meetup["group_chat_id"]:
        await callback.message.answer(
            "👥 <b>Группа уже создана.</b>\n\n"
            "Позже сюда будет добавлена кнопка "
            "для перехода в группу."
        )
        return

    await callback.answer()

    await callback.message.answer(
        "👥 <b>Группа для этой сходки</b>\n\n"
        "Создание Telegram-группы подключим следующим этапом.\n\n"
        "После подключения бот сможет хранить "
        "ID группы и использовать её для участников.",
        reply_markup=manage_keyboard(
            meetup_id
        ),
    )


# =========================================================
# ЗАВЕРШЕНИЕ СХОДКИ
# =========================================================

@router.callback_query(
    F.data.startswith("meetup:close:")
)
async def close_meetup_confirm(
    callback: CallbackQuery,
    db: Storage,
) -> None:

    try:
        meetup_id = int(
            callback.data.split(":")[2]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    meetup = await db.get_meetup(
        meetup_id
    )

    if not meetup:
        await callback.answer(
            "Сходка не найдена.",
            show_alert=True,
        )
        return

    if (
        meetup["creator_id"]
        != callback.from_user.id
    ):
        await callback.answer(
            "Только организатор может завершить сходку.",
            show_alert=True,
        )
        return

    await callback.answer()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏁 Да, завершить",
                    callback_data=(
                        f"meetup:close_yes:{meetup_id}"
                    ),
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=(
                        f"meetup:close_no:{meetup_id}"
                    ),
                ),
            ]
        ]
    )

    await callback.message.answer(
        "⚠️ <b>Завершить сходку?</b>\n\n"
        "После завершения новые участники "
        "не смогут присоединиться.",
        reply_markup=keyboard,
    )


@router.callback_query(
    F.data.startswith("meetup:close_yes:")
)
async def close_meetup_yes(
    callback: CallbackQuery,
    db: Storage,
) -> None:

    try:
        meetup_id = int(
            callback.data.split(":")[2]
        )
    except (ValueError, IndexError):
        await callback.answer(
            "Ошибка.",
            show_alert=True,
        )
        return

    meetup = await db.get_meetup(
        meetup_id
    )

    if not meetup:
        await callback.answer(
            "Сходка не найдена.",
            show_alert=True,
        )
        return

    if (
        meetup["creator_id"]
        != callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True,
        )
        return

    await db.close_meetup(
        meetup_id
    )

    await callback.answer(
        "Сходка завершена."
    )

    await callback.message.answer(
        "🏁 <b>Сходка завершена.</b>\n\n"
        "Спасибо за участие!",
        reply_markup=main_menu(),
    )


@router.callback_query(
    F.data.startswith("meetup:close_no:")
)
async def close_meetup_no(
    callback: CallbackQuery,
) -> None:

    await callback.answer()

    await callback.message.answer(
        "👌 Сходка не завершена.",
        reply_markup=main_menu(),
    )


# =========================================================
# НЕИЗВЕСТНЫЕ КОМАНДЫ
# =========================================================

@router.message()
async def fallback(
    message: Message,
) -> None:

    await message.answer(
        "Используй кнопки меню 👇",
        reply_markup=main_menu(),
    )
