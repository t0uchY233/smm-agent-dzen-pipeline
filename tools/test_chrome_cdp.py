"""CDP contracts from issue-2-auth, without its account-preflight dependencies."""
import asyncio
import os
from unittest.mock import MagicMock

import pytest

from tools import chrome_cdp as chrome


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    monkeypatch.setenv('DZEN_CDP_URL', 'http://127.0.0.1:19222')
    monkeypatch.setenv('DZEN_CDP_MODE', 'external')


@pytest.mark.parametrize('endpoint', [
    'https://127.0.0.1:9222', 'http://example.org:9222',
    'http://user:secret@127.0.0.1:9222', 'http://127.0.0.1:9222?secret=x',
    'http://127.0.0.1:9222/path', 'http://127.0.0.1:99999',
    'http://127.0.0.1:9222#secret', 'http://127.0.0.1:0',
])
def test_invalid_endpoint_is_blocked(endpoint, monkeypatch):
    monkeypatch.setenv('DZEN_CDP_URL', endpoint)
    with pytest.raises(ValueError):
        chrome.endpoint()


@pytest.mark.parametrize('endpoint', ['http://127.0.0.1:9222', 'http://localhost:19222/'])
def test_loopback_endpoint_is_accepted(endpoint, monkeypatch):
    monkeypatch.setenv('DZEN_CDP_URL', endpoint)
    assert chrome.endpoint() == endpoint.rstrip('/')


def test_given_external_tunnel_down_when_start_requested_then_no_local_browser(monkeypatch):
    monkeypatch.setattr(chrome, 'healthcheck', MagicMock(side_effect=OSError()))
    launch = MagicMock(side_effect=AssertionError('must not launch'))
    monkeypatch.setattr(chrome.subprocess, 'Popen', launch)
    monkeypatch.setattr(chrome, 'chrome_binary', lambda: pytest.fail('must not inspect local Chrome'))
    with pytest.raises(RuntimeError, match='External CDP'):
        chrome.ensure_chrome()
    launch.assert_not_called()


def test_given_existing_external_cdp_when_checked_then_profile_untouched(monkeypatch):
    monkeypatch.setattr(chrome, 'healthcheck', lambda: True)
    monkeypatch.setattr(chrome, 'chrome_binary', lambda: pytest.fail('must not inspect local Chrome'))
    assert chrome.ensure_chrome() == {'cdp': 'ready', 'started': False}


@pytest.mark.skipif(os.name == 'nt', reason='POSIX root guard')
def test_local_chrome_is_not_started_as_root(monkeypatch, tmp_path):
    monkeypatch.setenv('DZEN_CDP_MODE', 'local')
    monkeypatch.setenv('DZEN_CHROME_PROFILE', str(tmp_path / 'profile'))
    monkeypatch.setenv('DISPLAY', ':test')
    monkeypatch.setattr(chrome, 'healthcheck', lambda: False)
    monkeypatch.setattr(chrome, 'chrome_binary', lambda: '/fake/chrome')
    monkeypatch.setattr(chrome.os, 'geteuid', lambda: 0)
    launch = MagicMock(side_effect=AssertionError('must not launch'))
    monkeypatch.setattr(chrome.subprocess, 'Popen', launch)
    with pytest.raises(RuntimeError, match='desktop user'):
        chrome.ensure_chrome()
    launch.assert_not_called()


@pytest.mark.browser
def test_given_upstream_navigation_when_read_only_then_no_draft_click():
    async def scenario():
        from playwright.async_api import async_playwright
        from tools.publishing_dzen import transport_module
        channel = 'https://dzen.ru/profile/editor/example'
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(service_workers='block')
            await context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html',
                body='<button data-testid="add-publication-button" onclick="window.clicked=true">+</button>'))
            page = await context.new_page()
            module = transport_module()
            try:
                await module.open_channel(page, channel)
                assert page.url == channel
                assert not await page.evaluate('Boolean(window.clicked)')
                # A second read of the same channel does not navigate or mutate it.
                await module.open_channel(page, channel)
                assert not await page.evaluate('Boolean(window.clicked)')
            finally:
                await browser.close()
    asyncio.run(scenario())
