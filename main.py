import os
import asyncio
import nest_asyncio
import httpx
from telegram import (
    Update,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeAllGroupChats,
    BotCommandScopeChat,
    BotCommand,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    JobQueue,
)
from handlers.start_handler import (
    start,
    show_main_menu,
    show_group_menu,
    feedback_command,
    text_menu_handler,
    button_click,
    auto_add_user,
    redirect_to_private,
    category_callback,  # Added import for category_callback
    rating_callback,    # Added import for rating_callback
)
from handlers.youtube_menu import (
    latest_video_command,
    show_youtube_menu,
    most_popular_video_command,
    top_10_videos_command,
)

from handlers.notes_menu import show_notes_menu, get_sheet_command
from handlers.help_handler import help_command
from handlers.schedule_handler import (
    schedule_command,
    upcoming_birthdays_command,
    event_details_callback,
    performance_schedule_command,
)
from handlers.reminder_handler import (
    schedule_event_reminders,
    set_reminder,
    unset_reminder,
    send_daily_reminder,
    send_event_reminders,
    schedule_birthday_greetings,
    create_birthday_greetings_table,
    startup_daily_reminder,
)
from utils.logger import logger
from database import (
    init_db,
    migrate_database,
    get_value,
    set_value,
    update_user_list,
)
from handlers.share_handler import share_latest_video, share_popular_video
from handlers.notification_handler import (
    check_and_notify_new_videos,
    toggle_video_notifications,
)
from handlers.admin_handler import (
    analytics_command,
    admin_menu_command,
    users_list_command,
    group_chats_list_command,
    is_admin,
    delete_messages,
    delete_recent,
    force_daily_reminder_command,
    force_hourly_reminder_command,
    force_birthday_command,
    force_video_check_command,
)
from utils.analytics import Analytics
from handlers.feedback_handler import get_feedback_handlers
from utils.calendar_utils import (
    get_calendar_events,
    get_today_events,
    get_upcoming_event_reminders,
    get_event_details,
    get_latest_youtube_video,
    get_most_popular_youtube_video,
    check_new_videos,
)
import json
import time
from telegram.error import Conflict, NetworkError
from config import TELEGRAM_TOKEN


async def log_command(command_name: str, success: bool):
    if success:
        logger.info(f"Виконано команду: {command_name}")
    else:
        logger.warning(f"Помилка під час виконання команди: {command_name}")


ERROR_UNKNOWN_COMMAND = (
    "Невідома команда. Скористайтесь доступними кнопками або командою /start."
)
ERROR_PRIVATE_CHAT_ONLY = "Ця команда доступна лише в особистих повідомленнях.\nНапишіть мені в приватний чат."
ERROR_GENERAL = "Виникла помилка. Спробуйте пізніше або зверніться до адміністратора."
ERROR_INTERNAL = "Виникла внутрішня помилка. Адміністратор уже сповіщений."

_last_error_sig: str | None = None
_last_error_ts: float = 0.0
_last_error_count: int = 0

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning("Отримана невідома команда")
    if update.effective_chat.type != "private":
        if update.message:
            await update.message.reply_text(
                ERROR_PRIVATE_CHAT_ONLY, parse_mode="Markdown"
            )
    else:
        await help_command(update, context)
    logger.info("Обробка невідомої команди завершена")


def _summarize_update(update: object) -> str:
    """Повертає стислий опис update без чутливих даних для логів."""
    if not update:
        return "None"
    summary: dict[str, object] = {}
    try:
        chat = getattr(update, "effective_chat", None)
        if chat:
            summary["chat_id"] = getattr(chat, "id", None)
            summary["chat_type"] = getattr(chat, "type", None)
        user = getattr(update, "effective_user", None)
        if user:
            summary["user_id"] = getattr(user, "id", None)
            summary["username"] = getattr(user, "username", None)
        message = getattr(update, "effective_message", None)
        if message:
            summary["message_id"] = getattr(message, "message_id", None)
            if getattr(message, "text", None):
                summary["text_length"] = len(message.text)
            if getattr(message, "caption", None):
                summary["caption_length"] = len(message.caption)
        callback_query = getattr(update, "callback_query", None)
        if callback_query and getattr(callback_query, "data", None):
            summary["callback_data_length"] = len(callback_query.data)
        return json.dumps(summary, ensure_ascii=False)
    except Exception:
        return repr(update)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    global _last_error_sig, _last_error_ts, _last_error_count
    error = context.error

    is_network = isinstance(error, (httpx.ConnectError, NetworkError))
    if is_network:
        sig = f"{type(error).__name__}:{getattr(error, 'args', None)}"
        now_ts = time.time()
        if _last_error_sig == sig and now_ts - _last_error_ts < 60:
            _last_error_count += 1
            logger.warning(
                "Повторна мережева помилка (%s), кількість за хвилину: %d",
                sig,
                _last_error_count,
            )
            return
        _last_error_sig = sig
        _last_error_ts = now_ts
        _last_error_count = 1
        logger.warning("Мережева помилка: %s", sig)
        return

    logger.error(f"Виникла помилка: {error}")
    try:
        import traceback

        tb_list = traceback.format_exception(None, error, error.__traceback__)
        tb_string = "".join(tb_list)
        error_message = (
            f"Виникла помилка під час обробки оновлення:\n"
            f"update = {_summarize_update(update)}\n\n"
            f"error = {context.error}\n\n"
            f"traceback =\n{tb_string}"
        )
        logger.error(error_message)
        if update and hasattr(update, "effective_message") and update.effective_message:
            await update.effective_message.reply_text(ERROR_INTERNAL)
        admin_chat_id = os.getenv("ADMIN_CHAT_ID")
        if admin_chat_id:
            await context.bot.send_message(
                chat_id=admin_chat_id,
                text=f"*Сповіщення про помилку*\n\n{error_message[:3000]}",
                parse_mode="Markdown",
            )
    except Exception as e:
        logger.error(f"Помилка в обробнику помилок: {e}")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "help":
        await help_command(update, context)
    elif query.data.startswith("category_"):
        await category_callback(update, context)
    elif query.data.startswith("rating_"):
        await rating_callback(update, context)
    else:
        await button_click(update, context)


analytics = Analytics()


async def main():
    logger.info("Запуск основного додатка...")

    if not os.path.exists("bot_data.db"):
        logger.info("Файл bot_data.db не знайдено, ініціалізація нової бази...")
        init_db()
    else:
        logger.info("Використовуємо існуючу базу bot_data.db")
    migrate_database()

    group_notifications = get_value("group_notifications_disabled")
    if group_notifications is None:
        set_value("group_notifications_disabled", json.dumps({}))

    group_chats = get_value("group_chats")
    if group_chats is None:
        set_value("group_chats", json.dumps([]))
    else:
        print("Активні групові чати:")
        try:
            parsed_group_chats = json.loads(group_chats)
            if parsed_group_chats:
                for chat in parsed_group_chats:
                    print(
                        f"ID чату: {chat.get('chat_id', 'Невідомо')}, Назва: {chat.get('title', 'Без назви')}"
                    )
            else:
                print("Немає активних групових чатів")
        except json.JSONDecodeError:
            print("Помилка декодування списку групових чатів")

    bot_users = get_value("bot_users")
    if bot_users is None:
        set_value("bot_users", json.dumps([]))
    else:
        users = json.loads(bot_users)
        users_with_reminders = json.loads(get_value("users_with_reminders") or "[]")
        auto_added = []
        for user_id in users:
            if user_id not in users_with_reminders:
                update_user_list("users_with_reminders", user_id, add=True)
                auto_added.append(str(user_id))
        if auto_added:
            logger.info("✅ Автоматично додано %d користувачів до нагадувань за замовчуванням", len(auto_added))
            logger.debug("Додані користувачі до нагадувань: %s", ", ".join(auto_added))

    video_notifications = get_value("video_notifications_disabled")
    if video_notifications is None:
        set_value("video_notifications_disabled", json.dumps({}))

    application = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .build()
    )
    job_queue = application.job_queue
    try:
        bot_url = application.bot.base_url  # e.g. https://api.telegram.org/bot<token>
        if isinstance(bot_url, str) and "/bot" in bot_url:
            host_part, _ = bot_url.split("/bot", 1)
            logger.info("Using Telegram API host: %s", f"{host_part}/bot***")
        else:
            logger.info("Using Telegram API host: %s", bot_url or "unknown")
    except Exception:
        logger.debug("Unable to determine Telegram API URL")

    # Налаштування команд для різних типів чатів
    private_commands = [
        BotCommand("start", "Запустити бота"),
        BotCommand("help", "Показати допомогу"),
        BotCommand("rozklad", "Переглянути розклад подій"),
        BotCommand("performances", "Графік виступів"),
        BotCommand("upcoming_birthdays", "Найближчі дні народження"),
        BotCommand("reminder_on", "Увімкнути нагадування"),
        BotCommand("reminder_off", "Вимкнути нагадування"),
        BotCommand("get_sheet", "Отримати ноти"),
        BotCommand("latest_video", "Останнє відео"),
        BotCommand("most_popular_video", "Найпопулярніше відео"),
        BotCommand("top_10_videos", "Топ-10 відео"),  # Оновлюємо
        BotCommand("feedback", "Меню відгуків"),
        BotCommand("share_latest", "Поділитися останнім відео"),
        BotCommand("share_popular", "Поділитися популярним відео"),
        BotCommand("video_notifications_on", "Увімкнути сповіщення про відео"),
        BotCommand("video_notifications_off", "Вимкнути сповіщення про відео"),
        BotCommand("analytics", "Аналітика (адмін)"),
        BotCommand("admin_menu", "Меню адміністратора"),
        BotCommand("users_list", "Список користувачів (адмін)"),
        BotCommand("group_chats_list", "Список груп (адмін)"),
        BotCommand("delete_messages", "Видалити повідомлення (адмін)"),
        BotCommand("delete_recent", "Видалити за 30 хв (адмін)"),
        BotCommand("force_daily_reminder", "Примусово надіслати розклад"),
        BotCommand("force_hourly_reminder", "Примусово нагадати про події"),
        BotCommand("force_birthday", "Примусово вітати з ДН"),
        BotCommand("force_video_check", "Примусово перевірити нові відео"),
    ]

    group_commands = [BotCommand("start", "Запустити бота")]

    admin_commands = [
        BotCommand("start", "Запустити бота"),
        BotCommand("admin_menu", "Меню адміністратора"),
        BotCommand("analytics", "Аналітика"),
        BotCommand("users_list", "Список користувачів"),
        BotCommand("group_chats_list", "Список груп"),
        BotCommand("delete_messages", "Видалити повідомлення"),
        BotCommand("delete_recent", "Видалити за 30 хв (адмін)"),
        BotCommand("force_daily_reminder", "Примусово розклад"),
        BotCommand("force_hourly_reminder", "Примусово нагадування"),
        BotCommand("force_birthday", "Примусово ДН"),
        BotCommand("force_video_check", "Примусово відео"),
    ]

    try:
        # Видаляємо старі команди
        await application.bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())
        logger.info("Видалено команди для приватних чатів")
        await application.bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())
        logger.info("Видалено всі команди для групових чатів")

        admin_id = os.getenv("ADMIN_CHAT_ID")
        if admin_id:
            await application.bot.delete_my_commands(
                scope=BotCommandScopeChat(chat_id=int(admin_id))
            )
            logger.info(f"Видалено команди для адміністратора (chat_id: {admin_id})")
        else:
            logger.warning("ADMIN_CHAT_ID не вказано у файлі .env")

        # Встановлюємо нові команди
        await application.bot.set_my_commands(
            commands=private_commands, scope=BotCommandScopeAllPrivateChats()
        )
        logger.info("Встановлено команди для приватних чатів")
        await application.bot.set_my_commands(
            commands=group_commands, scope=BotCommandScopeAllGroupChats()
        )
        logger.info("Встановлено команди для всіх групових чатів (лише /start)")
        if admin_id:
            await application.bot.set_my_commands(
                commands=admin_commands,
                scope=BotCommandScopeChat(chat_id=int(admin_id)),
            )
            logger.info(f"Встановлено команди для адміністратора (chat_id: {admin_id})")

        logger.info("Успішно налаштовано команди з меню Telegram")
    except Exception as e:
        logger.error(f"Помилка при налаштуванні команд: {e}")
        await application.bot.send_message(
            chat_id=os.getenv("ADMIN_CHAT_ID", "0"), text=f"❌ Помилка: {str(e)}"
        )

    feedback_handlers = get_feedback_handlers()
    for handler in feedback_handlers:
        application.add_handler(handler)

    handlers = [
        CommandHandler("start", start),
        CommandHandler("help", help_command, filters=filters.ChatType.PRIVATE),
        CommandHandler("rozklad", schedule_command, filters=filters.ChatType.PRIVATE),
        CommandHandler(
            "performances",
            performance_schedule_command,
            filters=filters.ChatType.PRIVATE,
        ),
        CommandHandler(
            "upcoming_birthdays",
            upcoming_birthdays_command,
            filters=filters.ChatType.PRIVATE,
        ),
        CommandHandler("reminder_on", set_reminder, filters=filters.ChatType.PRIVATE),
        CommandHandler(
            "reminder_off", unset_reminder, filters=filters.ChatType.PRIVATE
        ),
        CommandHandler(
            "get_sheet",
            get_sheet_command,
            filters=filters.ChatType.PRIVATE,
        ),
        CommandHandler(
            "latest_video", latest_video_command, filters=filters.ChatType.PRIVATE
        ),
        CommandHandler(
            "most_popular_video",
            most_popular_video_command,
            filters=filters.ChatType.PRIVATE,
        ),
        CommandHandler(
            "top_10_videos", top_10_videos_command, filters=filters.ChatType.PRIVATE  # Оновлюємо
        ),
        CommandHandler("feedback", feedback_command, filters=filters.ChatType.PRIVATE),
        CommandHandler(
            "share_latest", share_latest_video, filters=filters.ChatType.PRIVATE
        ),
        CommandHandler(
            "share_popular", share_popular_video, filters=filters.ChatType.PRIVATE
        ),
        CommandHandler(
            "video_notifications_on",
            lambda update, context: toggle_video_notifications(update, context, True),
            filters=filters.ChatType.PRIVATE,
        ),
        CommandHandler(
            "video_notifications_off",
            lambda update, context: toggle_video_notifications(update, context, False),
            filters=filters.ChatType.PRIVATE,
        ),
        CommandHandler(
            "analytics", analytics_command, filters=filters.ChatType.PRIVATE
        ),
        CommandHandler(
            "admin_menu", admin_menu_command, filters=filters.ChatType.PRIVATE
        ),
        CommandHandler(
            "users_list", users_list_command, filters=filters.ChatType.PRIVATE
        ),
        CommandHandler(
            "group_chats_list",
            group_chats_list_command,
            filters=filters.ChatType.PRIVATE,
        ),
        CommandHandler(
            "delete_messages", delete_messages, filters=filters.ChatType.PRIVATE
        ),
        CommandHandler(
            "delete_recent", delete_recent, filters=filters.ChatType.PRIVATE
        ),
        CommandHandler(
            "force_daily_reminder",
            force_daily_reminder_command,
            filters=filters.ChatType.PRIVATE,
        ),
        CommandHandler(
            "force_hourly_reminder",
            force_hourly_reminder_command,
            filters=filters.ChatType.PRIVATE,
        ),
        CommandHandler(
            "force_birthday",
            force_birthday_command,
            filters=filters.ChatType.PRIVATE,
        ),
        CommandHandler(
            "force_video_check",
            force_video_check_command,
            filters=filters.ChatType.PRIVATE,
        ),
        MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, text_menu_handler),
    ]

    for handler in handlers:
        if isinstance(handler, CommandHandler):
            handler.callback = log_and_execute_command(handler.callback)
        application.add_handler(handler)

    application.add_handler(
        CallbackQueryHandler(event_details_callback, pattern=r"^event_")
    )
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_error_handler(error_handler)

    schedule_event_reminders(job_queue, initial_delay=15, daily_delay=3600)
    job_queue.run_once(
        startup_daily_reminder,
        when=30,
        job_kwargs={"misfire_grace_time": 60},
    )
    job_queue.run_once(check_and_notify_new_videos, when=45)
    job_queue.run_repeating(check_and_notify_new_videos, interval=1800, first=1800)

    create_birthday_greetings_table()
    schedule_birthday_greetings(job_queue)

    await application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Бот запущено успішно!")


def log_and_execute_command(handler):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if update.effective_user and update.message and update.message.text:
                command = update.message.text.split()[0].replace("/", "").split("@")[0]
                await analytics.log_command(update.effective_user.id, command)
            return await handler(update, context)
        except Exception as e:
            logger.error(f"Помилка в декораторі log_and_execute_command: {e}")
            return await handler(update, context)

    return wrapper


if __name__ == "__main__":
    nest_asyncio.apply()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    delay = 1
    max_delay = 60

    while True:
        try:
            loop.run_until_complete(main())
            break
        except httpx.ConnectError as connect_error:
            url = getattr(getattr(connect_error, "request", None), "url", "unknown")
            logger.error(f"Connection error while requesting {url}: {connect_error}")
            logger.info("Reinitializing client and retrying...")
            logger.info(f"Retrying in {delay} seconds...")
            time.sleep(delay)
            delay = min(delay * 2, max_delay)
        except Conflict as conflict_error:
            logger.error(f"Bot Conflict Error: {conflict_error}")
            logger.error("Ensure only one bot instance is running. Waiting and retrying...")
            time.sleep(5)
        except Exception as e:
            logger.error(f"Unexpected error during bot startup: {e}")
            raise
