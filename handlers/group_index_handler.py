from telegram import Update
from telegram.ext import ContextTypes

import asyncio
import re
import openai
from database import (
    cleanup_group_knowledge,
    save_group_message_embedding,
    save_group_message_index,
    save_group_fact,
)
from handlers.user_utils import auto_add_user
from utils.logger import logger
from utils import init_openai_api
from utils.privacy import mask_user_id

init_openai_api()

FACT_TYPE_PATTERNS = {
    "decision": [r"\bвирішили\b", r"\bрішення\b", r"\bухвалили\b"],
    "task": [r"\bтреба\b", r"\bпотрібно\b", r"\bзробити\b", r"\bдо\s+\d{1,2}[./-]\d{1,2}"],
    "announcement": [r"\bоголошення\b", r"\bувага\b", r"\bнагадую\b"],
    "performance": [r"\bвиступ\w*\b", r"\bконцерт\w*\b", r"\bauftritt\w*\b", r"\bkonzert\w*\b"],
    "rehearsal": [r"\bрепетиці\w*\b", r"\bprobe\b", r"\bchorprobe\b"],
    "confirmation": [r"\bпідтверджую\b", r"\bбуду\b", r"\bне буду\b", r"\bя йду\b"],
}


def _extract_date(text: str) -> str | None:
    m = re.search(r"\b(\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)\b", text)
    return m.group(1) if m else None


def _extract_time(text: str) -> str | None:
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)
    return m.group(0) if m else None


def _extract_location(text: str) -> str | None:
    m = re.search(r"(?:в|у|at)\s+([A-ZА-ЯІЇЄ][^,.]{3,60})", text)
    if not m:
        return None
    return m.group(1).strip()


def _extract_responsible(text: str) -> str | None:
    m = re.search(r"(?:відповідальн\w*|responsible)\s*[:\-]?\s*(@?\w+)", text, re.IGNORECASE)
    return m.group(1) if m else None


def _extract_facts(text: str) -> list[dict]:
    txt = (text or "").strip()
    if not txt:
        return []
    facts: list[dict] = []
    lowered = txt.lower()
    event_date = _extract_date(txt)
    event_time = _extract_time(txt)
    location = _extract_location(txt)
    responsible = _extract_responsible(txt)
    for fact_type, patterns in FACT_TYPE_PATTERNS.items():
        if any(re.search(pattern, lowered) for pattern in patterns):
            facts.append(
                {
                    "fact_type": fact_type,
                    "event_name": txt[:120],
                    "event_date": event_date,
                    "event_time": event_time,
                    "location": location,
                    "responsible": responsible,
                    "deadline": event_date if fact_type == "task" else None,
                    "details": txt[:400],
                    "confidence": 0.65,
                }
            )
    return facts


async def _build_embedding(text: str) -> list[float] | None:
    clean = (text or "").strip()
    if len(clean) < 8:
        return None
    try:
        response = await asyncio.to_thread(
            openai.embeddings.create,
            model="text-embedding-3-small",
            input=clean[:3000],
        )
        return response.data[0].embedding if response and response.data else None
    except Exception as e:
        logger.debug(f"Embedding недоступний для повідомлення: {e}")
        return None


async def index_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Silently index text messages from groups for private assistant search."""
    try:
        if not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
            return
        if not update.effective_message or not update.effective_message.text:
            return
        if not update.effective_user:
            return

        await auto_add_user(update, context)

        msg = update.effective_message
        user = update.effective_user
        reply_user = msg.reply_to_message.from_user if msg.reply_to_message else None
        full_name = " ".join(
            part for part in [user.first_name or "", user.last_name or ""] if part
        ).strip() or user.username or "Unknown"

        save_group_message_index(
            chat_id=str(update.effective_chat.id),
            message_id=msg.message_id,
            user_id=str(user.id),
            username=user.username,
            full_name=full_name,
            message_date=msg.date.isoformat(),
            text=msg.text,
            is_reply=bool(msg.reply_to_message),
            reply_to_user_id=str(reply_user.id) if reply_user else None,
        )
        logger.debug(
            "Indexed group message: chat_id=%s message_id=%s user=%s",
            str(update.effective_chat.id),
            msg.message_id,
            mask_user_id(user.id),
        )

        emb = await _build_embedding(msg.text)
        if emb:
            save_group_message_embedding(
                chat_id=str(update.effective_chat.id),
                message_id=msg.message_id,
                embedding=emb,
                model="text-embedding-3-small",
            )

        facts = _extract_facts(msg.text)
        for fact in facts:
            save_group_fact(
                chat_id=str(update.effective_chat.id),
                message_id=msg.message_id,
                user_id=str(user.id),
                fact_type=fact["fact_type"],
                event_name=fact.get("event_name"),
                event_date=fact.get("event_date"),
                event_time=fact.get("event_time"),
                location=fact.get("location"),
                responsible=fact.get("responsible"),
                deadline=fact.get("deadline"),
                details=fact.get("details"),
                confidence=fact.get("confidence", 0.5),
            )
    except Exception as e:
        logger.error(f"❌ Помилка індексації групового повідомлення: {e}")


async def cleanup_group_index_job(context: ContextTypes.DEFAULT_TYPE):
    """Delete old indexed group messages to keep only recent history."""
    try:
        deleted_idx, deleted_emb, deleted_facts = cleanup_group_knowledge(retention_days=90)
        if deleted_idx or deleted_emb or deleted_facts:
            logger.info(
                "🧹 Очищено записи знань групи: index=%d embeddings=%d facts=%d",
                deleted_idx,
                deleted_emb,
                deleted_facts,
            )
    except Exception as e:
        logger.error(f"❌ Помилка очищення індексу групових повідомлень: {e}")
