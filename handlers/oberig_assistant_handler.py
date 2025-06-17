import os
import json
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
from database import get_value, set_value
from datetime import datetime
from handlers.drive_utils import list_sheets, send_sheet
from handlers.notes_utils import search_notes
from utils import init_openai_api, call_openai_chat

# Налаштування API-ключа OpenAI
init_openai_api()

# Скорочений системний контекст для зменшення токенів
OBERIG_SYSTEM_PROMPT = """
Ти — OBERIG, привітний та ввічливий помічник українського аматорського хорового колективу «Оберіг» у Німеччині. Хор популяризує українську культуру через музику, хоровий спів, репетиції та концерти за адресою Planigenstasse 4, Bad Kreuznach. Керівниця — Віта Романченко. Ти маєш доступ до календаря (репетиції, виступи, дні народження), відео на YouTube (плейлист: https://youtube.com/playlist?list=PLEkdnztUMQ7-05r94OMzHyCVMCXvkgrFn), Facebook (https://www.facebook.com/profile.php?id=100094519583534) і чату. Відповідай дружньо, ввічливо з емоджі 🎵😊, хештегами #Оберіг #Хор, різними смайлами, різними емоджі та прикрасами (✨, 🌟) для візуального покращення. Якщо запит не про хор, скажи: "Вибач 😔, я допоможу лише з хором «Оберіг». Спробуй інше питання! #Оберіг".
"""


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
    chat_id = update.effective_chat.id
    messages = await context.bot.get_chat_history(
        chat_id=chat_id, limit=50
    )  # Зменшено до 50 для економії ресурсів
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
        response = f"Ось, що знайдено в чаті! ✨\n\n{'\n'.join(results[:3])} #Оберіг 😊"
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

    # Перевіряємо ліміт запитів
    if not check_chatgpt_limit(user_id):
        await update.message.reply_text(
            "❌ Наразі лише /start через ліміт. Спробуй пізніше! 😕 #Оберіг"
        )
        logger.warning(f"Ліміт запитів вичерпано для {user_id}")
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
                if keyword.lower() in event["summary"].lower()
                or (
                    event.get("description", "").lower()
                    if event.get("description")
                    else ""
                )
            ][:limit]

        # Формуємо короткий контекст для ChatGPT з мінімальними даними
        calendar_context = "\n".join(
            [
                f"📅 {event['summary']} - {event['start'].get('dateTime', event['start'].get('date'))}"
                for event in (events[:30] if events else [])
            ]
        )
        rehearsal_events = "\n".join(
            [
                f"📅 {event['summary']} - {event['start'].get('dateTime', event['start'].get('date'))}"
                for event in search_events("репетиція", events)[:10]
            ]
        )
        performance_events = "\n".join(
            [
                f"📅 {event['summary']} - {event['start'].get('dateTime', event['start'].get('date'))}"
                for event in search_events("виступ", events)[:10]
            ]
        )
        birthday_events = "\n".join(
            [
                f"🎂 {event['summary']} - {event['start'].get('dateTime', event['start'].get('date'))}"
                for event in search_events("день народження", events)[:10]
            ]
        )

        # \u041e\u0431\u0440\u043e\u0431\u043b\u044f\u0454\u043c\u043e \u0437\u0430\u043f\u0438\u0442 \u043f\u0440\u043e \u043c\u0438\u043d\u0443\u043b\u0456 \u043f\u043e\u0434\u0456\u0457
        past_events = None
        last_event_info = ""
        past_count_info = ""
        next_event_info = ""

        if any(word in user_message for word in ["останн", "минул"]):
            past_events = get_past_events_cached(max_results=50)
            # \u0441\u043f\u0440\u043e\u0431\u0443\u0454\u043c\u043e \u0432\u0438\u0434\u0456\u043b\u0438\u0442\u0438 \u043a\u043b\u044e\u0447\u043e\u0432\u0435 \u0441\u043b\u043e\u0432\u043e \u043f\u0456\u0441\u043b\u044f "\u0432 "
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

        video_context = (
            f"🎥 Найновіше: {latest_video}\n"
            f"⭐ Найпопулярніше: {popular_video}\n"
            f"🔝 Топ-10: {', '.join([f'{title[:30] + '...' if len(title) > 30 else title} ({url})' for title, url, _ in (top_videos[:5] if top_videos else [])])}"  # Оновлюємо на Топ-10
            if any([latest_video, popular_video, top_videos])
            else ""
        )
        social_context = (
            "🌐 Facebook: https://www.facebook.com/profile.php?id=100094519583534"
        )

        # \u0421\u0442\u0432\u043e\u0440\u044e\u0454\u043c\u043e dynamic_prompt \u0437 \u043c\u0430\u043a\u0441\u0438\u043c\u0430\u043b\u044c\u043d\u043e \u043a\u043e\u0440\u043e\u0442\u043a\u0438\u043c \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442\u043e\u043c
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

        # Формуємо контекст для ChatGPT з мінімальною історією
        chat_history_str = get_value(f"oberig_chat_history_{user_id}") or "[]"
        chat_history = json.loads(chat_history_str) if chat_history_str else []
        messages = [{"role": "system", "content": dynamic_prompt}]
        messages.extend(
            chat_history[-3:]
        )  # Зменшено до 3 повідомлень для економії токенів
        messages.append({"role": "user", "content": user_message})

        # Запит до ChatGPT з мінімальними токенами для відповіді
        bot_response = await call_openai_chat(
            messages=messages,
            max_tokens=200,
            temperature=0.9,
        )
        # Додаємо емоджі, хештеги, смайли та прикраси
        bot_response = (
            f"🎵 {bot_response} 😊 #Оберіг ✨\n🌟 Хочеш дізнатися більше? 🙂 #Хор"
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
            f"✅ OBERIG обробив запит від {user_id}: {user_message} з мінімальними токенами"
        )

    except openai.OpenAIError as e:
        await update.message.reply_text(
            "❌ Проблеми з ChatGPT 😕. Спробуй /start! #Оберіг 🌟"
        )
        logger.error(f"Помилка ChatGPT для {user_id}: {e}")
    except Exception as e:
        await update.message.reply_text("❌ Помилка 😔. Спробуй /start! #Оберіг ✨")
        logger.error(f"Помилка в OBERIG для {user_id}: {e}")


__all__ = ["handle_oberig_assistant"]