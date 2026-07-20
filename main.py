"""
Beauty Bot — Telegram-бот для записи клиентов (бьюти-мастера)
aiogram 3, SQLite

Запуск: python main.py
"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from config import BOT_TOKEN
from db import init_db, register_master, update_master, get_master, get_services
from db import add_service, update_service, delete_service, get_appointments
from db import get_today_appointments, get_upcoming_appointments
from db import book_appointment
from db import check_subscription, get_subscription, activate_subscription

PRICES = {
    "1_month": 300,    # 300 Stars ≈ 500₽
    "3_months": 750,   # 750 Stars ≈ 1250₽ (скидка ~17%)
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==================== FSM States ====================

class Register(StatesGroup):
    name = State()
    phone = State()

class AddService(StatesGroup):
    name = State()
    price = State()
    duration = State()

class EditProfile(StatesGroup):
    name = State()
    phone = State()
    service = State()
    date = State()
    time = State()
    client_name = State()
    phone = State()

# ==================== Keyboards ====================

def master_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Сегодня"), KeyboardButton(text="📋 Записи")],
            [KeyboardButton(text="🛠 Услуги"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="💳 Подписка")],
            [KeyboardButton(text="🔗 Моя ссылка")],
        ],
        resize_keyboard=True
    )

def client_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✍️ Записаться")]],
        resize_keyboard=True
    )

# ==================== Start ====================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    args = message.text.split()
    master_id = None
    if len(args) > 1:
        try:
            master_id = int(args[1])
        except ValueError:
            pass

    user_id = message.from_user.id
    master = get_master(user_id)

    if master:
        await message.answer(
            f"👋 С возвращением, {master['name']}!",
            reply_markup=master_menu()
        )
    elif master_id:
        # Клиент пришёл по ссылке мастера
        target_master = get_master(master_id)
        if target_master:
            await message.answer(
                f"✍️ **Запись к {target_master['name']}**\n\n"
                f"Выбери услугу и удобное время.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✍️ Выбрать услугу", callback_data=f"book_{master_id}")],
                ])
            )
        else:
            await message.answer("Мастер с таким ID не найден.")
    else:
        await message.answer(
            "👋 Привет!\n\n"
            "🧑‍💼 **Я мастер** — хочу принимать записи\n"
            "👤 **Я клиент** — ссылка от мастера уже есть",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🧑‍💼 Я мастер", callback_data="role_master")],
            ])
        )

# ==================== Master Registration ====================

@dp.callback_query(F.data == "role_master")
async def role_master(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("Давай познакомимся!\n\nКак тебя зовут?")
    await state.set_state(Register.name)

@dp.message(Register.name)
async def register_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Отлично! Укажи **номер телефона** для связи с клиентами:")
    await state.set_state(Register.phone)

@dp.message(Register.phone)
async def register_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    phone = message.text
    register_master(message.from_user.id, data["name"], phone)

    # 7 дней бесплатного доступа
    master = get_master(message.from_user.id)
    activate_subscription(master["id"], 7)

    await state.clear()
    await message.answer(
        f"✅ **Регистрация завершена!**\n\n"
        f"Имя: {data['name']}\n"
        f"Телефон: {phone}\n\n"
        f"🎁 **7 дней бесплатного доступа!**\n"
        f"Потом подписка — 500₽/мес\n\n"
        f"➡ Добавь услуги через «🛠 Услуги»\n"
        f"➡ Нажми «🔗 Моя ссылка» — кинь её клиентам",
        reply_markup=master_menu()
    )

# ==================== Master Panel ====================

@dp.message(F.text == "🔗 Моя ссылка")
async def my_link(message: types.Message, state: FSMContext):
    await state.clear()
    master = get_master(message.from_user.id)
    if not master:
        await message.answer("Сначала зарегистрируйся: /start")
        return

    link = f"https://t.me/{(await bot.me()).username}?start={message.from_user.id}"
    await message.answer(
        "🔗 **Твоя ссылка для клиентов:**\n\n"
        f"`{link}`\n\n"
        "Клиент нажимает → открывает бота → сразу выбирает услугу и записывается.",
        reply_markup=master_menu()
    )

@dp.message(F.text == "📋 Записи")
async def show_appointments(message: types.Message, state: FSMContext):
    await state.clear()
    master = get_master(message.from_user.id)
    if not master:
        await message.answer("Сначала зарегистрируйся: /start")
        return

    upcoming = get_upcoming_appointments(master["id"])
    if not upcoming:
        await message.answer("📋 Нет предстоящих записей.", reply_markup=master_menu())
        return

    text = "📋 **Предстоящие записи:**\n\n"
    for a in upcoming[:10]:
        text += (
            f"📅 {a['date']} в {a['time']}\n"
            f"👤 {a['client_name']} {a['client_phone'] or ''}\n"
            f"💅 {a.get('service_name', '—')} — {a.get('price', '—')}₽\n"
            f"{'✅ Подтверждено' if a['confirmed'] else '⏳ Ожидает подтверждения'}\n\n"
        )

    await message.answer(text, reply_markup=master_menu())

@dp.message(F.text == "📅 Сегодня")
async def show_today(message: types.Message, state: FSMContext):
    await state.clear()
    master = get_master(message.from_user.id)
    if not master:
        await message.answer("Сначала зарегистрируйся: /start")
        return

    today_records = get_today_appointments(master["id"])
    today_str = date.today().strftime('%d.%m.%Y')
    if not today_records:
        await message.answer(f"📅 **{today_str}** — записей нет.", reply_markup=master_menu())
        return

    total = sum(a.get("price", 0) or 0 for a in today_records)
    text = f"📅 **{today_str}:**\n\n"
    for a in today_records:
        text += (
            f"⏰ {a['time']} — {a['client_name']}\n"
            f"💅 {a.get('service_name', '—')} — {a.get('price', '—')}₽\n"
            f"{'✅' if a['confirmed'] else '⏳'}\n\n"
        )
    text += f"💰 **Итого: {total}₽**"

    await message.answer(text, reply_markup=master_menu())

@dp.message(F.text == "🛠 Услуги")
async def show_services(message: types.Message, state: FSMContext):
    await state.clear()
    master = get_master(message.from_user.id)
    if not master:
        await message.answer("Сначала зарегистрируйся: /start")
        return

    services = get_services(master["id"])
    text = "🛠 **Твои услуги:**\n\n"

    kb_buttons = []
    if services:
        for s in services:
            text += f"• {s['name']} — {s['price']}₽ ({s['duration_min']} мин)\n"
            kb_buttons.append([
                InlineKeyboardButton(text=f"✏️ {s['name']}", callback_data=f"edit_svc_{s['id']}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_svc_{s['id']}"),
            ])
    else:
        text += "Пока ничего не добавлено.\n"

    kb_buttons.append([InlineKeyboardButton(text="➕ Добавить услугу", callback_data="add_service")])

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    )

# --------------- Добавление / Редактирование / Удаление услуг ---------------

@dp.callback_query(F.data == "add_service")
async def add_service_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AddService.name)
    await callback.message.edit_text(
        "Введи **название услуги** (например: «Маникюр комбинированный»):\n\n"
        "Или нажми «❌ Отмена»",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add")],
        ])
    )

@dp.callback_query(F.data == "cancel_add")
async def cancel_add_flow(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Добавление отменено ✖️")
    await state.clear()
    await callback.message.edit_text("❌ **Добавление услуги отменено.**")
    await callback.message.answer("Твои услуги:", reply_markup=master_menu())

@dp.callback_query(F.data.startswith("edit_svc_"))
async def edit_service_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    service_id = int(callback.data.split("_")[2])
    await state.update_data(edit_service_id=service_id)
    await state.set_state(AddService.name)
    await callback.message.edit_text(
        "✏️ Введи **новое название** услуги:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit")],
        ])
    )

@dp.callback_query(F.data == "cancel_edit")
async def cancel_edit_flow(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Редактирование отменено ✖️")
    await state.clear()
    await callback.message.edit_text("❌ **Редактирование отменено.**")
    await callback.message.answer("Твои услуги:", reply_markup=master_menu())

@dp.callback_query(F.data.startswith("del_svc_"))
async def delete_service_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    service_id = int(callback.data.split("_")[2])
    master = get_master(callback.from_user.id)
    if not master:
        return

    services = get_services(master["id"])
    svc_name = next((s["name"] for s in services if s["id"] == service_id), "неизвестно")

    delete_service(service_id)
    await state.clear()
    await callback.message.edit_text(f"🗑 Услуга «{svc_name}» удалена.")

    remaining = get_services(master["id"])
    text = "🛠 **Твои услуги:**\n\n"
    kb = []
    if remaining:
        for s in remaining:
            text += f"• {s['name']} — {s['price']}₽ ({s['duration_min']} мин)\n"
    else:
        text += "Пока ничего не добавлено.\n"
    kb.append([InlineKeyboardButton(text="➕ Добавить услугу", callback_data="add_service")])
    await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.message.answer("Меню:", reply_markup=master_menu())

# Единый FSM-обработчик для всех шагов (добавление + редактирование)
@dp.message(AddService.name)
async def on_service_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(service_name=message.text)
    await state.set_state(AddService.price)
    mode = "edit" if "edit_service_id" in data else "add"
    cancel = "cancel_edit" if mode == "edit" else "cancel_add"
    prefix = "✏️ Введи **новую** " if mode == "edit" else "Введи "
    await message.answer(
        f"{prefix}цену** в рублях (только цифры):\n\n"
        "Или нажми «❌ Отмена»",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=cancel)],
        ])
    )

@dp.message(AddService.price)
async def on_service_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введи число, например: 1500")
        return
    data = await state.get_data()
    await state.update_data(price=int(message.text))
    await state.set_state(AddService.duration)
    mode = "edit" if "edit_service_id" in data else "add"
    cancel = "cancel_edit" if mode == "edit" else "cancel_add"
    prefix = "✏️ Введи **новую** " if mode == "edit" else ""
    await message.answer(
        f"{prefix}длительность** в минутах (например: 60):\n\n"
        "Или нажми «❌ Отмена»",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=cancel)],
        ])
    )

@dp.message(AddService.duration)
async def on_service_duration(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введи число, например: 60")
        return
    data = await state.get_data()
    master = get_master(message.from_user.id)
    if not master:
        await message.answer("Ошибка. Попробуй /start")
        await state.clear()
        return

    duration = int(message.text)

    if "edit_service_id" in data:
        update_service(data["edit_service_id"], data["service_name"], data["price"], duration)
        await state.clear()
        await message.answer(
            f"✅ Услуга «{data['service_name']}» обновлена!",
            reply_markup=master_menu()
        )
    else:
        add_service(master["id"], data["service_name"], data["price"], duration)
        await state.clear()
        await message.answer(
            f"✅ Услуга «{data['service_name']}» — {data['price']}₽ добавлена!",
            reply_markup=master_menu()
        )

@dp.message(F.text == "👤 Профиль")
async def show_profile(message: types.Message, state: FSMContext):
    await state.clear()
    master = get_master(message.from_user.id)
    if not master:
        await message.answer("Сначала зарегистрируйся: /start")
        return
    services = get_services(master["id"])
    appointments = get_appointments(master["id"])
    total_earned = sum(a.get("price", 0) or 0 for a in appointments if a["confirmed"])

    text = (
        f"👤 **Твой профиль:**\n\n"
        f"Имя: {master['name']}\n"
        f"Телефон: {master['phone']}\n"
        f"Услуг: {len(services)}\n"
        f"Всего записей: {len(appointments)}\n"
        f"💰 Заработано: {total_earned}₽\n"
    )
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Редактировать профиль", callback_data="edit_profile")],
        ])
    )
    await message.answer("Меню:", reply_markup=master_menu())

# --------------- Редактирование профиля ---------------

@dp.callback_query(F.data == "edit_profile")
async def edit_profile_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    master = get_master(callback.from_user.id)
    if not master:
        return
    await state.set_state(EditProfile.name)
    await callback.message.edit_text(
        f"✏️ Текущее имя: **{master['name']}**\n\n"
        "Введи **новое имя** (или отправь «пропустить»):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit_profile")],
        ])
    )

@dp.callback_query(F.data == "cancel_edit_profile")
async def cancel_edit_profile(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Редактирование отменено ✖️")
    await state.clear()
    await callback.message.edit_text("❌ **Редактирование отменено.**")
    await callback.message.answer("Меню:", reply_markup=master_menu())

@dp.message(EditProfile.name)
async def edit_profile_name(message: types.Message, state: FSMContext):
    name = message.text if message.text.lower() != "пропустить" else None
    await state.update_data(new_name=name)
    await state.set_state(EditProfile.phone)
    master = get_master(message.from_user.id)
    await message.answer(
        f"✏️ Текущий телефон: **{master['phone']}**\n\n"
        "Введи **новый номер телефона** (или отправь «пропустить»):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit_profile")],
        ])
    )

@dp.message(EditProfile.phone)
async def edit_profile_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    master = get_master(message.from_user.id)
    if not master:
        await message.answer("Ошибка. Попробуй /start")
        await state.clear()
        return

    new_name = data.get("new_name") or master["name"]
    new_phone = message.text if message.text.lower() != "пропустить" else master["phone"]

    update_master(message.from_user.id, new_name, new_phone)
    await state.clear()

    await message.answer(
        f"✅ **Профиль обновлён!**\n\n"
        f"Имя: {new_name}\n"
        f"Телефон: {new_phone}",
        reply_markup=master_menu()
    )

@dp.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message, state: FSMContext):
    await state.clear()
    master = get_master(message.from_user.id)
    if not master:
        await message.answer("Сначала зарегистрируйся: /start")
        return

    appointments = get_appointments(master["id"])
    total_earned = sum(a.get("price", 0) or 0 for a in appointments if a["confirmed"])

    text = (
        f"📊 **Статистика:**\n\n"
        f"📅 Всего записей: {len(appointments)}\n"
        f"✅ Подтверждено: {sum(1 for a in appointments if a['confirmed'])}"
        f"\n💰 Заработано: {total_earned}₽\n"
    )
    await message.answer(text, reply_markup=master_menu())

@dp.message(F.text == "💳 Подписка")
async def show_subscription(message: types.Message):
    master = get_master(message.from_user.id)
    if not master:
        await message.answer("Сначала зарегистрируйся: /start")
        return

    sub = get_subscription(master["id"])
    is_active = check_subscription(master["id"])

    if is_active:
        expires = datetime.fromisoformat(sub["expires_at"])
        days_left = (expires - datetime.now()).days + 1
        text = (
            "💳 **Твоя подписка активна** ✅\n\n"
            f"📅 Дней осталось: **{days_left}**\n"
            f"Действует до: {expires.strftime('%d.%m.%Y')}\n\n"
            "Продлить или сменить тариф можно ниже:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📆 +1 месяц — 300 ⭐", callback_data="pay_1_month"),
             InlineKeyboardButton(text="📆 +3 месяца — 750 ⭐", callback_data="pay_3_months")],
        ])
    else:
        text = (
            "💳 **Подписка**\n\n"
            "Без подписки бот работает в ознакомительном режиме.\n"
            "Для полноценного использования оформи подписку:\n\n"
            "📆 **1 месяц** — 300 ⭐ (≈500₽)\n"
            "📆 **3 месяца** — 750 ⭐ (≈1250₽, скидка 17%)\n\n"
            "⭐ Купить Stars: @PremiumBot → «Купить звёзды»"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📆 1 месяц — 300 ⭐", callback_data="pay_1_month"),
             InlineKeyboardButton(text="📆 3 месяца — 750 ⭐", callback_data="pay_3_months")],
        ])

    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("pay_"))
async def process_pay(callback: types.CallbackQuery):
    await callback.answer()
    plan = callback.data.replace("pay_", "")

    prices_map = {
        "1_month": (300, "1 месяц", 30),
        "3_months": (750, "3 месяца", 90),
    }

    if plan not in prices_map:
        return

    stars, label, days = prices_map[plan]

    await callback.message.answer(
        f"💳 Оплата: **{label}** — {stars} ⭐\n\n"
        "Нажми кнопку ниже для оплаты через Telegram Stars."
    )

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"Подписка {label}",
        description=f"Доступ ко всем функциям бота на {label}",
        payload=f"sub_{plan}_{callback.from_user.id}",
        currency="XTR",
        prices=[types.LabeledPrice(label=label, amount=stars)],
    )

# ==================== Payment Handlers ====================

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_q: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    payload = message.successful_payment.invoice_payload
    parts = payload.split("_")
    plan = parts[1]
    user_id = int(parts[2])

    days_map = {"month": 30, "months": 90}
    days = days_map.get(plan, 30)

    master = get_master(user_id)
    if master:
        activate_subscription(master["id"], days)
        star_count = message.successful_payment.total_amount
        await message.answer(
            f"✅ **Оплата прошла успешно!**\n\n"
            f"Спасибо за покупку! Подписка активирована.\n"
            f"⭐ Списано: {star_count} Stars\n\n"
            "Все функции бота теперь доступны.",
            reply_markup=master_menu()
        )

@dp.callback_query(F.data.startswith("book_"))
async def booking_service_select(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    master_id = int(callback.data.split("_")[1])
    master = get_master(master_id)
    if not master:
        await callback.message.edit_text("Мастер не найден.")
        return

    services = get_services(master["id"])
    if not services:
        await callback.message.edit_text("У мастера пока нет услуг.")
        return

    await state.update_data(master_id=master["id"])
    await state.set_state(Booking.service)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{s['name']} — {s['price']}₽", callback_data=f"svc_{s['id']}")]
        for s in services
    ])
    await callback.message.edit_text(
        f"✍️ **Запись к {master['name']}**\n\nВыбери услугу:",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("svc_"), Booking.service)
async def booking_choose_service(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    service_id = int(callback.data.split("_")[1])
    await state.update_data(service_id=service_id)
    await state.set_state(Booking.date)
    await callback.message.edit_text(
        "📅 Введи **дату** в формате ДД.ММ.ГГГГ\n"
        "Например: `20.07.2026`"
    )

@dp.message(Booking.date)
async def booking_enter_date(message: types.Message, state: FSMContext):
    try:
        datetime.strptime(message.text, "%d.%m.%Y")
    except ValueError:
        await message.answer("❌ Неверный формат. Введи как ДД.ММ.ГГГГ, например `20.07.2026`")
        return

    await state.update_data(booking_date=message.text)
    await state.set_state(Booking.time)
    await message.answer(
        "⏰ Введи **время** в формате ЧЧ:ММ\n"
        "Например: `14:30`"
    )

@dp.message(Booking.time)
async def booking_enter_time(message: types.Message, state: FSMContext):
    if ":" not in message.text or len(message.text) < 4:
        await message.answer("❌ Неверный формат. Введи как ЧЧ:ММ, например `14:30`")
        return

    await state.update_data(booking_time=message.text)
    await state.set_state(Booking.client_name)
    await message.answer("👤 Как к тебе обращаться? (Введи **имя**):")

@dp.message(Booking.client_name)
async def booking_enter_name(message: types.Message, state: FSMContext):
    await state.update_data(client_name=message.text)
    await state.set_state(Booking.phone)
    await message.answer("📱 Введи **номер телефона** для связи (или отправь «нет»):")

@dp.message(Booking.phone)
async def booking_enter_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    phone = message.text if message.text.lower() != "нет" else ""

    book_appointment(
        master_id=data["master_id"],
        client_name=data["client_name"],
        client_phone=phone,
        service_id=data["service_id"],
        date=data["booking_date"],
        time_slot=data["booking_time"],
    )

    await state.clear()

    await message.answer(
        "✅ **Ты записан(а)!** 🎉\n\n"
        f"📅 {data['booking_date']} в {data['booking_time']}\n\n"
        "Мастер получит уведомление. Приятного визита! 💅",
        reply_markup=client_menu()
    )

# ==================== Fallback ====================

@dp.message()
async def fallback(message: types.Message):
    master = get_master(message.from_user.id)
    await message.answer(
        "Используй кнопки меню или напиши /start",
        reply_markup=master_menu() if master else client_menu()
    )

# ==================== Main ====================

async def main():
    init_db()
    me = await bot.me()
    print(f"🤖 Beauty Bot запущен!")
    print(f"📱 @{me.username}")
    print(f"🔗 Ссылка для мастеров: https://t.me/{me.username}?start=")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
