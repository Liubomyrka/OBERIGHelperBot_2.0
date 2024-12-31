# reminder_handler.py

from telegram.ext import JobQueue, ContextTypes
from utils.calendar_utils import get_calendar_events
from utils.logger import logger
from config import REMINDER_CHAT_ID
from datetime import datetime, timedelta, timezone, time
from database import set_value, get_value, delete_value

# 🛡️ Ініціалізація глобальних змінних зі збереженими значеннями
daily_reminder_sent = get_value('daily_reminder_sent') == str(datetime.now(timezone.utc).date())
hourly_reminder_sent = set(get_value('hourly_reminder_sent').split(',')) if get_value('hourly_reminder_sent') else set()

# Словник для збереження нагадувань користувачів
user_reminders = {}


# 🕒 Функція для щоденних нагадувань у груповий чат
async def send_daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    global daily_reminder_sent
    now = datetime.now(timezone.utc).date()

    if daily_reminder_sent:
        logger.info("🔔 Щоденне нагадування вже було відправлено сьогодні.")
        return

    try:
        events = get_calendar_events()
        today_events = [
            event for event in events
            if event["start"].get("dateTime", event["start"].get("date")).startswith(str(now))
        ]

        if not today_events:
            logger.info("📅 Сьогодні немає запланованих подій.")
            return

        message = "🔔 *Нагадування про події на сьогодні:*\n\n"
        for event in today_events:
            summary = event.get("summary", "Без назви")
            start = event["start"].get("dateTime", event["start"].get("date"))

            if 'T' in start:
                event_time = datetime.fromisoformat(start.replace('Z', '+00:00')).astimezone(timezone.utc)
                time_str = event_time.strftime('%H:%M')
            else:
                time_str = "Весь день"

            message += f"📌 *{summary}* о {time_str}\n"

        await context.bot.send_message(chat_id=REMINDER_CHAT_ID, text=message, parse_mode="Markdown")
        logger.info("✅ Щоденне нагадування надіслано успішно.")
        set_value('daily_reminder_sent', str(now))
        daily_reminder_sent = True

    except Exception as e:
        logger.error(f"❌ Помилка під час надсилання щоденного нагадування: {e}")


# ⏰ Функція для годинних нагадувань в особисті чати
async def send_event_reminders(context: ContextTypes.DEFAULT_TYPE):
    global hourly_reminder_sent
    try:
        events = get_calendar_events()
        now = datetime.now(timezone.utc)
        one_hour_later = now + timedelta(hours=1)

        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            event_id = event.get("id", "")

            if event_id in hourly_reminder_sent:
                continue  # Уникнення дублювання нагадування

            if 'T' in start:
                event_time = datetime.fromisoformat(start.replace('Z', '+00:00')).astimezone(timezone.utc)
            else:
                event_time = datetime.strptime(start, '%Y-%m-%d').replace(tzinfo=timezone.utc)

            if now <= event_time <= one_hour_later:
                for user_id in user_reminders.keys():
                    if get_value(f'reminder_{user_id}') == 'on':
                        message = (
                            f"⏰ *Нагадування про подію:*\n\n"
                            f"📅 {event_time.strftime('%d-%m-%Y')} — *{event['summary']}*\n"
                            f"🕒 Час початку: {event_time.strftime('%H:%M')}"
                        )
                        await context.bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
                        logger.info(f"✅ Надіслано нагадування про подію: {event['summary']} користувачу {user_id}")

                hourly_reminder_sent.add(event_id)
                set_value('hourly_reminder_sent', ','.join(hourly_reminder_sent))
    except Exception as e:
        logger.error(f"❌ Помилка у функції годинних нагадувань: {e}")


# 🔔 Вмикання нагадувань
async def set_reminder(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    set_value(f'reminder_{user_id}', 'on')
    delete_value(f'hourly_reminder_{user_id}')
    logger.info(f"✅ Нагадування увімкнено для користувача {user_id}")
    await update.message.reply_text("🔔 Нагадування увімкнено.")


# 🔕 Вимкнення нагадувань
async def unset_reminder(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    set_value(f'reminder_{user_id}', 'off')
    delete_value(f'hourly_reminder_{user_id}')
    logger.info(f"✅ Нагадування вимкнено для користувача {user_id}")
    await update.message.reply_text("🔕 Нагадування вимкнено.")


# 🛡️ Скидання щоденних нагадувань
async def reset_daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    delete_value('daily_reminder_sent')
    delete_value('hourly_reminder_sent')
    hourly_reminder_sent.clear()
    logger.info("🔄 Прапорці щоденних і годинних нагадувань скинуто.")


# 📅 Планування завдань
def schedule_event_reminders(job_queue: JobQueue):
    job_queue.run_daily(send_daily_reminder, time=time(hour=9, minute=0, tzinfo=timezone.utc))
    job_queue.run_repeating(send_event_reminders, interval=900, first=10)
    job_queue.run_daily(reset_daily_reminder, time=time(hour=0, minute=0, tzinfo=timezone.utc))

