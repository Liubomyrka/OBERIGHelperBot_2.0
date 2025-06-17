from telegram.ext import JobQueue, ContextTypes
from utils.calendar_utils import get_calendar_events, get_today_events
from utils.logger import logger
from config import TIMEZONE
from datetime import datetime, timedelta, time
import asyncio
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

from utils import (
    init_openai_api,
    call_openai_chat,
    call_openai_assistant,
    get_openai_assistant_id,
)

ASSISTANT_ID = init_openai_api()
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
    if now.hour < 8:
        logger.info("🔇 Нічний режим активний, нагадування не надсилається")
        return

    current_date = now.date()
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
            link = event.get('htmlLink')
            if link:
                escaped_link = escape_markdown(link, version=2)
                daily_message += f"🔗 [Відкрити в календарі]({escaped_link})\n"
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
    if now.hour < 8:
        logger.info("🔇 Нічний режим: щоденне нагадування буде надіслано після 08:00")
        return
    already_sent = get_value('daily_reminder_sent')
    today = now.date().isoformat()
    if already_sent != today:
        logger.info("🔄 Запуск щоденних нагадувань при старті бота.")
        await send_daily_reminder(context)

async def send_event_reminders(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(pytz.timezone(TIMEZONE))
    one_hour_later = now + timedelta(hours=1)
    logger.info(f"⏰ Перевірка годинних нагадувань: Зараз {now}, Через годину {one_hour_later}")
    logger.info("🔔 Початок перевірки нагадувань...")
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

            start_str = start_info.get("dateTime") or start_info.get("date")
            if not start_str:
                continue

            if "T" in start_str:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00")).astimezone(pytz.timezone(TIMEZONE))
            else:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=pytz.timezone(TIMEZONE))
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

            sent_success = False
            for chat_id in target_chats:
                try:
                    await context.bot.send_message(
                        chat_id=int(chat_id),
                        text=reminder_text,
                        parse_mode=ParseMode.MARKDOWN_V2,
                        disable_web_page_preview=True,
                    )
                    sent_success = True
                except Exception as e:
                    logger.warning(f"⚠️ Не вдалося надіслати повідомлення в чат {chat_id}: {e}")

            if sent_success:
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


def inflect_to_dative(name: str) -> str:
    """Return the Ukrainian name inflected to the dative case."""
    try:
        from pymorphy3 import MorphAnalyzer  # type: ignore

        morph = MorphAnalyzer(lang="uk")
        parsed = morph.parse(name)
        for p in parsed:
            if {"Name", "Surn"} & set(p.tag):
                d = p.inflect({"datv"})
                if d:
                    result = d.word.capitalize()
                    return result
    except Exception:
        pass

    lower = name.lower()
    if lower.endswith("я"):
        return name[:-1] + "ї"
    if lower.endswith("а"):
        return name[:-1] + "і"
    if lower.endswith("й"):
        return name[:-1] + "ю"
    if lower.endswith("о"):
        return name[:-1] + "у"
    if lower.endswith("ь"):
        return name[:-1] + "ю"
    return name + "у"

async def generate_birthday_greeting(name: str, time_of_day: str) -> str:
    try:
        dative_name = inflect_to_dative(name)
        prompt = (
            "Ти — OBERIG, помічник хору \u00abОберіг\u00bb. Створи коротке та унікальне "
            "привітання з днем народження для групи з музичною тематикою. "
            f"Згадай {dative_name} і додай емоджі та хештеги. Стиль залежить від {time_of_day}: "
            "morning – енергійний, evening – теплий. Завершуй текст крапкою або знаком оклику."
        )

        if ASSISTANT_ID:
            greeting = await call_openai_assistant(
                messages=[{"role": "user", "content": prompt}],
                assistant_id=ASSISTANT_ID,
            )
        else:
            greeting = await call_openai_chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.9,
            )

        if greeting and greeting[-1] not in [".", "!", "?" ]:
            greeting += "!"

        greeting = escape_markdown(greeting, version=2)

        if not any(emoji in greeting for emoji in ["🎵", "🎂", "😊", "🎉"]):
            greeting = f"{greeting} 🎵🎂😊"
        if '#Оберіг' not in greeting:
            greeting += " #Оберіг #ДеньНародження"

        if len(greeting) > 4096:
            greeting = greeting[:4090] + "..."

        return greeting
    except openai.OpenAIError as e:
        logger.error(f"❌ Помилка при генерації привітання для {name}: {e}")
        default = (
            f"🎵 Друзі, чи знаєте ви, що у нас є іменинник? "
            f"Вітаємо тебе, {dative_name}, з днем народження! Нехай мелодії радують тебе! 😊 #Оберіг #ДеньНародження"
        )
        return escape_markdown(default, version=2)

async def check_birthday_greetings(context: ContextTypes.DEFAULT_TYPE):
    # Ensure the table exists before any DB operations
    create_birthday_greetings_table()

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
            await context.bot.send_message(
                chat_id=int(group_chat_id),
                text=greeting,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
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
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO birthday_greetings (event_id, date_sent, greeting_type, greeting_text)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        greeting['event_id'],
                        greeting['date_sent'],
                        greeting['greeting_type'],
                        greeting['greeting_text'],
                    ),
                )
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
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS birthday_greetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                date_sent TEXT NOT NULL,
                greeting_type TEXT NOT NULL CHECK(greeting_type IN ('morning', 'evening')),
                greeting_text TEXT NOT NULL,
                UNIQUE(event_id, date_sent, greeting_type)
            )
            """
        )

        cursor.execute("PRAGMA table_info(birthday_greetings)")
        columns = [col[1] for col in cursor.fetchall()]
        if "greeting_text" not in columns:
            cursor.execute(
                "ALTER TABLE birthday_greetings ADD COLUMN greeting_text TEXT"
            )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_birthday_unique ON birthday_greetings (event_id, date_sent, greeting_type)"
        )
    logger.info("✅ Таблиця birthday_greetings створена або вже існує.")

def schedule_event_reminders(job_queue: JobQueue):
    """
    Планує завдання для перевірки годинних нагадувань.
    """
    job_queue.run_repeating(
        send_event_reminders,
        interval=600,  # 600 секунд = 10 хвилин
        first=10,
    )
    job_queue.run_repeating(
        send_daily_reminder,
        interval=3600,  # раз на годину
        first=15,
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
    "cleanup_old_birthday_greetings", "schedule_cleanup",
    "inflect_to_dative",
]