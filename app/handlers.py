from future import annotations

from datetime import datetime, timedelta, timezone

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

router = Router(name=“meetups”)

============================================================

СОСТОЯНИЯ СОЗДАНИЯ СХОДКИ

============================================================

class MeetupStates(StatesGroup):
title = State()
place = State()
date = State()
time = State()
duration = State()
limit = State()
description = State()

============================================================

ОСНОВНЫЕ КНОПКИ

============================================================

def main_menu() -> InlineKeyboardMarkup:
return InlineKeyboardMarkup(
inline_keyboard=[
[
InlineKeyboardButton(
text=“📍 Сходки”,
callback_data=“meetups:list”,
)
],
[
InlineKeyboardButton(
text=“➕ Создать сходку”,
callback_data=“meetup:create”,
)
],
[
InlineKeyboardButton(
text=“👥 Мои сходки”,
callback_data=“meetups:mine”,
)
],
[
InlineKeyboardButton(
text=“📜 Правила”,
callback_data=“rules:show”,
)
],
]
)

def back_menu_keyboard() -> InlineKeyboardMarkup:
return InlineKeyboardMarkup(
inline_keyboard=[
[
InlineKeyboardButton(
text=“🏠 Главное меню”,
callback_data=“menu”,
)
]
]
)

def meetup_keyboard(
meetup_id: int,
joined: bool,
) -> InlineKeyboardMarkup:

buttons = []
if joined:
    buttons.append(
        [
            InlineKeyboardButton(
                text="❌ Покинуть сходку",
                callback_data=f"meetup:leave:{meetup_id}",
            )
        ]
    )
else:
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
            callback_data=f"meetup:participants:{meetup_id}",
        )
    ]
)
buttons.append(
    [
        InlineKeyboardButton(
            text="🏠 Меню",
            callback_data="menu",
        )
    ]
)
return InlineKeyboardMarkup(
    inline_keyboard=buttons
)

============================================================

ТЕКСТ СХОДКИ

============================================================

def meetup_text(data: dict) -> str:

starts_at = data["starts_at"]
ends_at = data["ends_at"]
if starts_at.tzinfo is None:
    starts_at = starts_at.replace(
        tzinfo=timezone.utc
    )
if ends_at.tzinfo is None:
    ends_at = ends_at.replace(
        tzinfo=timezone.utc
    )
date_text = starts_at.strftime(
    "%d.%m.%Y"
)
start_text = starts_at.strftime(
    "%H:%M"
)
end_text = ends_at.strftime(
    "%H:%M"
)
count = data.get(
    "participant_count",
    0,
)
limit = data["max_participants"]
description = data.get(
    "description",
    "",
)
result = (
    f"📍 <b>{html.quote(str(data['title']))}</b>\n\n"
    f"🗓 Дата: <b>{date_text}</b>\n"
    f"🕐 Время: <b>{start_text} — {end_text}</b>\n"
    f"📌 Место: <b>{html.quote(str(data['place']))}</b>\n"
    f"👥 Участники: <b>{count}/{limit}</b>\n\n"
)
if description:
    result += (
        "📝 <b>Описание:</b>\n"
        f"{html.quote(str(description))}\n\n"
    )
result += (
    "🔞 Возраст: <b>18+</b>\n"
    "🚫 Только отдых, прогулки и совместное "
    "проведение времени."
)
return result

============================================================

/START

============================================================

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
    "Здесь можно находить и создавать сходки:\n\n"
    "📍 прогулки\n"
    "🎮 игры\n"
    "⚽ активный отдых\n"
    "☕ общение\n"
    "🎉 совместное проведение времени\n\n"
    "Выбери действие:",
    reply_markup=main_menu(),
)

============================================================

ПОМОЩЬ

============================================================

@router.message(Command(“help”))
async def cmd_help(
message: Message,
) -> None:

await message.answer(
    "ℹ️ <b>Как пользоваться ботом</b>\n\n"
    "📍 Открывай список сходок.\n"
    "🙋 Выбирай подходящую и вступай.\n"
    "➕ Или создай свою сходку.\n\n"
    "Все мероприятия предназначены только "
    "для совместного отдыха и общения.",
    reply_markup=main_menu(),
)

============================================================

ГЛАВНОЕ МЕНЮ

============================================================

@router.callback_query(
F.data == “menu”
)
async def menu(
callback: CallbackQuery,
) -> None:

await callback.answer()
await callback.message.answer(
    "🏠 <b>Главное меню</b>",
    reply_markup=main_menu(),
)

============================================================

ПРАВИЛА

============================================================

@router.callback_query(
F.data == “rules:show”
)
async def show_rules(
callback: CallbackQuery,
) -> None:

await callback.answer()
await callback.message.answer(
    "📜 <b>ПРАВИЛА СХОДОК</b>\n\n"
    "1️⃣ Участие только для лиц <b>18+</b>.\n\n"
    "2️⃣ Сходки предназначены исключительно "
    "для общения, прогулок, игр и совместного "
    "проведения времени.\n\n"
    "3️⃣ 🚫 Запрещены наркотики и любые "
    "запрещённые вещества.\n\n"
    "4️⃣ 🚫 Запрещены любые незаконные услуги "
    "и деятельность.\n\n"
    "5️⃣ 🚫 Запрещены угрозы, агрессия, драки, "
    "оскорбления и травля.\n\n"
    "6️⃣ 🚫 Запрещено использовать сходки "
    "для продажи запрещённых товаров или услуг.\n\n"
    "7️⃣ Участники самостоятельно отвечают "
    "за своё поведение и соблюдение законов.\n\n"
    "8️⃣ Организатор указывает реальное место, "
    "дату, время и максимальное количество участников.\n\n"
    "9️⃣ После окончания срока сходки участники "
    "удаляются из Telegram-группы автоматически "
    "через 24 часа.\n\n"
    "🔟 Создатель бота также не остаётся в группе "
    "после автоматической очистки.",
    reply_markup=back_menu_keyboard(),
)

============================================================

СПИСОК СХОДОК

============================================================

@router.callback_query(
F.data == “meetups:list”
)
async def meetups_list(
callback: CallbackQuery,
db: Storage,
) -> None:

await callback.answer()
meetups = await db.get_active_meetups()
if not meetups:
    await callback.message.answer(
        "📍 <b>Сейчас нет активных сходок.</b>\n\n"
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
    "📍 <b>Доступные сходки:</b>"
)
for meetup in meetups:
    data = dict(meetup)
    joined = await db.is_participant(
        data["meetup_id"],
        callback.from_user.id,
    )
    await callback.message.answer(
        meetup_text(data),
        reply_markup=meetup_keyboard(
            data["meetup_id"],
            joined,
        ),
    )

============================================================

МОИ СХОДКИ

============================================================

@router.callback_query(
F.data == “meetups:mine”
)
async def my_meetups(
callback: CallbackQuery,
db: Storage,
) -> None:

await callback.answer()
meetups = await db.get_my_meetups(
    callback.from_user.id
)
if not meetups:
    await callback.message.answer(
        "👥 <b>Ты пока не участвуешь "
        "ни в одной сходке.</b>",
        reply_markup=main_menu(),
    )
    return
await callback.message.answer(
    "👥 <b>Мои сходки:</b>"
)
for meetup in meetups:
    data = dict(meetup)
    await callback.message.answer(
        meetup_text(data),
        reply_markup=meetup_keyboard(
            data["meetup_id"],
            True,
        ),
    )

============================================================

СОЗДАНИЕ СХОДКИ

============================================================

@router.callback_query(
F.data == “meetup:create”
)
async def meetup_create_start(
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
    "Как будет называться сходка?\n\n"
    "Например:\n"
    "🎮 Играем в футбол"
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
        "Напиши название."
    )
    return
if len(title) > 100:
    await message.answer(
        "Название слишком длинное.\n"
        "Максимум 100 символов."
    )
    return
await state.update_data(
    title=title
)
await state.set_state(
    MeetupStates.place
)
await message.answer(
    "📌 <b>Где будет сходка?</b>\n\n"
    "Напиши место."
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
        "Напиши место."
    )
    return
if len(place) > 200:
    await message.answer(
        "Место слишком длинное."
    )
    return
await state.update_data(
    place=place
)
await state.set_state(
    MeetupStates.date
)
await message.answer(
    "🗓 <b>Дата сходки</b>\n\n"
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

text = (
    message.text or ""
).strip()
try:
    date = datetime.strptime(
        text,
        "%d.%m.%Y",
    ).date()
except ValueError:
    await message.answer(
        "❌ Неверный формат.\n\n"
        "Используй:\n"
        "<b>25.08.2026</b>"
    )
    return
await state.update_data(
    date=date.isoformat()
)
await state.set_state(
    MeetupStates.time
)
await message.answer(
    "🕐 <b>Во сколько начинается?</b>\n\n"
    "Например:\n"
    "<b>18:30</b>"
)

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
    time = datetime.strptime(
        text,
        "%H:%M",
    ).time()
except ValueError:
    await message.answer(
        "❌ Неверный формат.\n\n"
        "Например:\n"
        "<b>18:30</b>"
    )
    return
data = await state.get_data()
date = datetime.fromisoformat(
    data["date"]
).date()
starts_at = datetime.combine(
    date,
    time,
).replace(
    tzinfo=timezone.utc
)
if starts_at <= datetime.now(
    timezone.utc
):
    await message.answer(
        "❌ Дата и время уже прошли.\n\n"
        "Укажи будущее время."
    )
    return
await state.update_data(
    starts_at=starts_at.isoformat()
)
await state.set_state(
    MeetupStates.duration
)
await message.answer(
    "⏱ <b>Сколько будет длиться сходка?</b>\n\n"
    "Например:\n"
    "<b>2</b> — два часа"
)

@router.message(
MeetupStates.duration
)
async def meetup_duration(
message: Message,
state: FSMContext,
) -> None:

text = (
    message.text or ""
).strip()
if not text.isdigit():
    await message.answer(
        "Напиши количество часов цифрой.\n"
        "Например: <b>2</b>"
    )
    return
hours = int(text)
if hours < 1 or hours > 24:
    await message.answer(
        "Продолжительность должна быть "
        "от 1 до 24 часов."
    )
    return
data = await state.get_data()
starts_at = datetime.fromisoformat(
    data["starts_at"]
)
ends_at = (
    starts_at
    + timedelta(hours=hours)
)
await state.update_data(
    ends_at=ends_at.isoformat()
)
await state.set_state(
    MeetupStates.limit
)
await message.answer(
    "👥 <b>Сколько максимум участников?</b>\n\n"
    "Например:\n"
    "<b>10</b>"
)

@router.message(
MeetupStates.limit
)
async def meetup_limit(
message: Message,
state: FSMContext,
) -> None:

text = (
    message.text or ""
).strip()
if not text.isdigit():
    await message.answer(
        "Напиши количество цифрой."
    )
    return
limit = int(text)
if limit < 1 or limit > 100:
    await message.answer(
        "Количество участников: "
        "от 1 до 100."
    )
    return
await state.update_data(
    limit=limit
)
await state.set_state(
    MeetupStates.description
)
await message.answer(
    "📝 <b>Описание сходки</b>\n\n"
    "Напиши, чем будете заниматься.\n\n"
    "Например:\n"
    "«Прогулка по городу, потом кофе и игры»"
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
        "Описание слишком длинное.\n"
        "Максимум 500 символов."
    )
    return
user = message.from_user
if user is None:
    return
data = await state.get_data()
starts_at = datetime.fromisoformat(
    data["starts_at"]
)
ends_at = datetime.fromisoformat(
    data["ends_at"]
)
meetup_id = await db.create_meetup(
    creator_id=user.id,
    title=data["title"],
    place=data["place"],
    starts_at=starts_at,
    ends_at=ends_at,
    description=description,
    max_participants=data["limit"],
)
# Создатель автоматически становится
# первым участником.
await db.join_meetup(
    meetup_id,
    user.id,
)
await state.clear()
meetup = await db.get_meetup(
    meetup_id
)
if meetup:
    await message.answer(
        "🎉 <b>Сходка создана!</b>\n\n"
        "Ты автоматически добавлен "
        "как первый участник.",
    )
    await message.answer(
        meetup_text(dict(meetup)),
        reply_markup=meetup_keyboard(
            meetup_id,
            True,
        ),
    )
else:
    await message.answer(
        "🎉 Сходка создана!",
        reply_markup=main_menu(),
    )

============================================================

ВСТУПЛЕНИЕ

============================================================

@router.callback_query(
F.data.startswith(“meetup:join:”)
)
async def meetup_join(
callback: CallbackQuery,
db: Storage,
) -> None:

try:
    meetup_id = int(
        callback.data.split(":")[2]
    )
except (
    ValueError,
    IndexError,
):
    await callback.answer(
        "Ошибка.",
        show_alert=True,
    )
    return
await callback.answer()
user = callback.from_user
await db.track_user(
    user.id,
    user.username,
)
success, reason = await db.join_meetup(
    meetup_id,
    user.id,
)
if not success:
    messages = {
        "not_found": "Сходка не найдена.",
        "closed": "Сходка уже закрыта.",
        "expired": "Срок сходки истёк.",
        "already_joined": "Ты уже участвуешь.",
        "full": "Свободных мест больше нет.",
    }
    await callback.message.answer(
        messages.get(
            reason,
            "Не удалось присоединиться.",
        ),
        reply_markup=main_menu(),
    )
    return
meetup = await db.get_meetup(
    meetup_id
)
if not meetup:
    return
await callback.message.answer(
    "🙋 <b>Ты добавлен в сходку!</b>\n\n"
    "До начала мероприятия оставайся "
    "в группе и следи за сообщениями.",
    reply_markup=meetup_keyboard(
        meetup_id,
        True,
    ),
)

============================================================

ВЫХОД

============================================================

@router.callback_query(
F.data.startswith(“meetup:leave:”)
)
async def meetup_leave(
callback: CallbackQuery,
db: Storage,
) -> None:

try:
    meetup_id = int(
        callback.data.split(":")[2]
    )
except (
    ValueError,
    IndexError,
):
    await callback.answer(
        "Ошибка.",
        show_alert=True,
    )
    return
await callback.answer()
success = await db.leave_meetup(
    meetup_id,
    callback.from_user.id,
)
if success:
    await callback.message.answer(
        "❌ Ты вышел из сходки.",
        reply_markup=main_menu(),
    )
else:
    await callback.message.answer(
        "Ты не являешься участником "
        "этой сходки.",
        reply_markup=main_menu(),
    )

============================================================

УЧАСТНИКИ

============================================================

@router.callback_query(
F.data.startswith(“meetup:participants:”)
)
async def meetup_participants(
callback: CallbackQuery,
db: Storage,
) -> None:

try:
    meetup_id = int(
        callback.data.split(":")[2]
    )
except (
    ValueError,
    IndexError,
):
    await callback.answer(
        "Ошибка.",
        show_alert=True,
    )
    return
await callback.answer()
participants = await db.get_participants(
    meetup_id
)
if not participants:
    await callback.message.answer(
        "👥 Пока участников нет."
    )
    return
lines = [
    "👥 <b>Участники сходки:</b>\n"
]
for index, participant in enumerate(
    participants,
    start=1,
):
    username = participant.get(
        "username"
    )
    if username:
        name = f"@{html.quote(username)}"
    else:
        name = "Участник"
    lines.append(
        f"{index}. {name}"
    )
await callback.message.answer(
    "\n".join(lines)
)

============================================================

НЕПРЕДУСМОТРЕННЫЕ СООБЩЕНИЯ

============================================================

@router.message()
async def fallback(
message: Message,
) -> None:

await message.answer(
    "👇 Используй готовые кнопки меню.",
    reply_markup=main_menu(),
)
