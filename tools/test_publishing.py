import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from tools import publishing_core as core
from tools import publishing_youtube as yt
from tools import publishing_telegram as tg
from tools.publish_release import main, record_browser


@pytest.fixture
def release(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    files = {}
    for key, name in [('docx_path', '2035-01-20-1400-Тема.docx'),
                      ('video_path', '2035-01-20-1400-Тема.mp4'),
                      ('thumbnail_path', 'cover.png'), ('render_report_path', 'qa.json')]:
        path = tmp_path / name
        path.write_bytes(b'artifact')
        files[key] = str(path)
    m = dict(files, title='Тема', description='Описание', made_for_kids=False,
             scheduled_at='2035-01-20 14:00', timezone='Europe/Moscow',
             platforms=['youtube', 'telegram', 'dzen'], youtube_channel='UC_TEST',
             telegram_channel='-100123', dzen_channel='https://dzen.ru/test',
             telegram_text='Текст {youtube_url}', dzen_article='Статья {youtube_url}')
    directory = core.prepare(m, tmp_path / 'release')
    result = core.Release(directory)
    result.state['approved_revision'] = core.revision(m)
    result.save()
    monkeypatch.setenv('YOUTUBE_CHANNEL_ID', 'UC_TEST')
    monkeypatch.setenv('TELEGRAM_CHANNEL_ID', '-100123')
    monkeypatch.setattr(yt, 'probe_video', lambda p: 120)
    monkeypatch.setattr(tg, 'probe_video', lambda p: 120)
    return result


def test_timezone_and_expired_guard():
    now = datetime(2035, 1, 20, 11, tzinfo=timezone.utc)
    assert core.scheduled_time('2035-01-20 14:00') == now
    for delta in (-1, 0, 59):
        with pytest.raises(core.ReleaseError):
            core.require_future((now + timedelta(seconds=delta)).isoformat(), now=now)
    assert core.require_future((now + timedelta(seconds=60)).isoformat(), now=now)


@pytest.mark.parametrize('change', ['text', 'time', 'channel', 'file'])
def test_approval_is_invalidated_by_changes(release, change):
    if change == 'file':
        Path(release.manifest['video_path']).write_bytes(b'changed')
    else:
        key = {'text': 'telegram_text', 'time': 'scheduled_at', 'channel': 'telegram_channel'}[change]
        release.manifest[key] += 'changed'
    with pytest.raises(core.ReleaseError, match='OK'):
        release.require_approval('telegram')


def test_nonselected_platform_cannot_publish(release):
    release.manifest['platforms'] = ['youtube']
    with pytest.raises(core.ReleaseError):
        release.require_approval('telegram')


def test_prepare_never_overwrites_existing_state(release):
    original = (release.directory / 'state.json').read_bytes()
    with pytest.raises(core.ReleaseError):
        core.prepare(release.manifest, release.directory)
    assert (release.directory / 'state.json').read_bytes() == original


def test_legacy_state_blocks_fresh_upload(release, tmp_path):
    old = tmp_path / '.tmp/youtube' / Path(release.manifest['docx_path']).stem / 'upload-state.json'
    core.write_json(old, {'youtube_url': 'https://youtube.com/watch?v=existing'})
    with pytest.raises(core.ReleaseError, match='старое состояние'):
        core.prepare(release.manifest, tmp_path / 'other-release')


def test_lock_prevents_concurrent_release(release):
    with core.release_lock(release.directory):
        with pytest.raises(core.ReleaseError):
            with core.release_lock(release.directory):
                pytest.fail('must not enter')
    assert not (release.directory / '.lock').exists()


def test_long_telegram_text_preserves_unicode_and_limits():
    text = '😀' * 5000
    chunks = core.telegram_parts(text, 'url')
    assert chunks[0] == 'url'
    assert ''.join(chunks[1:]) == text
    assert all(len(c.encode('utf-16-le')) // 2 <= 4096 for c in chunks)
    assert core.telegram_parts('Short', 'url') == ['Short']


def test_approval_cli_rejects_stale_preview(release):
    assert main(['approve', '--release', str(release.directory), '--revision', 'wrong']) == 1


def youtube_mock(release):
    service = MagicMock()
    service.channels().list().execute.return_value = {'items': [{'id': 'UC_TEST'}]}
    remote = {'id': 'video123', 'snippet': {'channelId': 'UC_TEST'},
              'status': {'privacyStatus': 'private', 'uploadStatus': 'processed'},
              'processingDetails': {'processingStatus': 'succeeded'}}
    service.videos().list().execute.side_effect = lambda: {'items': [remote]}
    service.videos().insert().next_chunk.return_value = (None, {'id': 'video123'})
    def update(**kwargs):
        remote['status'].update(kwargs['body']['status'])
        return NS(execute=lambda: remote)
    service.videos().update.side_effect = update
    service.reset_mock()
    return service, remote


def test_youtube_private_upload_then_schedule_and_no_duplicate(release):
    service, _ = youtube_mock(release)
    yt.schedule_youtube(release, service)
    assert release.state['youtube']['status'] == 'scheduled'
    assert service.videos().insert.call_count == 1
    body = service.videos().insert.call_args.kwargs['body']
    assert body['status']['privacyStatus'] == 'private'
    assert 'publishAt' not in body['status']
    assert body['snippet']['tags'] == ['codex-release-' + release.state['release_id']]
    assert 'categoryId' not in body['snippet']
    assert service.thumbnails().set.call_count == 1
    assert service.videos().update.call_args.kwargs['body']['status']['publishAt'] == '2035-01-20T11:00:00+00:00'
    yt.schedule_youtube(release, service)
    assert service.videos().insert.call_count == 1


def test_youtube_unknown_upload_result_never_retries_insert(release):
    service, _ = youtube_mock(release)
    service.videos().insert().next_chunk.side_effect = TimeoutError()
    with pytest.raises(TimeoutError):
        yt.schedule_youtube(release, service)
    reopened = core.Release(release.directory)
    count = service.videos().insert.call_count
    with pytest.raises(core.ReleaseError, match='неизвестен'):
        yt.schedule_youtube(reopened, service)
    assert service.videos().insert.call_count == count


def test_youtube_existing_id_is_read_only(release):
    release.manifest['youtube_id'] = 'video123'
    release.state['approved_revision'] = core.revision(release.manifest)
    service, _ = youtube_mock(release)
    yt.schedule_youtube(release, service)
    assert not service.videos().insert.called
    assert not service.videos().update.called


def test_wrong_youtube_account_is_blocked(release):
    service, _ = youtube_mock(release)
    service.channels().list().execute.return_value = {'items': [{'id': 'WRONG'}]}
    with pytest.raises(core.ReleaseError, match='другого'):
        yt.schedule_youtube(release, service)
    assert not service.videos().insert.called


def test_wrong_youtube_schedule_is_not_success(release):
    service, remote = youtube_mock(release)
    release.update('youtube', id='video123')
    remote['status']['publishAt'] = '2035-01-20T12:00:00Z'
    yt.check_youtube(release, service)
    assert release.state['youtube']['status'] == 'unconfirmed'


class FakeTelegram:
    def __init__(self):
        self.queue = []
        self.sent = []
        self.calls = 0
        self.uploads = 0
        self.fail_text = False
        self.authorized = True
        self.can_post = True

    async def is_user_authorized(self):
        return self.authorized

    async def get_me(self):
        return NS(bot=False, premium=False)

    async def get_entity(self, target):
        from telethon.tl.types import Channel
        return Channel(id=123, title='Test', photo=None, date=datetime.now(timezone.utc), broadcast=True)

    async def get_permissions(self, *args):
        return NS(is_creator=False, post_messages=self.can_post)

    async def __call__(self, request):
        if type(request).__name__ == 'GetConfigRequest':
            return NS(caption_length_max=1024, message_length_max=4096)
        return NS(messages=self.queue)

    async def upload_file(self, path):
        self.uploads += 1
        return 'uploaded'

    async def send_file(self, entity, file, **kwargs):
        self.calls += 1
        msg = NS(id=10 + self.calls, message=kwargs['caption'], date=kwargs['schedule'], document=NS(id=77))
        self.queue.append(msg)
        return msg

    async def send_message(self, entity, text, **kwargs):
        self.calls += 1
        if self.fail_text:
            raise TimeoutError()
        msg = NS(id=10 + self.calls, message=text, date=kwargs['schedule'], document=None)
        self.queue.append(msg)
        return msg

    async def iter_messages(self, *args, **kwargs):
        for msg in self.sent:
            yield msg


def link_youtube(release):
    release.update('youtube', id='video123', status='scheduled')


def test_telegram_server_schedule_and_repeat(release):
    link_youtube(release)
    client = FakeTelegram()
    assert asyncio.run(tg.schedule_telegram(release, client)) == 'scheduled'
    assert client.queue[0].date == core.scheduled_time(release.manifest['scheduled_at'])
    assert asyncio.run(tg.schedule_telegram(release, client)) == 'scheduled'
    assert client.calls == client.uploads == 1


def test_telegram_partial_timeout_preserves_ids_and_blocks_blind_retry(release):
    link_youtube(release)
    release.manifest['telegram_text'] = 'a' * 2000
    release.state['approved_revision'] = core.revision(release.manifest)
    core.write_json(release.directory / 'manifest.json', release.manifest)
    client = FakeTelegram()
    client.fail_text = True
    with pytest.raises(TimeoutError):
        asyncio.run(tg.schedule_telegram(release, client))
    reopened = core.Release(release.directory)
    assert reopened.state['telegram']['parts'][0]['id']
    with pytest.raises(core.ReleaseError, match='Неизвестен'):
        asyncio.run(tg.schedule_telegram(reopened, client))
    assert client.calls == 2
    assert reopened.state['youtube']['id'] == 'video123'


@pytest.mark.parametrize('attr', ['authorized', 'can_post'])
def test_telegram_missing_auth_or_rights_blocks_send(release, attr):
    link_youtube(release)
    client = FakeTelegram()
    setattr(client, attr, False)
    with pytest.raises(core.ReleaseError):
        asyncio.run(tg.schedule_telegram(release, client))
    assert client.calls == 0


def test_telegram_rechecks_deadline_after_upload(release, monkeypatch):
    link_youtube(release)
    client = FakeTelegram()
    original = tg.require_future
    def clock_changed(*args, **kwargs):
        if client.uploads:
            raise core.ReleaseError('До публикации меньше минуты')
        return original(*args, **kwargs)
    monkeypatch.setattr(tg, 'require_future', clock_changed)
    with pytest.raises(core.ReleaseError, match='меньше минуты'):
        asyncio.run(tg.schedule_telegram(release, client))
    assert client.calls == 0


def test_deleted_scheduled_message_not_reported_as_published(release):
    link_youtube(release)
    client = FakeTelegram()
    asyncio.run(tg.schedule_telegram(release, client))
    client.queue.clear()
    assert asyncio.run(tg.check_telegram(release, client)) == 'unconfirmed'


def test_telegram_media_replacement_detected(release):
    link_youtube(release)
    client = FakeTelegram()
    asyncio.run(tg.schedule_telegram(release, client))
    client.queue[0].document.id = 999
    assert asyncio.run(tg.check_telegram(release, client)) == 'unconfirmed'


def test_browser_evidence_wrong_channel_rejected(release, tmp_path):
    evidence = tmp_path / 'screen.txt'
    evidence.write_text('Observed schedule', encoding='utf-8')
    data = dict(url='https://dzen.ru/a/test', channel='wrong', status='scheduled',
                observed_at=datetime.now(timezone.utc).isoformat(), evidence_path=str(evidence),
                scheduled_at=release.manifest['scheduled_at'])
    with pytest.raises(core.ReleaseError, match='Канал'):
        record_browser(release, 'dzen', data)
    assert release.state['dzen']['status'] == 'prepared'


def test_browser_evidence_records_observation_without_claiming_api(release, tmp_path):
    evidence = tmp_path / 'screen.txt'
    evidence.write_text('Observed schedule', encoding='utf-8')
    data = dict(url='https://dzen.ru/a/test', channel=release.manifest['dzen_channel'], status='scheduled',
                observed_at=datetime.now(timezone.utc).isoformat(), evidence_path=str(evidence),
                scheduled_at=release.manifest['scheduled_at'])
    record_browser(release, 'dzen', data)
    assert release.state['dzen']['confirmation'] == 'browser'
    assert release.state['youtube']['status'] == 'prepared'


def test_telegram_large_video_blocked_before_upload(release, monkeypatch):
    link_youtube(release)
    client = FakeTelegram()
    original_stat = Path.stat
    video = Path(release.manifest['video_path'])
    def large_stat(path, *args, **kwargs):
        if path == video:
            return NS(st_size=5000 * 1024 * 1024)
        return original_stat(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', large_stat)
    with pytest.raises(core.ReleaseError, match='размер'):
        asyncio.run(tg.schedule_telegram(release, client))
    assert client.uploads == client.calls == 0


def test_telegram_published_requires_matching_channel_message(release):
    expected = datetime.now(timezone.utc) - timedelta(minutes=1)
    release.manifest['scheduled_at'] = expected.isoformat()
    client = FakeTelegram()
    part = dict(id=11, text='Exact', document_id=77, status='scheduled')
    release.update('telegram', parts=[part], part_count=1, channel_id=-1000000000123)
    client.sent = [NS(id=91, message='Exact', date=expected + timedelta(seconds=1), document=NS(id=77))]
    assert asyncio.run(tg.check_telegram(release, client)) == 'published'
    assert part['published_id'] == 91


def test_telegram_ambiguous_history_stays_unconfirmed(release):
    expected = datetime.now(timezone.utc) - timedelta(minutes=1)
    release.manifest['scheduled_at'] = expected.isoformat()
    client = FakeTelegram()
    release.update('telegram', parts=[dict(id=11, text='Exact', document_id=None, status='scheduled')],
                   part_count=1)
    client.sent = [NS(id=n, message='Exact', date=expected, document=None) for n in (91, 92)]
    assert asyncio.run(tg.check_telegram(release, client)) == 'unconfirmed'


def test_telegram_manual_reconciliation_does_not_resend(release):
    link_youtube(release)
    client = FakeTelegram()
    asyncio.run(tg.schedule_telegram(release, client))
    part = release.state['telegram']['parts'][0]
    known_id = part.pop('id')
    client.queue[0].document.size = Path(release.manifest['video_path']).stat().st_size
    client.queue[0].document.mime_type = 'video/mp4'
    assert asyncio.run(tg.reconcile_telegram(release, client, 0, known_id)) == 'scheduled'
    assert client.calls == 1


def test_approved_edit_does_not_overwrite_materialized_release(release):
    link_youtube(release)
    client = FakeTelegram()
    asyncio.run(tg.schedule_telegram(release, client))
    release.manifest['telegram_text'] = 'New text'
    release.state['approved_revision'] = core.revision(release.manifest)
    with pytest.raises(core.ReleaseError, match='другой версии'):
        asyncio.run(tg.schedule_telegram(release, client))
    assert client.calls == 1


def test_youtube_deadline_checked_after_upload(release, monkeypatch):
    service, remote = youtube_mock(release)
    original = yt.require_future
    def later(*args, **kwargs):
        if release.state.get('youtube', {}).get('id'):
            raise core.ReleaseError('До публикации меньше минуты')
        return original(*args, **kwargs)
    monkeypatch.setattr(yt, 'require_future', later)
    with pytest.raises(core.ReleaseError, match='меньше минуты'):
        yt.schedule_youtube(release, service)
    assert remote['status']['privacyStatus'] == 'private'
    assert not service.videos().update.called
    assert release.state['youtube']['id'] == 'video123'


def test_media_validation_rejects_missing_audio(monkeypatch):
    import json
    monkeypatch.setattr(core.subprocess, 'run', lambda *a, **k: NS(stdout=json.dumps({
        'format': {'duration': '10'}, 'streams': [{'codec_type': 'video'}]})))
    with pytest.raises(core.ReleaseError, match='звук'):
        core.probe_video('file.mp4')


def test_atomic_write_retries_temporary_windows_lock(tmp_path, monkeypatch):
    target = tmp_path / 'state.json'
    original = core.os.replace
    calls = []
    def briefly_locked(*args):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError('scanner lock')
        return original(*args)
    monkeypatch.setattr(core.os, 'replace', briefly_locked)
    core.write_json(target, {'confirmed': True})
    assert core.read_json(target) == {'confirmed': True}
    assert len(calls) == 2


@pytest.mark.parametrize('missing', ['YOUTUBE_CLIENT_ID', 'YOUTUBE_CLIENT_SECRET'])
def test_web_oauth_rejects_partial_configuration(monkeypatch, missing):
    monkeypatch.setenv('YOUTUBE_CLIENT_ID', 'test-client')
    monkeypatch.setenv('YOUTUBE_CLIENT_SECRET', 'test-secret')
    monkeypatch.delenv(missing)
    with pytest.raises(core.ReleaseError, match='одновременно'):
        yt.web_client_config()


def test_web_oauth_uses_registered_fixed_redirect(tmp_path, monkeypatch):
    from google_auth_oauthlib.flow import InstalledAppFlow
    import googleapiclient.discovery
    monkeypatch.setenv('YOUTUBE_CLIENT_ID', 'test-client')
    monkeypatch.setenv('YOUTUBE_CLIENT_SECRET', 'test-secret')
    token = tmp_path / 'token.json'
    monkeypatch.setenv('YOUTUBE_TOKEN_PATH', str(token))
    calls = []
    credentials = NS(has_scopes=lambda scopes: True, to_json=lambda: '{"token": "test"}')
    def local_login(flow, **kwargs):
        calls.append((flow.client_type, flow.client_config, kwargs))
        return credentials
    monkeypatch.setattr(InstalledAppFlow, 'run_local_server', local_login)
    monkeypatch.setattr(googleapiclient.discovery, 'build', lambda *a, **k: 'service')
    assert yt.youtube_service(login=True) == 'service'
    kind, config, kwargs = calls[0]
    assert kind == 'web'
    assert config['redirect_uris'] == ['http://localhost:8765/']
    assert kwargs['host'] == 'localhost' and kwargs['port'] == 8765
    assert kwargs['redirect_uri_trailing_slash'] is True
    assert kwargs['prompt'] == 'consent'
    assert token.exists()


def test_empty_web_settings_preserve_desktop_fallback(monkeypatch):
    monkeypatch.setenv('YOUTUBE_CLIENT_ID', '')
    monkeypatch.setenv('YOUTUBE_CLIENT_SECRET', '')
    assert yt.web_client_config() is None


def test_changed_web_client_requires_new_login(tmp_path, monkeypatch):
    from google.oauth2.credentials import Credentials
    monkeypatch.setenv('YOUTUBE_CLIENT_ID', 'new-client')
    monkeypatch.setenv('YOUTUBE_CLIENT_SECRET', 'new-secret')
    token = tmp_path / 'token.json'
    token.write_text('{}', encoding='utf-8')
    monkeypatch.setenv('YOUTUBE_TOKEN_PATH', str(token))
    monkeypatch.setattr(Credentials, 'from_authorized_user_file',
                        lambda *a: NS(client_id='old-client', client_secret='old-secret'))
    with pytest.raises(core.ReleaseError, match='изменился'):
        yt.youtube_service()


def test_browser_evidence_for_telegram_blocks_api_resend(release, tmp_path):
    link_youtube(release)
    evidence = tmp_path / 'tg.png'
    evidence.write_bytes(b'png')
    data = dict(url='https://web.telegram.org/a/#-100123', channel=release.manifest['telegram_channel'],
                status='scheduled', observed_at=datetime.now(timezone.utc).isoformat(),
                evidence_path=str(evidence), scheduled_at=release.manifest['scheduled_at'])
    record_browser(release, 'telegram', data)
    assert release.state['telegram']['confirmation'] == 'browser'
    client = FakeTelegram()
    with pytest.raises(core.ReleaseError, match='через браузер'):
        asyncio.run(tg.schedule_telegram(release, client))
    assert not client.queue


def test_browser_evidence_for_telegram_rejects_foreign_domain(release, tmp_path):
    evidence = tmp_path / 'tg.png'
    evidence.write_bytes(b'png')
    data = dict(url='https://t.me/channel', channel=release.manifest['telegram_channel'],
                status='scheduled', observed_at=datetime.now(timezone.utc).isoformat(),
                evidence_path=str(evidence), scheduled_at=release.manifest['scheduled_at'])
    with pytest.raises(core.ReleaseError, match='домен'):
        record_browser(release, 'telegram', data)
