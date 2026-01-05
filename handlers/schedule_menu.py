from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from utils.logger import logger
from database import get_value, save_bot_message
from .user_utils import auto_add_user
import json

SCHEDULE_MENU_TEXT_PRIVATE = """📅 *Меню розкладу*

Виберіть одну з опцій:
📋 - Переглянути розклад подій
🎤 - Графік виступів
🕒 - Переглянути події на сьогодні
🎂 - Переглянути найближчі дні народження

🔔 Нагадування (за замовчуванням увімкнені):
- 🔕 Вимкнути нагадування - припинити отримувати сповіщення за годину до події
- 🔔 Увімкнути нагадування - відновити сповіщення за годину до події"""

SCHEDULE_MENU_TEXT_GROUP = """📅 *Меню розкладу*

Виберіть одну з опцій:
📋 - Переглянути розклад подій
🎤 - Графік виступів
🕒 - Переглянути події на сьогодні
🎂 - Переглянути найближчі дні народження

🔔 Нагадування завжди увімкнені для групових чатів і не можуть бути вимкнені."""


async def show_schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_add_user(update, context)
    logger.info("🔄 Спроба відобразити меню розкладу")
    try:
        if update.effective_chat.type == "private":
            users_with_reminders_str = get_value("users_with_reminders")
            users_with_reminders = json.loads(users_with_reminders_str) if users_with_reminders_str else []
            user_id = str(update.effective_user.id)
            if user_id in users_with_reminders:
                reminder_button = KeyboardButton("🔕 Вимкнути нагадування")
            else:
                reminder_button = KeyboardButton("🔔 Увімкнути нагадування")

            keyboard = [
                [KeyboardButton("📋 Розклад подій"), KeyboardButton("🎤 Графік виступів")],
                [KeyboardButton("🕒 Події на сьогодні"), KeyboardButton("🎂 Найближчі ДН")],
                [reminder_button],
                [KeyboardButton("🔙 Головне меню")],
            ]
            menu_text = SCHEDULE_MENU_TEXT_PRIVATE
        else:
            keyboard = [
                [KeyboardButton("📋 Розклад подій"), KeyboardButton("🎤 Графік виступів")],
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


__all__ = ["show_schedule_menu"]
