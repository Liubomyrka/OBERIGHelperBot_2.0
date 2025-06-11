from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import ContextTypes

from utils.calendar_utils import (
    get_latest_youtube_video,
    get_most_popular_youtube_video,
    get_top_10_videos,
)
from database import save_bot_message
from utils.logger import logger

from .user_utils import auto_add_user

from .start_handler import auto_add_user


YOUTUBE_MENU_TEXT = """🎥 *Меню YouTube*

Виберіть одну з опцій:
📺 - Переглянути всі відео
🆕 - Переглянути найновіше відео
🔥 - Переглянути найпопулярніше відео
🏆 - Топ-10 найпопулярніших відео

🔔 Керування сповіщеннями:
- 🔔 Увімкнути сповіщення - отримувати повідомлення про нові відео
- 🔕 Вимкнути сповіщення - припинити отримувати повідомлення"""

ERROR_VIDEO_NOT_FOUND = "⚠️ *Відео не знайдено 😔* Спробуй пізніше! ⬇️"
ERROR_GENERAL = "❌ *Щось пішло не так 😔* Спробуй ще раз! ⬇️"


async def latest_video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_add_user(update, context)
    logger.info("🔄 Виконання команди: /latest_video")
    try:
        video_url = get_latest_youtube_video()
        if video_url:
            message = await update.message.reply_text(
                f"🆕 *Найновіше відео хору OBERIG:*\n\n"
                f"👆 [Переглянути відео]({video_url})\n\n"
                "📤 Поділитися цим відео: `/share_latest`",
                parse_mode="Markdown",
            )
            save_bot_message(
                str(update.effective_chat.id), message.message_id, "general"
            )
            logger.info("✅ Команда /latest_video виконана успішно.")
        else:
            message = await update.message.reply_text(ERROR_VIDEO_NOT_FOUND)
            save_bot_message(
                str(update.effective_chat.id), message.message_id, "general"
            )
            logger.warning(ERROR_VIDEO_NOT_FOUND)
    except Exception as e:
        logger.error(f"❌ Помилка у виконанні команди /latest_video: {e}")
        message = await update.message.reply_text(ERROR_GENERAL)
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")


async def top_10_videos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_add_user(update, context)
    logger.info("Виконання команди: /top_10_videos")
    try:
        videos = get_top_10_videos()
        if not videos:
            message = await update.message.reply_text(
                ERROR_VIDEO_NOT_FOUND
            )
            save_bot_message(
                str(update.effective_chat.id), message.message_id, "general"
            )
            logger.warning("Відео не знайдено")
            return

        page = context.user_data.get("top_10_page", 0)
        videos_per_page = 5
        total_pages = (len(videos) + videos_per_page - 1) // videos_per_page

        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1
        context.user_data["top_10_page"] = page

        start_idx = page * videos_per_page
        end_idx = min(start_idx + videos_per_page, len(videos))
        current_videos = videos[start_idx:end_idx]

        message_text = "*🏆 Топ-10 найпопулярніших відео:*\n\n"
        for i, (title, url, views) in enumerate(current_videos, start_idx + 1):
            title = title[:120] + "..." if len(title) > 120 else title
            message_text += f"**{i}.** [{title}]({url})\n👁 {views:,} переглядів\n\n"

        message_text += f"\n📄 Сторінка {page + 1} з {total_pages}"

        keyboard = []
        if page > 0:
            keyboard.append(InlineKeyboardButton("⬅️ Попередня п'ятірка", callback_data="top_10_prev"))
        if page < total_pages - 1:
            keyboard.append(InlineKeyboardButton("Наступна п'ятірка ➡️", callback_data="top_10_next"))
        reply_markup = InlineKeyboardMarkup([keyboard]) if keyboard else None

        if update.callback_query:
            await update.callback_query.edit_message_text(
                message_text,
                parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
        else:
            message = await update.message.reply_text(
                message_text,
                parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
            save_bot_message(
                str(update.effective_chat.id), message.message_id, "general"
            )

        logger.info(f"Команда /top_10_videos виконана успішно (Сторінка {page + 1})")
    except Exception as e:
        logger.error(f"Помилка у виконанні команди /top_10_videos: {e}")
        message = await update.message.reply_text(ERROR_GENERAL)
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")


async def show_youtube_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_add_user(update, context)
    logger.info("Спроба відобразити меню YouTube")
    try:
        keyboard = [
            [KeyboardButton("📺 Наші відео")],
            [KeyboardButton("🆕 Найновше відео")],
            [KeyboardButton("🔥 Найпопулярніше відео")],
            [KeyboardButton("🏆 Топ-10 відео")],
            [
                KeyboardButton("🔔 Увімкнути сповіщення"),
                KeyboardButton("🔕 Вимкнути сповіщення"),
            ],
            [KeyboardButton("🔙 Головне меню")],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        message = await update.message.reply_text(
            YOUTUBE_MENU_TEXT,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")
        logger.info("Відображено меню YouTube")
    except Exception as e:
        logger.error(f"Помилка при відображенні меню YouTube: {e}")
        message = await update.message.reply_text(ERROR_GENERAL)
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")


async def most_popular_video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_add_user(update, context)
    logger.info("🔄 Виконання команди: /most_popular_video")
    try:
        video_url = get_most_popular_youtube_video()
        if video_url:
            message = await update.message.reply_text(
                f"🔥 *Найпопулярніше відео хору OBERIG:*\n\n"
                f"👆 [Переглянути відео]({video_url})\n\n"
                "📤 Поділитися цим відео: `/share_popular`",
                parse_mode="Markdown",
            )
            save_bot_message(
                str(update.effective_chat.id), message.message_id, "general"
            )
            logger.info("✅ Команда /most_popular_video виконана успішно")
        else:
            message = await update.message.reply_text(
                ERROR_VIDEO_NOT_FOUND
            )
            save_bot_message(
                str(update.effective_chat.id), message.message_id, "general"
            )
            logger.warning("Відео не знайдено")
    except Exception as e:
        logger.error(f"❌ Помилка у виконанні команди /most_popular_video: {e}")
        message = await update.message.reply_text(ERROR_GENERAL)
        save_bot_message(str(update.effective_chat.id), message.message_id, "general")


__all__ = [
    "latest_video_command",
    "show_youtube_menu",
    "most_popular_video_command",
    "top_10_videos_command",
]
