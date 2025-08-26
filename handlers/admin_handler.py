import os
import json
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from utils.logger import logger
from utils.analytics import Analytics
from database import save_bot_message, get_value, set_value, get_cursor
from handlers.reminder_handler import (
    send_daily_reminder,
    send_event_reminders,
    check_birthday_greetings,
)


async def is_admin(user_id: int) -> bool:
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    return str(user_id) == admin_chat_id


async def admin_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Головне меню адміністратора з розділами."""
    logger.info(
        f"🔄 Спроба доступу до меню адміністратора від користувача {update.effective_user.id}"
    )
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        await update.message.reply_text(
            "❌ *Ця команда доступна тільки адміністратору.*", parse_mode="Markdown"
        )
        logger.warning(
            f"⚠️ Спроба несанкціонованого доступу до admin_menu від користувача {user_id}"
        )
        return

    ADMIN_MENU_TEXT = """⚙️ *Меню адміністратора*
Виберіть категорію:"""

    keyboard = [
        [KeyboardButton("📊 Аналітика"), KeyboardButton("👥 Списки")],
        [KeyboardButton("🗑️ Очищення"), KeyboardButton("⚡ Примусові дії")],
        [KeyboardButton("🔙 Головне меню")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        ADMIN_MENU_TEXT, parse_mode="Markdown", reply_markup=reply_markup
    )
    logger.info("✅ Відображено меню адміністратора")


async def show_admin_analytics_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує підменю аналітики."""
    if not await is_admin(update.effective_user.id):
        return
    keyboard = [
        [KeyboardButton("📊 7 днів"), KeyboardButton("📊 30 днів")],
        [KeyboardButton("📈 Статистика")],
        [KeyboardButton("🔙 Адмін меню")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("📊 *Обрати звіт*", parse_mode="Markdown", reply_markup=reply_markup)


async def show_admin_lists_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує підменю списків користувачів та чатів."""
    if not await is_admin(update.effective_user.id):
        return
    keyboard = [
        [KeyboardButton("👤 Користувачі"), KeyboardButton("💬 Чати")],
        [KeyboardButton("🔙 Адмін меню")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("👥 *Списки*", parse_mode="Markdown", reply_markup=reply_markup)


async def show_admin_cleanup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує підменю очищення повідомлень."""
    if not await is_admin(update.effective_user.id):
        return
    keyboard = [
        [KeyboardButton("🗑️ Видалити день"), KeyboardButton("🗑️ Видалити 30 хв")],
        [KeyboardButton("🔙 Адмін меню")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("🗑️ *Очищення*", parse_mode="Markdown", reply_markup=reply_markup)


async def show_admin_force_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує підменю примусових дій."""
    if not await is_admin(update.effective_user.id):
        return
    keyboard = [
        [KeyboardButton("📅 Розклад"), KeyboardButton("⏰ Нагадування")],
        [KeyboardButton("🎂 ДН")],
        [KeyboardButton("🔙 Адмін меню")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("⚡ *Примусові дії*", parse_mode="Markdown", reply_markup=reply_markup)


async def analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"🔄 Запит на аналітику від користувача {update.effective_user.id}")
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        await update.message.reply_text(
            "❌ *Ця команда доступна тільки адміністратору.*", parse_mode="Markdown"
        )
        logger.warning(
            f"⚠️ Спроба несанкціонованого доступу до analytics від користувача {user_id}"
        )
        return
    days = 7
    if context.args:
        try:
            days = int(context.args[0])
        except ValueError:
            await update.message.reply_text(
                "❌ *Вкажіть коректну кількість днів (наприклад, /analytics 30).*",
                parse_mode="Markdown",
            )
            return
    analytics = Analytics()
    report = await analytics.generate_analytics_report(days)
    await update.message.reply_text(report, parse_mode="Markdown")
    logger.info(f"✅ Аналітика за {days} днів надіслана користувачу {user_id}")


async def users_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"🔍 Виклик команди списку користувачів")
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        await update.message.reply_text(
            "❌ *Ця команда доступна тільки адміністратору.*", parse_mode="Markdown"
        )
        logger.warning(
            f"⚠️ Спроба несанкціонованого доступу до users_list від користувача {user_id}"
        )
        return
    bot_users_str = get_value("bot_users") or "[]"
    bot_users = json.loads(bot_users_str)
    bot_users_info_str = get_value("bot_users_info") or "{}"
    bot_users_info = json.loads(bot_users_info_str)
    users_list = "*Список користувачів бота:*\n\n"
    for uid in bot_users:
        user_name = bot_users_info.get(uid, "Невідомий")
        users_list += f"👤 ID: `{uid}` - {user_name}\n"
    if not bot_users:
        users_list = "ℹ️ Список користувачів порожній."
    await update.message.reply_text(users_list, parse_mode="Markdown")
    logger.info(f"✅ Список користувачів надіслано адміністратору {user_id}")


async def group_chats_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"🔍 Виклик команди списку групових чатів")
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        await update.message.reply_text(
            "❌ *Ця команда доступна тільки адміністратору.*", parse_mode="Markdown"
        )
        logger.warning(
            f"⚠️ Спроба несанкціонованого доступу до group_chats_list від користувача {user_id}"
        )
        return
    group_chats_str = get_value("group_chats") or "[]"
    group_chats = json.loads(group_chats_str)
    chats_list = "*Список групових чатів:*\n\n"
    for chat in group_chats:
        chat_id = chat.get("chat_id", "Невідомий ID")
        chat_title = chat.get("title", "Без назви")
        chats_list += f"👥 ID: `{chat_id}` - {chat_title}\n"
    if not group_chats:
        chats_list = "ℹ️ Список групових чатів порожній."
    await update.message.reply_text(chats_list, parse_mode="Markdown")
    logger.info(f"✅ Список групових чатів надіслано адміністратору {user_id}")


async def delete_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admin_ids = ["611511159"]
    if user_id not in admin_ids:
        message = await update.message.reply_text(
            "❌ *Ця команда доступна лише адміністраторам.*", parse_mode="Markdown"
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")
        logger.warning(
            f"⚠️ Спроба несанкціонованого доступу до команди delete_messages від користувача {user_id}"
        )
        return

    try:
        with get_cursor() as cursor:
            # Отримуємо повідомлення за останній день
            cursor.execute(
                """
                SELECT chat_id, message_id, message_type FROM bot_messages
                WHERE sent_at >= datetime('now', '-1 day')
            """
            )
            bot_messages = cursor.fetchall()

            deleted_count = 0
            failed_count = 0
            for chat_id, message_id, message_type in bot_messages:
                try:
                    await context.bot.delete_message(
                        chat_id=int(chat_id), message_id=int(message_id)
                    )
                    logger.info(
                        f"✅ Видалено повідомлення {message_id} із чату {chat_id}"
                    )
                    deleted_count += 1
                except Exception as e:
                    logger.error(
                        f"❌ Помилка при видаленні повідомлення {message_id} із чату {chat_id}: {e}"
                    )
                    failed_count += 1
                finally:
                    # Видаляємо запис із бази, незалежно від результату
                    cursor.execute(
                        "DELETE FROM bot_messages WHERE chat_id = ? AND message_id = ? AND message_type = ?",
                        (chat_id, message_id, message_type),
                    )

            if deleted_count == 0 and failed_count == 0:
                message = await update.message.reply_text(
                    "ℹ️ Немає повідомлень для видалення за останній день."
                )
                save_bot_message(
                    str(update.effective_chat.id), message.message_id, "general"
                )
                logger.info("ℹ️ Немає повідомлень для видалення за останній день.")
            else:
                message = await update.message.reply_text(
                    f"✅ Видалено {deleted_count} повідомлень за останній день.\n"
                    f"⚠️ Не вдалося видалити {failed_count} повідомлень через помилки."
                )
                save_bot_message(
                    str(update.effective_chat.id), message.message_id, "general"
                )
                logger.info(
                    f"✅ Видалено {deleted_count} повідомлень, не вдалося видалити {failed_count} через помилки."
                )

    except Exception as e:
        logger.error(f"❌ Помилка при виконанні команди delete_messages: {e}")
        message = await update.message.reply_text(
            "❌ *Виникла помилка при видаленні повідомлень.*\n\nБудь ласка, спробуйте пізніше.",
            parse_mode="Markdown",
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")


async def delete_recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admin_ids = ["611511159"]
    if user_id not in admin_ids:
        message = await update.message.reply_text(
            "❌ *Ця команда доступна лише адміністраторам.*", parse_mode="Markdown"
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")
        logger.warning(
            f"⚠️ Спроба несанкціонованого доступу до команди delete_recent від користувача {user_id}"
        )
        return
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT chat_id, message_id FROM bot_messages 
                WHERE sent_at >= datetime('now', '-30 minutes')
            """
            )
            bot_messages = cursor.fetchall()
            cursor.execute(
                """
                SELECT video_id, message_id FROM sent_notifications 
                WHERE sent_at >= datetime('now', '-30 minutes')
            """
            )
            sent_notifications = cursor.fetchall()
            if not bot_messages and not sent_notifications:
                message = await update.message.reply_text(
                    "ℹ️ За останні 30 хвилин бот не надсилав повідомлень."
                )
                save_bot_message(
                    str(update.effective_chat.id), message.message_id, "general"
                )
                logger.info("ℹ️ Немає повідомлень для видалення за останні 30 хвилин")
                return
            deleted_count = 0
            failed_count = 0
            for chat_id, message_id in bot_messages:
                try:
                    await context.bot.delete_message(
                        chat_id=int(chat_id), message_id=int(message_id)
                    )
                    logger.info(
                        f"✅ Видалено повідомлення {message_id} із чату {chat_id}"
                    )
                    deleted_count += 1
                except Exception as e:
                    logger.error(
                        f"❌ Помилка при видаленні повідомлення {message_id} із чату {chat_id}: {e}"
                    )
                    failed_count += 1
                finally:
                    # Видаляємо запис із бази одразу після спроби
                    cursor.execute(
                        "DELETE FROM bot_messages WHERE chat_id = ? AND message_id = ?",
                        (chat_id, message_id),
                    )

            for video_id, message_ids_json in sent_notifications:
                if message_ids_json is None:
                    logger.warning(
                        f"⚠️ Поле message_id для video_id {video_id} є None, пропускаємо."
                    )
                    continue
                try:
                    message_ids = json.loads(message_ids_json)
                    for chat_id, msg_id in message_ids:
                        try:
                            await context.bot.delete_message(
                                chat_id=int(chat_id), message_id=int(msg_id)
                            )
                            logger.info(
                                f"✅ Видалено повідомлення {msg_id} із чату {chat_id} для video_id {video_id}"
                            )
                            deleted_count += 1
                        except Exception as e:
                            logger.error(
                                f"❌ Помилка при видаленні повідомлення {msg_id} із чату {chat_id}: {e}"
                            )
                            failed_count += 1
                        finally:
                            # Оновлюємо або видаляємо запис у sent_notifications
                            remaining_messages = [
                                (c_id, m_id)
                                for c_id, m_id in message_ids
                                if not (c_id == chat_id and m_id == msg_id)
                            ]
                            if remaining_messages:
                                cursor.execute(
                                    "UPDATE sent_notifications SET message_id = ? WHERE video_id = ?",
                                    (json.dumps(remaining_messages), video_id),
                                )
                            else:
                                cursor.execute(
                                    "DELETE FROM sent_notifications WHERE video_id = ?",
                                    (video_id,),
                                )
                except json.JSONDecodeError as e:
                    logger.error(
                        f"❌ Помилка декодування JSON для video_id {video_id}: {e}"
                    )
                    continue

        message = await update.message.reply_text(
            f"✅ Видалено {deleted_count} повідомлень за останні 30 хвилин.\n"
            f"⚠️ Не вдалося видалити {failed_count} повідомлень через помилки."
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")
        logger.info(
            f"✅ Видалено {deleted_count} повідомлень за останні 30 хвилин, не вдалося видалити {failed_count} через помилки"
        )
    except Exception as e:
        logger.error(f"❌ Помилка при видаленні недавніх повідомлень: {e}")
        message = await update.message.reply_text(
            "❌ *Виникла помилка при видаленні недавніх повідомлень.*\n\nБудь ласка, спробуйте пізніше.",
            parse_mode="Markdown",
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")


async def force_daily_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        await update.message.reply_text(
            "❌ *Ця команда доступна тільки адміністратору.*",
            parse_mode="Markdown",
        )
        logger.warning(
            f"⚠️ Спроба несанкціонованого доступу до force_daily_reminder від користувача {user_id}"
        )
        return
    await send_daily_reminder(context, force=True)
    await update.message.reply_text("✅ Щоденне нагадування надіслано примусово.")
    logger.info(f"✅ Адміністратор {user_id} примусово відправив щоденне нагадування")


async def force_hourly_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        await update.message.reply_text(
            "❌ *Ця команда доступна тільки адміністратору.*",
            parse_mode="Markdown",
        )
        logger.warning(
            f"⚠️ Спроба несанкціонованого доступу до force_hourly_reminder від користувача {user_id}"
        )
        return
    await send_event_reminders(context, force=True)
    await update.message.reply_text("✅ Годинне нагадування надіслано примусово.")
    logger.info(f"✅ Адміністратор {user_id} примусово відправив годинне нагадування")


async def force_birthday_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        await update.message.reply_text(
            "❌ *Ця команда доступна тільки адміністратору.*",
            parse_mode="Markdown",
        )
        logger.warning(
            f"⚠️ Спроба несанкціонованого доступу до force_birthday від користувача {user_id}"
        )
        return
    await check_birthday_greetings(context, force=True)
    await update.message.reply_text("✅ Вітання з днем народження надіслано примусово.")
    logger.info(f"✅ Адміністратор {user_id} примусово відправив вітання з днем народження")

__all__ = [
    "is_admin",
    "admin_menu_command",
    "show_admin_analytics_menu",
    "show_admin_lists_menu",
    "show_admin_cleanup_menu",
    "show_admin_force_menu",
    "analytics_command",
    "users_list_command",
    "group_chats_list_command",
    "delete_messages",
    "delete_recent",
    "force_daily_reminder_command",
    "force_hourly_reminder_command",
    "force_birthday_command",
]
