from telegram import Update
from telegram.ext import ContextTypes
from utils.logger import logger
from database import (
    get_value,
    set_value,
    add_group_to_list,
)
import json


async def auto_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ensure user and group are tracked and reminders enabled."""
    try:
        user_id = str(update.effective_user.id)
        chat_type = update.effective_chat.type
        bot_users_str = get_value("bot_users")
        bot_users = json.loads(bot_users_str) if bot_users_str else []
        bot_users_info_str = get_value("bot_users_info")
        bot_users_info = json.loads(bot_users_info_str) if bot_users_info_str else {}

        # Add user if not already stored
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

        # Automatically enable reminders for private chats
        if chat_type == "private":
            users_with_reminders_str = get_value("users_with_reminders")
            users_with_reminders = (
                json.loads(users_with_reminders_str) if users_with_reminders_str else []
            )
            if user_id not in users_with_reminders:
                users_with_reminders.append(user_id)
                set_value("users_with_reminders", json.dumps(users_with_reminders))
                logger.info(f"✅ Автоматично додано користувача {user_id} до нагадувань")

        # Register groups
        if chat_type in ["group", "supergroup"]:
            add_group_to_list(
                str(update.effective_chat.id),
                update.effective_chat.title or "Невідома група",
            )

        logger.info(f"✅ Користувач {user_id} оброблений при взаємодії")
    except Exception as e:
        logger.error(f"❌ Помилка при автоматичному додаванні користувача: {e}")


__all__ = ["auto_add_user"]
