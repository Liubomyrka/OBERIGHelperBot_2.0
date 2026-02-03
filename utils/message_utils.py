import asyncio
from telegram.error import NetworkError, BadRequest
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from utils.logger import logger

async def safe_send_markdown(bot, chat_id: int, text: str, retries: int = 3, **kwargs):
    """Send a MarkdownV2 message with basic retries and escaping."""
    escaped = escape_markdown(text, version=2)
    for attempt in range(1, retries + 1):
        try:
            return await bot.send_message(
                chat_id=chat_id,
                text=escaped,
                parse_mode=ParseMode.MARKDOWN_V2,
                **kwargs,
            )
        except NetworkError as e:
            if "chat not found" in str(e).lower():
                logger.warning(f"Chat not found, припиняю відправку в chat_id={chat_id}")
                break
            logger.warning(f"Network error on attempt {attempt}/{retries}: {e}")
            await asyncio.sleep(attempt)
        except BadRequest as e:
            if "chat not found" in str(e).lower():
                logger.warning(f"Chat not found (BadRequest), припиняю відправку в chat_id={chat_id}")
                break
            logger.error(f"BadRequest while sending message: {e}")
            escaped = escape_markdown(text, version=2)
        except Exception as e:
            logger.error(f"Unexpected error while sending message: {e}")
            break
    logger.error("Failed to send message after retries")
    return None
