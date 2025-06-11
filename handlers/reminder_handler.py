from telegram.ext import JobQueue, ContextTypes
from utils.calendar_utils import get_calendar_events, get_today_events
from utils.logger import logger
from config import TIMEZONE
from datetime import datetime, timedelta, time
from database import (
    set_value, get_value, get_cursor,
    save_bot_message, db
)
import pytz
import json
import openai
import hashlib
import os
from telegram import Update
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

from utils import init_openai_api

init_openai_api()
TEST_CHAT_ID = os.getenv("REMINDER_TEST_CHAT_ID")
berlin_tz = pytz.timezone(TIMEZONE)

def get_event_signature(event: dict) -> str:
    summary = event.get('summary', '')
    location = event.get('location', '')
    description = event.get('description', '')
    start_time = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', ''))
    signature_string = f"{event.get('id', '')}_{summary}_{start_time}_{location}_{description}"
    return hashlib.sha256(signature_string.encode('utf-8')).hexdigest()

def get_current_time():
    now = datetime.now(berlin_tz)
    one_hour_later = now + timedelta(hours=1)
    return now, one_hour_later


def get_active_chats() -> list[str]:
    """
    Повертає список групових чатів, куди слід надсилати нагадування.
    Якщо задано REMINDER_TEST_CHAT_ID – повертаємо лише його.
    """
    try:
        # 🔒 1. Тестовий режим
        if TEST_CHAT_ID:
            return [TEST_CHAT_ID]

        # 🔓 2. Звичайний режим (старий алгоритм)
        chat_list = json.loads(get_value("group_chats") or "[]")
        return [chat["chat_id"] for chat in chat_list if chat.get("chat_id")]
    except Exception as e:
        logger.error(f"❌ Помилка get_active_chats: {e}")
        return []


async def set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_chat.type in ["group", "supergroup"]:
            await update.message.reply_text(
                "❗ Нагадування у групових чатах завжди увімкнені і не можуть бути вимкнені.",
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info("Спроба увімкнення нагадувань у груповому чаті – відхилено")
            return
        user_id = str(update.effective_user.id)
        users_with_reminders_str = get_value('users_with_reminders')
        users_with_reminders = json.loads(users_with_reminders_str) if users_with_reminders_str else []
        if user_id not in users_with_reminders:
            users_with_reminders.append(user_id)
            set_value('users_with_reminders', json.dumps(users_with_reminders))
            message = await update.message.reply_text(
                "✅ *Нагадування увімкнено!*\nВи будете отримувати сповіщення про події за годину до їх початку.",
                parse_mode=ParseMode.MARKDOWN
            )
            save_bot_message(str(update.effective_chat.id), message.message_id, "general")
            logger.info(f"✅ Увімкнено нагадування для користувача {user_id}")
    except Exception as e:
        logger.error(f"❌ Помилка при вмиканні нагадувань: {e}")
        message = await update.message.reply_text(
            "❌ Виникла помилка при вмиканні нагадувань. Спробуйте пізніше.",
            parse_mode=ParseMode.MARKDOWN
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")

async def unset_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_chat.type in ["group", "supergroup"]:
            await update.message.reply_text(
                "❗ Нагадування у групових чатах завжди увімкнені і не можуть бути вимкнені.",
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info("Спроба вимкнення нагадувань у груповому чаті – відхилено")
            return
        user_id = str(update.effective_user.id)
        users_with_reminders_str = get_value('users_with_reminders')
        users_with_reminders = json.loads(users_with_reminders_str) if users_with_reminders_str else []
        if user_id in users_with_reminders:
            users_with_reminders.remove(user_id)
            set_value('users_with_reminders', json.dumps(users_with_reminders))
            message = await update.message.reply_text(
                "🔕 *Нагадування вимкнено*\nВи більше не будете отримувати сповіщення про події за годину до їх початку.",
                parse_mode=ParseMode.MARKDOWN
            )
            save_bot_message(str(update.effective_chat.id), message.message_id, "general")
            logger.info(f"🔕 Вимкнено нагадування для користувача {user_id}")
    except Exception as e:
        logger.error(f"❌ Помилка при вимиканні нагадувань: {e}")
        message = await update.message.reply_text(
            "❌ Виникла помилка при вимиканні нагадувань. Спробуйте пізніше.",
            parse_mode=ParseMode.MARKDOWN
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")

async def send_daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(berlin_tz)
    current_date = now.date()
    if not (9 <= now.hour < 21):
        logger.info("⏰ Зараз не вказаний інтервал для щоденних нагадувань (9:00–21:00).")
        return
    already_sent = get_value('daily_reminder_sent')
    stored_hash = get_value('daily_reminder_hash')
    try:
        events = get_today_events()

        # Обчислюємо хеш поточних подій на сьогодні
        event_signatures = [get_event_signature(e) for e in events]
        current_hash = hashlib.sha256("".join(sorted(event_signatures)).encode('utf-8')).hexdigest()

        if already_sent == current_date.isoformat() and stored_hash == current_hash:
            logger.info("🔄 Щоденне нагадування вже було відправлено сьогодні і події не змінювались.")
            return

        logger.info("🔔 Початок надсилання щоденних нагадувань...")
        if not events:
            logger.info("⚠️ Подій на сьогодні немає, нагадування не відправлено.")
            return
        
        active_chats = get_active_chats()
        header = escape_markdown(
            f"🔔 Розклад подій на сьогодні, {current_date.day:02d}"
            f" {current_date.strftime('%B').lower()}:",
            version=2,
        )
        daily_message = f"*{header}*\n\n"
        for event in events:
            event_time = event.get('start', {}).get('dateTime', 'Весь день')
            if event_time and 'T' in event_time:
                event_time = datetime.fromisoformat(event_time.replace('Z', '+00:00')).astimezone(berlin_tz).strftime('%H:%M')
            summary = escape_markdown(event.get('summary', ''), version=2)
            daily_message += (
                f"📅 *{summary}*\n"
                f"🕒 Час: {event_time}\n"
            )
            if 'location' in event and event['location']:
                location = escape_markdown(event['location'], version=2)
                daily_message += f"📍 Місце: {location}\n"
            daily_message += "\n"
        
        if len(daily_message) > 4096:
            daily_message = daily_message[:4090] + "..."
        
        sent_any = False
        for chat_id in active_chats:
            try:
                message = await context.bot.send_message(
                    chat_id=int(chat_id),
                    text=daily_message,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                save_bot_message(chat_id, message.message_id, "daily_reminder")
                sent_any = True
            except Exception as e:
                logger.warning(
                    f"⚠️ Не вдалося надіслати щоденне нагадування в чат {chat_id}: {e}"
                )

        if sent_any:
            logger.info(
                f"✅ Щоденні нагадування на {current_date} відправлено успішно."
            )
            set_value("daily_reminder_sent", current_date.isoformat())
            set_value("daily_reminder_hash", current_hash)
        else:
            logger.error(
                "❌ Не вдалося надіслати щоденне нагадування жодному чату."
            )
    except Exception as e:
        logger.error(f"❌ Помилка у функції send_daily_reminder: {e}")
        if "Message is too long" in str(e):
            set_value('daily_reminder_sent', current_date.isoformat())
            set_value('daily_reminder_hash', current_hash)
            logger.info(f"✅ Стан daily_reminder_sent збережено попри помилку довжини повідомлення")

async def startup_daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(berlin_tz)
    if 9 <= now.hour < 21:
        already_sent = get_value('daily_reminder_sent')
        today = now.date().isoformat()
        if already_sent != today:
            logger.info("🔄 Запуск щоденних нагадувань при старті бота.")
            await send_daily_reminder(context)
    else:
        logger.info("⏳ Зараз не час для щоденних нагадувань (9:00–21:00).")

async def send_event_reminders(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(pytz.timezone(TIMEZONE))
    one_hour_later = now + timedelta(hours=1)
    logger.info(f"⏰ Перевірка годинних нагадувань: Зараз {now}, Через годину {one_hour_later}")
    logger.info("🔔 Початок перевірки нагадувань...")

    # 🆕 Try sending the daily schedule first in case it wasn't sent yet
    await send_daily_reminder(context)

    try:
        events = get_today_events()
        logger.info(f"📅 Отримано {len(events)} подій із календаря.")
    except Exception as e:
        logger.error(f"❌ Помилка при отриманні подій: {e}")
        return

    notified_count = 0

    for idx, event in enumerate(events, start=1):
        try:
            start_info = event.get("start", {})
            if isinstance(start_info, list):
                logger.error(f"❌ Подія має список у 'start', пропущено: {start_info}")
                continue

            start_str = start_info.get("dateTime")
            if not start_str:
                continue

            start_dt = datetime.fromisoformat(start_str).astimezone(pytz.timezone(TIMEZONE))
            if not (now < start_dt <= one_hour_later):
                continue

            # Формуємо текст нагадування
            title = escape_markdown(event.get("summary", "Без назви"), version=2)
            description = escape_markdown(event.get("description", ""), version=2)
            location = escape_markdown(event.get("location", "—"), version=2)
            link = event.get("htmlLink", "")
            start_formatted = start_dt.strftime("%H:%M")

            header = escape_markdown("🔔 Подія через годину!", version=2)
            reminder_text = (
                f"{header}\n\n"
                f"📅 *{title}*\n"
                f"🕒 Час: {start_formatted}\n"
                f"📍 Місце: {location}\n"
            )
            if description:
                reminder_text += f"📝 Опис: {description}\n"
            if link:
                escaped_link = escape_markdown(link, version=2)
                reminder_text += f"🔗 [Відкрити в календарі]({escaped_link})"

            # Хеш тексту
            event_id = event.get("id")
            reminder_type = "hourly"  # 🔧 додаємо явно тип
            reminder_hash = generate_event_hash(event, reminder_type)

            # Отримуємо попередній хеш
            last_hash = db.get_event_reminder_hash(event_id, reminder_type)


            if last_hash == reminder_hash:
                continue  # Уже надсилали таке саме повідомлення

            # 🔁 Надсилання у тестовий чат або всім користувачам з reminders
            target_chats = [TEST_CHAT_ID] if TEST_CHAT_ID else db.get_users_with_reminders()

            for chat_id in target_chats:
                try:
                    await context.bot.send_message(
                        chat_id=int(chat_id),
                        text=reminder_text,
                        parse_mode=ParseMode.MARKDOWN_V2,
                        disable_web_page_preview=True,
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Не вдалося надіслати повідомлення в чат {chat_id}: {e}")


            db.save_event_reminder_hash(event_id, reminder_type, reminder_hash)
            notified_count += 1

        except Exception as e:
            logger.error(f"❌ Помилка при обробці події #{idx} (id: {event.get('id')}): {e}")
            logger.error(f"🔍 Подія-сирець: {event}")

    if notified_count == 0:
        logger.info("⚠️ Немає подій, які потребують нагадувань за годину або всі вже надіслані без змін.")
    else:
        logger.info(f"✅ Надіслано {notified_count} нових нагадувань.")


async def startup_birthday_check(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(berlin_tz)
    today = now.date()
    current_hour = now.hour

    # Визначаємо період: ранковий (9:00–12:00) або вечірній (20:00–23:00)
    is_morning_period = 9 <= current_hour < 12
    is_evening_period = 20 <= current_hour < 23

    if not (is_morning_period or is_evening_period):
        logger.info("⏰ Зараз не час для надсилання вітань при запуску (не в ранковому чи вечірньому періоді).")
        return

    greeting_type = 'morning' if is_morning_period else 'evening'

    # Перевіряємо, чи нагадування вже було надіслане для цього періоду
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id FROM birthday_greetings 
            WHERE date_sent = ? AND greeting_type = ?
        """, (today.isoformat(), greeting_type))
        already_sent = cursor.fetchone() is not None

    if already_sent:
        logger.info(f"ℹ️ Нагадування про день народження вже надіслане ({greeting_type}) на {today} при запуску")
        return

    # Якщо нагадування ще не надсилалося, викликаємо check_birthday_greetings
    logger.info(f"🔄 Запуск перевірки днів народження при старті бота ({greeting_type})")
    await check_birthday_greetings(context)

async def generate_birthday_greeting(name: str, time_of_day: str) -> str:
    try:
        # Оновлений промпт: прибираємо "до 80 токенів" і додаємо вимогу завершеності
        prompt = f"""
        Ти — OBERIG, помічник хору «Оберіг». Створи коротке, унікальне привітання з днем народження, 
        адресоване групі (наприклад, "Друзі, чи знаєте ви...", "Наші любі хористи...", "Сьогодні особливий день...") 
        із згадкою іменинника {name} та музичною тематикою. 
        Для {time_of_day}:
        - morning (9:00–12:00): радісне, енергійне з побажанням гарного дня.
        - evening (20:00–23:00): тепле з сподіванням, що день пройшов чудово.
        Текст має бути завершеним, закінчуватися логічним реченням (з крапкою або знаком оклику).
        Додай емоджі (🎵, 🎂, 😊, 🎉) і хештеги (#Оберіг, #ДеньНародження).
        """
        
        # Збільшуємо max_tokens до 150, щоб дати більше простору
        max_tokens = 200
        attempts = 0
        max_attempts = 3  # Максимальна кількість спроб генерації

        while attempts < max_attempts:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.9
            )
            greeting = response.choices[0].message.content.strip()
            
            # Перевіряємо, чи текст виглядає завершеним (закінчується крапкою, знаком оклику або питальним знаком)
            if greeting and greeting[-1] in ['.', '!', '?']:
                break  # Текст завершений, виходимо з циклу
            else:
                logger.warning(f"⚠️ Згенероване привітання для {name} виглядає незавершеним: {greeting}")
                attempts += 1
                max_tokens += 50  # Збільшуємо max_tokens для наступної спроби
                logger.info(f"🔄 Спроба {attempts + 1}: Збільшуємо max_tokens до {max_tokens}")

        if attempts == max_attempts:
            logger.error(f"❌ Не вдалося згенерувати завершене привітання для {name} після {max_attempts} спроб")

        # Екрануємо спеціальні символи для Telegram
        for char in ['!', '.', '(', ')', '-', '+', '=', '[', ']', '{', '}', '#']:
            greeting = greeting.replace(char, f'\\{char}')

        # Перевіряємо наявність емоджі та хештегів
        if not any(emoji in greeting for emoji in ['🎵', '🎂', '😊', '🎉']):
            greeting = f"{greeting} 🎵🎂😊"
        if '#Оберіг' not in greeting:
            greeting += " #Оберіг #ДеньНародження"

        # Перевіряємо довжину повідомлення для Telegram (максимум 4096 символів)
        if len(greeting) > 4096:
            greeting = greeting[:4090] + "..."

        return greeting
    except openai.OpenAIError as e:
        logger.error(f"❌ Помилка при генерації привітання для {name}: {e}")
        default = f"🎵 Друзі, чи знаєте ви, що у нас є іменинник\\? Вітаємо тебе, {name}, з днем народження\\! Нехай мелодії радують тебе\\! 😊 #Оберіг #ДеньНародження"
        return default

async def check_birthday_greetings(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(berlin_tz)
    today = now.date()
    current_hour = now.hour
    greeting_type = 'morning' if current_hour < 12 else 'evening'

    # Перевіряємо, чи нагадування вже було надіслане сьогодні для цього періоду
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id FROM birthday_greetings 
            WHERE date_sent = ? AND greeting_type = ?
        """, (today.isoformat(), greeting_type))
        already_sent = cursor.fetchone() is not None

    if already_sent:
        logger.info(f"ℹ️ Нагадування про день народження вже надіслане ({greeting_type}) на {today}")
        return

    logger.info(f"⏰ Перевірка днів народження на {today} о {now.strftime('%H:%M')}")
    events = get_today_events()
    logger.info(f"Отримано {len(events)} подій на сьогодні: {[event['summary'] for event in events]}")

    if not events:
        logger.info("Сьогодні немає подій.")
        return

    active_group_chats = get_active_chats()
    logger.info(f"Активні групові чати: {active_group_chats}")

    if not active_group_chats:
        logger.warning("Немає активних групових чатів для надсилання вітань.")
        return

    # Збираємо всі привітання для збереження в базі
    greetings_to_save = []
    for event in events:
        summary = event.get('summary', '').lower()
        logger.debug(f"Обробка події: {summary}")

        if 'день народження' not in summary:
            logger.debug(f"Подія '{summary}' пропущена, не є днем народження")
            continue

        name = "співоча зірка"  # За замовчуванням
        if " – день народження" in summary:
            name = summary.split(" – день народження")[0].strip().split()[0]
        elif "день народження" in summary:
            name_part = summary.split('день народження')[1].strip()
            name = name_part.split()[0] if name_part else "співоча зірка"

        logger.info(f"Знайдено день народження: {name}")
        greeting = await generate_birthday_greeting(name, greeting_type)
        logger.info(f"Згенеровано вітання для {name}: {greeting}")

        # Надсилаємо привітання в усі активні чати
        for group_chat_id in active_group_chats:
            await context.bot.send_message(chat_id=int(group_chat_id), text=greeting)
            logger.info(f"Надіслано {greeting_type} привітання для {name} у чат {group_chat_id}")

        # Зберігаємо привітання для запису в базу
        greetings_to_save.append({
            'event_id': event.get('id', 'unknown'),
            'date_sent': today.isoformat(),
            'greeting_type': greeting_type,
            'greeting_text': greeting
        })

    # Зберігаємо інформацію про надіслані привітання в базу
    if greetings_to_save:
        with get_cursor() as cursor:
            for greeting in greetings_to_save:
                cursor.execute("""
                    INSERT INTO birthday_greetings (event_id, date_sent, greeting_type, greeting_text)
                    VALUES (?, ?, ?, ?)
                """, (
                    greeting['event_id'],
                    greeting['date_sent'],
                    greeting['greeting_type'],
                    greeting['greeting_text']
                ))
        logger.info(f"✅ Збережено {len(greetings_to_save)} привітань у таблиці birthday_greetings")

async def cleanup_old_birthday_greetings(context: ContextTypes.DEFAULT_TYPE):
    with get_cursor() as cursor:
        cursor.execute("""
            DELETE FROM birthday_greetings 
            WHERE date_sent < date('now', '-30 days')
        """)
    logger.info("✅ Очищено старі записи з таблиці birthday_greetings")

def schedule_cleanup(job_queue: JobQueue):
    job_queue.run_daily(
        cleanup_old_birthday_greetings,
        time=time(hour=0, minute=0, tzinfo=berlin_tz),
        days=(0, 1, 2, 3, 4, 5, 6)
    )
    logger.info("✅ Планування очищення старих записів birthday_greetings налаштовано.")

def schedule_birthday_greetings(job_queue: JobQueue):
    # Викликаємо перевірку при запуску
    job_queue.run_once(startup_birthday_check, when=10)

    # Плануємо перевірки на 9:00 і 20:00 щодня
    job_queue.run_daily(
        check_birthday_greetings,
        time=time(hour=9, minute=0, tzinfo=berlin_tz),
        days=(0, 1, 2, 3, 4, 5, 6)
    )
    job_queue.run_daily(
        check_birthday_greetings,
        time=time(hour=20, minute=0, tzinfo=berlin_tz),
        days=(0, 1, 2, 3, 4, 5, 6)
    )
    # Додаємо очищення старих записів
    schedule_cleanup(job_queue)
    logger.info("✅ Планування перевірок днів народження на 9:00 і 20:00 (з перевіркою при запуску) налаштовано.")

def create_birthday_greetings_table():
    with get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS birthday_greetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                date_sent TEXT NOT NULL,
                greeting_type TEXT NOT NULL CHECK(greeting_type IN ('morning', 'evening')),
                greeting_text TEXT NOT NULL
            )
        """)
    logger.info("✅ Таблиця birthday_greetings створена або вже існує.")

def schedule_event_reminders(job_queue: JobQueue):
    """
    Планує завдання для перевірки годинних нагадувань.
    """
    job_queue.run_repeating(
        send_event_reminders,
        interval=600,  # 600 секунд = 10 хвилин
        first=10
    )
    job_queue.run_daily(
        send_daily_reminder,
        time=time(hour=9, minute=0, tzinfo=berlin_tz),
        days=(0, 1, 2, 3, 4, 5, 6),
    )
    logger.info("✅ Планування завдань для нагадувань успішно налаштовано.")

def generate_event_hash(event: dict, reminder_type: str) -> str:
    """
    Генерує хеш події для виявлення змін. Логує всі дані.
    """
    summary = event.get("summary", "")
    start = event.get("start", {}).get("dateTime", "")
    end = event.get("end", {}).get("dateTime", "")
    location = event.get("location", "")
    description = event.get("description", "")
    html_link = event.get("htmlLink", "")

    content = f"{summary}|{start}|{end}|{location}|{description}|{html_link}|{reminder_type}"
    hash_value = hashlib.md5(content.encode("utf-8")).hexdigest()

    logger.debug(f"🔍 Хеш події {event.get('id')} ({reminder_type}):")
    logger.debug(f"  Назва      : {summary}")
    logger.debug(f"  Початок    : {start}")
    logger.debug(f"  Кінець     : {end}")
    logger.debug(f"  Місце      : {location}")
    logger.debug(f"  Опис       : {description}")
    logger.debug(f"  Посилання  : {html_link}")
    logger.debug(f"  HASH       : {hash_value}")
    return hash_value

__all__ = [
    "schedule_event_reminders", "set_reminder", "unset_reminder", "send_daily_reminder",
    "startup_daily_reminder",
    "send_event_reminders", "check_birthday_greetings", "schedule_birthday_greetings",
    "create_birthday_greetings_table", "startup_birthday_check",
    "cleanup_old_birthday_greetings", "schedule_cleanup"
]