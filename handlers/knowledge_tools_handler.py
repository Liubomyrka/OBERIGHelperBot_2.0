import json
import os
import re
from collections import Counter
from telegram import Update
from telegram.ext import ContextTypes

from config import CHOIR_LEADER_USER_ID, DEFAULT_GROUP_CHAT_ID
from database import (
    find_group_conflicts,
    get_group_facts,
    get_recent_group_messages,
    get_value,
    set_value,
)
from utils import call_openai_chat
from utils.logger import logger


async def _is_group_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not DEFAULT_GROUP_CHAT_ID:
        logger.error("DEFAULT_GROUP_CHAT_ID не задано: доступ до knowledge-tools заборонено (fail-closed).")
        return False
    try:
        member = await context.bot.get_chat_member(
            chat_id=int(DEFAULT_GROUP_CHAT_ID), user_id=int(update.effective_user.id)
        )
        status = getattr(member, "status", "")
        if status in {"creator", "administrator", "member"}:
            return True
        if status == "restricted" and getattr(member, "is_member", False):
            return True
        return False
    except Exception as e:
        logger.error(f"Не вдалося перевірити членство користувача: {e}")
        return False


async def _notify_admin_misconfig(context: ContextTypes.DEFAULT_TYPE, message: str):
    admin_id = os.getenv("ADMIN_CHAT_ID")
    if not admin_id or not admin_id.lstrip("-").isdigit():
        return
    try:
        await context.bot.send_message(chat_id=int(admin_id), text=message)
    except Exception as e:
        logger.debug(f"Не вдалося надіслати misconfig адміну: {e}")


async def _ensure_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.effective_chat.type != "private":
        await update.message.reply_text("Ця команда доступна лише в приватному чаті.")
        return False
    if not DEFAULT_GROUP_CHAT_ID:
        await _notify_admin_misconfig(
            context,
            "❗ Misconfig: DEFAULT_GROUP_CHAT_ID не задано. Knowledge-команди заблоковано (fail-closed).",
        )
        await update.message.reply_text(
            "❌ Функція тимчасово недоступна: не налаштовано DEFAULT_GROUP_CHAT_ID."
        )
        return False
    if not await _is_group_member(update, context):
        await update.message.reply_text(
            "Функція доступна лише учасникам основної групи хору."
        )
        return False
    return True


def _facts_to_lines(facts: list[dict], limit: int = 16) -> list[str]:
    lines = []
    for item in facts[:limit]:
        dt = item.get("event_date") or item.get("created_at", "")[:10]
        name = item.get("event_name") or item.get("details") or "без назви"
        msg_id = item.get("message_id")
        lines.append(f"- {dt}: {name} (msg_id={msg_id})")
    return lines


def _messages_to_lines(messages: list[dict], limit: int = 20) -> list[str]:
    lines = []
    for item in messages[:limit]:
        dt = item.get("message_date", "")
        author = item.get("full_name") or item.get("username") or item.get("user_id")
        text = (item.get("text") or "").replace("\n", " ").strip()
        if len(text) > 160:
            text = text[:157] + "..."
        lines.append(f"- {dt}: {author}: {text} (msg_id={item.get('message_id')})")
    return lines


def _clip(text: str, limit: int = 160) -> str:
    value = re.sub(r"\s+", " ", (text or "")).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _author_name(item: dict) -> str:
    return item.get("full_name") or item.get("username") or f"user_id={item.get('user_id')}"


def _tg_message_link(chat_id: str, message_id: int | str) -> str | None:
    chat_str = str(chat_id or "").strip()
    msg_str = str(message_id or "").strip()
    if not chat_str or not msg_str:
        return None
    if chat_str.startswith("-100"):
        internal_id = chat_str[4:]
        if internal_id.isdigit() and msg_str.isdigit():
            return f"https://t.me/c/{internal_id}/{msg_str}"
    return None


def _build_source_line(chat_id: str, item: dict, leader_id: str | None = None) -> str:
    dt = (item.get("message_date") or item.get("created_at") or "")[:19]
    author = _author_name(item)
    msg_id = item.get("message_id")
    snippet = _clip(item.get("text") or item.get("details") or "")
    prefix = "Джерело"
    if leader_id and str(item.get("user_id")) == str(leader_id):
        prefix = "Джерело (керівниця)"
    line = f"{prefix}: {dt}, {author}, msg_id={msg_id}, фрагмент: {snippet}"
    link = _tg_message_link(chat_id, msg_id)
    if link:
        line += f", link={link}"
    return line


def _confidence_label(messages_count: int, facts_count: int, conflicts_count: int) -> str:
    score = 0
    if messages_count >= 30:
        score += 2
    elif messages_count >= 10:
        score += 1
    if facts_count >= 8:
        score += 2
    elif facts_count >= 3:
        score += 1
    if conflicts_count > 0:
        score -= 1
    if score >= 4:
        return "високий"
    if score >= 2:
        return "середній"
    return "низький"


def _build_structured_summary(title: str, chat_id: str, days: int, messages: list[dict], facts: list[dict]) -> str:
    if not messages and not facts:
        return (
            f"{title}\n\n"
            "Що відомо:\n"
            "- За вибраний період у локальному індексі немає повідомлень або фактів.\n\n"
            "На чому базується:\n"
            "- Локальна БД `group_message_index` / `group_facts`.\n\n"
            "Що непідтверджено:\n"
            "- Підсумок неможливий без даних.\n\n"
            "Рівень впевненості:\n"
            "низький"
        )

    facts_by_type = Counter([f.get("fact_type", "unknown") for f in facts if f.get("fact_type")])
    top_types = ", ".join([f"{k}={v}" for k, v in facts_by_type.most_common(5)]) or "факти не виділено"
    conflicts = find_group_conflicts(chat_id, days=max(7, days))

    known_lines = [
        f"- Проаналізовано повідомлень: {len(messages)}.",
        f"- Виділено фактів: {len(facts)}.",
        f"- Типи фактів: {top_types}.",
    ]

    if facts:
        for fact in facts[:4]:
            fdt = fact.get("event_date") or (fact.get("created_at") or "")[:10]
            fname = fact.get("event_name") or fact.get("details") or "без назви"
            known_lines.append(
                f"- {fact.get('fact_type', 'fact')}: {fdt} | {_clip(fname, 100)} (msg_id={fact.get('message_id')})."
            )

    source_lines = []
    seen = set()
    leader_sources = []
    for item in messages:
        key = (item.get("chat_id"), item.get("message_id"))
        if key in seen:
            continue
        seen.add(key)
        line = _build_source_line(chat_id, item, CHOIR_LEADER_USER_ID)
        if CHOIR_LEADER_USER_ID and str(item.get("user_id")) == str(CHOIR_LEADER_USER_ID):
            leader_sources.append(line)
        else:
            source_lines.append(line)
        if len(source_lines) >= 8:
            break
    for fact in facts:
        key = (fact.get("chat_id"), fact.get("message_id"), fact.get("id"))
        if key in seen:
            continue
        seen.add(key)
        source_lines.append(_build_source_line(chat_id, fact, CHOIR_LEADER_USER_ID))
        if len(source_lines) >= 12:
            break

    base_lines = []
    for line in leader_sources[:4]:
        base_lines.append(line)
    for line in source_lines[:8]:
        base_lines.append(line)
    if not base_lines:
        base_lines.append("- Релевантні джерела не знайдено в локальному індексі.")

    unknown_lines = []
    if conflicts:
        for conflict in conflicts[:3]:
            items = conflict.get("items") or []
            dates = sorted({str(i.get("event_date")) for i in items if i.get("event_date")})
            unknown_lines.append(
                f"- Є конфлікт по '{conflict.get('event_key')}': різні дати {', '.join(dates)}."
            )
    if not conflicts:
        unknown_lines.append("- Явних конфліктів дат у збережених фактах не виявлено.")
    if len(messages) < 5:
        unknown_lines.append("- Даних мало: могло потрапити не все, що писали в чаті.")

    confidence = _confidence_label(len(messages), len(facts), len(conflicts))
    return (
        f"{title}\n\n"
        "Що відомо:\n"
        + "\n".join(known_lines[:10])
        + "\n\n"
        "На чому базується:\n"
        + "\n".join(base_lines[:12])
        + "\n\n"
        "Що непідтверджено:\n"
        + "\n".join(unknown_lines[:6])
        + "\n\n"
        "Рівень впевненості:\n"
        + confidence
    )


async def _llm_summary(title: str, messages: list[dict], facts: list[dict], ask: str) -> str:
    source_lines = _messages_to_lines(messages, limit=18) + _facts_to_lines(facts, limit=18)
    prompt = (
        f"Ти асистент хору. Потрібно дати стислу аналітику.\n"
        f"Запит: {ask}\n"
        f"Дані:\n" + "\n".join(source_lines[:30]) + "\n\n"
        "Формат відповіді:\n"
        "Що відомо\nНа чому базується\nЩо непідтверджено\nРівень впевненості\n"
        "В кінці обов'язково додай 3-8 рядків 'Джерело: дата, автор, msg_id=...'."
    )
    try:
        result = await call_openai_chat(
            messages=[{"role": "user", "content": prompt}],
            model="gpt-4o-mini",
            max_tokens=550,
            temperature=0.2,
        )
        return result
    except Exception as e:
        logger.error(f"Не вдалося згенерувати LLM summary: {e}")
        fallback_sources = "\n".join(source_lines[:8]) or "Джерела відсутні."
        return (
            f"{title}\n\nЩо відомо:\nНедостатньо даних для LLM-підсумку.\n\n"
            f"На чому базується:\n{fallback_sources}\n\n"
            "Що непідтверджено:\nПотрібна додаткова ручна перевірка.\n\n"
            "Рівень впевненості:\nнизький"
        )


async def summary_day_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_access(update, context):
        return
    chat_id = str(DEFAULT_GROUP_CHAT_ID or "")
    messages = get_recent_group_messages(chat_id, days=1, limit=200)
    facts = get_group_facts(chat_id, fact_type=None, days=1, limit=120)
    text = _build_structured_summary("Підсумок за день", chat_id, 1, messages, facts)
    await update.message.reply_text(text)


async def summary_week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_access(update, context):
        return
    chat_id = str(DEFAULT_GROUP_CHAT_ID or "")
    messages = get_recent_group_messages(chat_id, days=7, limit=350)
    facts = get_group_facts(chat_id, fact_type=None, days=7, limit=180)
    text = _build_structured_summary("Підсумок за тиждень", chat_id, 7, messages, facts)
    await update.message.reply_text(text)


async def decisions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_access(update, context):
        return
    chat_id = str(DEFAULT_GROUP_CHAT_ID or "")
    facts = get_group_facts(chat_id, fact_type="decision", days=60, limit=120)
    if not facts:
        await update.message.reply_text("Рішень за останній період не знайдено.")
        return
    lines = _facts_to_lines(facts, limit=40)
    await update.message.reply_text("Рішення:\n" + "\n".join(lines))


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_access(update, context):
        return
    chat_id = str(DEFAULT_GROUP_CHAT_ID or "")
    facts = get_group_facts(chat_id, fact_type="task", days=60, limit=120)
    if not facts:
        await update.message.reply_text("Задач за останній період не знайдено.")
        return
    lines = _facts_to_lines(facts, limit=50)
    await update.message.reply_text("Задачі:\n" + "\n".join(lines))


async def announcements_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_access(update, context):
        return
    chat_id = str(DEFAULT_GROUP_CHAT_ID or "")
    facts = get_group_facts(chat_id, fact_type="announcement", days=45, limit=120)
    if not facts:
        messages = get_recent_group_messages(chat_id, days=14, limit=250)
        keyword_lines = [
            f"- {m.get('message_date')}: {(m.get('text') or '')[:150]} (msg_id={m.get('message_id')})"
            for m in messages
            if any(
                k in (m.get("text") or "").lower()
                for k in ["оголошення", "увага", "нагадую", "важливо"]
            )
        ][:30]
        if not keyword_lines:
            await update.message.reply_text("Оголошень за останній період не знайдено.")
            return
        await update.message.reply_text("Оголошення:\n" + "\n".join(keyword_lines))
        return
    await update.message.reply_text("Оголошення:\n" + "\n".join(_facts_to_lines(facts, limit=40)))


async def digest_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_access(update, context):
        return
    user_id = str(update.effective_user.id)
    set_value(f"digest_auto_{user_id}", "1")
    await update.message.reply_text("Автоматичні щотижневі дайджести увімкнено.")


async def digest_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_access(update, context):
        return
    user_id = str(update.effective_user.id)
    set_value(f"digest_auto_{user_id}", "0")
    await update.message.reply_text("Автоматичні щотижневі дайджести вимкнено.")


async def draft_announcement_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_access(update, context):
        return
    topic = " ".join(context.args).strip() if context.args else "найближчі події хору"
    chat_id = str(DEFAULT_GROUP_CHAT_ID or "")
    messages = get_recent_group_messages(chat_id, days=14, limit=220)
    facts = get_group_facts(chat_id, fact_type=None, days=14, limit=120)
    text = await _llm_summary("Чернетка оголошення", messages, facts, f"Зроби анонс на тему: {topic}")
    await update.message.reply_text("Чернетка оголошення:\n\n" + text)


async def confirmations_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_access(update, context):
        return
    chat_id = str(DEFAULT_GROUP_CHAT_ID or "")
    facts = get_group_facts(chat_id, fact_type="confirmation", days=45, limit=200)
    if not facts:
        await update.message.reply_text("Підтверджень участі не знайдено.")
        return
    by_user = Counter()
    for f in facts:
        by_user[f.get("user_id", "unknown")] += 1
    lines = [f"- user_id={uid}: {cnt} підтверджень" for uid, cnt in by_user.most_common(30)]
    await update.message.reply_text("Підтвердження участі:\n" + "\n".join(lines))


async def weekly_digest_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        users_raw = get_value("bot_users") or "[]"
        users = json.loads(users_raw)
    except Exception:
        users = []
    chat_id = str(DEFAULT_GROUP_CHAT_ID or "")
    if not chat_id:
        return
    messages = get_recent_group_messages(chat_id, days=7, limit=300)
    facts = get_group_facts(chat_id, fact_type=None, days=7, limit=180)
    digest_text = await _llm_summary("Щотижневий дайджест", messages, facts, "Сформуй щотижневий дайджест")
    for user_id in users:
        try:
            enabled = get_value(f"digest_auto_{user_id}")
            if enabled != "1":
                continue
            await context.bot.send_message(chat_id=int(user_id), text=digest_text)
        except Exception as e:
            logger.debug(f"Не вдалося надіслати weekly digest користувачу {user_id}: {e}")
