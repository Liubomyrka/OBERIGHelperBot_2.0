# share_handler.py

from telegram import Update
from telegram.ext import ContextTypes
from utils.logger import logger
from utils.calendar_utils import (
    get_latest_youtube_video,
    get_most_popular_youtube_video,
)


async def share_latest_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обробляє команду /share_latest для поділу найновішим відео.
    """
    logger.info("🔄 Виконання команди: /share_latest")
    try:
        video_url = get_latest_youtube_video()
        if video_url:
            share_text = (
                "🎵 *Нове відео від хору OBERIG!*\n\n"
                f"Переглянути: {video_url}\n\n"
                "Підписуйтесь на наш канал, щоб не пропустити нові відео! 🎼"
            )
            await update.message.reply_text(share_text, parse_mode="Markdown")
            logger.info("✅ Команда /share_latest виконана успішно")
        else:
            await update.message.reply_text(
                "⚠️ На жаль, не вдалося отримати відео для поділу."
            )
            logger.warning("⚠️ Не вдалося отримати відео для поділу")
    except Exception as e:
        logger.error(f"❌ Помилка при виконанні команди /share_latest: {e}")
        await update.message.reply_text(
            "❌ Виникла помилка при спробі поділитися відео."
        )


async def share_popular_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обробляє команду /share_popular для поділу найпопулярнішим відео.
    """
    logger.info("🔄 Виконання команди: /share_popular")
    try:
        video_url = get_most_popular_youtube_video()
        if video_url:
            share_text = (
                "🔥 *Найпопулярніше відео хору OBERIG!*\n\n"
                f"Переглянути: {video_url}\n\n"
                "Підписуйтесь на наш канал, щоб побачити більше! 🎼"
            )
            await update.message.reply_text(share_text, parse_mode="Markdown")
            logger.info("✅ Команда /share_popular виконана успішно")
        else:
            await update.message.reply_text(
                "⚠️ На жаль, не вдалося отримати відео для поділу."
            )
            logger.warning("⚠️ Не вдалося отримати відео для поділу")
    except Exception as e:
        logger.error(f"❌ Помилка при виконанні команди /share_popular: {e}")
        await update.message.reply_text(
            "❌ Виникла помилка при спробі поділитися відео."
        )


__all__ = ["share_latest_video", "share_popular_video"]
