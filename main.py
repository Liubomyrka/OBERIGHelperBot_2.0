# main.py

import os
import asyncio
import nest_asyncio
from dotenv import load_dotenv
from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from handlers.start_handler import (
    start, 
    show_main_menu,
    latest_video_command,
    feedback_command,
)
from handlers.help_handler import help_command
from handlers.schedule_handler import (
    schedule_command,
    set_reminder,
    unset_reminder,
    event_details_callback,
)
from handlers.reminder_handler import schedule_event_reminders
from utils.logger import logger
from database import init_db
from handlers.birthday_handler import birthday_command, clear_messages


# 🛡️ Завантаження змінних середовища
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не знайдено у файлі .env")
CALENDAR_ID = os.getenv("CALENDAR_ID")


# 🛡️ Логування виконання команд
async def log_command(command_name: str, success: bool):
    if success:
        logger.info(f"✅ Виконано команду: {command_name}")
    else:
        logger.warning(f"❌ Помилка під час виконання команди: {command_name}")


# 🛡️ Обробник невідомих команд
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning("⚠️ Отримана невідома команда")
    if update.effective_chat.type != "private":
        if update.message:
            await update.message.reply_text(
                "❗ Ця команда доступна лише в особистих повідомленнях. "
                "[Напишіть мені в приватний чат](https://t.me/OBERIGHelperBot).",
                parse_mode="Markdown"
            )
    else:
        await help_command(update, context)
    logger.info("✅ Обробка невідомої команди завершена")


# 🛡️ Глобальний обробник помилок
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ Виникла помилка: {context.error}")
    if update and hasattr(update, 'message') and update.message:
        await update.message.reply_text(
            "❌ Виникла внутрішня помилка. Адміністратор уже сповіщений."
        )


# 🛡️ Обробник текстових кнопок нижнього меню
async def text_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    logger.info(f"🔄 Обробка текстової кнопки: {text}")

    try:
        if text == "📅 Розклад":
            await schedule_command(update, context)
        elif text == "ℹ️ Допомога":
            await help_command(update, context)
        elif text == "🔔 Увімкнути нагадування":
            await set_reminder(update, context)
        elif text == "🔕 Вимкнути нагадування":
            await unset_reminder(update, context)
        elif text in ["/latest_video", "▶️ Останнє відео"]:
            await latest_video_command(update, context)
        elif text == "🌐 Соцмережі":
            await update.message.reply_text(
                "🌐 *Офіційні сторінки хору OBERIG:*\n\n"
                "📘 [Facebook](https://www.facebook.com/profile.php?id=100094519583534)\n"
                "▶️ [YouTube](https://youtube.com/playlist?list=PLEkdnztUMQ7-05r94OMzHyCVMCXvkgrFn&si=YmlcTWci7Iyfsmss)",
                parse_mode="Markdown"
            )
            logger.info("✅ Натиснуто кнопку '🌐 Соцмережі'")
        elif text.startswith("/feedback"):
            await feedback_command(update, context)
        elif text.startswith("/birthday"):
            await birthday_command(update, context)
        elif text.startswith("/clear"):
            await clear_messages(update, context)
        else:
            logger.warning(f"⚠️ Невідома текстова команда: {text}")
            await update.message.reply_text("❌ Невідома команда. Скористайтесь доступними кнопками.")
    except Exception as e:
        logger.error(f"❌ Помилка у text_menu_handler: {e}")
        await update.message.reply_text("❌ Виникла помилка під час обробки команди.")



# 🛡️ Обробник для кнопок InlineKeyboard
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    try:
        if data == 'rozklad':
            await schedule_command(update, context)
        elif data == 'reminder_on':
            await set_reminder(update, context)
        elif data == 'reminder_off':
            await unset_reminder(update, context)
        elif data == 'help':
            await help_command(update, context)
        elif data.startswith("event_details_"):
            await event_details_callback(update, context)
        else:
            if query.message:
                await query.message.reply_text("❌ Невідомий запит.")
            logger.warning(f"⚠️ Отримано невідомий запит: {data}")
    except Exception as e:
        logger.error(f"❌ Помилка у button_handler: {e}")
        if query.message:
            await query.message.reply_text("❌ Виникла помилка під час обробки запиту.")


# 🛡️ Встановлення команд меню
async def set_bot_commands(application):
    private_commands = [
        BotCommand("start", "👋 Вітання та інструкція"),
        BotCommand("rozklad", "📅 Розклад подій"),
        BotCommand("reminder_on", "🔔 Увімкнути нагадування"),
        BotCommand("reminder_off", "🚫 Вимкнути нагадування"),
        BotCommand("latest_video", "▶️ Останнє відео YouTube"),
        BotCommand("help", "ℹ️ Допомога"),
        BotCommand("feedback", "📩 Надіслати відгук"),
        BotCommand("birthday", "🎉 Вітання з днем народження"),
        BotCommand("clear", "🗑️ Очистити повідомлення"),
    ]
    group_commands = [BotCommand("start", "👋 Вітання та інструкція")]

    await application.bot.set_my_commands(private_commands, scope=BotCommandScopeAllPrivateChats())
    await application.bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())
    logger.info("✅ Команди меню успішно налаштовані для приватних і групових чатів.")


# 🛡️ Основна функція запуску
async def main():
    logger.info("🔄 Запуск основного додатка...")
    
    init_db()  # Ініціалізація бази даних перед запуском бота    
    logger.info("✅ База даних ініціалізована.")
    
    application = ApplicationBuilder().token(TOKEN).build()
    await set_bot_commands(application)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rozklad", schedule_command))
    application.add_handler(CommandHandler("reminder_on", set_reminder))
    application.add_handler(CommandHandler("reminder_off", unset_reminder))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, text_menu_handler))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CommandHandler("latest_video", latest_video_command))
    application.add_handler(CommandHandler("feedback", feedback_command))
    application.add_handler(CommandHandler("birthday", birthday_command))
    application.add_handler(CommandHandler("clear", clear_messages))
    application.add_error_handler(error_handler)

    schedule_event_reminders(application.job_queue)
    await application.run_polling()


# 🛡️ Запуск програми
if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
