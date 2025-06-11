from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime
import hashlib
import json
from utils.calendar_utils import (
    get_calendar_events,
    get_today_events,
    get_event_details,
)
from utils.logger import logger
from database import (
    get_value,
    set_value,
)

# Глобальний словник для кешування ID подій
_event_id_cache = {}


def _generate_short_id(event_id: str) -> str:
    """Генерує короткий ID для події"""
    hash_object = hashlib.md5(event_id.encode())
    return hash_object.hexdigest()[:8]  # Використовуємо перші 8 символів MD5 хешу


def _cache_event_id(short_id: str, full_id: str):
    """Кешує повний ID події"""
    _event_id_cache[short_id] = full_id


def _get_cached_event_id(short_id: str) -> str:
    """Отримує повний ID події з кешу"""
    return _event_id_cache.get(short_id)


# 🛡️ Перевірка приватного чату
async def ensure_private_chat(
    update: Update, context: ContextTypes.DEFAULT_TYPE, command: str
) -> bool:
    """
    Перевіряє, чи команда виконується в особистому чаті.
    """
    if update.effective_chat.type != "private":
        try:
            logger.warning(f"⚠️ Команда /{command} виконується не в приватному чаті.")
            await update.message.reply_text(
                f"❗ Команда /{command} доступна лише в особистих повідомленнях.\n"
                f"👉 Перейдіть до приватного чату: https://t.me/OBERIGHelperBot",
                parse_mode=None,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.error(f"❌ Помилка у ensure_private_chat: {e}")
        return False
    return True


# 🛡️ Функція schedule_command
async def schedule_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, today_only: bool = False
):
    """
    Відображає розклад подій.

    :param today_only: якщо True, показує тільки події на сьогодні
    """
    logger.info("🔄 Запит на виконання команди: /rozklad")

    try:
        # Перевіряємо тип чату
        if update.effective_chat.type != "private":
            # В груповому чаті команда недоступна
            return

        # Отримуємо події (змінено max_results на 5 для повного розкладу)
        events = (
            get_today_events() if today_only else get_calendar_events(max_results=5)
        )

        if not events:
            await update.message.reply_text(
                "📅 На даний момент немає запланованих подій.",
                parse_mode=None,
                disable_web_page_preview=True,
            )
            return

        # Очищуємо кеш ID подій перед новим відображенням
        _event_id_cache.clear()

        # Словник для мапінгу чисел на емоджі (змінено до 5 подій)
        number_emojis = {1: "①", 2: "②", 3: "③", 4: "④", 5: "⑤"}

        # Формуємо та надсилаємо кожну подію з кнопкою окремо
        for event_number, event in enumerate(events, 1):
            try:
                # Отримуємо базову інформацію про подію
                summary = event.get("summary", "Без назви")
                start = event["start"].get("dateTime", event["start"].get("date"))

                # Форматуємо дату та час для компактного виведення
                if "T" in start:  # Якщо є час
                    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    end = event["end"].get("dateTime", event["start"].get("date"))
                    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                    time_str = f"⏰ {start_dt.strftime('%H:%M')} – {end_dt.strftime('%H:%M')}"  # Залишаємо '–'
                    date_str = f"📅 {start_dt.strftime('%d-%m-%Y')}"
                else:  # Якщо тільки дата
                    start_dt = datetime.strptime(start, "%Y-%m-%d")
                    date_str = f"📅 {start_dt.strftime('%d-%m-%Y')}"
                    time_str = "📍 (повноденна подія)"

                # Формуємо рядок події
                event_line = f"{number_emojis[event_number]} 🎯 {summary}\n{date_str}"
                if time_str.startswith("⏰"):
                    event_line += f"\n{time_str}"
                else:
                    event_line += f"\n{time_str}"

                # Створюємо інлайн-клавіатуру для цієї події
                short_id = _generate_short_id(event["id"])
                _cache_event_id(short_id, event["id"])
                keyboard = [
                    [
                        InlineKeyboardButton(
                            f"{number_emojis[event_number]} Деталі",
                            callback_data=f"event_{short_id}",
                        )
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                # Надсилаємо кожну подію з її кнопкою як окреме повідомлення
                await update.message.reply_text(
                    event_line,
                    parse_mode=None,  # Залишаємо без форматування
                    disable_web_page_preview=True,
                    reply_markup=reply_markup,
                )

            except Exception as e:
                logger.error(f"❌ Помилка при форматуванні події: {e}")
                continue

        # Додаємо інформацію про нагадування в кінці як окреме повідомлення
        reminder_message = (
            "\nЩоб дізнатись деталі подій — натисніть на кнопку «Деталі» під кожною подією\n\n"
            "🔔 Нагадування:\n"
        )
        logger.info("✅ Команда /rozklad виконана успішно")

    except Exception as e:
        logger.error(f"❌ Помилка при виконанні команди /rozklad: {e}")
        await update.message.reply_text(
            "❌ Виникла помилка при отриманні розкладу. Спробуйте пізніше.",
            parse_mode=None,
            disable_web_page_preview=True,
        )


# 🛡️ Функція event_details_callback
async def event_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Показує деталі вибраної події.
    """
    logger.info("🔄 Запит на деталі події через callback")
    query = update.callback_query
    await query.answer()

    try:
        # Отримуємо ID події з callback_data
        if not query.data.startswith("event_"):
            return

        short_id = query.data[6:]  # Отримуємо короткий ID події
        full_event_id = _get_cached_event_id(short_id)

        if not full_event_id:
            await query.message.edit_text(
                "❌ Інформація про подію застаріла. Будь ласка, оновіть розклад.",
                parse_mode=None,
            )
            return

        # Отримуємо деталі події
        event_details = get_event_details(full_event_id)
        if event_details:
            # Отримуємо інформацію про подію
            summary = (
                event_details["summary"] if event_details["summary"] else "Без назви"
            )
            description = (
                event_details["description"]
                if event_details["description"]
                else "Опис відсутній"
            )
            location = (
                event_details["location"]
                if event_details["location"]
                else "Місце не вказано"
            )
            time_str = (
                event_details["time"] if event_details["time"] else "Час не вказано"
            )

            # Формуємо повідомлення з деталями події у форматі, який ви вказали
            message = (
                "📌 Деталі події\n\n"
                f"📝 Назва: {summary}\n"
                f"📅 Дата: {time_str.split(' - ')[0] if ' - ' in time_str else 'Дата не вказано'}\n"
                f"⏰ Час: {time_str if ' - ' in time_str else 'Час не вказано'}\n"
                f"📍 Місце: {location}\n\n"
                f"📋 Опис:\n{description}"
            )

            await query.message.edit_text(
                message, parse_mode=None  # Залишаємо без форматування
            )
            logger.info("✅ Деталі події успішно відображено")
        else:
            await query.message.edit_text(
                "❌ Подію не знайдено або вона була видалена.", parse_mode=None
            )
            logger.warning("⚠️ Подію не знайдено при спробі показати деталі")

    except Exception as e:
        logger.error(f"❌ Помилка при відображенні деталей події: {e}")
        await query.message.edit_text(
            "❌ Виникла помилка при отриманні деталей події.", parse_mode=None
        )


