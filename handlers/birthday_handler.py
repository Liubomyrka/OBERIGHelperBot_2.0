from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

async def send_birthday_greeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a birthday greeting and track the message with a timestamp."""
    messages = context.chat_data.setdefault("bot_messages", [])
    sent = await context.bot.send_message(chat_id=update.effective_chat.id, text="🎉 З Днем народження!")
    messages.append((sent.message_id, datetime.now()))
