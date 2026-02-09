# schedule_handler.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.calendar_utils import get_calendar_events
from datetime import datetime, timezone, timedelta
from utils.logger import logger
import pytz  # Для обробки часових поясів

# Словник для статусу нагадувань
user_reminders = {}
notified_events = set()


# 🛡️ Перевірка приватного чату
async def ensure_private_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, command: str) -> bool:
    """
    Перевіряє, чи команда виконується в особистому чаті.
    """
    if update.effective_chat.type != "private":
        try:
            logger.warning(f"⚠️ Команда /{command} виконується не в приватному чаті.")
            if update.effective_message:
                await update.effective_message.reply_text(
                f"❗ *Команда /{command} доступна лише в особистих повідомленнях.*\n"
                f"👉 [Перейдіть до приватного чату](https://t.me/OBERIGHelperBot).",
                parse_mode="Markdown",
                disable_web_page_preview=True
                )
        except Exception as e:
            logger.error(f"❌ Помилка у ensure_private_chat: {e}")
        return False
    return True


# 🛡️ Функція schedule_command
async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Відображає розклад подій з Google Calendar.
    """
    logger.info("🔄 Запит на виконання команди: /rozklad")
    if not await ensure_private_chat(update, context, "rozklad"):
        return

    try:
        events = get_calendar_events()
        if not events:
            await update.effective_message.reply_text("📅 Немає запланованих подій.")
            logger.info("⚠️ Події в Google Calendar відсутні.")
        else:
            response = "📅 **Розклад подій:**\n──────────────\n"
            buttons = []

            # Використовуємо часовий пояс Берліну
            berlin_tz = pytz.timezone('Europe/Berlin')

            emoji_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

            for index, event in enumerate(events[:10]):
                event_id = event.get("id", "")
                summary = event.get("summary", "Без назви")
                start = event["start"].get("dateTime", event["start"].get("date"))
                end = event["end"].get("dateTime", event["end"].get("date"))

                try:
                    if 'T' in start and 'T' in end:
                        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00')).astimezone(berlin_tz)
                        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00')).astimezone(berlin_tz)
                        start_date = start_dt.strftime('%d-%m-%Y')
                        start_time = start_dt.strftime('%H:%M')
                        end_time = end_dt.strftime('%H:%M')
                    else:
                        start_date = datetime.strptime(start, '%Y-%m-%d').strftime('%d-%m-%Y')
                        start_time = "Весь день"
                        end_time = ""

                    response += (
                        f"{emoji_numbers[index]} *{summary}*\n"
                        f"📅 {start_date} ⏰ {start_time} - {end_time}\n"
                        f"──────────────\n"
                    )
                    buttons.append([
                        InlineKeyboardButton(
                            text=f"ℹ️ {emoji_numbers[index]} {summary}",
                            callback_data=f"event_details_{event_id[:20]}"
                        )
                    ])
                except Exception as e:
                    logger.error(f"❌ Помилка при обробці події: {e}")

            await update.effective_message.reply_text(
                text=response,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            logger.info("✅ Команда /rozklad виконана успішно")
    except Exception as e:
        logger.error(f"❌ Помилка у команді /rozklad: {e}")
        if update.effective_message:
            await update.effective_message.reply_text("❌ Виникла помилка при отриманні подій.")


# 🛡️ Функція event_details_callback
async def event_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Показує деталі вибраної події.
    """
    logger.info("🔄 Запит на деталі події через callback")
    query = update.callback_query
    await query.answer()

    try:
        event_id = query.data.replace("event_details_", "")
        events = get_calendar_events()
        event = next((e for e in events if e.get("id", "").startswith(event_id)), None)

        if event:
            description = event.get("description", "Опис відсутній.")
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))

            berlin_tz = pytz.timezone('Europe/Berlin')

            if 'T' in start and 'T' in end:
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00')).astimezone(berlin_tz)
                end_dt = datetime.fromisoformat(end.replace('Z', '+00:00')).astimezone(berlin_tz)
                start_date = start_dt.strftime('%d-%m-%Y')
                start_time = start_dt.strftime('%H:%M')
                end_time = end_dt.strftime('%H:%M')
            else:
                start_date = datetime.strptime(start, '%Y-%m-%d').strftime('%d-%m-%Y')
                start_time = "Весь день"
                end_time = ""

            response = (
                f"📅 **Деталі події:**\n"
                f"📌 **Назва:** {event['summary']}\n"
                f"📅 **Дата:** {start_date}\n"
                f"⏰ **Час:** {start_time} - {end_time}\n"
                f"📝 **Опис:** {description}"
            )
            await query.message.reply_text(text=response, parse_mode="Markdown")
            logger.info("✅ Деталі події надіслано успішно")
        else:
            await query.message.reply_text("❌ Подію не знайдено.")
            logger.warning("❌ Подію не знайдено")
    except Exception as e:
        logger.error(f"❌ Помилка у callback: {e}")
        await query.message.reply_text(f"❌ Помилка: {e}")


# 🔔 Увімкнення нагадувань
async def set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_private_chat(update, context, "reminder_on"):
        return
    user_reminders[update.effective_chat.id] = True
    await update.effective_message.reply_text("🔔 Нагадування увімкнено.")


# 🔕 Вимкнення нагадувань
async def unset_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_private_chat(update, context, "reminder_off"):
        return
    user_reminders.pop(update.effective_chat.id, None)
    await update.effective_message.reply_text("🔕 Нагадування вимкнено.")
