"""YouTube OAuth, private upload, native scheduling and read-back verification."""
from datetime import datetime, timezone
import os
from pathlib import Path

from tools.publishing_core import ReleaseError, local_path, require_future, scheduled_time, probe_video

SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl',
          'https://www.googleapis.com/auth/youtube.readonly']
WEB_REDIRECT_URI = 'http://localhost:8765/'


def web_client_config():
    client_id = os.getenv('YOUTUBE_CLIENT_ID', '').strip()
    client_secret = os.getenv('YOUTUBE_CLIENT_SECRET', '').strip()
    if bool(client_id) != bool(client_secret):
        raise ReleaseError('Заполните одновременно YOUTUBE_CLIENT_ID и YOUTUBE_CLIENT_SECRET.')
    if not client_id:
        return None
    return {'web': {'client_id': client_id, 'client_secret': client_secret,
                    'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                    'token_uri': 'https://oauth2.googleapis.com/token',
                    'redirect_uris': [WEB_REDIRECT_URI]}}


def youtube_service(login=False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token = local_path(os.getenv('YOUTUBE_TOKEN_PATH', '.local/auth/youtube-token.json'))
    client_file = local_path(os.getenv('YOUTUBE_CLIENT_SECRETS_PATH', '.local/auth/youtube-client.json'))
    config = web_client_config()
    credentials = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() and not login else None
    if credentials and config and (credentials.client_id != config['web']['client_id'] or
                                   credentials.client_secret != config['web']['client_secret']):
        raise ReleaseError('OAuth-клиент изменился. Повторите auth-youtube для нового клиента.')
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        if not login:
            raise ReleaseError('Выполните auth-youtube в интерактивном локальном терминале.')
        if config:
            flow = InstalledAppFlow.from_client_config(config, SCOPES)
            credentials = flow.run_local_server(host='localhost', port=8765,
                                                redirect_uri_trailing_slash=True, prompt='consent')
        else:
            credentials = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES).run_local_server(
                port=0, prompt='consent')
    if not credentials.has_scopes(SCOPES):
        raise ReleaseError('OAuth не предоставил необходимые права. Повторите авторизацию.')
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(credentials.to_json(), encoding='utf-8')
    return build('youtube', 'v3', credentials=credentials, cache_discovery=False)


def verify_channel(service, expected):
    configured = os.getenv('YOUTUBE_CHANNEL_ID')
    if not configured or configured != expected:
        raise ReleaseError('YOUTUBE_CHANNEL_ID не совпадает с утверждённым каналом.')
    items = service.channels().list(part='id,contentDetails', mine=True).execute().get('items', [])
    channel = next((c for c in items if c['id'] == expected), None)
    if not channel:
        raise ReleaseError('OAuth авторизован для другого YouTube-канала.')
    return channel


def check_youtube(release, service):
    m = release.manifest
    verify_channel(service, m['youtube_channel'])
    video_id = release.state.get('youtube', {}).get('id') or m.get('youtube_id')
    if not video_id:
        raise ReleaseError('YouTube ID неизвестен; проверьте Studio перед повтором загрузки.')
    items = service.videos().list(part='snippet,status,processingDetails', id=video_id).execute().get('items', [])
    if not items or items[0]['snippet']['channelId'] != m['youtube_channel']:
        raise ReleaseError('Ролик отсутствует или принадлежит другому каналу.')
    item = items[0]
    remote = item['status']
    processing = item.get('processingDetails', {}).get('processingStatus')
    status = 'uploaded'
    if remote.get('uploadStatus') in ('failed', 'rejected', 'deleted') or processing == 'failed':
        status = 'failed'
    elif remote.get('privacyStatus') == 'public':
        status = 'published'
    elif remote.get('publishAt'):
        status = ('scheduled' if scheduled_time(remote['publishAt']) ==
                  scheduled_time(m['scheduled_at'], m.get('timezone', 'Europe/Moscow')) else 'unconfirmed')
    release.update('youtube', id=video_id, url='https://www.youtube.com/watch?v=' + video_id,
                   status=status, privacy=remote.get('privacyStatus'), scheduled_at=remote.get('publishAt'),
                   processing=processing, checked_at=datetime.now(timezone.utc).isoformat())
    return item


def schedule_youtube(release, service):
    from googleapiclient.http import MediaFileUpload

    release.require_approval('youtube')
    m = release.manifest
    verify_channel(service, m['youtube_channel'])
    expected = require_future(m['scheduled_at'], m.get('timezone', 'Europe/Moscow'))
    state = release.state.get('youtube', {})
    # An explicitly supplied existing URL is a lookup, not permission to edit its metadata.
    if m.get('youtube_id'):
        return check_youtube(release, service)
    if state.get('status') in ('scheduled', 'published'):
        return check_youtube(release, service)
    video_id = state.get('id')
    if not video_id and state.get('upload_attempted'):
        raise ReleaseError('Результат прошлой загрузки неизвестен. Найдите ролик в Studio и привяжите ID; повтор заблокирован.')
    if not video_id:
        probe_video(local_path(m['video_path']))
        # The marker is also visible in Studio tags for manual reconciliation after an uncertain upload.
        marker = 'codex-release-' + release.state['release_id']
        release.update('youtube', upload_attempted=True, status='uploading', marker=marker,
                       materialized_revision=release.state['approved_revision'])
        request = service.videos().insert(part='snippet,status', body={
            'snippet': {'title': m['title'], 'description': m['description'], 'tags': [marker]},
            'status': {'privacyStatus': 'private', 'selfDeclaredMadeForKids': m['made_for_kids']}},
            media_body=MediaFileUpload(str(local_path(m['video_path'])), chunksize=8 * 1024 * 1024, resumable=True))
        response = None
        while response is None:
            _, response = request.next_chunk(num_retries=0)
        video_id = response['id']
        release.update('youtube', id=video_id, status='uploaded')
    item = check_youtube(release, service)
    if item['status'].get('privacyStatus') != 'private' or item['status'].get('publishAt'):
        return item  # Never undo an existing server schedule/publication on retry.
    if release.state['youtube']['status'] == 'failed':
        raise ReleaseError('YouTube отклонил обработку. Проверьте Studio.')
    service.thumbnails().set(videoId=video_id,
        media_body=MediaFileUpload(str(local_path(m['thumbnail_path'])))).execute()
    require_future(m['scheduled_at'], m.get('timezone', 'Europe/Moscow'))
    service.videos().update(part='status', body={'id': video_id, 'status': {
        'privacyStatus': 'private', 'publishAt': expected.isoformat(),
        'selfDeclaredMadeForKids': m['made_for_kids']}}).execute()
    item = check_youtube(release, service)
    actual = item['status'].get('publishAt')
    if not actual or scheduled_time(actual) != expected:
        raise ReleaseError('YouTube не подтвердил время. Проверьте ограничения проекта и существующий ролик в Studio.')
    release.audit('youtube', 'scheduled')
    return item
