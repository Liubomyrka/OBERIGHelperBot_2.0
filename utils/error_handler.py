# error_handler.py

from telegram import Update
from telegram.ext import ContextTypes
from utils.logger import logger


# 🛡️ Глобальний обробник помилок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обробка глобальних помилок у боті.
    """
    error_message = f"❌ Виникла помилка: {context.error}"
    logger.error(msg=error_message, exc_info=context.error)

    # Перевірка, чи доступний об'єкт message
    if update and hasattr(update, "message") and update.message:
        await update.message.reply_text(
            "❌ Виникла внутрішня помилка. Можливі причини:\n"
            "1️⃣ Помилка з'єднання з сервером.\n"
            "2️⃣ Некоректні дані або команда.\n"
            "3️⃣ Внутрішня помилка бота.\n\n"
            "🔄 Будь ласка, спробуйте ще раз або зверніться до адміністратора."
        )
    elif update and hasattr(update, "callback_query") and update.callback_query:
        await update.callback_query.answer(
            "❌ Виникла внутрішня помилка. Спробуйте ще раз або зверніться до адміністратора.",
            show_alert=True,
        )

    # Повідомлення адміністратору (за потреби, додайте ID адміністратора)
    admin_chat_id = "@LiubomyrK"  # Змініть на актуальний ID адміністратора
    try:
        await context.bot.send_message(
            chat_id=admin_chat_id,
            text=f"🚨 *Критична помилка в боті!*\n\n{error_message}",
        )
    except Exception as e:
        logger.error(f"❌ Не вдалося надіслати повідомлення адміністратору: {e}")
