import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, List

import gspread
from google.oauth2.service_account import Credentials
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup, Update
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


class Survey(StatesGroup):
    parent_name = State()
    phone = State()
    child_name = State()
    child_age = State()
    experience = State()
    direction = State()
    time = State()


# Варіанти з короткими ID для callback_data
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


bot = Bot(
    token=SURVEY_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher(storage=MemoryStorage())


def kb_age() -> InlineKeyboardMarkup:
    """Клавіатура для віку (короткі callback_data)"""
    keyboard = []
    for i in range(0, len(AGE_OPTIONS), 3):
        row = [
            InlineKeyboardButton(text=opt, callback_data=f"age_{opt}")
            for opt in AGE_OPTIONS[i:i+3]
        ]
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def kb_experience() -> InlineKeyboardMarkup:
    """Клавіатура для досвіду"""
    keyboard = [
        [InlineKeyboardButton(text=opt, callback_data=f"exp_{i}")]
        for i, opt in enumerate(EXPERIENCE_OPTIONS)
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def kb_direction(selected: List[int]) -> InlineKeyboardMarkup:
    """Клавіатура для напрямку (множинний вибір)"""
    keyboard = []
    for i, opt in enumerate(DIRECTION_OPTIONS):
        prefix = "✅ " if i in selected else "⬜ "
        keyboard.append([
            InlineKeyboardButton(text=prefix + opt, callback_data=f"dir_{i}")
        ])
    keyboard.append([
        InlineKeyboardButton(text="✅ Готово", callback_data="dir_done")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def kb_time(selected: List[int]) -> InlineKeyboardMarkup:
    """Клавіатура для часу (множинний вибір)"""
    keyboard = []
    for i, opt in enumerate(TIME_OPTIONS):
        prefix = "✅ " if i in selected else "⬜ "
        keyboard.append([
            InlineKeyboardButton(text=prefix + opt, callback_data=f"time_{i}")
        ])
    keyboard.append([
        InlineKeyboardButton(text="✅ Готово", callback_data="time_done")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def safe_answer(callback: CallbackQuery, text: str = None, alert: bool = False):
    try:
        if text:
            await callback.answer(text, show_alert=alert)
        else:
            await callback.answer()
    except Exception as e:
        logger.warning(f"Callback answer failed: {e}")


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
    await message.answer("❌ Опитування скасовано.\n\nЩоб почати знову — введіть /start")


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
        await message.answer("⚠️ Введіть коректний номер телефону\n(наприклад: +380501234567)")
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
        reply_markup=kb_age()
    )
    await state.set_state(Survey.child_age)


# ========== 4. Вік ==========
@dp.callback_query(Survey.child_age, F.data.startswith("age_"))
async def get_child_age(callback: CallbackQuery, state: FSMContext):
    age = callback.data.replace("age_", "")
    
    if age not in AGE_OPTIONS:
        await safe_answer(callback, "⚠️ Невідомий вік!")
        return
    
    await state.update_data(child_age=age)
    await safe_answer(callback)
    
    try:
        await callback.message.answer(
            "📋 *Питання 5 з 7*\n\n"
            "💻 Чи має дитина *досвід у програмуванні / IT*?",
            reply_markup=kb_experience()
        )
        await state.set_state(Survey.experience)
    except Exception as e:
        logger.error(f"Помилка переходу до питання 5: {e}")


# ========== 5. Досвід ==========
@dp.callback_query(Survey.experience, F.data.startswith("exp_"))
async def get_experience(callback: CallbackQuery, state: FSMContext):
    try:
        idx = int(callback.data.replace("exp_", ""))
        exp = EXPERIENCE_OPTIONS[idx]
    except (ValueError, IndexError):
        await safe_answer(callback, "⚠️ Невірна відповідь!")
        return
    
    await state.update_data(experience=exp, direction_selected=[])
    await safe_answer(callback)
    
    try:
        await callback.message.answer(
            "📋 *Питання 6 з 7*\n\n"
            "🎯 *Блок 3/3: Курс та час*\n\n"
            "Який *напрямок інтенсивів* вас цікавить найбільше?\n\n"
            "_Можна обрати кілька варіантів — натискайте по черзі. Коли оберете все — натисніть «✅ Готово»._",
            reply_markup=kb_direction([])
        )
        await state.set_state(Survey.direction)
    except Exception as e:
        logger.error(f"Помилка переходу до питання 6: {e}")


# ========== 6. Напрямок (множинний) ==========
@dp.callback_query(Survey.direction, F.data.startswith("dir_"))
async def get_direction(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("direction_selected", [])
    action = callback.data.replace("dir_", "")
    
    if action == "done":
        if not selected:
            await safe_answer(callback, "⚠️ Оберіть хоча б один варіант!", alert=True)
            return
        
        direction = ", ".join([DIRECTION_OPTIONS[i] for i in selected])
        await state.update_data(direction=direction, time_selected=[])
        await safe_answer(callback)
        
        try:
            await callback.message.answer(
                "📋 *Питання 7 з 7*\n\n"
                "🕐 *Зручний час для занять?*\n\n"
                "_Можна обрати кілька варіантів._",
                reply_markup=kb_time([])
            )
            await state.set_state(Survey.time)
        except Exception as e:
            logger.error(f"Помилка переходу до питання 7: {e}")
        return
    
    try:
        idx = int(action)
        if idx < 0 or idx >= len(DIRECTION_OPTIONS):
            await safe_answer(callback)
            return
    except ValueError:
        await safe_answer(callback)
        return
    
    if idx in selected:
        selected.remove(idx)
    else:
        selected.append(idx)
    
    await state.update_data(direction_selected=selected)
    await safe_answer(callback)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=kb_direction(selected))
    except Exception as e:
        logger.warning(f"Edit direction failed: {e}")


# ========== 7. Час (множинний) ==========
@dp.callback_query(Survey.time, F.data.startswith("time_"))
async def get_time(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("time_selected", [])
    action = callback.data.replace("time_", "")
    
    if action == "done":
        if not selected:
            await safe_answer(callback, "⚠️ Оберіть хоча б один варіант!", alert=True)
            return
        
        time = ", ".join([TIME_OPTIONS[i] for i in selected])
        await state.update_data(time=time)
        await safe_answer(callback)
        
        all_data = await state.get_data()
        await finish_survey(callback.message, all_data)
        await state.clear()
        return
    
    try:
        idx = int(action)
        if idx < 0 or idx >= len(TIME_OPTIONS):
            await safe_answer(callback)
            return
    except ValueError:
        await safe_answer(callback)
        return
    
    if idx in selected:
        selected.remove(idx)
    else:
        selected.append(idx)
    
    await state.update_data(time_selected=selected)
    await safe_answer(callback)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=kb_time(selected))
    except Exception as e:
        logger.warning(f"Edit time failed: {e}")


# ========== ЗАВЕРШЕННЯ ==========
async def finish_survey(message: Message, data: Dict):
    try:
        save_to_sheet(data)
    except Exception as e:
        logger.error(f"Помилка збереження в таблицю: {e}")
    
    try:
        await message.answer(
            "✅ *Дякуємо за заявку!* 💙\n\n"
            "Ваша заявка успішно надіслана. Наш менеджер зв'яжеться з вами найближчим часом для уточнення деталей.\n\n"
            "До зустрічі на заняттях! 🚀\n\n"
            "_Щоб подати нову заявку — /start_"
        )
    except Exception as e:
        logger.error(f"Помилка фінального повідомлення: {e}")
    
    try:
        await notify_admin(data)
    except Exception as e:
        logger.error(f"Помилка сповіщення адміна: {e}")


def save_to_sheet(data: Dict):
    sheet = get_google_sheet()
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    row_data = [
        timestamp,
        data.get("parent_name", ""),
        data.get("phone", ""),
        data.get("child_name", ""),
        data.get("child_age", ""),
        data.get("experience", ""),
        data.get("direction", ""),
        data.get("time", "")
    ]
    
    # Знаходимо реальний останній рядок з даними
    all_values = sheet.get_all_values()
    next_row = len(all_values) + 1
    
    # Вставляємо дані саме там
    sheet.insert_row(row_data, next_row, value_input_option="USER_ENTERED")
    
    logger.info(f"Заявка збережена в рядок {next_row}: {data.get('parent_name')}")


async def notify_admin(data: Dict):
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


async def on_startup(app):
    await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}", drop_pending_updates=True)
    logger.info(f"✅ Webhook встановлено: {WEBHOOK_URL}{WEBHOOK_PATH}")


async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()


async def handle_webhook(request):
    try:
        update_data = await request.json()
        update_obj = Update(**update_data)
        await dp.feed_update(bot, update_obj)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
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
