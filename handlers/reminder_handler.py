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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from utils.birthday_image import create_birthday_image_bytes
try:
    from utils.message_utils import safe_send_markdown
except Exception:  # pragma: no cover - fallback for tests
    async def safe_send_markdown(bot, chat_id, text, **kwargs):
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
            **kwargs,
        )
from handlers.schedule_handler import _generate_short_id, _cache_event_id

from utils import (
    init_openai_api,
    call_openai_chat,
    call_openai_assistant,
    get_openai_assistant_id,
)

ASSISTANT_ID = init_openai_api()
TEST_CHAT_ID = os.getenv("REMINDER_TEST_CHAT_ID")
berlin_tz = pytz.timezone(TIMEZONE)
BIRTHDAY_IMAGE_ENABLED = os.getenv("BIRTHDAY_IMAGE_ENABLED", "1").strip().lower() not in {"0", "false", "no"}

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

async def send_daily_reminder(context: ContextTypes.DEFAULT_TYPE, force: bool = False):
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

        if (not force) and already_sent == current_date.isoformat() and stored_hash == current_hash:
            logger.info("🔄 Щоденне нагадування вже було відправлено сьогодні і події не змінювались.")
            return

        logger.info("🔔 Початок надсилання щоденних нагадувань...")
        if not events:
            logger.debug("⚠️ Подій на сьогодні немає, нагадування не відправлено.")
            return
        
        # Build recipients list: test chat only, or groups + private users
        if TEST_CHAT_ID:
            recipients = [TEST_CHAT_ID]
        else:
            try:
                group_chats = get_active_chats()
            except Exception:
                group_chats = []
            try:
                private_chats = db.get_users_with_reminders()
            except Exception:
                private_chats = []
            recipients = list(dict.fromkeys([*(group_chats or []), *(private_chats or [])]))

        def _pluralize_events(n: int) -> str:
            if n % 10 == 1 and n % 100 != 11:
                return "подія"
            if 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
                return "події"
            return "подій"

        header_text = escape_markdown(
            f"🔔 Розклад подій на сьогодні, {current_date.day:02d} {current_date.strftime('%B').lower()} – {len(events)} {_pluralize_events(len(events))}",
            version=2,
        )

        sent_any = False
        for chat_id in recipients:
            message = await safe_send_markdown(
                context.bot,
                int(chat_id),
                f"*{header_text}*",
            )
            if message:
                save_bot_message(chat_id, message.message_id, "daily_reminder")
                sent_any = True

        for event in events:
            try:
                event_time = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', ''))
                if event_time and 'T' in event_time:
                    event_time = datetime.fromisoformat(event_time.replace('Z', '+00:00')).astimezone(berlin_tz).strftime('%H:%M')
                    event_time = escape_markdown(event_time, version=2)
                elif event_time:
                    event_time = escape_markdown("(весь день)", version=2)
                summary = escape_markdown(event.get('summary', 'Без назви'), version=2)
                text = f"📅 *{summary}*"
                if event_time:
                    text += f"\n🕒 Час: {event_time}"
                location = event.get('location')
                if location:
                    text += f"\n📍 Місце: {escape_markdown(location, version=2)}"

                short_id = _generate_short_id(event['id'])
                _cache_event_id(short_id, event['id'])

                buttons = [[InlineKeyboardButton("Деталі", callback_data=f"event_{short_id}")]]
                link = event.get('htmlLink')
                if link:
                    buttons[0].append(InlineKeyboardButton("деталі в календарі", url=link))
                markup = InlineKeyboardMarkup(buttons)

                for chat_id in recipients:
                    message = await safe_send_markdown(
                        context.bot,
                        int(chat_id),
                        text,
                        reply_markup=markup,
                    )
                    if message:
                        save_bot_message(chat_id, message.message_id, "daily_reminder")
                        sent_any = True

            except Exception as e:
                logger.error(f"❌ Помилка при обробці події в daily_reminder: {e}")

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

async def send_event_reminders(context: ContextTypes.DEFAULT_TYPE, force: bool = False):
    now = datetime.now(pytz.timezone(TIMEZONE))
    one_hour_later = now + timedelta(hours=1)
    logger.debug(f"⏰ Перевірка годинних нагадувань: Зараз {now}, Через годину {one_hour_later}")
    logger.debug("🔔 Початок перевірки нагадувань...")
    try:
        events = get_today_events()
        logger.debug(f"📅 Отримано {len(events)} подій із календаря.")
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
            reply_markup = None
            buttons = []
            event_id = event.get("id")
            if event_id:
                short_id = _generate_short_id(event_id)
                _cache_event_id(short_id, event_id)
                buttons.append(InlineKeyboardButton("Деталі", callback_data=f"event_{short_id}"))
            if link:
                buttons.append(InlineKeyboardButton("Відкрити в календарі", url=link))
            if buttons:
                reply_markup = InlineKeyboardMarkup([buttons])

            # Хеш тексту
            reminder_type = "hourly"  # 🔧 додаємо явно тип
            reminder_hash = generate_event_hash(event, reminder_type)

            # Отримуємо попередній хеш
            last_hash = db.get_event_reminder_hash(event_id, reminder_type)


            if (not force) and last_hash == reminder_hash:
                continue  # Уже надсилали таке саме повідомлення

            # 🔁 Надсилання у тестовий чат або всім користувачам з reminders
            if TEST_CHAT_ID:
                target_chats = [TEST_CHAT_ID]
            else:
                try:
                    group_chats = get_active_chats()
                except Exception:
                    group_chats = []
                try:
                    private_chats = db.get_users_with_reminders()
                except Exception:
                    private_chats = []
                target_chats = list(dict.fromkeys([*(group_chats or []), *(private_chats or [])]))

            sent_success = False
            for chat_id in target_chats:
                send_kwargs = {"disable_web_page_preview": True}
                if reply_markup:
                    send_kwargs["reply_markup"] = reply_markup
                message = await safe_send_markdown(
                    context.bot,
                    int(chat_id),
                    reminder_text,
                    **send_kwargs,
                )
                if message:
                    sent_success = True
                    save_bot_message(str(chat_id), message.message_id, "hourly_reminder")
                else:
                    logger.warning(f"⚠️ Не вдалося надіслати повідомлення в чат {chat_id}")

            if sent_success:
                db.save_event_reminder_hash(event_id, reminder_type, reminder_hash)
                notified_count += 1

        except Exception as e:
            logger.error(f"❌ Помилка при обробці події #{idx} (id: {event.get('id')}): {e}")
            logger.error(f"🔍 Подія-сирець: {event}")

    if notified_count == 0:
        logger.debug("⚠️ Немає подій, які потребують нагадувань за годину або всі вже надіслані без змін.")
    else:
        logger.info(f"✅ Надіслано {notified_count} нових нагадувань.")


async def startup_birthday_check(context: ContextTypes.DEFAULT_TYPE):
    """Check for birthdays when the bot starts, regardless of the time."""
    logger.info("🔄 Запуск перевірки днів народження при старті бота")
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


def extract_birthday_name(summary: str) -> str:
    """Extract the celebrant's name from a calendar event summary."""
    try:
        import re

        cleaned = summary.replace("\u2013", "-").replace("\u2014", "-").strip()

        # Pattern: "день народження Name"
        match = re.search(
            r"день народження[:\s-]*([\w'’\-\u0400-\u04FF]+)",
            cleaned,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1)

        # Pattern: "Name - день народження"
        match = re.match(r"(.+?)\s*-\s*день народження", cleaned, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1)
            parts = re.findall(r"[\w'’\-\u0400-\u04FF]+", candidate)
            if parts:
                # take the first token as the name to avoid returning the surname
                return parts[0]
    except Exception:
        pass

    return "співоча зірка"

async def generate_birthday_greeting(
    name: str, time_of_day: str, prompt_override: str | None = None
) -> str:
    try:
        dative_name = inflect_to_dative(name)
        prompt = (
            "Ти — OBERIG, помічник хору \u00abОберіг\u00bb. Створи коротке та унікальне "
            "привітання з днем народження для групи з музичною тематикою. "
            f"Згадай {dative_name} і додай емоджі та хештеги. Стиль залежить від {time_of_day}: "
            "morning – енергійний, evening – теплий. Завершуй текст крапкою або знаком оклику."
        ) if prompt_override is None else prompt_override

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
            greeting += r" \#Оберіг \#ДеньНародження"

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

async def check_birthday_greetings(context: ContextTypes.DEFAULT_TYPE, force: bool = False):
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

    if already_sent and not force:
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
        raw_summary = event.get("summary", "")
        summary = raw_summary.lower()
        logger.debug(f"Обробка події: {summary}")

        if "день народження" not in summary:
            logger.debug(f"Подія '{summary}' пропущена, не є днем народження")
            continue

        name = extract_birthday_name(raw_summary)

        logger.info(f"Знайдено день народження: {name}")
        greeting = await generate_birthday_greeting(name, greeting_type)

        dative_name = inflect_to_dative(name)
        if (
            name.lower() not in greeting.lower()
            and dative_name.lower() not in greeting.lower()
        ):
            logger.warning(
                f"⚠️ Згенероване привітання не містить імені для події '{raw_summary}' (id={event.get('id')}); повторюю запит"
            )
            fix_prompt = (
                "Попередній текст привітання не містив імені іменинника. "
                f"Створи новий варіант і обов'язково згадай {dative_name}. "
                "Додай емоджі та хештеги. Завершуй текст крапкою або знаком оклику."
            )
            greeting = await generate_birthday_greeting(
                name, greeting_type, prompt_override=fix_prompt
            )

        logger.info(f"Згенеровано вітання для {name}: {greeting}")

        image_bytes = None
        if BIRTHDAY_IMAGE_ENABLED:
            seed = f"{event.get('id', '')}_{today.isoformat()}_{greeting_type}"
            image_bytes = create_birthday_image_bytes(name=name, seed=seed, greeting_type=greeting_type)

        # Надсилаємо привітання в усі активні чати
        for group_chat_id in active_group_chats:
            try:
                message = None
                if image_bytes:
                    caption = greeting if len(greeting) <= 1000 else None
                    send_kwargs = {}
                    if caption:
                        send_kwargs["caption"] = caption
                        send_kwargs["parse_mode"] = ParseMode.MARKDOWN_V2
                    message = await context.bot.send_photo(
                        chat_id=int(group_chat_id),
                        photo=image_bytes,
                        **send_kwargs,
                    )
                    if message and not caption:
                        await safe_send_markdown(
                            context.bot,
                            int(group_chat_id),
                            greeting,
                        )
                else:
                    message = await safe_send_markdown(
                        context.bot,
                        int(group_chat_id),
                        greeting,
                    )
                if message:
                    logger.info(
                        f"Надіслано {greeting_type} привітання для {name} у чат {group_chat_id}"
                    )
            except Exception as e:
                logger.error(f"❌ Помилка надсилання привітання з зображенням у чат {group_chat_id}: {e}")
                await safe_send_markdown(
                    context.bot,
                    int(group_chat_id),
                    greeting,
                )

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
    job_queue.run_repeating(
        check_birthday_greetings,
        interval=timedelta(hours=4),
        first=0,
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

def schedule_event_reminders(
    job_queue: JobQueue, initial_delay: int = 10, daily_delay: int = 3600
):
    """
    Планує завдання для перевірки годинних нагадувань.
    """
    job_queue.run_repeating(
        send_event_reminders,
        interval=600,  # 600 секунд = 10 хвилин
        first=initial_delay,
    )
    job_queue.run_repeating(
        send_daily_reminder,
        interval=3600,  # раз на годину
        first=daily_delay,
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
