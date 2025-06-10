import importlib
import types
import sys
import asyncio
import pytest

@pytest.fixture(autouse=True)
def stub_dependencies(monkeypatch):
    tg = types.ModuleType('telegram')
    tg.ext = types.ModuleType('telegram.ext')
    tg.Update = object
    tg.ext.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=object)
    class KB:
        def __init__(self, *a, **k):
            pass
    tg.KeyboardButton = KB
    tg.ReplyKeyboardMarkup = lambda *a, **kw: None
    tg.InputFile = object
    monkeypatch.setitem(sys.modules, 'telegram', tg)
    monkeypatch.setitem(sys.modules, 'telegram.ext', tg.ext)

    # stub google client libs used by drive_utils
    ga_flow = types.ModuleType('google_auth_oauthlib.flow')
    ga_flow.InstalledAppFlow = object
    monkeypatch.setitem(sys.modules, 'google_auth_oauthlib.flow', ga_flow)
    ga_req = types.ModuleType('google.auth.transport.requests')
    ga_req.Request = object
    monkeypatch.setitem(sys.modules, 'google.auth.transport.requests', ga_req)
    ga_creds = types.ModuleType('google.oauth2.credentials')
    ga_creds.Credentials = object
    monkeypatch.setitem(sys.modules, 'google.oauth2.credentials', ga_creds)
    sa_mod = types.ModuleType('google.oauth2.service_account')
    sa_mod.Credentials = types.SimpleNamespace(from_service_account_file=lambda *a, **kw: object())
    monkeypatch.setitem(sys.modules, 'google.oauth2.service_account', sa_mod)

    google_mod = types.ModuleType('google')
    oauth2_mod = types.ModuleType('google.oauth2')
    oauth2_mod.service_account = sa_mod
    google_mod.oauth2 = oauth2_mod
    monkeypatch.setitem(sys.modules, 'google', google_mod)
    monkeypatch.setitem(sys.modules, 'google.oauth2', oauth2_mod)
    gapi = types.ModuleType('googleapiclient.discovery')
    gapi.build = lambda *a, **kw: types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, 'googleapiclient.discovery', gapi)
    errors_mod = types.ModuleType('googleapiclient.errors')
    errors_mod.HttpError = Exception
    monkeypatch.setitem(sys.modules, 'googleapiclient.errors', errors_mod)
    http_mod = types.ModuleType('googleapiclient.http')
    http_mod.MediaIoBaseDownload = object
    monkeypatch.setitem(sys.modules, 'googleapiclient.http', http_mod)

    monkeypatch.setitem(sys.modules, 'openai', types.SimpleNamespace(api_key=None))
    dotenv_mod = types.ModuleType('dotenv')
    dotenv_mod.load_dotenv = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, 'dotenv', dotenv_mod)

    monkeypatch.setenv('TELEGRAM_TOKEN', 'x')
    monkeypatch.setenv('GOOGLE_CREDENTIALS', 'x')
    monkeypatch.setenv('CALENDAR_ID', 'x')
    monkeypatch.setenv('YOUTUBE_API_KEY', 'x')
    monkeypatch.setenv('OBERIG_PLAYLIST_ID', 'x')


def test_search_notes(monkeypatch, stub_dependencies):
    module = importlib.import_module('handlers.notes_utils')
    importlib.reload(module)

    async def fake_list(update=None, context=None):
        return {'all': [{'name': 'Test Note', 'id': '1'}]}

    monkeypatch.setattr(module, 'list_sheets', fake_list)

    class Msg:
        text = 'test'
        async def reply_text(self, *a, **kw):
            return types.SimpleNamespace(message_id=1)
    update = types.SimpleNamespace(effective_chat=types.SimpleNamespace(id=1, type='private'), message=Msg())
    context = types.SimpleNamespace(user_data={})

    results = asyncio.run(module.search_notes(update, context, keyword='Test'))
    assert results and results[0]['id'] == '1'
