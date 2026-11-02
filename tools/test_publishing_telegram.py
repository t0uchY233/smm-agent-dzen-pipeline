"""Offline Telegram transport checks; never instantiate a real Telegram client."""
import ast
import asyncio
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
import subprocess
from unittest.mock import AsyncMock, MagicMock

import pytest

from tools import publishing_core as core
from tools import publishing_telegram as tg
from tools.test_publishing import release, FakeTelegram, link_youtube


@pytest.fixture
def telegram_errors():
    return pytest.importorskip('telethon.errors')


@pytest.fixture(autouse=True)
def no_host_allowlist(monkeypatch):
    monkeypatch.delenv('TELEGRAM_ALLOWED_CHAT_IDS', raising=False)


def test_tg_post_verbatim_blocks_match_upstream():
    root = Path(__file__).resolve().parents[1] / 'telegram-publish'
    source = (root / 'tg_post.py').read_text()
    nodes = {n.name: n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
    expected = {
        'parse_schedule_date', '_parse_allowed_chat_ids', 'check_chat_access',
        '_is_flood_wait', '_video_send_attributes', '_mp4_video_attributes',
        '_find_box', '_parse_moov', '_parse_mvhd', '_parse_trak', '_parse_tkhd',
    }
    checked = set()
    for line in (root / 'UPSTREAM.md').read_text().splitlines():
        columns = [c.strip().strip('`') for c in line.split('|')[1:-1]]
        if len(columns) != 4 or columns[2] != 'verbatim':
            continue
        name, location, _, digest = columns
        node = nodes[name]
        segment = ast.get_source_segment(source, node)
        assert hashlib.sha256(segment.encode()).hexdigest() == digest, name
        assert f'# upstream: {location} (verbatim)' in source
        checked.add(name)
    assert checked == expected


def test_telegram_schedule_parsed_via_upstream_msk(release, monkeypatch, telegram_errors):
    link_youtube(release)
    vendor = tg.telegram_vendor()
    parse = MagicMock(wraps=vendor.parse_schedule_date)
    monkeypatch.setattr(vendor, 'parse_schedule_date', parse)
    client = FakeTelegram()
    assert asyncio.run(tg.schedule_telegram(release, client)) == 'scheduled'
    parse.assert_called_once()
    assert datetime.fromisoformat(parse.call_args.args[0]) == datetime(2035, 1, 20, 11, tzinfo=timezone.utc)
    assert client.queue[0].date == datetime(2035, 1, 20, 11, tzinfo=timezone.utc)


def test_telegram_past_schedule_rejected(release, monkeypatch, telegram_errors):
    link_youtube(release)
    past = datetime(2000, 1, 1, tzinfo=timezone.utc)
    # Exercise upstream's error conversion independently of our stricter minute guard.
    monkeypatch.setattr(tg, 'require_future', lambda *args: past)
    client = FakeTelegram()
    with pytest.raises(core.ReleaseError, match='must be in the future'):
        asyncio.run(tg.schedule_telegram(release, client))
    assert client.uploads == client.calls == 0


def test_telegram_video_attributes_from_mp4(release, tmp_path, telegram_errors):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        pytest.skip('ffmpeg is unavailable')
    path = Path(release.manifest['video_path'])
    subprocess.run([
        ffmpeg, '-nostdin', '-y', '-v', 'error', '-filter_threads', '1',
        '-f', 'lavfi', '-i', 'testsrc=size=1920x1080:rate=25',
        '-f', 'lavfi', '-i', 'sine', '-t', '2', '-c:v', 'libx264',
        '-threads', '1', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(path),
    ], check=True, capture_output=True, timeout=90)
    release.state['approved_revision'] = core.revision(release.manifest)
    release.save()
    link_youtube(release)
    client = FakeTelegram()
    client.send_file = AsyncMock(wraps=client.send_file)
    assert asyncio.run(tg.schedule_telegram(release, client)) == 'scheduled'
    kwargs = client.send_file.call_args.kwargs
    attribute, = kwargs['attributes']
    assert (attribute.w, attribute.h, attribute.duration) == (1920, 1080, 2)
    assert attribute.supports_streaming is True
    assert kwargs['supports_streaming'] is True
    assert kwargs['mime_type'] == 'video/mp4'
    assert kwargs['force_document'] is False
    assert kwargs['parse_mode'] is None
    part = release.state['telegram']['parts'][0]
    assert part['id'] == client.queue[0].id
    assert part['document_id'] == 77


def test_telegram_unreadable_mp4_uses_existing_fallback(release, telegram_errors):
    link_youtube(release)
    client = FakeTelegram()
    client.send_file = AsyncMock(wraps=client.send_file)
    asyncio.run(tg.schedule_telegram(release, client))
    attribute, = client.send_file.call_args.kwargs['attributes']
    assert (attribute.w, attribute.h, attribute.duration) == (1920, 1080, 120)


def test_telegram_allowlist_blocks_before_upload(release, monkeypatch, telegram_errors):
    monkeypatch.setenv('TELEGRAM_ALLOWED_CHAT_IDS', '-1000000000999,@other')
    link_youtube(release)
    client = FakeTelegram()
    with pytest.raises(core.ReleaseError, match='TELEGRAM_ALLOWED_CHAT_IDS'):
        asyncio.run(tg.schedule_telegram(release, client))
    assert client.uploads == client.calls == 0
    assert not release.state.get('telegram', {}).get('parts')


@pytest.mark.parametrize('allowed', ['', '123', '-1000000000123'])
def test_telegram_allowlist_permits_target(release, monkeypatch, allowed, telegram_errors):
    monkeypatch.setenv('TELEGRAM_ALLOWED_CHAT_IDS', allowed)
    link_youtube(release)
    client = FakeTelegram()
    assert asyncio.run(tg.schedule_telegram(release, client)) == 'scheduled'
    assert client.calls == 1


@pytest.mark.parametrize('method', ['send_file', 'send_message'])
def test_telegram_flood_wait_is_not_retried(release, monkeypatch, method, telegram_errors):
    if method == 'send_message':
        release.manifest['telegram_text'] = 'a' * 2000
        release.state['approved_revision'] = core.revision(release.manifest)
        core.write_json(release.directory / 'manifest.json', release.manifest)
    link_youtube(release)
    client = FakeTelegram()
    send = AsyncMock(side_effect=telegram_errors.FloodWaitError(request=None, capture=37))
    monkeypatch.setattr(client, method, send)
    with pytest.raises(core.ReleaseError, match='37 с'):
        asyncio.run(tg.schedule_telegram(release, client))
    reopened = core.Release(release.directory)
    parts = reopened.state['telegram']['parts']
    assert parts[-1]['attempted'] is True
    assert parts[-1]['status'] == 'sending'
    assert 'id' not in parts[-1]
    if method == 'send_message':
        assert parts[0]['id'] == 11
        assert parts[0]['document_id'] == 77
    with pytest.raises(core.ReleaseError, match='Неизвестен результат'):
        asyncio.run(tg.schedule_telegram(reopened, client))
    send.assert_awaited_once()
    assert client.uploads == 1
    assert reopened.state['youtube']['id'] == 'video123'
