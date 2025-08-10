from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

async def clear_bot_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete bot messages older than a threshold.

    Usage:
        /clear           # remove messages older than 30 minutes
        /clear day       # remove messages older than one day
    """
    messages = context.chat_data.get("bot_messages", [])
    if not messages:
        return

    threshold = timedelta(minutes=30)
    if context.args and context.args[0].lower() in {"day", "1d", "24h"}:
        threshold = timedelta(days=1)

    now = datetime.now()
    remaining = []
    for msg_id, ts in messages:
        if now - ts >= threshold:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except Exception:
                remaining.append((msg_id, ts))
        else:
            remaining.append((msg_id, ts))

    context.chat_data["bot_messages"] = remaining
