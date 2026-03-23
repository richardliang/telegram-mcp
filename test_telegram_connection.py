import os

import pytest

os.environ["TELEGRAM_API_ID"] = "12345"
os.environ["TELEGRAM_API_HASH"] = "dummy_hash"

import main


class _FakeClient:
    def __init__(self, connected: bool):
        self.connected = connected

    def is_connected(self) -> bool:
        return self.connected


@pytest.mark.asyncio
async def test_ensure_telegram_client_starts_when_disconnected(monkeypatch):
    fake_client = _FakeClient(connected=False)
    start_calls = 0

    async def fake_start():
        nonlocal start_calls
        start_calls += 1
        fake_client.connected = True

    monkeypatch.setattr(main, "client", fake_client)
    monkeypatch.setattr(main, "_start_telegram_client", fake_start)

    await main._ensure_telegram_client()

    assert start_calls == 1
    assert fake_client.is_connected() is True


@pytest.mark.asyncio
async def test_ensure_telegram_client_skips_start_when_already_connected(monkeypatch):
    fake_client = _FakeClient(connected=True)

    async def fake_start():
        raise AssertionError("_start_telegram_client should not run")

    monkeypatch.setattr(main, "client", fake_client)
    monkeypatch.setattr(main, "_start_telegram_client", fake_start)

    await main._ensure_telegram_client()


@pytest.mark.asyncio
async def test_wrapped_tool_reconnects_before_running(monkeypatch):
    fake_client = _FakeClient(connected=False)
    start_calls = 0
    tool_calls = 0

    async def fake_start():
        nonlocal start_calls
        start_calls += 1
        fake_client.connected = True

    async def dummy_tool():
        nonlocal tool_calls
        tool_calls += 1
        return "ok"

    monkeypatch.setattr(main, "client", fake_client)
    monkeypatch.setattr(main, "_start_telegram_client", fake_start)

    wrapped = main._wrap_tool_with_telegram_connection(dummy_tool)
    result = await wrapped()

    assert result == "ok"
    assert start_calls == 1
    assert tool_calls == 1


@pytest.mark.asyncio
async def test_wrapped_tool_returns_formatted_error_when_reconnect_fails(monkeypatch):
    fake_client = _FakeClient(connected=False)
    tool_calls = 0

    async def fake_start():
        raise RuntimeError("connect failed")

    async def dummy_tool():
        nonlocal tool_calls
        tool_calls += 1
        return "ok"

    monkeypatch.setattr(main, "client", fake_client)
    monkeypatch.setattr(main, "_start_telegram_client", fake_start)

    wrapped = main._wrap_tool_with_telegram_connection(dummy_tool)
    result = await wrapped()

    assert "An error occurred (code:" in result
    assert tool_calls == 0
