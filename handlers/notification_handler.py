from telegram import Update
from telegram.ext import ContextTypes
from utils.logger import logger
from utils.calendar_utils import check_new_videos
from database import get_value, set_value, get_cursor
import json


async def check_and_notify_new_videos(context: ContextTypes.DEFAULT_TYPE):
    """
    Перевіряє наявність нових відео в YouTube і надсилає сповіщення.
    """
    logger.info("🔍 Перевірка нових відео в YouTube...")

    try:
        # Отримуємо нові відео
        new_videos = await check_new_videos()

        if not new_videos:
            logger.info("Немає нових відео для сповіщення.")
            return

        # Отримуємо список активних користувачів і груп
        bot_users_str = get_value("bot_users")
        bot_users = json.loads(bot_users_str) if bot_users_str else []
        group_chats_str = get_value("group_chats")
        group_chats = json.loads(group_chats_str) if group_chats_str else []

        # Отримуємо статус сповіщень для користувачів і груп
        video_notifications_disabled_str = get_value("video_notifications_disabled")
        video_notifications_disabled = (
            json.loads(video_notifications_disabled_str)
            if video_notifications_disabled_str
            else {}
        )
        group_notifications_disabled_str = get_value("group_notifications_disabled")
        group_notifications_disabled = (
            json.loads(group_notifications_disabled_str)
            if group_notifications_disabled_str
            else {}
        )

        for video in new_videos:
            video_id = video["video_id"]
            title = video["title"]
            url = video["url"]

            # Список для зберігання ID повідомлень
            message_ids = []

            # Надсилаємо сповіщення користувачам
            for user_id in bot_users:
                if (
                    str(user_id) not in video_notifications_disabled
                    or not video_notifications_disabled[str(user_id)]
                ):
                    try:
                        message = await context.bot.send_message(
                            chat_id=user_id,
                            text=f"🎥 Нове відео на каналі!\n\n*{title}*\n{url}",
                            parse_mode="Markdown",
                        )
                        message_ids.append((str(user_id), message.message_id))
                        logger.info(
                            f"✅ Надіслано сповіщення про нове відео користувачу {user_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"❌ Помилка при надсиланні сповіщення користувачу {user_id}: {e}"
                        )

            # Надсилаємо сповіщення групам
            for group in group_chats:
                chat_id = group["chat_id"]
                if (
                    str(chat_id) not in group_notifications_disabled
                    or not group_notifications_disabled[str(chat_id)]
                ):
                    try:
                        message = await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"🎥 Нове відео на каналі!\n\n*{title}*\n{url}",
                            parse_mode="Markdown",
                        )
                        message_ids.append((str(chat_id), message.message_id))
                        logger.info(
                            f"✅ Надіслано сповіщення про нове відео в груповий чат {chat_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"❌ Помилка при надсиланні сповіщення в груповий чат {chat_id}: {e}"
                        )

            # Зберігаємо, що відео надіслано разом із ID повідомлень
            await save_video_sent(video_id, message_ids)

    except Exception as e:
        logger.error(f"❌ Помилка при перевірці та надсиланні нових відео: {e}")


async def check_video_sent(video_id: str) -> bool:
    """
    Перевіряє, чи відео вже надсилалося.
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM sent_notifications WHERE video_id = ?",
                (video_id,),
            )
            count = cursor.fetchone()[0]
        return count > 0
    except Exception as e:
        logger.error(f"❌ Помилка при перевірці відправленого відео {video_id}: {e}")
        return False


async def save_video_sent(video_id: str, message_ids: list = None):
    """
    Зберігає інформацію, що відео було надіслано, разом із ID повідомлень.
    """
    try:
        with get_cursor() as cursor:
            message_ids_json = json.dumps(message_ids) if message_ids else None
            cursor.execute(
                "INSERT INTO sent_notifications (video_id, sent_at, message_id) VALUES (?, datetime('now'), ?)",
                (video_id, message_ids_json),
            )
        logger.info(
            f"✅ Збережено, що відео {video_id} надіслано з message_ids: {message_ids_json}"
        )
    except Exception as e:
        logger.error(f"❌ Помилка при збереженні відправленого відео {video_id}: {e}")


async def toggle_video_notifications(
    update: Update, context: ContextTypes.DEFAULT_TYPE, enable: bool
):
    """
    Увімкнення або вимкнення сповіщень про нові відео для користувача.
    """
    user_id = str(update.effective_user.id)
    video_notifications_disabled_str = get_value("video_notifications_disabled")
    video_notifications_disabled = (
        json.loads(video_notifications_disabled_str)
        if video_notifications_disabled_str
        else {}
    )

    video_notifications_disabled[user_id] = not enable
    set_value("video_notifications_disabled", json.dumps(video_notifications_disabled))

    status = "увімкнено" if enable else "вимкнено"
    await update.message.reply_text(
        f"🎥 Сповіщення про нові відео {status} для вас.", parse_mode="Markdown"
    )
    logger.info(
        f"✅ Сповіщення про відео {'увімкнено' if enable else 'вимкнено'} для користувача {user_id}"
    )


__all__ = ["check_and_notify_new_videos", "toggle_video_notifications"]
