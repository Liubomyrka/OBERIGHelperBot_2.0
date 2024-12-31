from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from utils.logger import logger


# 🛡️ Обробник команди /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда /start для особистих і групових чатів.
    """
    logger.info("🔄 Виконання команди: /start")

    try:
        if update.effective_chat.type == "private":
            # 🛡️ Відповідь у особистому чаті з кнопками
            keyboard = [
                [KeyboardButton("📅 Розклад"), KeyboardButton("ℹ️ Допомога")],
                [KeyboardButton("🔔 Увімкнути нагадування"), KeyboardButton("🔕 Вимкнути нагадування")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

            await update.message.reply_text(
                "👋 *Вітаю! Я OBERIG Bot.*\n\n"
                "Я допоможу вам з керуванням розкладом, нагадуваннями та важливими подіями.\n\n"
                "ℹ️ *Скористайтесь кнопками нижче або командами для продовження.* 🚀",
                parse_mode="Markdown",
                reply_markup=reply_markup
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


# 🛡️ Оновлене меню у приватному чаті
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Відображає головне меню користувачеві у приватному чаті.
    """
    logger.info("🔄 Відображення головного меню для користувача.")

    try:
        keyboard = [
            [KeyboardButton("📅 Розклад"), KeyboardButton("ℹ️ Допомога")],
            [KeyboardButton("🔔 Увімкнути нагадування"), KeyboardButton("🔕 Вимкнути нагадування")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

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
