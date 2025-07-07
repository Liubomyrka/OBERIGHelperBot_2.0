import importlib
import sys
import types
import sqlite3
import contextlib
import datetime
from unittest.mock import AsyncMock
import hashlib
import pytest

@pytest.fixture(autouse=True)
def stub_dependencies(monkeypatch):
    tg = types.ModuleType('telegram')
    tg.ext = types.ModuleType('telegram.ext')
    tg.constants = types.ModuleType('telegram.constants')
    tg.helpers = types.ModuleType('telegram.helpers')
    tg.Update = object
    tg.ext.JobQueue = object
    tg.ext.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=object)
    tg.constants.ParseMode = types.SimpleNamespace(MARKDOWN='markdown', MARKDOWN_V2='markdown_v2')
    tg.helpers.escape_markdown = lambda text, version=None: text
    class Btn:
        def __init__(self, *a, **kw):
            self.text = a[0] if a else ''
            self.kw = kw
    class Markup:
        def __init__(self, buttons):
            self.inline_keyboard = buttons
    tg.InlineKeyboardButton = Btn
    tg.InlineKeyboardMarkup = Markup
    monkeypatch.setitem(sys.modules, 'telegram', tg)
    monkeypatch.setitem(sys.modules, 'telegram.ext', tg.ext)
    monkeypatch.setitem(sys.modules, 'telegram.constants', tg.constants)
    monkeypatch.setitem(sys.modules, 'telegram.helpers', tg.helpers)

    openai_mod = types.SimpleNamespace(api_key=None, OpenAIError=Exception)
    openai_mod.beta = types.SimpleNamespace(
        threads=types.SimpleNamespace(
            create=lambda: types.SimpleNamespace(id='t'),
            messages=types.SimpleNamespace(create=lambda **kw: None, list=lambda **kw: types.SimpleNamespace(data=[])),
            runs=types.SimpleNamespace(create=lambda **kw: types.SimpleNamespace(id='r', status='queued'), retrieve=lambda **kw: types.SimpleNamespace(id='r', status='completed')),
        )
    )
    monkeypatch.setitem(sys.modules, 'openai', openai_mod)
    dotenv_mod = types.ModuleType('dotenv')
    dotenv_mod.load_dotenv = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, 'dotenv', dotenv_mod)
    pytz_mod = types.ModuleType('pytz')
    pytz_mod.timezone = lambda name: datetime.timezone.utc
    monkeypatch.setitem(sys.modules, 'pytz', pytz_mod)
    cal_mod = types.ModuleType('utils.calendar_utils')
    cal_mod.get_calendar_events = lambda *a, **kw: []
    cal_mod.get_today_events = lambda *a, **kw: []
    cal_mod.get_event_details = lambda *a, **kw: {}
    cal_mod.get_upcoming_birthdays_cached = lambda *a, **kw: []
    monkeypatch.setitem(sys.modules, 'utils.calendar_utils', cal_mod)
    logger_mod = types.ModuleType('utils.logger')
    logger_mod.logger = types.SimpleNamespace(info=lambda *a, **kw: None, warning=lambda *a, **kw: None, error=lambda *a, **kw: None, debug=lambda *a, **kw: None)
    monkeypatch.setitem(sys.modules, 'utils.logger', logger_mod)
    utils_mod = types.ModuleType('utils')
    utils_mod.init_openai_api = lambda: None
    utils_mod.call_openai_chat = lambda *a, **kw: None
    utils_mod.call_openai_assistant = lambda *a, **kw: None
    utils_mod.get_openai_assistant_id = lambda: None
    monkeypatch.setitem(sys.modules, 'utils', utils_mod)

    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row

    @contextlib.contextmanager
    def get_cursor():
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        finally:
            cursor.close()

    store = {}
    db_mod = types.ModuleType('database')
    db_mod.get_cursor = get_cursor
    db_mod.set_value = lambda k, v: store.__setitem__(k, v)
    db_mod.get_value = lambda k: store.get(k)
    db_mod.save_bot_message = lambda *a, **kw: None
    db_mod.get_event_reminder_hash = lambda *a, **kw: store.get('hash')
    db_mod.save_event_reminder_hash = lambda eid, rt, hv: store.__setitem__('saved', hv)
    db_mod.get_users_with_reminders = lambda: ['100']
    db_mod.db = types.SimpleNamespace(**{
        'get_event_reminder_hash': db_mod.get_event_reminder_hash,
        'save_event_reminder_hash': db_mod.save_event_reminder_hash,
        'get_users_with_reminders': db_mod.get_users_with_reminders,
    })
    monkeypatch.setitem(sys.modules, 'database', db_mod)

    for var in ['TELEGRAM_TOKEN', 'GOOGLE_CREDENTIALS', 'CALENDAR_ID', 'YOUTUBE_API_KEY', 'OBERIG_PLAYLIST_ID']:
        monkeypatch.setenv(var, 'x')

    return conn, store


def test_force_daily_reminder_overrides(monkeypatch, stub_dependencies):
    conn, store = stub_dependencies
    module = importlib.import_module('handlers.reminder_handler')
    importlib.reload(module)

    events = [{'id': '1', 'summary': 'E', 'start': {'dateTime': '2024-01-01T10:00:00Z'}}]
    monkeypatch.setattr(module, 'get_today_events', lambda: events)
    monkeypatch.setattr(module, 'get_active_chats', lambda: ['100'])
    monkeypatch.setattr(module, '_generate_short_id', lambda x: 's'+x)
    monkeypatch.setattr(module, '_cache_event_id', lambda s, f: None)
    monkeypatch.setattr(module, 'get_event_signature', lambda e: 'sig')

    store['daily_reminder_sent'] = '2024-01-01'
    store['daily_reminder_hash'] = hashlib.sha256('sig'.encode()).hexdigest()

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2024, 1, 1, 9, 0, tzinfo=datetime.timezone.utc)

    monkeypatch.setattr(module, 'datetime', FakeDT)

    context = types.SimpleNamespace(bot=types.SimpleNamespace(send_message=AsyncMock()))
    import asyncio
    asyncio.run(module.send_daily_reminder(context, force=True))

    assert context.bot.send_message.await_count == 2


def test_force_hourly_reminder_overrides(monkeypatch, stub_dependencies):
    conn, store = stub_dependencies
    module = importlib.import_module('handlers.reminder_handler')
    importlib.reload(module)

    events = [{'id': '1', 'summary': 'E', 'start': {'dateTime': '2024-01-01T09:30:00Z'}}]
    monkeypatch.setattr(module, 'get_today_events', lambda: events)
    store['hash'] = 'h1'
    monkeypatch.setattr(module, 'generate_event_hash', lambda e, t: 'h1')

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2024, 1, 1, 9, 0, tzinfo=datetime.timezone.utc)

    monkeypatch.setattr(module, 'datetime', FakeDT)

    context = types.SimpleNamespace(bot=types.SimpleNamespace(send_message=AsyncMock()))
    import asyncio
    asyncio.run(module.send_event_reminders(context, force=True))

    context.bot.send_message.assert_awaited()


def test_force_birthday_overrides(monkeypatch, stub_dependencies):
    conn, store = stub_dependencies
    module = importlib.import_module('handlers.reminder_handler')
    importlib.reload(module)

    monkeypatch.setattr(module, 'get_today_events', lambda: [{'id': '1', 'summary': 'Марія – день народження'}])
    monkeypatch.setattr(module, 'get_active_chats', lambda: ['100'])

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2024, 1, 1, 9, 0, tzinfo=datetime.timezone.utc)

    monkeypatch.setattr(module, 'datetime', FakeDT)

    module.create_birthday_greetings_table()
    conn.execute(
        "INSERT INTO birthday_greetings (event_id, date_sent, greeting_type, greeting_text) VALUES (?, ?, ?, ?)",
        ('1', '2024-01-01', 'morning', 'test')
    )
    conn.commit()

    context = types.SimpleNamespace(bot=types.SimpleNamespace(send_message=AsyncMock()))
    import asyncio
    asyncio.run(module.check_birthday_greetings(context, force=True))

    context.bot.send_message.assert_awaited()
