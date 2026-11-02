"""Offline adapter checks; the shared release fixture contains only temporary artifacts."""
from pathlib import Path
from unittest.mock import MagicMock

from googleapiclient.errors import HttpError
from httplib2 import Response
import pytest

from tools import publishing_core as core
from tools import publishing_youtube as yt
from tools.publish_release import main
from tools.test_publishing import release, youtube_mock


@pytest.mark.parametrize('category', [None, '27'])
def test_youtube_insert_body_from_upstream(release, monkeypatch, category):
    if category:
        release.manifest['youtube_category'] = category
        release.state['approved_revision'] = core.revision(release.manifest)
    vendor = yt.youtube_vendor()
    build = MagicMock(wraps=vendor.build_body)
    monkeypatch.setattr(vendor, 'build_body', build)
    service, _ = youtube_mock(release)
    request = service.videos().insert.return_value
    marker = 'codex-release-' + release.state['release_id']

    def insert(**kwargs):
        saved = core.Release(release.directory).state['youtube']
        assert saved['upload_attempted'] is True
        assert saved['status'] == 'uploading'
        assert saved['marker'] == marker
        assert saved['materialized_revision'] == release.state['approved_revision']
        return request

    service.videos().insert.side_effect = insert
    yt.schedule_youtube(release, service)
    build.assert_called_once()
    plan = build.call_args.args[0]
    assert plan['video'] == str(Path(release.manifest['video_path']).resolve())
    assert plan['thumbnail'] == str(Path(release.manifest['thumbnail_path']).resolve())
    assert plan['tags'] == [marker]
    assert plan['privacy'] == 'private'
    assert plan['madeForKids'] is False
    assert 'publishAt' not in plan
    body = service.videos().insert.call_args.kwargs['body']
    assert body['status'] == {'privacyStatus': 'private', 'selfDeclaredMadeForKids': False}
    assert body['snippet']['tags'] == [marker]
    assert body['snippet']['title'] == release.manifest['title']
    assert body['snippet']['description'] == release.manifest['description']
    if category:
        assert body['snippet']['categoryId'] == category
    else:
        assert 'categoryId' not in body['snippet']
    calls = [call[0] for call in service.mock_calls]
    assert calls.index('thumbnails().set().execute') < calls.index('videos().update')
    status = service.videos().update.call_args.kwargs['body']['status']
    assert status['publishAt'] == '2035-01-20T11:00:00+00:00'
    assert release.state['youtube']['status'] == 'scheduled'


@pytest.mark.parametrize('change', ['title_pipe', 'thumb_size'])
def test_youtube_upstream_validation_blocks_prepare(release, tmp_path, monkeypatch, change):
    service = MagicMock(side_effect=AssertionError('prepare must be offline'))
    monkeypatch.setattr(yt, 'youtube_service', service)
    manifest = dict(release.manifest)
    if change == 'title_pipe':
        manifest['title'] = 'Invalid | title'
    else:
        Path(manifest['thumbnail_path']).write_bytes(b'x' * (2 * 1024 * 1024 + 1))
    directory = tmp_path / 'invalid-release'
    with pytest.raises(core.ReleaseError, match='YouTube:'):
        core.prepare(manifest, directory)
    assert not directory.exists()
    service.assert_not_called()


@pytest.mark.parametrize('status,failures', [(500, 1), (502, 1), (503, 1), (504, 1), (503, 5), (503, 6), (400, 1)])
def test_youtube_resumable_retries_5xx_without_second_insert(release, monkeypatch, status, failures):
    service, _ = youtube_mock(release)
    request = service.videos().insert.return_value
    errors = [HttpError(Response({'status': status}), b'') for _ in range(failures)]
    request.next_chunk.side_effect = errors + [(None, {'id': 'video123'})]
    sleep = MagicMock()
    monkeypatch.setattr(yt, 'sleep', sleep)
    if failures > 5 or status == 400:
        with pytest.raises(HttpError):
            yt.schedule_youtube(release, service)
        saved = core.Release(release.directory)
        assert saved.state['youtube']['upload_attempted'] is True
        assert saved.state['youtube']['status'] == 'uploading'
        service.videos().update.assert_not_called()
        with pytest.raises(core.ReleaseError, match='неизвестен'):
            yt.schedule_youtube(saved, service)
        attempts = 6 if failures > 5 else 1
    else:
        yt.schedule_youtube(release, service)
        assert release.state['youtube']['status'] == 'scheduled'
        attempts = failures + 1
    assert service.videos().insert.call_count == 1
    assert request.next_chunk.call_count == attempts
    assert all(call.kwargs == {'num_retries': 0} for call in request.next_chunk.call_args_list)
    waits = min(failures, 5) if status != 400 else 0
    assert [call.args[0] for call in sleep.call_args_list] == [2 ** n for n in range(1, waits + 1)]


def test_preview_youtube_cli_offline(release, monkeypatch, capsys):
    import dotenv

    def forbidden(*args, **kwargs):
        pytest.fail('offline preview must not load .env, authenticate or call Google')

    monkeypatch.setattr(dotenv, 'load_dotenv', forbidden)
    monkeypatch.setattr(yt, 'youtube_service', forbidden)
    vendor = yt.youtube_vendor()
    monkeypatch.setattr(vendor, 'get_creds', forbidden)
    monkeypatch.setattr(vendor, 'service', forbidden)
    original_preview = vendor.preview

    def preview(plan, body):
        assert (release.directory / '.lock').exists()
        return original_preview(plan, body)

    monkeypatch.setattr(vendor, 'preview', preview)
    release.state.pop('approved_revision')  # Preview is used before approval.
    release.save()
    before = (release.directory / 'state.json').read_bytes()
    assert main(['preview-youtube', '--release', str(release.directory)]) == 0
    output = capsys.readouterr().out
    assert 'upload preview' in output
    assert release.manifest['title'] in output
    assert 'privacy: private' in output
    assert '(channel default)' in output
    assert 'codex-release-' + release.state['release_id'] in output
    assert (release.directory / 'state.json').read_bytes() == before
    assert not (release.directory / '.lock').exists()


def test_youtube_thumbnail_failure_does_not_schedule(release):
    service, _ = youtube_mock(release)
    service.thumbnails().set().execute.side_effect = RuntimeError('thumbnail failed')
    with pytest.raises(RuntimeError, match='thumbnail failed'):
        yt.schedule_youtube(release, service)
    service.videos().update.assert_not_called()
    assert release.state['youtube']['id'] == 'video123'


def test_youtube_rechecks_deadline_before_insert(release, monkeypatch):
    service, _ = youtube_mock(release)

    def expired_after_probe(path):
        release.manifest['scheduled_at'] = '2000-01-01T00:00:00Z'

    monkeypatch.setattr(yt, 'probe_video', expired_after_probe)
    with pytest.raises(core.ReleaseError, match='меньше минуты'):
        yt.schedule_youtube(release, service)
    service.videos().insert.assert_not_called()
    assert not release.state['youtube'].get('upload_attempted')
