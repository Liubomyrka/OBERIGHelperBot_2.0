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
from database import (
    set_value,
    get_value,
    add_user_to_list,
    add_group_to_list,
    save_bot_message,
    update_user_list,
)
from handlers.help_handler import help_command
from handlers.schedule_handler import schedule_command, upcoming_birthdays_command
from handlers.reminder_handler import set_reminder, unset_reminder
from handlers.notification_handler import toggle_video_notifications
from handlers.admin_handler import (
    admin_menu_command,
    show_admin_analytics_menu,
    show_admin_lists_menu,
    show_admin_cleanup_menu,
    show_admin_force_menu,
    analytics_command,
    users_list_command,
    group_chats_list_command,
    is_admin,
    delete_messages,
    delete_recent,
    force_daily_reminder_command,
    force_hourly_reminder_command,
    force_birthday_command,
)
from handlers.feedback_handler import start_feedback, show_my_feedback
from handlers.oberig_assistant_handler import handle_oberig_assistant
from handlers.drive_utils import (
    list_sheets,
    send_sheet,
)
from handlers.notes_utils import search_notes

from .notes_menu import show_notes_menu, show_all_notes
from .youtube_menu import (
    show_youtube_menu,
    latest_video_command,
    most_popular_video_command,
    top_10_videos_command,
)
from .schedule_menu import show_schedule_menu
from .user_utils import auto_add_user


SCHEDULE_MENU_TEXT_PRIVATE = """📅 *Меню розкладу*

Виберіть одну з опцій:
📋 - Переглянути розклад подій
🕒 - Переглянути події на сьогодні
🎂 - Переглянути найближчі дні народження

🔔 Нагадування (за замовчуванням увімкнені):
- 🔕 Вимкнути нагадування - припинити отримувати сповіщення за годину до події
- 🔔 Увімкнути нагадування - відновити сповіщення за годину до події"""

SCHEDULE_MENU_TEXT_GROUP = """📅 *Меню розкладу*

Виберіть одну з опцій:
📋 - Переглянути розклад подій
🕒 - Переглянути події на сьогодні
🎂 - Переглянути найближчі дні народження

🔔 Нагадування завжди увімкнені для групових чатів і не можуть бути вимкнені."""


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
• 🔔 Нагадування про події (за замовчуванням увімкнені, можна вимкнути)
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


async def text_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_add_user(update, context)
    chat_id = str(update.effective_chat.id)
    from .notes_menu import show_notes_menu, show_all_notes
    from .youtube_menu import show_youtube_menu, latest_video_command, most_popular_video_command, top_10_videos_command
    chat_type = update.effective_chat.type
    text = update.message.text
    logger.info(f"🔄 Обробка текстової кнопки або повідомлення: {text}")

    if chat_type != "private":
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
        "📅 Розклад",
        "ℹ️ Допомога",
        "▶️ YouTube",
        "🌐 Соцмережі",
        "📝 Відгуки",
        "📩 Надіслати відгук",
        "📋 Мої відгуки",
        "⚙️ Меню адміністратора",
        "📊 Аналітика",
        "👥 Списки",
        "🗑️ Очищення",
        "⚡ Примусові дії",
        "🎵 Ноти",
        "👤 Користувачі",
        "💬 Чати",
        "👥 Список користувачів",
        "👥 Список чатів",
        "📋 Розклад подій",
        "🕒 Події на сьогодні",
        "🎂 Найближчі ДН",
        "🔕 Вимкнути нагадування",
        "🔔 Увімкнути нагадування",
        "📺 Наші відео",
        "🆕 Найновше відео",
        "🔥 Найпопулярніше відео",
        "🏆 Топ-10 відео",
        "📤 Поділитися новим",
        "📤 Поділитися популярним",
        "🔔 Увімкнути сповіщення",
        "🔕 Вимкнути сповіщення",
        "🔙 Головне меню",
        "🗑️ Видалити день",
        "🗑️ Видалити повідомлення",
        "🗑️ Видалити 30 хв",
        "📅 Примусово розклад",
        "⏰ Примусово нагадування",
        "🎂 Примусово ДН",
        "📅 Розклад",
        "⏰ Нагадування",
        "🎂 ДН",
        "📊 7 днів",
        "📊 30 днів",
        "📈 Статистика",
        "🔙 Адмін меню",
        "📊 Аналітика за 7 днів",
        "📊 Аналітика за 30 днів",
        "📈 Статистика використання",
        "📋 Всі ноти",
        "🔍 За ключовим словом",
        "Помічник",
        "🔙 Меню нот",
    ]

    try:
        if text in standard_commands or text.startswith("/"):
            if text == "📅 Розклад":
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
            elif text == "📝 Відгуки":
                await feedback_command(update, context)
                logger.info("✅ Натиснуто кнопку '📝 Відгуки'")
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
            elif text == "📊 Аналітика":
                if await is_admin(update.effective_user.id):
                    await show_admin_analytics_menu(update, context)
                    logger.info("✅ Натиснуто кнопку '📊 Аналітика'")
            elif text == "👥 Списки":
                if await is_admin(update.effective_user.id):
                    await show_admin_lists_menu(update, context)
                    logger.info("✅ Натиснуто кнопку '👥 Списки'")
            elif text == "🗑️ Очищення":
                if await is_admin(update.effective_user.id):
                    await show_admin_cleanup_menu(update, context)
                    logger.info("✅ Натиснуто кнопку '🗑️ Очищення'")
            elif text == "⚡ Примусові дії":
                if await is_admin(update.effective_user.id):
                    await show_admin_force_menu(update, context)
                    logger.info("✅ Натиснуто кнопку '⚡ Примусові дії'")
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
            elif text == "🎂 Найближчі ДН":
                await upcoming_birthdays_command(update, context)
                logger.info("✅ Натиснуто кнопку '🎂 Найближчі ДН'")
            elif text == "🔕 Вимкнути нагадування":
                await unset_reminder(update, context)
                logger.info("✅ Натиснуто кнопку '🔕 Вимкнути нагадування'")
            elif text == "🔔 Увімкнути нагадування":
                await set_reminder(update, context)
                logger.info("✅ Натиснуто кнопку '🔔 Увімкнути нагадування'")
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
            elif text == "📤 Поділитися новим":
                await share_latest_video(update, context)
                logger.info("✅ Натиснуто кнопку '📤 Поділитися новим'")
            elif text == "📤 Поділитися популярним":
                await share_popular_video(update, context)
                logger.info("✅ Натиснуто кнопку '📤 Поділитися популярним'")
            elif text == "🏆 Топ-10 відео":
                # Скидаємо сторінку до 0 при новому виклику команди
                context.user_data["top_10_page"] = 0
                await top_10_videos_command(update, context)
                logger.info("✅ Натиснуто кнопку '🏆 Топ-10 відео'")
            elif text == "🔔 Увімкнути сповіщення":
                await toggle_video_notifications(update, context, True)
                logger.info("✅ Натиснуто кнопку '🔔 Увімкнути сповіщення'")
            elif text == "🔕 Вимкнути сповіщення":
                await toggle_video_notifications(update, context, False)
                logger.info("✅ Натиснуто кнопку '🔕 Вимкнути сповіщення'")
            elif text == "🔙 Головне меню":
                if chat_type == "private":
                    await show_main_menu(update, context)
            elif text == "🔙 Адмін меню":
                if await is_admin(update.effective_user.id):
                    await admin_menu_command(update, context)
                    logger.info("✅ Повернення до адмін меню")
            elif text == "📊 7 днів":
                if await is_admin(update.effective_user.id):
                    context.args = ["7"]
                    await analytics_command(update, context)
                    logger.info("✅ Натиснуто кнопку '📊 7 днів'")
            elif text == "📊 30 днів":
                if await is_admin(update.effective_user.id):
                    context.args = ["30"]
                    await analytics_command(update, context)
                    logger.info("✅ Натиснуто кнопку '📊 30 днів'")
            elif text == "📈 Статистика":
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
                    logger.info("✅ Натиснуто кнопку '📈 Статистика'")
            elif text == "🗑️ Видалити повідомлення":
                if await is_admin(update.effective_user.id):
                    await delete_messages(update, context)
                    logger.info("✅ Виконано команду '🗑️ Видалити повідомлення'")
            elif text == "🗑️ Видалити день":
                if await is_admin(update.effective_user.id):
                    await delete_messages(update, context)
                    logger.info("✅ Виконано команду '🗑️ Видалити день'")
            elif text == "🗑️ Видалити 30 хв":
                if await is_admin(update.effective_user.id):
                    await delete_recent(update, context)
                    logger.info("✅ Виконано команду '🗑️ Видалити за 30 хв'")
            elif text == "👤 Користувачі":
                if await is_admin(update.effective_user.id):
                    await users_list_command(update, context)
                    logger.info("✅ Натиснуто кнопку '👤 Користувачі'")
            elif text == "💬 Чати":
                if await is_admin(update.effective_user.id):
                    await group_chats_list_command(update, context)
                    logger.info("✅ Натиснуто кнопку '💬 Чати'")
            elif text == "📅 Примусово розклад":
                if await is_admin(update.effective_user.id):
                    await force_daily_reminder_command(update, context)
                    logger.info("✅ Натиснуто кнопку '📅 Примусово розклад'")
            elif text == "📅 Розклад":
                if await is_admin(update.effective_user.id):
                    await force_daily_reminder_command(update, context)
                    logger.info("✅ Натиснуто кнопку '📅 Розклад'")
            elif text == "⏰ Примусово нагадування":
                if await is_admin(update.effective_user.id):
                    await force_hourly_reminder_command(update, context)
                    logger.info("✅ Натиснуто кнопку '⏰ Примусово нагадування'")
            elif text == "⏰ Нагадування":
                if await is_admin(update.effective_user.id):
                    await force_hourly_reminder_command(update, context)
                    logger.info("✅ Натиснуто кнопку '⏰ Нагадування'")
            elif text == "🎂 Примусово ДН":
                if await is_admin(update.effective_user.id):
                    await force_birthday_command(update, context)
                    logger.info("✅ Натиснуто кнопку '🎂 Примусово ДН'")
            elif text == "🎂 ДН":
                if await is_admin(update.effective_user.id):
                    await force_birthday_command(update, context)
                    logger.info("✅ Натиснуто кнопку '🎂 ДН'")
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
            elif text == "Помічник":
                await redirect_to_private(update, context)
                logger.info("✅ Натиснуто кнопку 'Помічник' у групі")
            elif text == "🎵 Ноти" and chat_type == "private":
                await show_notes_menu(update, context)
                logger.info("✅ Натиснуто кнопку '🎵 Ноти'")
            elif text == "📋 Всі ноти" and chat_type == "private":
                await show_all_notes(update, context)
                logger.info("✅ Натиснуто кнопку '📋 Всі ноти'")

            elif text == "🔤 За назвою" and chat_type == "private":
                await show_all_notes(update, context)
                logger.info("✅ Натиснуто кнопку '🔤 За назвою'")

            elif text == "🔍 За ключовим словом" and chat_type == "private":
                message = await update.message.reply_text(
                    "🔍 *Введи слово для пошуку нот* ⬇️", parse_mode="Markdown"
                )
                save_bot_message(chat_id, message.message_id, "general")
                context.user_data["awaiting_keyword"] = True
                logger.info("✅ Натиснуто кнопку '🔍 За ключовим словом'")
            elif text == "➡️ Ще результати" and chat_type == "private":
                await search_notes(
                    update,
                    context,
                    keyword=context.user_data.get("last_search_keyword"),
                    next_page=True,
                )
                logger.info("✅ Показано наступні результати пошуку нот")
            elif text == "🔙 Меню нот" and chat_type == "private":
                await show_notes_menu(update, context)
                logger.info("✅ Повернення до меню нот")

        # Обробка лише тексту, який не пов’язаний із нотами або стандартними командами
        elif context.user_data.get("awaiting_keyword") and chat_type == "private":
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
                reminder_button = KeyboardButton("🔕 Вимкнути нагадування")
            else:
                reminder_button = KeyboardButton("🔔 Увімкнути нагадування")

            keyboard = [
                [KeyboardButton("📋 Розклад подій")],
                [KeyboardButton("🕒 Події на сьогодні"), KeyboardButton("🎂 Найближчі ДН")],
                [reminder_button],
                [KeyboardButton("🔙 Головне меню")],
            ]
            menu_text = SCHEDULE_MENU_TEXT_PRIVATE
        else:
            keyboard = [
                [KeyboardButton("📋 Розклад подій")],
                [KeyboardButton("🕒 Події на сьогодні"), KeyboardButton("🎂 Найближчі ДН")],
                [KeyboardButton("🔙 Головне меню")],
            ]
            menu_text = SCHEDULE_MENU_TEXT_GROUP
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
        [KeyboardButton("📅 Розклад"), KeyboardButton("🎵 Ноти")],
        [KeyboardButton("▶️ YouTube"), KeyboardButton("🌐 Соцмережі")],
        [KeyboardButton("📝 Відгуки"), KeyboardButton("ℹ️ Допомога")],
    ]
    # Додаємо кнопку "⚙️ Меню адміністратора" для адміністраторів
    if await is_admin(user_id):
        keyboard.append([KeyboardButton("⚙️ Меню адміністратора")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_add_user(update, context)
    query = update.callback_query
    from .youtube_menu import top_10_videos_command
    await query.answer()
    data = query.data

    if data == "redirect_private":
        await redirect_to_private(update, context)
        logger.info("✅ Натиснуто кнопку 'Помічник' у групі")
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



__all__ = [
    "start",
    "show_main_menu",
    "show_group_menu",
    "feedback_command",
    "text_menu_handler",
    "button_click",
    "redirect_to_private",
    "show_schedule_menu",

]
