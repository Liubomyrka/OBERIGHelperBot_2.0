# reminder_handler.py - модуль, який містить функції для нагадувань про події у календарі
from datetime import datetime, timedelta, time

import pytz
from telegram.ext import ContextTypes, JobQueue

from config import TIMEZONE
from database import get_value, set_value
from utils.calendar_utils import (
    get_today_events,
    get_calendar_events,
    get_upcoming_event_reminders,
)
from utils.logger import logger

# 🛡️ Ініціалізація глобальних змінних
berlin_tz = pytz.timezone(TIMEZONE)


def _format_event_line(event: dict) -> str:
    """Форматує подію у короткий рядок для повідомлень."""
    summary = event.get("summary", "Без назви")
    start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))

    if not start:
        return f"• {summary}"

    if "T" in start:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(berlin_tz)
        return f"• {summary} — {start_dt.strftime('%d-%m-%Y %H:%M')}"

    return f"• {summary} — {datetime.strptime(start, '%Y-%m-%d').strftime('%d-%m-%Y')}"


# 🛡️ Функція для отримання актуального часу
def get_current_time():
    """
    Отримує поточний час і час на годину вперед у часовому поясі Берліна.
    """
    now = datetime.now(berlin_tz)
    one_hour_later = now + timedelta(hours=1)
    return now, one_hour_later


# 🛡️ Функція для отримання списку активних чатів
def get_active_chats():
    """
    Отримує список усіх активних групових чатів із бази даних.
    """
    try:
        chat_list = get_value('group_chat_list') or ''
        if chat_list:
            return list(filter(None, chat_list.split(',')))
        logger.warning("⚠️ Список групових чатів для нагадувань порожній. Нагадування не буде надіслано.")
        return []
    except Exception as e:
        logger.error(f"❌ Помилка при отриманні списку активних чатів: {e}")
        return []


# 🛡️ Функція для отримання користувачів з увімкненими нагадуваннями
def get_users_with_enabled_reminders():
    user_list = (get_value('user_reminder_list') or '').split(',') if get_value('user_reminder_list') else []
    return [user_id for user_id in user_list if user_id and get_value(f'reminder_{user_id}') == 'on']


# 🔔 Увімкнення нагадувань
async def set_reminder(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    try:
        logger.info(f"🔄 Спроба увімкнення нагадувань для користувача {user_id}")

        set_value(f'reminder_{user_id}', 'on')

        current_list = set(filter(None, (get_value('user_reminder_list') or '').split(',')))
        current_list.add(user_id)
        set_value('user_reminder_list', ','.join(current_list))

        await update.effective_message.reply_text("🔔 Нагадування увімкнено.")
    except Exception as e:
        logger.error(f"❌ Помилка при увімкненні нагадувань для користувача {user_id}: {e}")
        await update.effective_message.reply_text("❌ Виникла помилка при увімкненні нагадувань.")


# 🔕 Вимкнення нагадувань
async def unset_reminder(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    try:
        logger.info(f"🔄 Спроба вимкнення нагадувань для користувача {user_id}")

        set_value(f'reminder_{user_id}', 'off')

        current_list = set(filter(None, (get_value('user_reminder_list') or '').split(',')))
        current_list.discard(user_id)
        set_value('user_reminder_list', ','.join(current_list))

        await update.effective_message.reply_text("🔕 Нагадування вимкнено.")
    except Exception as e:
        logger.error(f"❌ Помилка при вимкненні нагадувань для користувача {user_id}: {e}")
        await update.effective_message.reply_text("❌ Виникла помилка при вимкненні нагадувань.")


# 🕒 Функція для щоденних нагадувань
async def send_daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    """
    Надсилає щоденні нагадування один раз на день.
    """
    now = datetime.now(berlin_tz)
    current_date = now.date().isoformat()

    already_sent = get_value('daily_reminder_sent')
    if already_sent == current_date:
        logger.info("🔄 Щоденне нагадування вже було відправлено сьогодні.")
        return

    try:
        events = get_today_events()
        if not events:
            logger.info("⚠️ Подій на сьогодні немає.")
            set_value('daily_reminder_sent', current_date)
            return

        event_lines = "\n".join(_format_event_line(event) for event in events)
        text = f"🔔 Сьогоднішні події:\n{event_lines}"

        active_chats = get_active_chats()
        for chat_id in active_chats:
            await context.bot.send_message(chat_id=int(chat_id), text=text)

        set_value('daily_reminder_sent', current_date)
        logger.info(f"✅ Щоденні нагадування на {current_date} відправлено успішно.")

    except Exception as e:
        logger.error(f"❌ Помилка у функції send_daily_reminder: {e}")


# ⏰ Функція для нагадувань за годину до події
async def send_event_reminders(context: ContextTypes.DEFAULT_TYPE):
    now, _ = get_current_time()
    logger.info(f"⏰ Перевірка нагадувань за годину: {now}")

    try:
        events = get_calendar_events(max_results=20)
        upcoming = get_upcoming_event_reminders(events, reminder_minutes=60)
        if not upcoming:
            return

        sent_keys = set(filter(None, (get_value('hourly_reminder_sent') or '').split(',')))
        users = get_users_with_enabled_reminders()

        for event in upcoming:
            event_id = event.get('id', '')
            start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', ''))
            dedupe_key = f"{event_id}:{start}"
            if dedupe_key in sent_keys:
                continue

            message = f"⏰ Нагадування за 1 годину:\n{_format_event_line(event)}"
            for user_id in users:
                await context.bot.send_message(chat_id=int(user_id), text=message)

            sent_keys.add(dedupe_key)

        set_value('hourly_reminder_sent', ','.join(sent_keys))

    except Exception as e:
        logger.error(f"❌ Помилка у функції годинних нагадувань: {e}")


# 🛡️ Планування завдань
def schedule_event_reminders(job_queue: JobQueue):
    job_queue.run_daily(send_daily_reminder, time=time(hour=9, minute=0, tzinfo=berlin_tz))
    job_queue.run_repeating(send_event_reminders, interval=900, first=10)
    logger.info("✅ Планування завдань для нагадувань успішно налаштовано.")


__all__ = ["schedule_event_reminders", "set_reminder", "unset_reminder", "send_daily_reminder", "send_event_reminders"]
