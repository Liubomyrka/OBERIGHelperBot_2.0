import importlib
import types
import sys
import datetime
from unittest.mock import AsyncMock
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
    def fake_escape(text, version=None):
        if version == 2:
            for ch in '_*[]()~`>#+-=|{}.!':
                text = text.replace(ch, '\\' + ch)
        return text
    tg.helpers.escape_markdown = fake_escape
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

    logger_mod = types.ModuleType('utils.logger')
    logger_mod.logger = types.SimpleNamespace(info=lambda *a, **kw: None, warning=lambda *a, **kw: None, error=lambda *a, **kw: None)
    monkeypatch.setitem(sys.modules, 'utils.logger', logger_mod)

    db_mod = types.ModuleType('database')
    db_mod.get_value = lambda k: None
    db_mod.set_value = lambda k, v: None
    db_mod.save_bot_message = lambda *a, **kw: None
    db_mod.get_cursor = lambda: None
    db_mod.db = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, 'database', db_mod)

    cal_mod = types.ModuleType('utils.calendar_utils')
    cal_mod.get_calendar_events = lambda *a, **kw: []
    cal_mod.get_today_events = lambda *a, **kw: []
    cal_mod.get_event_details = lambda *a, **kw: {}
    cal_mod.get_upcoming_birthdays_cached = lambda *a, **kw: []
    monkeypatch.setitem(sys.modules, 'utils.calendar_utils', cal_mod)

    utils_mod = types.ModuleType('utils')
    utils_mod.init_openai_api = lambda: None
    utils_mod.call_openai_chat = lambda *a, **kw: None
    utils_mod.call_openai_assistant = lambda *a, **kw: None
    utils_mod.get_openai_assistant_id = lambda: None
    monkeypatch.setitem(sys.modules, 'utils', utils_mod)

    for var in ['TELEGRAM_TOKEN', 'GOOGLE_CREDENTIALS', 'CALENDAR_ID', 'YOUTUBE_API_KEY', 'OBERIG_PLAYLIST_ID']:
        monkeypatch.setenv(var, 'x')

    return tg


def test_all_day_event_parsing(monkeypatch, stub_dependencies):
    tg = stub_dependencies
    module = importlib.import_module('handlers.reminder_handler')
    importlib.reload(module)

    events = [
        {'id': '1', 'summary': 'E1', 'start': {'date': '2024-01-01'}}
    ]
    monkeypatch.setattr(module, 'get_today_events', lambda: events)
    monkeypatch.setattr(module, 'get_active_chats', lambda: ['100'])
    monkeypatch.setattr(module, '_generate_short_id', lambda x: 's'+x)
    monkeypatch.setattr(module, '_cache_event_id', lambda s, f: None)

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2024, 1, 1, 9, 0, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(module, 'datetime', FakeDT)

    context = types.SimpleNamespace(bot=types.SimpleNamespace(send_message=AsyncMock()))
    import asyncio
    asyncio.run(module.send_daily_reminder(context))

    assert context.bot.send_message.await_count == 2
    header_args, header_kwargs = context.bot.send_message.await_args_list[0]
    assert '1 подія' in header_kwargs['text']
    args, kwargs = context.bot.send_message.await_args_list[1]
    assert '\\(весь день\\)' in kwargs['text']
    assert kwargs['parse_mode'] == tg.constants.ParseMode.MARKDOWN_V2
