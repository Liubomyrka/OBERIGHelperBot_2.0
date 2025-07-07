import importlib
import sys
import types
import sqlite3
import contextlib
import datetime
from unittest.mock import AsyncMock
import pytest

@pytest.fixture(autouse=True)
def stub_dependencies(monkeypatch):
    # telegram stubs
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
            pass
    class Markup:
        def __init__(self, buttons):
            self.inline_keyboard = buttons
    tg.InlineKeyboardButton = Btn
    tg.InlineKeyboardMarkup = Markup
    monkeypatch.setitem(sys.modules, 'telegram', tg)
    monkeypatch.setitem(sys.modules, 'telegram.ext', tg.ext)
    monkeypatch.setitem(sys.modules, 'telegram.constants', tg.constants)
    monkeypatch.setitem(sys.modules, 'telegram.helpers', tg.helpers)

    # openai stub
    msg = types.SimpleNamespace(content='Вітаємо!')
    openai_mod = types.ModuleType('openai')
    openai_mod.api_key = None
    openai_mod.OpenAIError = Exception
    openai_mod.chat = types.SimpleNamespace(
        completions=types.SimpleNamespace(
            create=lambda **kw: types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=msg)]
            )
        )
    )
    openai_mod.beta = types.SimpleNamespace(
        threads=types.SimpleNamespace(
            create=lambda: types.SimpleNamespace(id='t'),
            messages=types.SimpleNamespace(
                create=lambda **kw: None,
                list=lambda **kw: types.SimpleNamespace(
                    data=[
                        types.SimpleNamespace(
                            content=[
                                types.SimpleNamespace(
                                    text=types.SimpleNamespace(value='Вітаємо!')
                                )
                            ]
                        )
                    ]
                ),
            ),
            runs=types.SimpleNamespace(
                create=lambda **kw: types.SimpleNamespace(id='r', status='queued'),
                retrieve=lambda **kw: types.SimpleNamespace(id='r', status='completed'),
            ),
        )
    )
    monkeypatch.setitem(sys.modules, 'openai', openai_mod)

    # other libs
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
    async def fake_call(*a, **kw):
        return 'Вітаємо!'
    utils_mod.call_openai_chat = fake_call
    utils_mod.call_openai_assistant = fake_call
    utils_mod.get_openai_assistant_id = lambda: None
    monkeypatch.setitem(sys.modules, 'utils', utils_mod)

    # in-memory database
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

    db_mod = types.ModuleType('database')
    db_mod.get_cursor = get_cursor
    db_mod.set_value = lambda *a, **kw: None
    db_mod.get_value = lambda *a, **kw: None
    db_mod.save_bot_message = lambda *a, **kw: None
    db_mod.db = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, 'database', db_mod)

    for var in ['TELEGRAM_TOKEN', 'GOOGLE_CREDENTIALS', 'CALENDAR_ID', 'YOUTUBE_API_KEY', 'OBERIG_PLAYLIST_ID']:
        monkeypatch.setenv(var, 'x')

    yield conn

import asyncio


def test_check_birthday_greetings_sends_and_stores(monkeypatch, stub_dependencies):
    module = importlib.import_module('handlers.reminder_handler')
    importlib.reload(module)

    conn = stub_dependencies

    monkeypatch.setattr(module, 'get_today_events', lambda: [{'id': '1', 'summary': 'Марія – день народження'}])
    monkeypatch.setattr(module, 'get_active_chats', lambda: ['100'])

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2024, 1, 1, 9, 0, tzinfo=datetime.timezone.utc)

    monkeypatch.setattr(module, 'datetime', FakeDT)

    module.create_birthday_greetings_table()

    context = types.SimpleNamespace(bot=types.SimpleNamespace(send_message=AsyncMock()))
    asyncio.run(module.check_birthday_greetings(context))

    context.bot.send_message.assert_awaited_once()
    args, kwargs = context.bot.send_message.await_args
    assert kwargs['parse_mode'] == module.ParseMode.MARKDOWN_V2
    assert '\\' not in kwargs['text']

    rows = conn.execute('SELECT * FROM birthday_greetings').fetchall()
    assert len(rows) == 1


def test_check_birthday_greetings_skips_if_already_sent(monkeypatch, stub_dependencies):
    module = importlib.import_module('handlers.reminder_handler')
    importlib.reload(module)

    conn = stub_dependencies

    monkeypatch.setattr(module, 'get_today_events', lambda: [{'id': '1', 'summary': 'Марія – день народження'}])
    monkeypatch.setattr(module, 'get_active_chats', lambda: ['100'])

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2024, 1, 1, 9, 0, tzinfo=datetime.timezone.utc)

    monkeypatch.setattr(module, 'datetime', FakeDT)

    module.create_birthday_greetings_table()
    # insert existing record
    conn.execute(
        "INSERT INTO birthday_greetings (event_id, date_sent, greeting_type, greeting_text) VALUES (?, ?, ?, ?)",
        ('1', '2024-01-01', 'morning', 'test')
    )
    conn.commit()

    context = types.SimpleNamespace(bot=types.SimpleNamespace(send_message=AsyncMock()))
    asyncio.run(module.check_birthday_greetings(context))

    context.bot.send_message.assert_not_awaited()


def test_inflect_to_dative(monkeypatch, stub_dependencies):
    module = importlib.import_module('handlers.reminder_handler')
    importlib.reload(module)

    assert module.inflect_to_dative('Галина') == 'Галині'


def test_fallback_uses_dative(monkeypatch, stub_dependencies):
    module = importlib.import_module('handlers.reminder_handler')
    importlib.reload(module)

    async def raise_error(*a, **kw):
        raise module.openai.OpenAIError('err')

    monkeypatch.setattr(module, 'call_openai_chat', raise_error)

    greeting = asyncio.run(module.generate_birthday_greeting('Галина', 'morning'))
    assert 'Галині' in greeting


def test_startup_birthday_check_runs_any_time(monkeypatch, stub_dependencies):
    module = importlib.import_module('handlers.reminder_handler')
    importlib.reload(module)

    run_mock = AsyncMock()
    monkeypatch.setattr(module, 'check_birthday_greetings', run_mock)

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2024, 1, 1, 14, 0, tzinfo=datetime.timezone.utc)

    monkeypatch.setattr(module, 'datetime', FakeDT)

    context = types.SimpleNamespace()
    asyncio.run(module.startup_birthday_check(context))

    run_mock.assert_awaited_once_with(context)

