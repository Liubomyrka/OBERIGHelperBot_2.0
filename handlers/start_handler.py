import os
import json

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import ContextTypes
from utils.logger import logger
from utils.calendar_utils import (
    get_latest_youtube_video,
    get_most_popular_youtube_video,
    get_top_10_videos,
)
from database import (
    set_value,
    get_value,
    add_user_to_list,
    add_group_to_list,
    save_bot_message,
    update_user_list,
)
from handlers.help_handler import help_command
from handlers.schedule_handler import schedule_command
from handlers.reminder_handler import set_reminder, unset_reminder
from handlers.notification_handler import toggle_video_notifications
from handlers.admin_handler import (
    admin_menu_command,
    analytics_command,
    users_list_command,
    group_chats_list_command,
    is_admin,
    delete_messages,
    delete_recent,
)
from handlers.feedback_handler import start_feedback, show_my_feedback
from handlers.oberig_assistant_handler import handle_oberig_assistant
from handlers.drive_utils import (
    list_sheets,
    search_sheets,
    send_sheet,
)
from handlers.notes_utils import search_notes

SCHEDULE_MENU_TEXT_PRIVATE = """📅 *Меню розкладу*

Виберіть одну з опцій:
📋 - Переглянути розклад подій
🕒 - Переглянути події на сьогодні

🠸 Нагадування (за замовчуванням увімкнені):
- Вимкнути нагадування - припинити отримувати сповіщення за годину до події
- Увімкнути нагадування - відновити сповіщення за годину до події"""

SCHEDULE_MENU_TEXT_GROUP = """📅 *Меню розкладу*

Виберіть одну з опцій:
📋 - Переглянути розклад подій
🕒 - Переглянути події на сьогодні

🠸 Нагадування завжди увімкнені для групових чатів і не можуть бути вимкнені."""

YOUTUBE_MENU_TEXT = """🎥 *Меню YouTube*

Виберіть одну з опцій:
📺 - Переглянути всі відео
🆕 - Переглянути найновіше відео
🔥 - Переглянути найпопулярніше відео
🏆 - Топ-10 найпопулярніших відео

🠸 Керування сповіщеннями:
- Увімкнути сповіщення - отримувати повідомлення про нові відео
- Вимкнути сповіщення - припинити отримувати повідомлення"""

MAIN_MENU_TEXT = """
🎶 *Головне меню OBERIG*  
Обери опцію внизу ⬇️:  
• 📅 Розклад  
• ▶️ YouTube  
• 📝 Відгуки  
• 🌐 Соцмережі
"""

WELCOME_TEXT = """
*Вітаємо у боті OBERIG! 🎵*

Я — OBERIG, твій віртуальний помічник. Я допоможу вам бути в курсі всіх подій хору:
• 📅 Перегляд розкладу
• 🠸 Нагадування про події (за замовчуванням увімкнені, можна вимкнути)
• ▶️ Відео з YouTube
• 🎵 Ноти
• 📝 Зворотний зв’язок
• 🚀 Задавайте мені будь-які запитання про хор OBERIG!

Натисніть кнопки нижче, щоб розпочати.
"""

GROUP_CHAT_TEXT = (
    "👋 *Питай мене в приваті!* Перейди сюди ⬇️: [OBERIG](https://t.me/OBERIGHelperBot)"
)

ERROR_VIDEO_NOT_FOUND = "⚠️ *Відео не знайдено 😔* Спробуй пізніше! ⬇️"
ERROR_UNKNOWN_COMMAND = (
    "❌ *Команда не знайдена 😕* Обери кнопку внизу ⬇️ чи спитай мене!"
)
ERROR_GENERAL = "❌ *Щось пішло не так 😔* Спробуй ще раз! ⬇️"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_add_user(update, context)
    logger.info("🔄 Виконання команди: /start")
    try:
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        bot_users_str = get_value("bot_users")
        bot_users = json.loads(bot_users_str) if bot_users_str else []
        bot_users_info_str = get_value("bot_users_info")
        bot_users_info = json.loads(bot_users_info_str) if bot_users_info_str else {}
        if user_id not in bot_users:
            bot_users.append(user_id)
            set_value("bot_users", json.dumps(bot_users))
        user_name = (
            update.effective_user.first_name
            or update.effective_user.username
            or "Невідомо"
        )
        bot_users_info[str(user_id)] = user_name
        set_value("bot_users_info", json.dumps(bot_users_info))
        logger.info(f"Збережено користувачів: {get_value('bot_users')}")
        logger.info(
            f"Збережено інформацію про користувачів: {get_value('bot_users_info')}"
        )
        if update.effective_chat.type == "private":
            update_user_list("users_with_reminders", user_id, add=True)
            await show_main_menu(update, context)
            message = await update.message.reply_text(
                WELCOME_TEXT, parse_mode="Markdown"
            )
            save_bot_message(chat_id, message.message_id, "general")
            logger.info("✅ Команда /start виконана успішно у приватному чаті.")
        elif chat_id == "-1001906486581":
            keyboard = [[KeyboardButton("Помічник"), KeyboardButton("🎵 Ноти")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            message = await update.message.reply_text(
                "🎵 *Обери ноти внизу* ⬇️",
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            save_bot_message(chat_id, message.message_id, "general")
            logger.info("✅ Відображено початкове меню в групі -1001906486581")
        else:
            try:
                all_chats = get_value("group_chats")
                logger.info(f"🔍 Поточний список групових чатів: {all_chats}")
                if all_chats:
                    group_list = json.loads(all_chats)
                else:
                    group_list = []
                chat_exists = False
                for chat in group_list:
                    if chat.get("chat_id") == chat_id:
                        chat_exists = True
                        if chat.get("title") != update.effective_chat.title:
                            chat["title"] = update.effective_chat.title
                            set_value("group_chats", json.dumps(group_list))
                            logger.info(f"✅ Оновлено назву групового чату {chat_id}")
                        break
                if not chat_exists:
                    chat_info = {
                        "chat_id": chat_id,
                        "title": update.effective_chat.title,
                    }
                    group_list.append(chat_info)
                    set_value("group_chats", json.dumps(group_list))
                    logger.info(f"✅ Груповий чат {chat_id} додано до списку")
                updated_chats = get_value("group_chats")
                logger.info(f"🔍 Оновлений список групових чатів: {updated_chats}")
            except Exception as e:
                logger.error(f"❌ Помилка при додаванні групового чату до списку: {e}")
            message = await update.message.reply_text(
                GROUP_CHAT_TEXT,
                parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_to_message_id=update.message.message_id,
            )
            save_bot_message(chat_id, message.message_id, "general")
            logger.info("✅ Команда /start виконана успішно у груповому чаті.")
    except Exception as e:
        logger.error(f"❌ Помилка у команді /start: {e}")
        message = await update.message.reply_text(
            "❌ *Помилка запуску 😕* Спробуй ще раз! ⬇️"
        )
        save_bot_message(chat_id, message.message_id, "general")


async def latest_video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_add_user(update, context)
    logger.info("🔄 Виконання команди: /latest_video")
    try:
        video_url = get_latest_youtube_video()
        if video_url:
            message = await update.message.reply_text(
                f"🆕 *Найновіше відео хору OBERIG:*\n\n"
                f"👆 [Переглянути відео]({video_url})\n\n"
                "📤 Поділитися цим відео: `/share_latest`",
                parse_mode="Markdown",
            )
            save_bot_message(
                str(update.effective_chat.id), message.message_id, "general"
            )
            logger.info("✅ Команда /latest_video виконана успішно.")
        else:
            message = await update.message.reply_text(ERROR_VIDEO_NOT_FOUND)
            save_bot_message(
                str(update.effective_chat.id), message.message_id, "general"
            )
            logger.warning(ERROR_VIDEO_NOT_FOUND)
    except Exception as e:
        logger.error(f"❌ Помилка у виконанні команди /latest_video: {e}")
        message = await update.message.reply_text(ERROR_GENERAL)
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_add_user(update, context)
    keyboard = [
        [KeyboardButton("📩 Надіслати відгук"), KeyboardButton("📋 Мої відгуки")],
        [KeyboardButton("🔙 Головне меню")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    message = await update.message.reply_text(
        "📝 *Меню відгуків*  Обери внизу ⬇️:",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )
    save_bot_message(str(update.effective_chat.id), message.message_id, "general")


async def redirect_to_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перенаправляє користувача з групового чату в приватний чат із ботом."""
    chat_id = str(update.effective_chat.id)
    message = await update.message.reply_text(
        "👋 *Питай мене в приваті!* Перейди сюди ⬇️: [OBERIG](https://t.me/OBERIGHelperBot)",
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )
    save_bot_message(chat_id, message.message_id, "general")
    logger.info("✅ Користувач перенаправлений у приватний чат")


async def show_notes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує початкове меню нот із клавіатурою."""
    chat_id = str(update.effective_chat.id)
    if chat_id != "-1001906486581" and update.effective_chat.type != "private":
        return

    keyboard = [
        [KeyboardButton("📋 Всі ноти"), KeyboardButton("🔤 За назвою")],
        [KeyboardButton("🔍 За ключовим словом"), KeyboardButton("🔙 Головне меню")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    if chat_id == "-1001906486581":
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=update.message.message_id - 1,
            reply_markup=reply_markup,
        )
    else:
        message = await update.message.reply_text(
            "🎵 *Обери ноти внизу* ⬇️", parse_mode="Markdown", reply_markup=reply_markup
        )
        save_bot_message(chat_id, message.message_id, "general")
    logger.info("✅ Відображено початкове меню нот")


async def show_all_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує список усіх нот із клавіатурою."""
    chat_id = str(update.effective_chat.id)
    if chat_id != "-1001906486581" and update.effective_chat.type != "private":
        return

    # Отримуємо список нот
    sheets = await list_sheets(update, context)
    if not sheets:
        await update.message.reply_text("❌ *Помилка з нотами 😕* Спробуй пізніше! ⬇️")
        return

    # Створюємо клавіатуру з нотами
    keyboard = []
    all_sheets = []
    for category, items in sheets.items():
        all_sheets.extend(items)
    all_sheets.sort(key=lambda x: x["name"].lower())  # Сортуємо за назвою

    # Додаємо кнопки для кожної ноти
    for sheet in all_sheets:
        keyboard.append([KeyboardButton(f"📃 {sheet['name']}")])

    # Додаємо кнопку "Повернутися до меню нот"
    keyboard.append([KeyboardButton("🔙 Меню нот")])

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    if chat_id == "-1001906486581":
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=update.message.message_id - 1,
            reply_markup=reply_markup,
        )
    else:
        message = await update.message.reply_text(
            "🎵 *Вибери ноти внизу* ⬇️", parse_mode="Markdown", reply_markup=reply_markup
        )
        save_bot_message(chat_id, message.message_id, "general")
    logger.info("✅ Відображено список усіх нот")


async def show_notes_by_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує список нот, відсортованих за назвою, із клавіатурою."""
    chat_id = str(update.effective_chat.id)
    if chat_id != "-1001906486581" and update.effective_chat.type != "private":
        return

    # Отримуємо список нот
    sheets = await list_sheets(update, context)
    if not sheets:
        await update.message.reply_text("❌ *Помилка з нотами 😕* Спробуй пізніше! ⬇️")
        return

    # Створюємо клавіатуру з нотами, відсортованими за назвою
    keyboard = []
    all_sheets = []
    for category, items in sheets.items():
        all_sheets.extend(items)
    all_sheets.sort(key=lambda x: x["name"].lower())  # Сортуємо за назвою

    # Додаємо кнопки для кожної ноти
    for sheet in all_sheets:
        keyboard.append([KeyboardButton(f"📃 {sheet['name']}")])

    # Додаємо кнопку "Повернутися до меню нот"
    keyboard.append([KeyboardButton("🔙 Меню нот")])

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    if chat_id == "-1001906486581":
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=update.message.message_id - 1,
            reply_markup=reply_markup,
        )
    else:
        message = await update.message.reply_text(
            "🎵 *Вибери ноти внизу* ⬇️ (за назвою)",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
        save_bot_message(chat_id, message.message_id, "general")
    logger.info("✅ Відображено список нот, відсортованих за назвою")




async def text_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_add_user(update, context)
    chat_id = str(update.effective_chat.id)
    chat_type = update.effective_chat.type
    text = update.message.text
    logger.info(f"🔄 Обробка текстової кнопки або повідомлення: {text}")

    if chat_type != "private" and chat_id != "-1001906486581":
        if text == "Помічник":
            await redirect_to_private(update, context)
        return

    # Спочатку перевіряємо текст, пов’язаний із нотами, щоб уникнути обробки OBERIG-асистентом
    if text.startswith("📃 "):
        sheet_name = text[2:].strip()
        logger.debug(f"Спроба завантажити ноту: {sheet_name}")
        sheets = await list_sheets(update, context)
        if not sheets:
            await update.message.reply_text(
                "❌ *Помилка з нотами 😕* Спробуй пізніше! ⬇️"
            )
            return
        all_sheets = []
        for category, items in sheets.items():
            all_sheets.extend(items)
        found = False
        for sheet in all_sheets:
            logger.debug(f"Порівнюємо з нотою: {sheet['name']}")
            if sheet["name"] == sheet_name:  # Точне порівняння
                await send_sheet(update, context, sheet["id"])
                logger.info(f"✅ Вибрано ноту '{sheet_name}'")
                found = True
                return
        await update.message.reply_text(
            f"❌ *Ноту '{sheet_name}' не знайдено 😔* Перевір назву чи вибери з клавіатури. ⬇️"
        )
        logger.warning(f"Ноту '{sheet_name}' не знайдено у списку")
        return

    standard_commands = [
        "/start",
        "Старт",
        "📅 Розклад",
        "ℹ️ Допомога",
        "▶️ YouTube",
        "🌐 Соцмережі",
        "📩 Надіслати відгук",
        "📋 Мої відгуки",
        "⚙️ Меню адміністратора",
        "🎵 Ноти",
        "👥 Список користувачів",
        "👥 Список чатів",
        "📋 Розклад подій",
        "🕒 Події на сьогодні",
        "Вимкнути нагадування",
        "Увімкнути нагадування",
        "📺 Наші відео",
        "🆕 Найновше відео",
        "🔥 Найпопулярніше відео",
        "🏆 Топ-10 відео",
        "🠸 Увімкнути сповіщення",
        "🔕 Вимкнути сповіщення",
        "🔙 Головне меню",
        "🗑️ Видалити повідомлення",
        "🗑️ Видалити за 30 хв",
        "📊 Аналітика за 7 днів",
        "📊 Аналітика за 30 днів",
        "📈 Статистика використання",
        "📋 Всі ноти",
        "🔤 За назвою",
        "🔍 За ключовим словом",
        "Помічник",
        "🔙 Меню нот",
    ]

    try:
        if text in standard_commands or text.startswith("/"):
            if text == "Старт":
                await start(update, context)
            elif text == "📅 Розклад":
                await show_schedule_menu(update, context)
                logger.info("✅ Натиснуто кнопку '📅 Розклад'")
            elif text == "ℹ️ Допомога":
                await help_command(update, context)
                logger.info("✅ Натиснуто кнопку 'ℹ️ Допомога'")
            elif text == "▶️ YouTube":
                await show_youtube_menu(update, context)
                logger.info("✅ Натиснуто кнопку '▶️ YouTube'")
            elif text == "🌐 Соцмережі":
                message = await update.message.reply_text(
                    "📘 [Facebook](https://www.facebook.com/profile.php?id=100094519583534)",
                    parse_mode="Markdown",
                )
                save_bot_message(chat_id, message.message_id, "general")
                logger.info("✅ Натиснуто кнопку '🌐 Соцмережі'")
            elif text == "📩 Надіслати відгук":
                await start_feedback(update, context)
                logger.info("✅ Натиснуто кнопку '📩 Надіслати відгук'")
            elif text == "📋 Мої відгуки":
                await show_my_feedback(update, context)
                logger.info("✅ Натиснуто кнопку '📋 Мої відгуки'")
            elif text == "⚙️ Меню адміністратора":
                if await is_admin(update.effective_user.id):
                    await admin_menu_command(update, context)
                    logger.info("✅ Натиснуто кнопку '⚙️ Меню адміністратора'")
            elif text == "👥 Список користувачів":
                if await is_admin(update.effective_user.id):
                    await users_list_command(update, context)
                    logger.info("✅ Натиснуто кнопку '👥 Список користувачів'")
            elif text == "👥 Список чатів":
                if await is_admin(update.effective_user.id):
                    await group_chats_list_command(update, context)
                    logger.info("✅ Натиснуто кнопку '👥 Список чатів'")
            elif text == "📋 Розклад подій":
                await schedule_command(update, context)
                logger.info("✅ Натиснуто кнопку '📋 Розклад подій'")
            elif text == "🕒 Події на сьогодні":
                await schedule_command(update, context, today_only=True)
                logger.info("✅ Натиснуто кнопку '🕒 Події на сьогодні'")
            elif text == "Вимкнути нагадування":
                await unset_reminder(update, context)
                logger.info("✅ Натиснуто кнопку 'Вимкнути нагадування'")
            elif text == "Увімкнути нагадування":
                await set_reminder(update, context)
                logger.info("✅ Натиснуто кнопку 'Увімкнути нагадування'")
            elif text == "📺 Наші відео":
                message = await update.message.reply_text(
                    "📺 [Наші відео](https://youtube.com/playlist?list=PLEkdnztUMQ7-05r94OMzHyCVMCXvkgrFn&si=GoW-Kr5DVWnX5cCl)\n\n👆 Натисніть, щоб переглянути всі відео хору OBERIG",
                    parse_mode="Markdown",
                )
                save_bot_message(chat_id, message.message_id, "general")
                logger.info("✅ Натиснуто кнопку '📺 Наші відео'")
            elif text == "🆕 Найновше відео":
                await latest_video_command(update, context)
                logger.info("✅ Натиснуто кнопку '🆕 Найновше відео'")
            elif text == "🔥 Найпопулярніше відео":
                await most_popular_video_command(update, context)
                logger.info("✅ Натиснуто кнопку '🔥 Найпопулярніше відео'")
            elif text == "🏆 Топ-10 відео":
                # Скидаємо сторінку до 0 при новому виклику команди
                context.user_data["top_10_page"] = 0
                await top_10_videos_command(update, context)
                logger.info("✅ Натиснуто кнопку '🏆 Топ-10 відео'")
            elif text == "🠸 Увімкнути сповіщення":
                await toggle_video_notifications(update, context, True)
                logger.info("✅ Натиснуто кнопку '🠸 Увімкнути сповіщення'")
            elif text == "🔕 Вимкнути сповіщення":
                await toggle_video_notifications(update, context, False)
                logger.info("✅ Натиснуто кнопку '🔕 Вимкнути сповіщення'")
            elif text == "🔙 Головне меню":
                if chat_type == "private":
                    await show_main_menu(update, context)
                elif chat_id == "-1001906486581":
                    keyboard = [[KeyboardButton("Помічник"), KeyboardButton("🎵 Ноти")]]
                    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                    await context.bot.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=update.message.message_id - 1,
                        reply_markup=reply_markup,
                    )
                    logger.info(
                        "✅ Оновлено клавіатуру до головного меню в групі -1001906486581"
                    )
            elif text == "🗑️ Видалити повідомлення":
                if await is_admin(update.effective_user.id):
                    await delete_messages(update, context)
                    logger.info("✅ Виконано команду '🗑️ Видалити повідомлення'")
            elif text == "🗑️ Видалити за 30 хв":
                if await is_admin(update.effective_user.id):
                    await delete_recent(update, context)
                    logger.info("✅ Виконано команду '🗑️ Видалити за 30 хв'")
            elif text == "📊 Аналітика за 7 днів":
                if await is_admin(update.effective_user.id):
                    context.args = ["7"]
                    await analytics_command(update, context)
                    logger.info("✅ Натиснуто кнопку '📊 Аналітика за 7 днів'")
            elif text == "📊 Аналітика за 30 днів":
                if await is_admin(update.effective_user.id):
                    context.args = ["30"]
                    await analytics_command(update, context)
                    logger.info("✅ Натиснуто кнопку '📊 Аналітика за 30 днів'")
            elif text == "📈 Статистика використання":
                if await is_admin(update.effective_user.id):
                    stats = json.loads(get_value("commands_stats") or "{}")
                    message_text = "📈 *Статистика використання команд:*\n\n"
                    for date, commands in stats.items():
                        message_text += f"📅 *{date}:*\n"
                        for command, count in commands.items():
                            message_text += f"/{command}: {count} разів\n"
                        message_text += "\n"
                    message = await update.message.reply_text(
                        message_text, parse_mode="Markdown"
                    )
                    save_bot_message(chat_id, message.message_id, "general")
                    logger.info("✅ Натиснуто кнопку '📈 Статистика використання'")
            elif text == "Помічник" and chat_id == "-1001906486581":
                await redirect_to_private(update, context)
                logger.info("✅ Натиснуто кнопку 'Помічник' у групі -1001906486581")
            elif text == "🎵 Ноти" and (
                chat_type == "private" or chat_id == "-1001906486581"
            ):
                await show_notes_menu(update, context)
                logger.info("✅ Натиснуто кнопку '🎵 Ноти'")
            elif text == "📋 Всі ноти" and (
                chat_type == "private" or chat_id == "-1001906486581"
            ):
                await show_all_notes(update, context)
                logger.info("✅ Натиснуто кнопку '📋 Всі ноти'")
            elif text == "🔤 За назвою" and (
                chat_type == "private" or chat_id == "-1001906486581"
            ):
                await show_notes_by_name(update, context)
                logger.info("✅ Натиснуто кнопку '🔤 За назвою'")
            elif text == "🔍 За ключовим словом" and (
                chat_type == "private" or chat_id == "-1001906486581"
            ):
                message = await update.message.reply_text(
                    "🔍 *Введи слово для пошуку нот* ⬇️", parse_mode="Markdown"
                )
                save_bot_message(chat_id, message.message_id, "general")
                context.user_data["awaiting_keyword"] = True
                logger.info("✅ Натиснуто кнопку '🔍 За ключовим словом'")
            elif text == "🔙 Меню нот" and (
                chat_type == "private" or chat_id == "-1001906486581"
            ):
                await show_notes_menu(update, context)
                logger.info("✅ Повернення до меню нот")

        # Обробка лише тексту, який не пов’язаний із нотами або стандартними командами
        elif context.user_data.get("awaiting_keyword") and (
            chat_type == "private" or chat_id == "-1001906486581"
        ):
            # Передаємо текст як ключове слово для пошуку нот
            await search_notes(update, context)
            logger.info(f"✅ Виконується пошук нот за ключовим словом: {text}")
        else:
            await handle_oberig_assistant(update, context)
            logger.info(f"✅ OBERIG-помічник обробив запит: {text}")
    except Exception as e:
        logger.error(f"❌ Помилка при обробці команди: {e}")
        message = await update.message.reply_text(
            "❌ *Щось пішло не так 😔* Спробуй ще раз! ⬇️"
        )
        save_bot_message(chat_id, message.message_id, "general")


async def top_10_videos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_add_user(update, context)
    logger.info("Виконання команди: /top_10_videos")
    try:
        videos = get_top_10_videos()
        if not videos:
            message = await update.message.reply_text(
                "⚠️ *Відео не знайдено 😔* Спробуй пізніше! ⬇️"
            )
            save_bot_message(
                str(update.effective_chat.id), message.message_id, "general"
            )
            logger.warning("Відео не знайдено")
            return

        # Отримуємо поточну сторінку з user_data (за замовчуванням 0)
        page = context.user_data.get("top_10_page", 0)
        videos_per_page = 5
        total_pages = (len(videos) + videos_per_page - 1) // videos_per_page

        # Перевіряємо межі сторінки
        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1
        context.user_data["top_10_page"] = page

        # Отримуємо відео для поточної сторінки
        start_idx = page * videos_per_page
        end_idx = min(start_idx + videos_per_page, len(videos))
        current_videos = videos[start_idx:end_idx]

        # Формуємо текст повідомлення
        message_text = "*🏆 Топ-10 найпопулярніших відео:*\n\n"
        for i, (title, url, views) in enumerate(current_videos, start_idx + 1):
            title = title[:120] + "..." if len(title) > 120 else title  # Збільшуємо до 120 символів
            message_text += f"**{i}.** [{title}]({url})\n👁 {views:,} переглядів\n\n"

        # Додаємо інформацію про сторінку
        message_text += f"\n📄 Сторінка {page + 1} з {total_pages}"

        # Додаємо кнопки пагінації
        keyboard = []
        if page > 0:
            keyboard.append(InlineKeyboardButton("⬅️ Попередня п'ятірка", callback_data="top_10_prev"))
        if page < total_pages - 1:
            keyboard.append(InlineKeyboardButton("Наступна п'ятірка ➡️", callback_data="top_10_next"))
        reply_markup = InlineKeyboardMarkup([keyboard]) if keyboard else None

        # Надсилаємо або оновлюємо повідомлення
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message_text,
                parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
        else:
            message = await update.message.reply_text(
                message_text,
                parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
            save_bot_message(
                str(update.effective_chat.id), message.message_id, "general"
            )

        logger.info(f"Команда /top_10_videos виконана успішно (Сторінка {page + 1})")
    except Exception as e:
        logger.error(f"Помилка у виконанні команди /top_10_videos: {e}")
        message = await update.message.reply_text(
            "❌ *Щось пішло не так 😔* Спробуй ще раз! ⬇️"
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")


async def show_youtube_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_add_user(update, context)
    logger.info("Спроба відобразити меню YouTube")
    try:
        keyboard = [
            [KeyboardButton("📺 Наші відео")],
            [KeyboardButton("🆕 Найновше відео")],
            [KeyboardButton("🔥 Найпопулярніше відео")],
            [KeyboardButton("🏆 Топ-10 відео")],
            [
                KeyboardButton("🠸 Увімкнути сповіщення"),
                KeyboardButton("🔕 Вимкнути сповіщення"),
            ],
            [KeyboardButton("🔙 Головне меню")],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        message = await update.message.reply_text(
            "🎥 *Меню YouTube*  Обери внизу ⬇️:",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")
        logger.info("Відображено меню YouTube")
    except Exception as e:
        logger.error(f"Помилка при відображенні меню YouTube: {e}")
        message = await update.message.reply_text(
            "❌ *Щось пішло не так 😔* Спробуй ще раз! ⬇️"
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")


async def most_popular_video_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    await auto_add_user(update, context)
    logger.info("🔄 Виконання команди: /most_popular_video")
    try:
        video_url = get_most_popular_youtube_video()
        if video_url:
            message = await update.message.reply_text(
                f"🔥 *Найпопулярніше відео хору OBERIG:*\n\n"
                f"👆 [Переглянути відео]({video_url})\n\n"
                "📤 Поділитися цим відео: `/share_popular`",
                parse_mode="Markdown",
            )
            save_bot_message(
                str(update.effective_chat.id), message.message_id, "general"
            )
            logger.info("✅ Команда /most_popular_video виконана успішно")
        else:
            message = await update.message.reply_text(
                "⚠️ *Відео не знайдено 😔* Спробуй пізніше! ⬇️"
            )
            save_bot_message(
                str(update.effective_chat.id), message.message_id, "general"
            )
            logger.warning("Відео не знайдено")
    except Exception as e:
        logger.error(f"❌ Помилка у виконанні команди /most_popular_video: {e}")
        message = await update.message.reply_text(
            "❌ *Щось пішло не так 😔* Спробуй ще раз! ⬇️"
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")


async def show_schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_add_user(update, context)
    logger.info("🔄 Спроба відобразити меню розкладу")
    try:
        if update.effective_chat.type == "private":
            users_with_reminders_str = get_value("users_with_reminders")
            users_with_reminders = (
                json.loads(users_with_reminders_str) if users_with_reminders_str else []
            )
            user_id = str(update.effective_user.id)
            if user_id in users_with_reminders:
                reminder_button = KeyboardButton("Вимкнути нагадування")
            else:
                reminder_button = KeyboardButton("Увімкнути нагадування")

            keyboard = [
                [KeyboardButton("📋 Розклад подій")],
                [KeyboardButton("🕒 Події на сьогодні")],
                [reminder_button],
                [KeyboardButton("🔙 Головне меню")],
            ]
            menu_text = "📅 *Меню розкладу*  Обери внизу ⬇️:"
        else:
            keyboard = [
                [KeyboardButton("📋 Розклад подій")],
                [KeyboardButton("🕒 Події на сьогодні")],
                [KeyboardButton("🔙 Головне меню")],
            ]
            menu_text = "📅 *Меню розкладу*  Обери внизу ⬇️:"
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        message = await update.message.reply_text(
            menu_text, parse_mode="Markdown", reply_markup=reply_markup
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")
        logger.info("✅ Відображено меню розкладу")
    except Exception as e:
        logger.error(f"❌ Помилка при відображенні меню розкладу: {e}")
        message = await update.message.reply_text(
            "❌ *Щось пішло не так 😔* Спробуй ще раз! ⬇️"
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")


async def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Повертає клавіатуру головного меню з урахуванням ролі користувача."""
    keyboard = [
        [KeyboardButton("Старт")],
        [KeyboardButton("📅 Розклад"), KeyboardButton("▶️ YouTube")],
        [KeyboardButton("🎵 Ноти"), KeyboardButton("🌐 Соцмережі")],
        [KeyboardButton("📩 Надіслати відгук"), KeyboardButton("📋 Мої відгуки")],
        [KeyboardButton("ℹ️ Допомога"), KeyboardButton("🔙 Головне меню")],
    ]
    # Додаємо кнопку "⚙️ Меню адміністратора" для адміністраторів
    if await is_admin(user_id):
        keyboard.insert(4, [KeyboardButton("⚙️ Меню адміністратора")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_add_user(update, context)
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "redirect_private":
        await redirect_to_private(update, context)
        logger.info("✅ Натиснуто кнопку 'Помічник' у групі -1001906486581")
    elif data == "top_10_prev":
        # Переходимо на попередню сторінку
        context.user_data["top_10_page"] = context.user_data.get("top_10_page", 0) - 1
        await top_10_videos_command(update, context)
        logger.info("✅ Натиснуто кнопку 'Попередня п'ятірка'")
    elif data == "top_10_next":
        # Переходимо на наступну сторінку
        context.user_data["top_10_page"] = context.user_data.get("top_10_page", 0) + 1
        await top_10_videos_command(update, context)
        logger.info("✅ Натиснуто кнопку 'Наступна п'ятірка'")
    else:
        await query.answer(
            "❌ *Команда не знайдена 😕* Обери кнопку внизу ⬇️ чи спитай мене!"
        )
        logger.warning(f"⚠️ Невідома callback команда: {data}")


async def auto_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = str(update.effective_user.id)
        chat_type = update.effective_chat.type
        bot_users_str = get_value("bot_users")
        bot_users = json.loads(bot_users_str) if bot_users_str else []
        bot_users_info_str = get_value("bot_users_info")
        bot_users_info = json.loads(bot_users_info_str) if bot_users_info_str else {}

        # Додаємо користувача до bot_users і bot_users_info лише якщо його ще немає
        if user_id not in bot_users:
            bot_users.append(user_id)
            bot_users_info[user_id] = (
                update.effective_user.first_name
                or update.effective_user.username
                or "Невідомо"
            )
            set_value("bot_users", json.dumps(bot_users))
            set_value("bot_users_info", json.dumps(bot_users_info))
            logger.info(f"✅ Додано нового користувача {user_id} до списку bot_users")

        # Додаємо до нагадувань лише для приватних чатів і лише якщо користувача ще немає в users_with_reminders
        if chat_type == "private":
            users_with_reminders_str = get_value("users_with_reminders")
            users_with_reminders = (
                json.loads(users_with_reminders_str) if users_with_reminders_str else []
            )
            if user_id not in users_with_reminders:
                users_with_reminders.append(user_id)
                set_value("users_with_reminders", json.dumps(users_with_reminders))
                logger.info(
                    f"✅ Автоматично додано користувача {user_id} до нагадувань"
                )

        # Додаємо групу, якщо це груповий чат
        if chat_type in ["group", "supergroup"]:
            add_group_to_list(
                str(update.effective_chat.id),
                update.effective_chat.title or "Невідома група",
            )

        logger.info(f"✅ Користувач {user_id} оброблений при взаємодії")
    except Exception as e:
        logger.error(f"❌ Помилка при автоматичному додаванні користувача: {e}")


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("🔄 Відображення головного меню для користувача.")
    try:
        user_id = update.effective_user.id
        is_admin_user = await is_admin(user_id)
        keyboard = await get_main_keyboard(user_id)
        menu_text = (
            MAIN_MENU_TEXT
            + "\n\n🚀 Я — OBERIG, твій віртуальний помічник. Задавайте мені будь-які запитання про хор, і я допоможу!"
        )
        if is_admin_user:
            menu_text += "\n\n👑 *Ви увійшли як адміністратор*"
        message = await update.message.reply_text(
            menu_text, parse_mode="Markdown", reply_markup=keyboard
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")
        logger.info(
            f"✅ Головне меню відображено для {'адміністратора' if is_admin_user else 'користувача'}"
        )
    except Exception as e:
        logger.error(f"❌ Помилка при відображенні головного меню: {e}")
        message = await update.message.reply_text(
            "❌ *Щось пішло не так 😔* Спробуй ще раз! ⬇️"
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")


async def show_group_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("🔄 Відображення меню у груповому чаті.")
    try:
        keyboard = [[KeyboardButton("🗨️ Перейти до приватного чату з OBERIG")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        message = await update.message.reply_text(
            "❗ *Ця команда доступна лише у приватних повідомленнях з OBERIG.*\n"
            "👉 [Перейдіть у приватний чат зі мною, OBERIG](https://t.me/OBERIGHelperBot).",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")
        logger.info("✅ Меню для групового чату відображено.")
    except Exception as e:
        logger.error(f"❌ Помилка при відображенні групового меню: {e}")
        message = await update.message.reply_text(
            "❌ *Щось пішло не так 😔* Спробуй ще раз! ⬇️"
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")


async def get_sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обробляє команду /get_sheet для надсилання нот з Google Drive.
    """
    await auto_add_user(update, context)

    # Перевіряємо, чи передано номер файлу
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "❌ Вкажіть номер файлу з попереднього списку. Наприклад, /get_sheet 1"
        )
        return

    try:
        # Отримуємо номер файлу
        file_number = context.args[0].strip(".")

        # Перевіряємо, чи є число
        if not file_number.isdigit():
            await update.message.reply_text(
                "❌ Номер файлу має бути цілим числом. Наприклад, /get_sheet 1"
            )
            return

        # Отримуємо список нот
        sheets = await list_sheets(update, context)
        if not sheets:
            await update.message.reply_text(
                "❌ *Помилка з нотами 😕* Спробуй пізніше! ⬇️"
            )
            return

        # Збираємо всі ноти в один список
        all_sheets = []
        for category, items in sheets.items():
            all_sheets.extend(items)

        # Перевіряємо діапазон номера
        index = int(file_number) - 1
        if index < 0 or index >= len(all_sheets):
            await update.message.reply_text(
                f"❌ Номер файлу має бути від 1 до {len(all_sheets)}"
            )
            return

        # Надсилаємо ноту
        sheet = all_sheets[index]
        await send_sheet(update, context, sheet["id"])

    except Exception as e:
        logger.error(f"Помилка при отриманні нот: {e}")
        await update.message.reply_text(
            "❌ Виникла несподівана помилка. Спробуйте пізніше. #Оберіг 😔"
        )


__all__ = [
    "start",
    "show_main_menu",
    "show_group_menu",
    "latest_video_command",
    "feedback_command",
    "text_menu_handler",
    "show_youtube_menu",
    "most_popular_video_command",
    "top_10_videos_command",
    "button_click",
    "auto_add_user",
    "redirect_to_private",
    "show_notes_menu",
    "show_all_notes",
    "show_notes_by_name",
    "get_sheet_command",
]