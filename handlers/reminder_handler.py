# reminder_handler.py - модуль, який містить функції для нагадувань про події у календарі
from telegram.ext import JobQueue, ContextTypes
from utils.calendar_utils import get_calendar_events
from utils.logger import logger
from config import TIMEZONE
from datetime import datetime, timedelta, time
from database import set_value, get_value, delete_value
import pytz

# 🛡️ Ініціалізація глобальних змінних
berlin_tz = pytz.timezone(TIMEZONE)


# 🛡️ Функція для отримання актуального часу
def get_current_time():
    """
    Отримує поточний час і час на годину вперед у часовому поясі Берліна.
    """
    now = datetime.now(berlin_tz)
    one_hour_later = now + timedelta(hours=1)
    return now, one_hour_later


# 🛡️ Ініціалізація глобальних змінних зі збереженими значеннями
try:
    daily_reminder_sent = get_value('daily_reminder_sent') == str(datetime.now(berlin_tz).date())
    hourly_reminder_sent = set((get_value('hourly_reminder_sent') or '').split(',')) if get_value('hourly_reminder_sent') else set()
except Exception as e:
    logger.error(f"❌ Помилка під час ініціалізації змінних нагадувань: {e}")
    daily_reminder_sent = False
    hourly_reminder_sent = set()


# 🛡️ Функція для отримання списку активних чатів
def get_active_chats():
    """
    Отримує список усіх активних групових чатів із бази даних.
    """
    try:
        chat_list = get_value('group_chat_list') or ''
        if chat_list:
            return chat_list.split(',')
        logger.warning("⚠️ Список групових чатів для нагадувань порожній. Нагадування не буде надіслано.")
        return []
    except Exception as e:
        logger.error(f"❌ Помилка при отриманні списку активних чатів: {e}")
        return []


# 🔔 Увімкнення нагадувань
async def set_reminder(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    try:
        logger.info(f"🔄 Спроба увімкнення нагадувань для користувача {user_id}")
        
        # Встановлюємо нагадування для користувача
        set_value(f'reminder_{user_id}', 'on')
        logger.info(f"✅ Ключ reminder_{user_id} встановлено на 'on'")
        
        # Отримуємо та оновлюємо список користувачів
        current_list = get_value('user_reminder_list')
        if current_list:
            current_list = set(filter(None, current_list.split(',')))
        else:
            current_list = set()
        
        logger.info(f"🔄 Поточний список користувачів перед оновленням: {current_list}")
        
        # Додаємо користувача
        current_list.add(user_id)
        updated_list = ','.join(current_list)
        set_value('user_reminder_list', updated_list)
        logger.info(f"✅ Оновлений список користувачів: {updated_list}")
        
        # Перевірка збереження
        saved_list = get_value('user_reminder_list')
        logger.info(f"🔍 Перевірка збереження списку у базі: {saved_list}")
        
        await update.message.reply_text("🔔 Нагадування увімкнено.")
    except Exception as e:
        logger.error(f"❌ Помилка при увімкненні нагадувань для користувача {user_id}: {e}")
        await update.message.reply_text("❌ Виникла помилка при увімкненні нагадувань.")


# 🔕 Вимкнення нагадувань
async def unset_reminder(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    try:
        logger.info(f"🔄 Спроба вимкнення нагадувань для користувача {user_id}")
        
        # Вимикаємо нагадування для користувача
        set_value(f'reminder_{user_id}', 'off')
        logger.info(f"✅ Ключ reminder_{user_id} встановлено на 'off'")
        
        # Отримуємо та оновлюємо список користувачів
        current_list = get_value('user_reminder_list')
        if current_list:
            current_list = set(filter(None, current_list.split(',')))
        else:
            current_list = set()
        
        logger.info(f"🔄 Поточний список користувачів перед оновленням: {current_list}")
        
        # Видаляємо користувача зі списку
        current_list.discard(user_id)
        updated_list = ','.join(current_list)
        set_value('user_reminder_list', updated_list)
        logger.info(f"✅ Оновлений список користувачів: {updated_list}")
        
        # Перевірка збереження
        saved_list = get_value('user_reminder_list')
        logger.info(f"🔍 Перевірка збереження списку у базі: {saved_list}")
        
        await update.message.reply_text("🔕 Нагадування вимкнено.")
    except Exception as e:
        logger.error(f"❌ Помилка при вимкненні нагадувань для користувача {user_id}: {e}")
        await update.message.reply_text("❌ Виникла помилка при вимкненні нагадувань.")


# 🕒 Функція для щоденних нагадувань
async def send_daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    """
    Надсилає щоденні нагадування один раз на день в інтервалі 9:00–21:00.
    """
    now = datetime.now(berlin_tz)
    current_date = now.date().isoformat()

    # Перевірка діапазону часу
    if not (9 <= now.hour < 21):
        logger.info("⏰ Зараз не вказаний інтервал для щоденних нагадувань (9:00–21:00).")
        return

    # Перевірка дублювання
    already_sent = get_value('daily_reminder_sent')
    if already_sent == current_date:
        logger.info("🔄 Щоденне нагадування вже було відправлено сьогодні.")
        return

    try:
        logger.info("🔔 Початок надсилання щоденних нагадувань...")

        # Видалення старих записів
        logger.info("🧹 Видалення старих записів щоденних нагадувань...")
        delete_value('daily_reminder_sent')
        delete_value('daily_reminder_%')

        # Отримання подій на сьогодні
        events = get_calendar_events()
        if not events:
            logger.info("⚠️ Подій на сьогодні немає.")
            return

        # Надсилання нагадувань у активні чати
        active_chats = get_active_chats()
        for chat_id in active_chats:
            await context.bot.send_message(
                chat_id=int(chat_id),
                text="🔔 Сьогоднішні події:\n" + "\n".join(events),
                parse_mode="Markdown"
            )

        # Встановлення ключа для запобігання дублювання
        set_value('daily_reminder_sent', current_date)
        logger.info(f"✅ Щоденні нагадування на {current_date} відправлено успішно.")

    except Exception as e:
        logger.error(f"❌ Помилка у функції send_daily_reminder: {e}")


# 🛡️ Функція для перевірки щоденних нагадувань при запуску
async def startup_daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    """
    Виконує перевірку щоденних нагадувань одразу після запуску бота.
    """
    now = datetime.now(berlin_tz)
    if 9 <= now.hour < 21:
        already_sent = get_value('daily_reminder_sent')
        today = now.date().isoformat()
        if already_sent != today:
            logger.info("🔄 Запуск щоденних нагадувань при старті бота.")
            await send_daily_reminder(context)
    else:
        logger.info("⏳ Зараз не час для щоденних нагадувань (9:00–21:00).")


# 🛡️ Планування завдань
def schedule_event_reminders(job_queue: JobQueue):
    """
    Планування щоденних та годинних нагадувань.
    """
    # Щоденні нагадування
    job_queue.run_daily(
        send_daily_reminder, 
        time=time(hour=9, minute=0, tzinfo=berlin_tz)
    )

    # Щогодинна перевірка
    job_queue.run_repeating(
        send_daily_reminder,
        interval=3600,  # Кожну годину
        first=10  # Затримка 10 секунд після запуску
    )

    logger.info("✅ Планування щоденних і годинних нагадувань налаштовано успішно.")


# ⏰ Функція для годинних нагадувань
async def send_event_reminders(context):
    now, one_hour_later = get_current_time()
    logger.info(f"⏰ Перевірка годинних нагадувань: Зараз {now}, Через годину {one_hour_later}")
    try:
        user_reminders = []
        user_list = (get_value('user_reminder_list') or '').split(',') if get_value('user_reminder_list') else []
        logger.info(f"📊 Список користувачів із бази: {user_list}")

        for user_id in user_list:
            if get_value(f'reminder_{user_id}') == 'on':
                user_reminders.append(user_id)

        logger.info(f"🔄 Користувачі з увімкненими нагадуваннями: {user_reminders}")
    except Exception as e:
        logger.error(f"❌ Помилка у функції годинних нагадувань: {e}")



# 🛡️ Планування завдань
def schedule_event_reminders(job_queue: JobQueue):
    job_queue.run_daily(send_daily_reminder, time=time(hour=9, minute=0, tzinfo=berlin_tz))
    job_queue.run_repeating(send_event_reminders, interval=900, first=10)
    logger.info("✅ Планування завдань для нагадувань успішно налаштовано.")


__all__ = ["schedule_event_reminders", "set_reminder", "unset_reminder", "send_daily_reminder", "send_event_reminders"]
