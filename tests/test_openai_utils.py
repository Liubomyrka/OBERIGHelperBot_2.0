import importlib
import types
import sys
import asyncio

import pytest

@pytest.fixture(autouse=True)
def stub_openai(monkeypatch):
    msg = types.SimpleNamespace(content='hi')
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
                            content=[types.SimpleNamespace(text=types.SimpleNamespace(value='hi'))]
                        )
                    ]
                ),
            ),
            runs=types.SimpleNamespace(
                create=lambda **kw: types.SimpleNamespace(id='r'),
                retrieve=lambda **kw: types.SimpleNamespace(id='r', status='completed'),
            ),
        )
    )
    monkeypatch.setitem(sys.modules, 'openai', openai_mod)


def test_call_openai_chat(stub_openai):
    utils = importlib.import_module('utils')
    importlib.reload(utils)
    result = asyncio.run(utils.call_openai_chat([{'role': 'user', 'content': 'hi'}]))
    assert result == 'hi'


def test_call_openai_assistant(stub_openai):
    utils = importlib.import_module('utils')
    importlib.reload(utils)
    result = asyncio.run(
        utils.call_openai_assistant([
            {'role': 'user', 'content': 'hi'}
        ], assistant_id='asst')
    )
    assert result == 'hi'
