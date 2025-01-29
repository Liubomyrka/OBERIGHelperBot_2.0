#start_handler.py
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from utils.logger import logger
from utils.calendar_utils import get_latest_youtube_video


# 🛡️ Обробник команди /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда /start для особистих і групових чатів.
    """
    logger.info("🔄 Виконання команди: /start")

    try:
        if update.effective_chat.type == "private":
            # Використовуємо функцію show_main_menu для відображення меню
            await show_main_menu(update, context)

            # Детальний опис функціоналу
            await update.message.reply_text(
                "👋 *Вітаю! Я OBERIG Bot – ваш надійний помічник у хорових подіях.* 🎶\n\n"
                "📚 *Що я вмію:*\n"
                "✅ Надавати актуальний розклад подій.\n"
                "✅ Надсилати нагадування про важливі події.\n"
                "✅ Забезпечувати доступ до соціальних сторінок хору.\n"
                "✅ Дозволяти надсилати зворотний зв'язок.\n"
                "✅ Показувати найновіші відео з YouTube.\n\n"
                "🔑 *Доступні команди:*\n"
                "`/rozklad` – Переглянути розклад подій.\n"
                "`/reminder_on` – Увімкнути нагадування.\n"
                "`/reminder_off` – Вимкнути нагадування.\n"
                "`/latest_video` – Переглянути останнє відео.\n"
                "`/feedback` – Надіслати відгук.\n\n"
                "ℹ️ *Скористайтесь кнопками або командами для продовження.* 🚀",
                parse_mode="Markdown"
            )
            logger.info("✅ Команда /start виконана успішно у приватному чаті.")
        else:
            # 🛡️ Відповідь у груповому чаті
            keyboard = [
                [InlineKeyboardButton("🗨️ Відкрити приватний чат", url="https://t.me/OBERIGHelperBot")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "👋 *Вітаю! Я OBERIG Bot.*\n\n"
                "Цей бот працює ефективніше у приватному чаті.\n"
                "👉 [Перейдіть у приватний чат зі мною](https://t.me/OBERIGHelperBot).",
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            logger.info("✅ Команда /start виконана успішно у груповому чаті.")
    except Exception as e:
        logger.error(f"❌ Помилка у команді /start: {e}")
        await update.message.reply_text("❌ Виникла помилка при виконанні команди /start.")


# 🛡️ Оновлене меню для приватного чату
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Відображає головне меню користувачеві у приватному чаті.
    """
    logger.info("🔄 Відображення головного меню для користувача.")

    try:
        keyboard = [
            [KeyboardButton("📅 Розклад"), KeyboardButton("ℹ️ Допомога")],
            [KeyboardButton("🔔 Увімкнути нагадування"), KeyboardButton("🔕 Вимкнути нагадування")],
            [KeyboardButton("🌐 Соцмережі"), KeyboardButton("▶️ Останнє відео")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

        await update.message.reply_text(
            "🛠️ *Головне меню*\n\n"
            "Виберіть одну з доступних опцій для продовження:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        logger.info("✅ Головне меню успішно відображено.")
    except Exception as e:
        logger.error(f"❌ Помилка при відображенні головного меню: {e}")
        await update.message.reply_text("❌ Виникла помилка при відображенні меню.")


# 🛡️ Оновлене меню у груповому чаті
async def show_group_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Відображає підказку для групових чатів з переходом до приватного чату.
    """
    logger.info("🔄 Відображення меню у груповому чаті.")

    try:
        keyboard = [
            [InlineKeyboardButton("🗨️ Перейти до приватного чату", url="https://t.me/OBERIGHelperBot")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "❗ *Ця команда доступна лише у приватних повідомленнях.*\n"
            "👉 [Перейдіть у приватний чат зі мною](https://t.me/OBERIGHelperBot).",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        logger.info("✅ Меню для групового чату успішно відображено.")
    except Exception as e:
        logger.error(f"❌ Помилка при відображенні групового меню: {e}")
        await update.message.reply_text("❌ Виникла помилка при відображенні меню у груповому чаті.")


# 🛡️ Обробник команди /latest_video
async def latest_video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Відображає останнє відео зі списку YouTube.
    """
    logger.info("🔄 Виконання команди: /latest_video")
    try:
        video_url = get_latest_youtube_video()
        if video_url:
            await update.message.reply_text(
                f"▶️ *Останнє відео хору OBERIG:*\n\n"
                f"🎵 [Переглянути відео]({video_url})",
                parse_mode="Markdown"
            )
            logger.info("✅ Команда /latest_video виконана успішно.")
        else:
            await update.message.reply_text("⚠️ Наразі немає доступного відео в списку.")
            logger.warning("⚠️ Наразі немає доступного відео в списку.")
    except Exception as e:
        logger.error(f"❌ Помилка у виконанні команди /latest_video: {e}")
        await update.message.reply_text("❌ Виникла помилка при отриманні відео.")


# 🛡️ Обробник команди /feedback
import os

async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Збирає зворотний зв'язок від користувача.
    """
    logger.info("🔄 Виконання команди: /feedback")

    user = update.effective_user
    feedback_text = ' '.join(context.args) if context.args else None

    # Альтернативний метод отримання тексту
    if not feedback_text and update.message.text:
        feedback_text = update.message.text.replace('/feedback', '').strip()

    if not feedback_text:
        await update.message.reply_text(
            "📝 *Будь ласка, надішліть ваш відгук після команди.*\n\n"
            "📌 *Приклад:* `/feedback Дуже задоволений роботою бота!`",
            parse_mode="Markdown"
        )
        logger.warning("⚠️ Відгук не містить тексту.")
        return

    try:
        admin_chat_id = os.getenv("ADMIN_CHAT_ID")
        if not admin_chat_id:
            raise ValueError("❌ ADMIN_CHAT_ID не вказано у файлі .env")

        feedback_message = (
            f"📩 *Новий відгук від користувача:*\n\n"
            f"👤 Ім'я: {user.first_name} {user.last_name or ''}\n"
            f"🆔 ID: {user.id}\n"
            f"💬 Відгук: {feedback_text}"
        )
        await context.bot.send_message(chat_id=admin_chat_id, text=feedback_message, parse_mode="Markdown")
        await update.message.reply_text("✅ *Ваш відгук успішно надіслано. Дякуємо!*", parse_mode="Markdown")
        logger.info(f"✅ Відгук надіслано адміністратору: {feedback_text}")
    except Exception as e:
        logger.error(f"❌ Помилка при надсиланні відгуку: {e}")
        await update.message.reply_text("❌ Виникла помилка при надсиланні відгуку. Спробуйте пізніше.")


__all__ = [
    'start',
    'show_main_menu',
    'latest_video_command',
    'feedback_command'
]
