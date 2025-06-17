import importlib
import types
import sys
import datetime
import asyncio
import pytest

@pytest.fixture(autouse=True)
def stub_dependencies(monkeypatch, tmp_path):
    tg = types.ModuleType('telegram')
    tg.ext = types.ModuleType('telegram.ext')
    tg.Update = object
    tg.ext.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=object)
    class KB:
        def __init__(self, *a, **k):
            pass
    tg.KeyboardButton = KB
    tg.ReplyKeyboardMarkup = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, 'telegram', tg)
    monkeypatch.setitem(sys.modules, 'telegram.ext', tg.ext)

    openai_mod = types.ModuleType('openai')
    openai_mod.api_key = None
    openai_mod.OpenAIError = Exception
    openai_mod.beta = types.SimpleNamespace(
        threads=types.SimpleNamespace(
            create=lambda: types.SimpleNamespace(id='t'),
            messages=types.SimpleNamespace(
                create=lambda **kw: None,
                list=lambda **kw: types.SimpleNamespace(data=[]),
            ),
            runs=types.SimpleNamespace(
                create=lambda **kw: types.SimpleNamespace(id='r', status='queued'),
                retrieve=lambda **kw: types.SimpleNamespace(id='r', status='completed'),
            ),
        )
    )
    monkeypatch.setitem(sys.modules, 'openai', openai_mod)

    dotenv_mod = types.ModuleType('dotenv')
    dotenv_mod.load_dotenv = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, 'dotenv', dotenv_mod)

    pytz_mod = types.ModuleType('pytz')
    pytz_mod.timezone = lambda name: datetime.timezone.utc
    monkeypatch.setitem(sys.modules, 'pytz', pytz_mod)

    cred = tmp_path / 'cred.json'
    cred.write_text('{}')
    for var in ['TELEGRAM_TOKEN', 'GOOGLE_CREDENTIALS', 'CALENDAR_ID', 'YOUTUBE_API_KEY', 'OBERIG_PLAYLIST_ID']:
        monkeypatch.setenv(var, str(cred))
    if 'config' in sys.modules:
        del sys.modules['config']
    for mod in ['utils.calendar_utils', 'handlers.oberig_assistant_handler']:
        if mod in sys.modules:
            del sys.modules[mod]

    logger_mod = types.ModuleType('utils.logger')
    logger_mod.logger = types.SimpleNamespace(info=lambda *a, **kw: None, warning=lambda *a, **kw: None, error=lambda *a, **kw: None, debug=lambda *a, **kw: None)
    monkeypatch.setitem(sys.modules, 'utils.logger', logger_mod)

    events_container = []
    class FakeEvents:
        def list(self, **kwargs):
            return types.SimpleNamespace(execute=lambda: {'items': events_container})
    class FakeService:
        def events(self):
            return FakeEvents()
    gapi_mod = types.ModuleType('googleapiclient.discovery')
    gapi_mod.build = lambda *a, **kw: FakeService()
    gapi_mod.CACHE = None
    googleapi_root = types.ModuleType('googleapiclient')
    googleapi_root.discovery = gapi_mod
    monkeypatch.setitem(sys.modules, 'googleapiclient', googleapi_root)
    monkeypatch.setitem(sys.modules, 'googleapiclient.discovery', gapi_mod)

    sa_mod = types.ModuleType('google.oauth2.service_account')
    sa_mod.Credentials = types.SimpleNamespace(from_service_account_file=lambda *a, **kw: object())
    oauth2_mod = types.ModuleType('google.oauth2')
    oauth2_mod.service_account = sa_mod
    google_mod = types.ModuleType('google')
    google_mod.oauth2 = oauth2_mod
    monkeypatch.setitem(sys.modules, 'google', google_mod)
    monkeypatch.setitem(sys.modules, 'google.oauth2', oauth2_mod)
    monkeypatch.setitem(sys.modules, 'google.oauth2.service_account', sa_mod)

    err_mod = types.ModuleType('googleapiclient.errors')
    err_mod.HttpError = Exception
    monkeypatch.setitem(sys.modules, 'googleapiclient.errors', err_mod)

    yt_mod = types.ModuleType('utils.youtube_utils')
    yt_mod.get_youtube_service = lambda: None
    monkeypatch.setitem(sys.modules, 'utils.youtube_utils', yt_mod)

    drive_mod = types.ModuleType('handlers.drive_utils')
    drive_mod.list_sheets = lambda *a, **kw: {}
    drive_mod.send_sheet = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, 'handlers.drive_utils', drive_mod)

    notes_mod = types.ModuleType('handlers.notes_utils')
    notes_mod.search_notes = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, 'handlers.notes_utils', notes_mod)

    db_store = {}
    db_mod = types.ModuleType('database')
    db_mod.get_value = lambda k: db_store.get(k)
    db_mod.set_value = lambda k, v: db_store.__setitem__(k, v)
    db_mod.get_cursor = lambda: None
    monkeypatch.setitem(sys.modules, 'database', db_mod)

    yield events_container

def test_get_past_events_returns_only_past(monkeypatch, stub_dependencies):
    events_container = stub_dependencies
    events_container[:] = [
        {'summary': 'future', 'start': {'dateTime': '2024-01-20T10:00:00Z'}},
        {'summary': 'past1', 'start': {'dateTime': '2024-01-01T10:00:00Z'}},
        {'summary': 'past2', 'start': {'dateTime': '2024-01-05T10:00:00Z'}},
    ]
    module = importlib.import_module('utils.calendar_utils')
    importlib.reload(module)

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2024, 1, 10, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(module, 'datetime', FakeDT)

    events = module.get_past_events(max_results=10)
    assert [e['summary'] for e in events] == ['past2', 'past1']


def test_get_last_event_returns_latest(monkeypatch, stub_dependencies):
    events_container = stub_dependencies
    events_container[:] = [
        {'summary': 'Виступ у Ніколаус кірше', 'description': '', 'location': '', 'start': {'dateTime': '2023-12-01T10:00:00Z'}},
        {'summary': 'Виступ у Ніколаус кірше', 'description': '', 'location': '', 'start': {'dateTime': '2024-01-03T10:00:00Z'}},
    ]
    module = importlib.import_module('utils.calendar_utils')
    importlib.reload(module)

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2024, 1, 10, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(module, 'datetime', FakeDT)

    event = module.get_last_event('ніколаус')
    assert event['start']['dateTime'] == '2024-01-03T10:00:00Z'


