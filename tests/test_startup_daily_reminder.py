import importlib
import os
import sys
import types
import datetime
from unittest.mock import AsyncMock
import pytest

# Stub external dependencies before importing the module under test
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
    monkeypatch.setitem(sys.modules, 'telegram', tg)
    monkeypatch.setitem(sys.modules, 'telegram.ext', tg.ext)
    monkeypatch.setitem(sys.modules, 'telegram.constants', tg.constants)
    monkeypatch.setitem(sys.modules, 'telegram.helpers', tg.helpers)

    # other stubs
    monkeypatch.setitem(sys.modules, 'openai', types.SimpleNamespace(api_key=None, OpenAIError=Exception))
    dotenv_mod = types.ModuleType('dotenv')
    dotenv_mod.load_dotenv = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, 'dotenv', dotenv_mod)
    pytz_mod = types.ModuleType('pytz')
    pytz_mod.timezone = lambda name: datetime.timezone.utc
    monkeypatch.setitem(sys.modules, 'pytz', pytz_mod)

    cal_mod = types.ModuleType('utils.calendar_utils')
    cal_mod.get_calendar_events = lambda *a, **kw: []
    cal_mod.get_today_events = lambda *a, **kw: []
    monkeypatch.setitem(sys.modules, 'utils.calendar_utils', cal_mod)

    # minimal environment variables required by config
    monkeypatch.setenv('TELEGRAM_TOKEN', 'x')
    monkeypatch.setenv('GOOGLE_CREDENTIALS', 'x')
    monkeypatch.setenv('CALENDAR_ID', 'x')
    monkeypatch.setenv('YOUTUBE_API_KEY', 'x')
    monkeypatch.setenv('OBERIG_PLAYLIST_ID', 'x')

def test_startup_daily_reminder_triggers(monkeypatch, stub_dependencies):
    module = importlib.import_module('handlers.reminder_handler')
    importlib.reload(module)

    monkeypatch.setattr(module, 'get_value', lambda key: None)
    send_mock = AsyncMock()
    monkeypatch.setattr(module, 'send_daily_reminder', send_mock)

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2024, 1, 1, 22, 0, tzinfo=datetime.timezone.utc)

    monkeypatch.setattr(module, 'datetime', FakeDT)

    context = AsyncMock()
    import asyncio
    asyncio.run(module.startup_daily_reminder(context))

    send_mock.assert_awaited_once_with(context)


def test_main_schedules_startup_daily_reminder_with_grace(monkeypatch, stub_dependencies):
    data = open('main.py').read()
    assert 'misfire_grace_time' in data


def test_startup_daily_reminder_skips_during_quiet_hours(monkeypatch, stub_dependencies):
    module = importlib.import_module('handlers.reminder_handler')
    importlib.reload(module)

    monkeypatch.setattr(module, 'get_value', lambda key: None)
    send_mock = AsyncMock()
    monkeypatch.setattr(module, 'send_daily_reminder', send_mock)

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2024, 1, 1, 1, 0, tzinfo=datetime.timezone.utc)

    monkeypatch.setattr(module, 'datetime', FakeDT)

    context = AsyncMock()
    import asyncio
    asyncio.run(module.startup_daily_reminder(context))

    send_mock.assert_not_called()
