# feedback_handler.py

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters
from utils.logger import logger
from database import set_value, get_value
import json
from datetime import datetime
import os

# Стани розмови
FEEDBACK_TEXT = 0


async def start_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Початок процесу надання відгуку
    """
    logger.info("🔄 Початок процесу надання відгуку")

    await update.message.reply_text(
        "📝 *Напишіть нам відгук:*\n\n"
        "Це допоможе нам краще зрозуміти ваші потреби та покращити сервіс.",
        parse_mode="Markdown",
    )

    return FEEDBACK_TEXT


async def handle_feedback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обробка текстового відгуку
    """
    user = update.effective_user
    feedback_text = update.message.text

    # Зберігаємо відгук
    try:
        # Отримуємо поточні відгуки
        feedback_history = get_value("feedback_history") or "{}"
        feedback_data = json.loads(feedback_history)

        # Додаємо новий відгук
        if str(user.id) not in feedback_data:
            feedback_data[str(user.id)] = []

        feedback_data[str(user.id)].append(
            {
                "text": feedback_text,
                "date": datetime.now().isoformat(),
                "username": user.username or "Unknown",
            }
        )

        # Зберігаємо оновлені дані
        set_value("feedback_history", json.dumps(feedback_data))

        # Надсилаємо відгук адміністратору
        admin_id = os.getenv("ADMIN_CHAT_ID")
        if admin_id:
            admin_message = (
                f"📝 *Новий відгук від користувача:*\n"
                f"👤 Користувач: {user.username or 'Unknown'}\n"
                f"🆔 ID: {user.id}\n"
                f"📝 Текст: {feedback_text}"
            )
            await context.bot.send_message(
                chat_id=admin_id, text=admin_message, parse_mode="Markdown"
            )

        await update.message.reply_text(
            "✅ Дякуємо за ваш відгук! Ми обов'язково врахуємо вашу думку.",
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"❌ Помилка при збереженні відгуку: {e}")
        await update.message.reply_text(
            "❌ Виникла помилка при збереженні відгуку. Спробуйте пізніше.",
            parse_mode="Markdown",
        )

    return ConversationHandler.END


async def show_my_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Показує історію відгуків користувача
    """
    user_id = str(update.effective_user.id)

    try:
        feedback_history = get_value("feedback_history") or "{}"
        feedback_data = json.loads(feedback_history)

        if user_id not in feedback_data or not feedback_data[user_id]:
            await update.message.reply_text(
                "📝 *У вас поки немає відгуків*", parse_mode="Markdown"
            )
            return

        # Формуємо повідомлення з відгуками
        message = "📋 *Ваші відгуки:*\n\n"
        for i, feedback in enumerate(feedback_data[user_id], 1):
            date = datetime.fromisoformat(feedback["date"]).strftime("%d.%m.%Y %H:%M")
            message += f"{i}. {date}\n{feedback['text']}\n\n"

        await update.message.reply_text(message, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"❌ Помилка при показі відгуків: {e}")
        await update.message.reply_text(
            "❌ Виникла помилка при отриманні відгуків. Спробуйте пізніше.",
            parse_mode="Markdown",
        )


def get_feedback_handlers():
    """
    Повертає обробники для системи відгуків
    """
    return [
        ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex("^📩 Надіслати відгук$"), start_feedback)
            ],
            states={
                FEEDBACK_TEXT: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, handle_feedback_text
                    )
                ]
            },
            fallbacks=[],
            name="feedback_conversation",
        ),
        MessageHandler(filters.Regex("^📋 Мої відгуки$"), show_my_feedback),
    ]


__all__ = ["get_feedback_handlers"]
