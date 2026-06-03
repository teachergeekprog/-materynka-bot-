import os
import json
import logging
from datetime import datetime
from typing import Dict, List

import gspread
from google.oauth2.service_account import Credentials
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web
import asyncio

# ============ НАЛАШТУВАННЯ ============
SURVEY_BOT_TOKEN = os.getenv("SURVEY_BOT_TOKEN", "")
ALERT_BOT_TOKEN = os.getenv("ALERT_BOT_TOKEN", "")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "565328944"))
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
SHEET_NAME = "Ответы на форму (1)"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
PORT = int(os.getenv("PORT", 10000))
# ======================================

# Логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Підключаємось до Google Sheets
def get_google_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_json = os.getenv("GOOGLE_CREDENTIALS", "")
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

# Стани опитування
class Survey(StatesGroup):
    parent_name = State()
    phone = State()
    child_name = State()
    child_age = State()
    experience = State()
    direction = State()
    time = State()

# Варіанти для кнопок
AGE_OPTIONS = ["7", "8", "9", "10", "11", "12", "13", "14", "15"]

EXPERIENCE_OPTIONS = [
    "Ні, починаємо абсолютно з нуля",
    "Пробували Scratch / візуальне програмування",
    "Грає в Minecraft / Roblox, але код ще не писав(ла)",
    "Уже має базовий досвід (писав(ла) код, створював(ла) ігри)"
]

DIRECTION_OPTIONS = [
    "🤖 LEGO BOOST & Scratch (Робототехніка)",
    "⛏ Minecraft Education (Логіка та алгоритми)",
    "🎮 Roblox Studio (3D-моделювання та ігри на Lua)",
    "🐍 Python (Розробка ігор / Текстове програмування)"
]

TIME_OPTIONS = [
    "Ранкові години (Перша половина дня)",
    "Денний час (Після обіду)",
    "Вечірні години (Після 16:00 / 17:00)",
    "Зручно в будь-який час (Ми вільні)"
]

# Створюємо бота
bot = Bot(
    token=SURVEY_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher(storage=MemoryStorage())


# ========== КЛАВІАТУРИ ==========
def kb_single(options: List[str]) -> InlineKeyboardMarkup:
    """Клавіатура з одним вибором"""
    if len(options) <= 4:
        keyboard = [[InlineKeyboardButton(text=opt, callback_data=opt)] for opt in options]
    else:
        # По 3 кнопки в ряд (для віку)
        keyboard = []
        for i in range(0, len(options), 3):
            row = [InlineKeyboardButton(text=opt, callback_data=opt) for opt in options[i:i+3]]
            keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def kb_multi(options: List[str], selected: List[str]) -> InlineKeyboardMarkup:
    """Клавіатура з множинним вибором + кнопка Готово"""
    keyboard = []
    for opt in options:
        prefix = "✅ " if opt in selected else "⬜ "
        keyboard.append([InlineKeyboardButton(text=prefix + opt, callback_data=opt)])
    keyboard.append([InlineKeyboardButton(text="✅ Готово", callback_data="DONE_MULTI")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ========== /start ==========
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    
    await message.answer(
        "👋 *Вітаємо в ОЦ МАТЕРИНКА!* 💙\n\n"
        "Дякуємо за інтерес до наших IT-інтенсивів для дітей! 🚀\n\n"
        "Зараз я поставлю кілька питань, щоб підібрати найкращий курс для вашої дитини.\n\n"
        "⏱ Це займе 1-2 хвилини\n"
        "❌ Для скасування — /cancel"
    )
    
    await asyncio.sleep(1)
    
    await message.answer(
        "📋 *Питання 1 з 7*\n\n"
        "👨‍👩‍👧 *Блок 1/3: Знайомство*\n\n"
        "Введіть ваше *Ім'я та Прізвище* (одного з батьків):"
    )
    await state.set_state(Survey.parent_name)


# ========== /cancel ==========
@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Опитування скасовано.\n\nЩоб почати знову — введіть /start"
    )


# ========== 1. Ім'я батька ==========
@dp.message(Survey.parent_name)
async def get_parent_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Введіть коректне ім'я (мінімум 2 символи).")
        return
    
    await state.update_data(parent_name=name)
    
    await message.answer(
        "📋 *Питання 2 з 7*\n\n"
        "📱 Ваш *номер телефону* (Viber / Telegram):\n\n"
        "_Будь ласка, вкажіть актуальний номер, до якого прив'язаний месенджер для швидкого зв'язку._"
    )
    await state.set_state(Survey.phone)


# ========== 2. Телефон ==========
@dp.message(Survey.phone)
async def get_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    cleaned = ''.join(c for c in phone if c.isdigit() or c == '+')
    
    if len(cleaned) < 10:
        await message.answer(
            "⚠️ Введіть коректний номер телефону\n"
            "(наприклад: +380501234567)"
        )
        return
    
    await state.update_data(phone=phone)
    
    await message.answer(
        "📋 *Питання 3 з 7*\n\n"
        "👶 *Блок 2/3: Про дитину*\n\n"
        "Введіть *ім'я дитини*:"
    )
    await state.set_state(Survey.child_name)


# ========== 3. Ім'я дитини ==========
@dp.message(Survey.child_name)
async def get_child_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Введіть коректне ім'я (мінімум 2 символи).")
        return
    
    await state.update_data(child_name=name)
    
    await message.answer(
        "📋 *Питання 4 з 7*\n\n"
        "🎂 Скільки *років* дитині?",
        reply_markup=kb_single(AGE_OPTIONS)
    )
    await state.set_state(Survey.child_age)


# ========== 4. Вік дитини ==========
@dp.callback_query(Survey.child_age)
async def get_child_age(callback: CallbackQuery, state: FSMContext):
    age = callback.data
    if age not in AGE_OPTIONS:
        await callback.answer("⚠️ Оберіть варіант з кнопок!")
        return
    
    await state.update_data(child_age=age)
    await callback.answer()
    
    await callback.message.answer(
        "📋 *Питання 5 з 7*\n\n"
        "💻 Чи має дитина *досвід у програмуванні / IT*?",
        reply_markup=kb_single(EXPERIENCE_OPTIONS)
    )
    await state.set_state(Survey.experience)


# ========== 5. Досвід ==========
@dp.callback_query(Survey.experience)
async def get_experience(callback: CallbackQuery, state: FSMContext):
    exp = callback.data
    if exp not in EXPERIENCE_OPTIONS:
        await callback.answer("⚠️ Оберіть варіант з кнопок!")
        return
    
    await state.update_data(experience=exp, direction_selected=[])
    await callback.answer()
    
    await callback.message.answer(
        "📋 *Питання 6 з 7*\n\n"
        "🎯 *Блок 3/3: Курс та час*\n\n"
        "Який *напрямок інтенсивів* вас цікавить найбільше?\n\n"
        "_Можна обрати кілька варіантів — натискайте по черзі. Коли оберете все — натисніть «✅ Готово»._",
        reply_markup=kb_multi(DIRECTION_OPTIONS, [])
    )
    await state.set_state(Survey.direction)


# ========== 6. Напрямок (множинний вибір) ==========
@dp.callback_query(Survey.direction)
async def get_direction(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("direction_selected", [])
    choice = callback.data
    
    if choice == "DONE_MULTI":
        if not selected:
            await callback.answer("⚠️ Оберіть хоча б один варіант!", show_alert=True)
            return
        
        direction = ", ".join(selected)
        await state.update_data(direction=direction, time_selected=[])
        await callback.answer()
        
        await callback.message.answer(
            "📋 *Питання 7 з 7*\n\n"
            "🕐 *Зручний час для занять?*\n\n"
            "_Можна обрати кілька варіантів._",
            reply_markup=kb_multi(TIME_OPTIONS, [])
        )
        await state.set_state(Survey.time)
        return
    
    if choice not in DIRECTION_OPTIONS:
        await callback.answer()
        return
    
    if choice in selected:
        selected.remove(choice)
    else:
        selected.append(choice)
    
    await state.update_data(direction_selected=selected)
    await callback.answer()
    
    try:
        await callback.message.edit_reply_markup(
            reply_markup=kb_multi(DIRECTION_OPTIONS, selected)
        )
    except Exception as e:
        logger.warning(f"Edit failed: {e}")


# ========== 7. Час (множинний вибір) ==========
@dp.callback_query(Survey.time)
async def get_time(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("time_selected", [])
    choice = callback.data
    
    if choice == "DONE_MULTI":
        if not selected:
            await callback.answer("⚠️ Оберіть хоча б один варіант!", show_alert=True)
            return
        
        time = ", ".join(selected)
        await state.update_data(time=time)
        await callback.answer()
        
        # Завершуємо опитування
        all_data = await state.get_data()
        await finish_survey(callback.message, all_data)
        await state.clear()
        return
    
    if choice not in TIME_OPTIONS:
        await callback.answer()
        return
    
    if choice in selected:
        selected.remove(choice)
    else:
        selected.append(choice)
    
    await state.update_data(time_selected=selected)
    await callback.answer()
    
    try:
        await callback.message.edit_reply_markup(
            reply_markup=kb_multi(TIME_OPTIONS, selected)
        )
    except Exception as e:
        logger.warning(f"Edit failed: {e}")


# ========== ЗАВЕРШЕННЯ ==========
async def finish_survey(message: Message, data: Dict):
    # Зберігаємо в таблицю
    try:
        save_to_sheet(data)
    except Exception as e:
        logger.error(f"Помилка збереження в таблицю: {e}")
    
    # Дякуємо клієнту
    await message.answer(
        "✅ *Дякуємо за заявку!* 💙\n\n"
        "Ваша заявка успішно надіслана. Наш менеджер зв'яжеться з вами найближчим часом для уточнення деталей.\n\n"
        "До зустрічі на заняттях! 🚀\n\n"
        "_Щоб подати нову заявку — /start_"
    )
    
    # Сповіщаємо адміна
    try:
        await notify_admin(data)
    except Exception as e:
        logger.error(f"Помилка сповіщення адміна: {e}")


def save_to_sheet(data: Dict):
    """Запис заявки в Google Sheets"""
    sheet = get_google_sheet()
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    sheet.append_row([
        timestamp,
        data.get("parent_name", ""),
        data.get("phone", ""),
        data.get("child_name", ""),
        data.get("child_age", ""),
        data.get("experience", ""),
        data.get("direction", ""),
        data.get("time", "")
    ])
    logger.info(f"Заявка збережена: {data.get('parent_name')}")


async def notify_admin(data: Dict):
    """Сповіщення адміну через старий бот"""
    msg = (
        "🔔 *НОВА ЗАЯВКА* (Telegram-бот) 🤖\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"👨‍👩‍👧 *Батько/мати:* {data.get('parent_name', '')}\n"
        f"📱 *Телефон:* `{data.get('phone', '')}`\n\n"
        f"👶 *Дитина:* {data.get('child_name', '')}\n"
        f"🎂 *Вік:* {data.get('child_age', '')} років\n"
        f"💻 *Досвід:* {data.get('experience', '')}\n\n"
        f"🎯 *Напрямок:*\n{data.get('direction', '')}\n\n"
        f"🕐 *Зручний час:*\n{data.get('time', '')}"
    )
    
    alert_bot = Bot(
        token=ALERT_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    )
    try:
        await alert_bot.send_message(ADMIN_CHAT_ID, msg)
    finally:
        await alert_bot.session.close()


# ========== ЗАПУСК ЧЕРЕЗ WEBHOOK ==========
async def on_startup(app):
    await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}", drop_pending_updates=True)
    logger.info(f"✅ Webhook встановлено: {WEBHOOK_URL}{WEBHOOK_PATH}")


async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()


async def handle_webhook(request):
    update = await request.json()
    from aiogram.types import Update
    update_obj = Update(**update)
    await dp.feed_update(bot, update_obj)
    return web.Response(text="ok")


async def handle_health(request):
    return web.Response(text="Bot is alive!")


def main():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", handle_health)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
