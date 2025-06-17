import importlib
import types
import sys
import datetime
import pytest

@pytest.fixture(autouse=True)
def stub_dependencies(monkeypatch, tmp_path):
    tg = types.ModuleType('telegram')
    tg.ext = types.ModuleType('telegram.ext')
    tg.Update = object
    tg.ext.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=object)
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
    if 'utils.calendar_utils' in sys.modules:
        del sys.modules['utils.calendar_utils']

    logger_mod = types.ModuleType('utils.logger')
    logger_mod.logger = types.SimpleNamespace(info=lambda *a, **kw: None, warning=lambda *a, **kw: None, error=lambda *a, **kw: None)
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

    yield events_container


def test_get_upcoming_birthdays(monkeypatch, stub_dependencies):
    events_container = stub_dependencies
    events_container[:] = [
        {'summary': 'Anna – день народження', 'start': {'date': '2024-01-15'}},
        {'summary': 'Test', 'start': {'date': '2024-03-01'}},
    ]
    module = importlib.import_module('utils.calendar_utils')
    importlib.reload(module)

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2024, 1, 10, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(module, 'datetime', FakeDT)

    events = module.get_upcoming_birthdays(days=20)
    assert len(events) == 1 and events[0]['summary'].startswith('Anna')


def test_get_next_event(monkeypatch, stub_dependencies):
    events_container = stub_dependencies
    events_container[:] = [
        {'summary': 'Репетиція', 'start': {'date': '2024-01-15'}},
        {'summary': 'Репетиція', 'start': {'date': '2024-01-20'}},
    ]
    module = importlib.import_module('utils.calendar_utils')
    importlib.reload(module)

    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2024, 1, 10, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(module, 'datetime', FakeDT)

    ev = module.get_next_event('репетиція')
    assert ev['start']['date'] == '2024-01-15'


def test_events_in_range_and_count(monkeypatch, stub_dependencies):
    events_container = stub_dependencies
    events_container[:] = [
        {'summary': 'Виступ', 'location': 'Кірха', 'start': {'date': '2023-12-01'}},
        {'summary': 'Виступ', 'location': 'Кірха', 'start': {'date': '2023-12-15'}},
        {'summary': 'Репетиція', 'location': 'Зала', 'start': {'date': '2023-12-20'}},
    ]
    module = importlib.import_module('utils.calendar_utils')
    importlib.reload(module)

    start = datetime.datetime(2023, 12, 1, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2023, 12, 31, tzinfo=datetime.timezone.utc)
    events = module.get_events_in_range(start, end, keyword='виступ', location='Кірха')
    assert module.count_events(events) == 2
