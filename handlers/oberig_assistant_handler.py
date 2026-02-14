import os
import json
import re
import openai
from telegram import Update
from telegram.ext import ContextTypes
from utils.logger import logger
from utils.calendar_utils import (
    get_calendar_events_cached,
    get_latest_youtube_video_cached,
    get_most_popular_youtube_video_cached,
    get_top_10_videos_cached,
    get_past_events_cached,
    get_last_event,
    get_events_in_range,
    count_events,
    get_next_event,
)
from database import (
    get_group_facts,
    get_value,
    set_value,
    find_group_conflicts,
    search_group_messages,
    search_group_messages_semantic,
)
from datetime import datetime, timedelta
from handlers.drive_utils import list_sheets, send_sheet
from handlers.notes_utils import search_notes
from config import DEFAULT_GROUP_CHAT_ID, CHOIR_LEADER_USER_ID
from utils import (
    init_openai_api,
    call_openai_chat,
    call_openai_assistant,
    get_openai_assistant_id,
)
from utils.privacy import mask_user_id, new_request_id, text_meta

# Налаштування API-ключа OpenAI
ASSISTANT_ID = init_openai_api()

# Скорочений системний контекст для зменшення токенів
OBERIG_SYSTEM_PROMPT = """
Ти — OBERIG, привітний та ввічливий помічник українського аматорського хорового колективу «Оберіг» у Німеччині. Хор популяризує українську культуру через музику, хоровий спів, репетиції та концерти за адресою Planigenstasse 4, Bad Kreuznach. Керівниця — Віта Романченко. Ти маєш доступ до календаря (репетиції, виступи, дні народження), відео на YouTube (плейлист: https://youtube.com/playlist?list=PLEkdnztUMQ7-05r94OMzHyCVMCXvkgrFn), Facebook (https://www.facebook.com/profile.php?id=100094519583534) і чату. Відповідай дружньо, ввічливо з емоджі 🎵😊, хештегами #Оберіг #Хор, різними смайлами, різними емоджі та прикрасами (✨, 🌟) для візуального покращення. Якщо запит не про хор, скажи: "Вибач 😔, я допоможу лише з хором «Оберіг». Спробуй інше питання! #Оберіг".
"""


def _extract_search_query(user_message: str) -> str:
    parts = re.findall(r"[\w\u0400-\u04FF]+", user_message.lower())
    tokens = [p for p in parts if len(p) >= 3]
    return " ".join(tokens[:10]).strip() or user_message[:80].strip()


async def _is_user_in_main_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not DEFAULT_GROUP_CHAT_ID:
        logger.error("DEFAULT_GROUP_CHAT_ID не задано: доступ до асистента заборонено (fail-closed).")
        return False
    try:
        member = await context.bot.get_chat_member(
            chat_id=int(DEFAULT_GROUP_CHAT_ID),
            user_id=int(update.effective_user.id),
        )
        status = getattr(member, "status", "")
        if status in {"creator", "administrator", "member"}:
            return True
        if status == "restricted" and getattr(member, "is_member", False):
            return True
        return False
    except Exception as e:
        logger.error(f"Не вдалося перевірити членство користувача у групі: {e}")
        return False


async def _notify_admin_misconfig(context: ContextTypes.DEFAULT_TYPE, message: str):
    admin_id = os.getenv("ADMIN_CHAT_ID")
    if not admin_id or not admin_id.lstrip("-").isdigit():
        return
    try:
        await context.bot.send_message(chat_id=int(admin_id), text=message)
    except Exception as e:
        logger.debug(f"Не вдалося надіслати повідомлення адміну про misconfig: {e}")


def _build_chat_insights(user_message: str) -> tuple[str, str, str]:
    if not DEFAULT_GROUP_CHAT_ID:
        return "Не налаштовано основний груповий чат.", "", "низький"

    query = _extract_search_query(user_message)
    keyword_hits = search_group_messages(
        chat_id=str(DEFAULT_GROUP_CHAT_ID),
        query=query,
        lookback_days=90,
        limit=24,
        priority_user_id=CHOIR_LEADER_USER_ID,
    )
    semantic_hits = []
    try:
        emb_resp = openai.embeddings.create(
            model="text-embedding-3-small",
            input=query[:1000],
        )
        query_emb = emb_resp.data[0].embedding if emb_resp and emb_resp.data else []
        if query_emb:
            semantic_hits = search_group_messages_semantic(
                chat_id=str(DEFAULT_GROUP_CHAT_ID),
                query_embedding=query_emb,
                lookback_days=90,
                limit=24,
                priority_user_id=CHOIR_LEADER_USER_ID,
            )
    except Exception as e:
        logger.debug(f"Semantic search не спрацював, fallback на keyword: {e}")

    merged_map: dict[tuple[str, int], dict] = {}
    for item in keyword_hits:
        key = (str(item.get("chat_id")), int(item.get("message_id")))
        merged_map[key] = dict(item)
    for item in semantic_hits:
        key = (str(item.get("chat_id")), int(item.get("message_id")))
        if key in merged_map:
            merged_map[key]["score"] = max(
                float(merged_map[key].get("score", 0)),
                float(item.get("score", 0)),
            )
        else:
            merged_map[key] = dict(item)
    hits = sorted(
        list(merged_map.values()),
        key=lambda x: (float(x.get("score", 0)), x.get("message_date", "")),
        reverse=True,
    )
    if not hits:
        return "За останні 90 днів релевантних повідомлень у групі не знайдено.", "", "низький"

    top_hits = hits[:8]
    chat_lines = []
    for item in top_hits:
        author = item.get("full_name") or item.get("username") or item.get("user_id")
        text = (item.get("text") or "").replace("\n", " ").strip()
        if len(text) > 140:
            text = text[:137] + "..."
        dt = item.get("message_date", "")
        chat_lines.append(f"- {dt}: {author}: {text}")

    leader_lines = []
    if CHOIR_LEADER_USER_ID:
        leader_hits = [i for i in hits if str(i.get("user_id")) == str(CHOIR_LEADER_USER_ID)][:3]
        for item in leader_hits:
            text = (item.get("text") or "").replace("\n", " ").strip()
            if len(text) > 160:
                text = text[:157] + "..."
            leader_lines.append(f"- {item.get('message_date', '')}: {text}")

    confidence = "високий" if len(hits) >= 10 else "середній" if len(hits) >= 4 else "низький"
    return "\n".join(chat_lines), "\n".join(leader_lines), confidence


def _build_sources_block(chat_insights: str, leader_insights: str) -> str:
    source_lines = []
    for line in (chat_insights or "").splitlines()[:5]:
        m = re.match(r"^-\s*(.*?):\s*(.*?):\s*(.*)$", line)
        if m:
            dt, author, fragment = m.groups()
            source_lines.append(f"Джерело: {dt}, {author}, фрагмент: {fragment}")
    for line in (leader_insights or "").splitlines()[:3]:
        m = re.match(r"^-\s*(.*?):\s*(.*)$", line)
        if m:
            dt, fragment = m.groups()
            source_lines.append(
                f"Джерело (керівниця): {dt}, user_id={CHOIR_LEADER_USER_ID or 'n/a'}, фрагмент: {fragment}"
            )
    if not source_lines:
        return "Джерела: релевантних повідомлень у чаті не знайдено."
    return "\n".join(source_lines[:8])


def _cross_source_verification(events: list | None, chat_insights: str, sheet_names: list[str]) -> str:
    events = events or []
    cal_tokens = set()
    for ev in events[:40]:
        summary = (ev.get("summary") or "").lower()
        for tok in re.findall(r"[\w\u0400-\u04FF]{4,}", summary):
            cal_tokens.add(tok)
    chat_tokens = set(re.findall(r"[\w\u0400-\u04FF]{4,}", (chat_insights or "").lower()))
    notes_tokens = set()
    for name in sheet_names[:120]:
        for tok in re.findall(r"[\w\u0400-\u04FF]{4,}", (name or "").lower()):
            notes_tokens.add(tok)

    cal_chat = sorted(cal_tokens.intersection(chat_tokens))
    cal_notes = sorted(cal_tokens.intersection(notes_tokens))
    if not cal_chat and not cal_notes:
        return "Крос-перевірка: явних перетинів між чатом, календарем і нотами не виявлено."

    parts = []
    if cal_chat:
        parts.append(f"чат+календар: {', '.join(cal_chat[:8])}")
    if cal_notes:
        parts.append(f"календар+ноти: {', '.join(cal_notes[:8])}")
    return "Крос-перевірка підтверджує: " + " | ".join(parts)


def check_chatgpt_limit(user_id: str) -> bool:
    """
    Перевіряє ліміт запитів до ChatGPT для користувача.
    """
    usage_str = get_value(f"oberig_assistant_usage_{user_id}") or "0"
    usage = int(usage_str)
    max_requests = 10  # Ліміт запитів на день
    if usage >= max_requests:
        return False
    set_value(f"oberig_assistant_usage_{user_id}", str(usage + 1))
    return True


async def search_chat_content(
    update: Update, context: ContextTypes.DEFAULT_TYPE, query: str
):
    """
    Шукає повідомлення і файли в історії чату за ключовим словом.
    """
    messages = []
    async for message in update.effective_chat.get_history(limit=50):
        messages.append(message)
    # Зменшено до 50 для економії ресурсів

    results = []

    for message in messages:
        if message.text and query.lower() in message.text.lower():
            results.append(
                f"📩 {message.date}: {message.text[:50]}..."
            )  # Скорочено текст
        elif message.document:
            results.append(f"📂 {message.date}: {message.document.file_name}")
        elif message.photo:
            results.append(f"📸 {message.date}")

    if results:
        joined = "\n".join(results[:3])
        response = f"Ось, що знайдено в чаті! ✨\n\n{joined} #Оберіг 😊"
    else:
        response = "Вибач 😔, нічого не знайдено. Спробуй уточнити! #Оберіг 🌟"
    await update.message.reply_text(response)


async def search_drive_files(
    update: Update, context: ContextTypes.DEFAULT_TYPE, query: str
):
    """
    Шукає файли у Google Drive для помічника OBERIG.

    :param update: Telegram Update
    :param context: Telegram Context
    :param query: Пошуковий запит
    """
    try:
        # Виклик існуючої функції пошуку нот
        await search_notes(update, context, keyword=query)
    except Exception as e:
        logger.error(f"Помилка пошуку файлів: {e}")
        await update.message.reply_text(
            f"Вибач 😔, не вдалося знайти файли. Помилка: {e} #Оберіг"
        )


async def handle_oberig_assistant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обробляє текстові запити як помічник OBERIG, використовуючи ChatGPT із мінімальними токенами.
    """
    user_message = update.message.text.lower()
    user_id = str(update.effective_user.id)
    request_id = new_request_id()
    safe_user = mask_user_id(user_id)

    if not DEFAULT_GROUP_CHAT_ID:
        await _notify_admin_misconfig(
            context,
            "❗ Misconfig: DEFAULT_GROUP_CHAT_ID не задано. Асистент заблоковано (fail-closed).",
        )
        await update.message.reply_text(
            "❌ Функція тимчасово недоступна: не налаштовано DEFAULT_GROUP_CHAT_ID."
        )
        return

    if not await _is_user_in_main_group(update, context):
        await update.message.reply_text(
            "❌ Ця функція доступна лише учасникам основної групи хору."
        )
        return

    # Перевіряємо ліміт запитів
    if not check_chatgpt_limit(user_id):
        await update.message.reply_text(
            "❌ Наразі лише /start через ліміт. Спробуй пізніше! 😕 #Оберіг"
        )
        logger.warning("Ліміт запитів вичерпано user=%s request_id=%s", safe_user, request_id)
        return

    try:
        # Розширені варіанти пошуку файлів
        search_keywords = [
            "знайди",
            "пошук",
            "документ",
            "файл",
            "нота",
            "ноти",
            "sheet",
            "pdf",
            "music",
            "document",
        ]

        # Перевірка на пошук файлів
        if any(keyword in user_message for keyword in search_keywords):
            # Витягуємо ключове слово для пошуку
            search_query = (
                user_message.replace("знайди", "").replace("пошук", "").strip()
            )

            # Якщо є конкретний пошуковий запит
            if search_query:
                await search_drive_files(update, context, search_query)
                return

        # Перевіряємо, чи це запит на пошук у чаті
        if "знайди" in user_message or "пошук" in user_message:
            await search_chat_content(update, context, user_message)
            return

        # Визначаємо тип запиту і завантажуємо лише потрібні дані
        events = None
        latest_video = None
        popular_video = None
        top_videos = None

        # Ключові слова для фільтрації
        calendar_keywords = [
            "репетиція",
            "виступ",
            "день народження",
            "розклад",
            "події",
            "календар",
        ]
        youtube_keywords = ["ютуб", "відео", "записи", "youtube", "пісні"]

        # Завантажуємо дані залежно від ключових слів
        if any(keyword in user_message for keyword in calendar_keywords):
            events = get_calendar_events_cached(max_results=50)
        if any(keyword in user_message for keyword in youtube_keywords):
            latest_video = get_latest_youtube_video_cached()
            popular_video = get_most_popular_youtube_video_cached()
            top_videos = get_top_10_videos_cached()

        # Для загальних запитів завантажуємо мінімальні дані
        if not events and not any([latest_video, popular_video, top_videos]):
            events = get_calendar_events_cached(max_results=30)
            latest_video = get_latest_youtube_video_cached()
            popular_video = get_most_popular_youtube_video_cached()
            top_videos = get_top_10_videos_cached()

        # Шукаємо події за ключовими словами, обмежуючи кількість
        def search_events(keyword, events_list=None, limit=10):  # Зменшено ліміт до 10
            if not events_list:
                return []
            return [
                event
                for event in events_list
                if keyword.lower() in event.get("summary", "").lower()
                or keyword.lower() in (event.get("description", "") or "").lower()
                or keyword.lower() in (event.get("location", "") or "").lower()
            ][:limit]

        # Формуємо короткий контекст для ChatGPT з мінімальними даними
        calendar_context = "\n".join(
            [
                f"📅 {event.get('summary','Без назви')} - {event.get('start',{}).get('dateTime', event.get('start',{}).get('date'))} | "
                f"📍 {event.get('location','(місце не вказано)')} | "
                f"📝 {event.get('description','').strip()[:160]}"
                for event in (events[:30] if events else [])
            ]
        )
        rehearsal_events = "\n".join(
            [
                f"📅 {event.get('summary','Без назви')} - {event.get('start',{}).get('dateTime', event.get('start',{}).get('date'))} | "
                f"📍 {event.get('location','(місце не вказано)')} | "
                f"📝 {event.get('description','').strip()[:120]}"
                for event in search_events("репетиція", events)[:10]
            ]
        )
        performance_events = "\n".join(
            [
                f"📅 {event.get('summary','Без назви')} - {event.get('start',{}).get('dateTime', event.get('start',{}).get('date'))} | "
                f"📍 {event.get('location','(місце не вказано)')} | "
                f"📝 {event.get('description','').strip()[:120]}"
                for event in (search_events("виступ", events) + search_events("концерт", events))[:10]
            ]
        )
        birthday_events = "\n".join(
            [
                f"🎂 {event.get('summary','Без назви')} - {event.get('start',{}).get('dateTime', event.get('start',{}).get('date'))}"
                for event in search_events("день народження", events)[:10]
            ]
        )

        # Обробляємо запит про минулі події
        past_events = None
        last_event_info = ""
        past_count_info = ""
        next_event_info = ""

        if any(word in user_message for word in ["останн", "минул"]):
            past_events = get_past_events_cached(max_results=50)
            # спробуємо виділити ключове слово після "в "
            import re

            m = re.search(r"[вв]\s+([\w\s\u0400-\u04FF]+)", user_message)
            keyword = m.group(1).strip() if m else ""
            event = get_last_event(keyword) if keyword else (past_events[0] if past_events else None)
            if event:
                last_event_info = f"{event['summary']} - {event['start'].get('dateTime', event['start'].get('date'))}"

        if "наступн" in user_message:
            import re
            m = re.search(r"наступн[\w\s]*\s+([\w\s\u0400-\u04FF]+)", user_message)
            keyword = m.group(1).strip() if m else ""
            event = get_next_event(keyword) if keyword else None
            if event:
                next_event_info = f"{event['summary']} - {event['start'].get('dateTime', event['start'].get('date'))}"

        if "скільки" in user_message and "раз" in user_message:
            if past_events is None:
                past_events = get_past_events_cached(max_results=50)
            import re

            m = re.search(r"[вв]\s+([\w\s\u0400-\u04FF]+)", user_message)
            keyword = m.group(1).strip() if m else ""
            if keyword and past_events:
                count = sum(
                    1
                    for ev in past_events
                    if keyword.lower()
                    in " ".join(
                        [ev.get("summary", ""), ev.get("description", ""), ev.get("location", "")]
                    ).lower()
                )
                past_count_info = f"{keyword}: {count}"
        elif "скільки" in user_message and any(w in user_message for w in ["місяця", "року"]):
            import re
            now_dt = datetime.now()
            if "минулого місяця" in user_message:
                start_dt = (now_dt.replace(day=1) - timedelta(days=1)).replace(day=1)
                end_dt = start_dt + timedelta(days=31)
            elif "цього року" in user_message:
                start_dt = now_dt.replace(month=1, day=1)
                end_dt = now_dt
            else:
                start_dt = now_dt.replace(day=1)
                end_dt = now_dt
            m = re.search(r"[вв]\s+([\w\s\u0400-\u04FF]+)", user_message)
            keyword = m.group(1).strip() if m else ""
            events_range = get_events_in_range(start_dt, end_dt, keyword=keyword or None)
            past_count_info = f"{keyword}: {count_events(events_range)}"

        if any([latest_video, popular_video, top_videos]):
            top_list = ", ".join(
                [
                    f"{(title[:30] + '...' if len(title) > 30 else title)} ({url})"
                    for title, url, _ in (top_videos[:5] if top_videos else [])
                ]
            )
            video_context = (
                f"🎥 Найновіше: {latest_video}\n"
                f"⭐ Найпопулярніше: {popular_video}\n"
                f"🔝 Топ-10: {top_list}"
            )
        else:
            video_context = ""
        social_context = (
            "🌐 Facebook: https://www.facebook.com/profile.php?id=100094519583534"
        )
        chat_insights, leader_insights, confidence_level = _build_chat_insights(user_message)
        sources_block = _build_sources_block(chat_insights, leader_insights)
        conflicts = find_group_conflicts(str(DEFAULT_GROUP_CHAT_ID), days=120) if DEFAULT_GROUP_CHAT_ID else []
        conflict_hint = ""
        if conflicts:
            sample = conflicts[0]
            dates = sorted(
                {
                    it.get("event_date")
                    for it in sample.get("items", [])
                    if it.get("event_date")
                }
            )
            if dates:
                conflict_hint = f"Є потенційний конфлікт у чаті щодо '{sample.get('event_key')}': дати {', '.join(dates[:4])}."
        facts_recent = get_group_facts(
            str(DEFAULT_GROUP_CHAT_ID),
            fact_type=None,
            days=30,
            limit=40,
        ) if DEFAULT_GROUP_CHAT_ID else []
        facts_hint = ", ".join(
            sorted({f.get("fact_type", "") for f in facts_recent if f.get("fact_type")})
        )

        sheet_names = []
        try:
            sheets = await list_sheets(update=None, context=None, use_cache=True)
            for _, items in (sheets or {}).items():
                for item in items:
                    if item.get("name"):
                        sheet_names.append(item["name"])
        except Exception as e:
            logger.debug(f"Не вдалося отримати дані нот для крос-перевірки: {e}")
        cross_check = _cross_source_verification(events, chat_insights, sheet_names)

        # Створюємо dynamic_prompt з максимально коротким контекстом
        dynamic_prompt = f"{OBERIG_SYSTEM_PROMPT}\n\nДані для відповіді:"
        dynamic_prompt += f"\n- Події: {calendar_context}"
        dynamic_prompt += f"\n- Репетиції: {rehearsal_events}"
        dynamic_prompt += f"\n- Виступи: {performance_events}"
        dynamic_prompt += f"\n- Дні народження: {birthday_events}"
        if last_event_info:
            dynamic_prompt += f"\n- Остання подія: {last_event_info}"
        if past_count_info:
            dynamic_prompt += f"\n- Лічильник подій: {past_count_info}"
        if next_event_info:
            dynamic_prompt += f"\n- Наступна подія: {next_event_info}"
        dynamic_prompt += f"\n- YouTube: {video_context}"
        dynamic_prompt += f"\n- Соцмережі: {social_context}"
        dynamic_prompt += f"\n- За повідомленнями в чаті: {chat_insights}"
        dynamic_prompt += f"\n- Пріоритетні повідомлення керівниці: {leader_insights or 'немає релевантних'}"
        dynamic_prompt += f"\n- Рівень впевненості: {confidence_level}"
        dynamic_prompt += f"\n- Структуровані факти з чату: {facts_hint or 'немає'}"
        dynamic_prompt += f"\n- Конфлікти: {conflict_hint or 'не виявлено'}"
        dynamic_prompt += f"\n- Крос-верифікація: {cross_check}"
        dynamic_prompt += f"\n- Джерела: {sources_block}"
        dynamic_prompt += (
            "\nПобудуй відповідь структуровано: "
            "'За календарем', 'За повідомленнями в чаті', "
            "'Пріоритетні повідомлення керівниці', 'Що підтверджено'."
        )

        # Формуємо контекст для ChatGPT з мінімальною історією
        chat_history_str = get_value(f"oberig_chat_history_{user_id}") or "[]"
        chat_history = json.loads(chat_history_str) if chat_history_str else []
        messages = [{"role": "system", "content": dynamic_prompt}]
        messages.extend(
            chat_history[-3:]
        )  # Зменшено до 3 повідомлень для економії токенів
        messages.append({"role": "user", "content": user_message})

        # Запит до ChatGPT або асистента з мінімальними токенами для відповіді
        if ASSISTANT_ID:
            bot_response = await call_openai_assistant(
                messages=messages, assistant_id=ASSISTANT_ID
            )
        else:
            bot_response = await call_openai_chat(
                messages=messages,
                max_tokens=200,
                temperature=0.9,
            )
        # Доказовий формат відповіді + джерела
        bot_response = (
            f"Що відомо:\n{bot_response}\n\n"
            f"На чому базується:\n{sources_block}\n\n"
            f"Що непідтверджено:\n{conflict_hint or 'Явних суперечностей не виявлено.'}\n\n"
            f"Рівень впевненості:\n{confidence_level}\n\n"
            f"Що підтверджено:\n{cross_check}"
        )

        # Перевіряємо довжину повідомлення
        if len(bot_response) > 4096:
            bot_response = bot_response[:4090] + "..."
        await update.message.reply_text(bot_response)

        # Зберігаємо лише ключові повідомлення в історії (5 останніх)
        chat_history.append({"role": "user", "content": user_message})
        chat_history.append({"role": "assistant", "content": bot_response})
        set_value(f"oberig_chat_history_{user_id}", json.dumps(chat_history[-5:]))

        logger.info(
            "✅ OBERIG обробив запит user=%s request_id=%s %s",
            safe_user,
            request_id,
            text_meta(user_message),
        )

    except openai.OpenAIError as e:
        await update.message.reply_text(
            "❌ Проблеми з ChatGPT 😕. Спробуй /start! #Оберіг 🌟"
        )
        logger.error("Помилка ChatGPT user=%s request_id=%s: %s", safe_user, request_id, e)
    except Exception as e:
        await update.message.reply_text("❌ Помилка 😔. Спробуй /start! #Оберіг ✨")
        logger.error("Помилка в OBERIG user=%s request_id=%s: %s", safe_user, request_id, e)


__all__ = ["handle_oberig_assistant"]
