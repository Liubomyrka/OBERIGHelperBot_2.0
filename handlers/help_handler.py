# help_handler.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.logger import logger


# 🛡️ Обробник команди /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда /help доступна лише в особистих чатах.
    """
    logger.info("🔄 Виконання команди: /help")
    if update.effective_chat.type != "private":
        logger.warning("⚠️ Команда /help виконується лише в особистих чатах.")
        await update.message.reply_text(
            "❗ Ця команда доступна лише в особистих повідомленнях. "
            "[Напишіть мені в приватний чат](https://t.me/OBERIGHelperBot).",
            parse_mode="Markdown"
        )
        return

    try:
        keyboard = [
            [InlineKeyboardButton("🏠 Start", callback_data='start')],
            [InlineKeyboardButton("📋 Розклад подій", callback_data='rozklad')],
            [InlineKeyboardButton("🔔 Увімкнути нагадування", callback_data='reminder_on')],
            [InlineKeyboardButton("🔕 Вимкнути нагадування", callback_data='reminder_off')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "📋 *Список доступних команд:*\n"
            "Натисніть на кнопку, щоб виконати команду. 🚀",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        logger.info("✅ Команда /help виконана успішно")
    except Exception as e:
        logger.error(f"❌ Помилка у команді /help: {e}")
        await update.message.reply_text("❌ Виникла помилка при виконанні команди /help.")
