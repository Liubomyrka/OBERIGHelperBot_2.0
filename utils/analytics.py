# analytics.py

from datetime import datetime, timedelta
from database import get_value, set_value
import json
from utils.logger import logger
from telegram.helpers import escape_markdown


class Analytics:
    def __init__(self):
        self.commands_stats_key = "commands_stats"
        self.users_activity_key = "users_activity"
        self.popular_queries_key = "popular_queries"

    async def log_command(self, user_id: int, command: str):
        """
        Логує використання команди користувачем
        """
        try:
            # Отримуємо поточну статистику команд
            stats = json.loads(get_value(self.commands_stats_key) or "{}")
            today = datetime.now().strftime("%Y-%m-%d")

            if today not in stats:
                stats[today] = {}
            if command not in stats[today]:
                stats[today][command] = 0

            stats[today][command] += 1

            # Зберігаємо оновлену статистику
            set_value(self.commands_stats_key, json.dumps(stats))

            # Оновлюємо активність користувача
            await self.update_user_activity(user_id, command)

            logger.info(f"✅ Залоговано використання команди {command}")
        except Exception as e:
            logger.error(f"❌ Помилка при логуванні команди: {e}")

    async def update_user_activity(self, user_id: int, action: str):
        """
        Оновлює інформацію про активність користувача
        """
        try:
            activity = json.loads(get_value(self.users_activity_key) or "{}")
            user_id = str(user_id)
            timestamp = datetime.now().isoformat()

            if user_id not in activity:
                activity[user_id] = {
                    "first_seen": timestamp,
                    "last_seen": timestamp,
                    "actions_count": 0,
                    "last_actions": [],
                }

            # Оновлюємо дані користувача
            activity[user_id]["last_seen"] = timestamp
            activity[user_id]["actions_count"] += 1

            # Зберігаємо останні 10 дій
            actions = activity[user_id].get("last_actions", [])
            actions.append({"action": action, "timestamp": timestamp})
            activity[user_id]["last_actions"] = actions[-10:]

            set_value(self.users_activity_key, json.dumps(activity))
            logger.info(f"✅ Оновлено активність користувача {user_id}")
        except Exception as e:
            logger.error(f"❌ Помилка при оновленні активності користувача: {e}")

    async def log_query(self, query: str):
        """
        Логує пошуковий запит для аналізу популярних запитів
        """
        try:
            queries = json.loads(get_value(self.popular_queries_key) or "{}")
            today = datetime.now().strftime("%Y-%m-%d")

            if today not in queries:
                queries[today] = {}

            query = query.lower().strip()
            if query not in queries[today]:
                queries[today][query] = 0

            queries[today][query] += 1

            set_value(self.popular_queries_key, json.dumps(queries))
            logger.info(f"✅ Залоговано пошуковий запит: {query}")
        except Exception as e:
            logger.error(f"❌ Помилка при логуванні запиту: {e}")

    async def get_commands_stats(self, days: int = 7) -> dict:
        """
        Повертає статистику використання команд за вказаний період
        """
        try:
            stats = json.loads(get_value(self.commands_stats_key) or "{}")
            result = {}

            # Фільтруємо статистику за вказаний період
            start_date = datetime.now() - timedelta(days=days)
            for date_str, commands in stats.items():
                date = datetime.strptime(date_str, "%Y-%m-%d")
                if date >= start_date:
                    for command, count in commands.items():
                        if command not in result:
                            result[command] = 0
                        result[command] += count

            return result
        except Exception as e:
            logger.error(f"❌ Помилка при отриманні статистики команд: {e}")
            return {}

    async def get_active_users(self, days: int = 7) -> dict:
        """
        Повертає статистику активних користувачів за вказаний період
        """
        try:
            activity = json.loads(get_value(self.users_activity_key) or "{}")
            active_users = {}
            start_date = datetime.now() - timedelta(days=days)

            for user_id, data in activity.items():
                last_seen = datetime.fromisoformat(data["last_seen"])
                if last_seen >= start_date:
                    active_users[user_id] = {
                        "actions_count": data["actions_count"],
                        "last_seen": data["last_seen"],
                    }

            return active_users
        except Exception as e:
            logger.error(
                f"❌ Помилка при отриманні статистики активних користувачів: {e}"
            )
            return {}

    async def get_popular_queries(self, days: int = 7, limit: int = 10) -> list:
        """
        Повертає найпопулярніші запити за вказаний період
        """
        try:
            queries = json.loads(get_value(self.popular_queries_key) or "{}")
            combined_queries = {}
            start_date = datetime.now() - timedelta(days=days)

            for date_str, daily_queries in queries.items():
                date = datetime.strptime(date_str, "%Y-%m-%d")
                if date >= start_date:
                    for query, count in daily_queries.items():
                        if query not in combined_queries:
                            combined_queries[query] = 0
                        combined_queries[query] += count

            # Сортуємо за популярністю і повертаємо топ limit запитів
            sorted_queries = sorted(
                combined_queries.items(), key=lambda x: x[1], reverse=True
            )
            return sorted_queries[:limit]
        except Exception as e:
            logger.error(f"❌ Помилка при отриманні популярних запитів: {e}")
            return []

    async def generate_analytics_report(self, days: int = 7) -> str:
        """
        Генерує повний звіт з аналітикою
        """
        try:
            commands_stats = await self.get_commands_stats(days)
            active_users = await self.get_active_users(days)
            popular_queries = await self.get_popular_queries(days)

            report = f"📊 *Аналітичний звіт за {days} днів*\n\n"

            # Статистика команд
            report += "*Використання команд:*\n"
            for command, count in sorted(
                commands_stats.items(), key=lambda x: x[1], reverse=True
            ):
                safe_cmd = escape_markdown(command, version=1)
                report += f"/{safe_cmd}: {count} разів\n"

            # Активні користувачі
            report += f"\n👥 *Активні користувачі:* {len(active_users)}\n"

            # Популярні запити
            if popular_queries:
                report += "\n🔍 *Популярні запити:*\n"
                for query, count in popular_queries:
                    safe_q = escape_markdown(str(query), version=1)
                    report += f"• {safe_q}: {count} разів\n"

            return report
        except Exception as e:
            logger.error(f"❌ Помилка при генерації звіту: {e}")
            return "❌ Помилка при генерації звіту"
