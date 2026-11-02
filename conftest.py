"""Ordinary tests cannot inherit production credentials or connect to external services."""
import os
import socket
import pytest


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch):
    monkeypatch.setenv('SMM_TESTING', '1')
    # Keep production CLI behavior unchanged while preventing tests from reading .env.
    monkeypatch.setattr('dotenv.load_dotenv', lambda *args, **kwargs: False)
    for key in list(os.environ):
        if key.startswith(('YOUTUBE_', 'TELEGRAM_', 'DZEN_')):
            monkeypatch.delenv(key)
    original = socket.socket.connect

    def local_only(sock, address):
        if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1', 'localhost'):
            raise AssertionError('External network is disabled in ordinary tests')
        return original(sock, address)
    monkeypatch.setattr(socket.socket, 'connect', local_only)

