"""Telegram user-session publishing; no bot token and no local timer."""
from datetime import datetime, timezone
from functools import lru_cache
import importlib.util
import os
from pathlib import Path

from tools.publishing_core import ReleaseError, local_path, require_future, scheduled_time, telegram_parts, probe_video


@lru_cache(maxsize=1)
def telegram_vendor():
    path = Path(__file__).resolve().parents[1] / 'telegram-publish' / 'tg_post.py'
    spec = importlib.util.spec_from_file_location('tg_post', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def telegram_client():
    from telethon import TelegramClient
    api_id, api_hash = os.getenv('TELEGRAM_API_ID'), os.getenv('TELEGRAM_API_HASH')
    if not api_id or not api_hash:
        raise ReleaseError('Заполните TELEGRAM_API_ID и TELEGRAM_API_HASH.')
    session = local_path(os.getenv('TELEGRAM_SESSION_PATH', '.local/auth/telegram.session'))
    session.parent.mkdir(parents=True, exist_ok=True)
    return TelegramClient(str(session), int(api_id), api_hash, request_retries=0, flood_sleep_threshold=0)


async def verify_channel(client, expected):
    from telethon import utils
    if str(expected) != os.getenv('TELEGRAM_CHANNEL_ID'):
        raise ReleaseError('TELEGRAM_CHANNEL_ID не совпадает с утверждённым каналом.')
    if not await client.is_user_authorized():
        raise ReleaseError('Выполните auth-telegram в интерактивном терминале.')
    me = await client.get_me()
    if me.bot:
        raise ReleaseError('Для серверной отложки нужна пользовательская сессия.')
    target = int(expected) if str(expected).lstrip('-').isdigit() else expected
    try:
        entity = await client.get_entity(target)
    except ValueError:
        await client.get_dialogs()  # Resolve numeric channel IDs after first login.
        entity = await client.get_entity(target)
    if not getattr(entity, 'broadcast', False):
        raise ReleaseError('Получатель должен быть Telegram-каналом.')
    permissions = await client.get_permissions(entity, me)
    if not (getattr(permissions, 'is_creator', False) or getattr(permissions, 'post_messages', False)):
        raise ReleaseError('Нет права публикации в Telegram-канале.')
    return entity, utils.get_peer_id(entity)


async def check_telegram(release, client):
    from telethon.tl.functions.messages import GetScheduledHistoryRequest
    entity, channel_id = await verify_channel(client, release.manifest['telegram_channel'])
    state = release.state.get('telegram', {})
    if state.get('channel_id') and state['channel_id'] != channel_id:
        raise ReleaseError('Канал Telegram изменился после назначения.')
    parts = state.get('parts', [])
    queue = (await client(GetScheduledHistoryRequest(entity, 0))).messages
    by_id = {msg.id: msg for msg in queue}
    expected = scheduled_time(release.manifest['scheduled_at'], release.manifest.get('timezone', 'Europe/Moscow'))
    complete = bool(parts) and len(parts) == state.get('part_count')
    recent = []
    if datetime.now(timezone.utc) >= expected and any(p.get('id') not in by_id for p in parts):
        recent = [msg async for msg in client.iter_messages(entity, limit=200)]
    for part in parts:
        msg = by_id.get(part.get('id'))
        if msg:
            if (msg.date != expected or msg.message != part['text'] or
                    (part.get('document_id') and getattr(getattr(msg, 'document', None), 'id', None) != part['document_id'])):
                part['status'] = 'mismatch'
            else:
                part['status'] = 'scheduled'
        elif part.get('status') != 'published':
            part['status'] = 'unconfirmed'
            matches = [msg for msg in recent if msg.message == part['text']
                       and 0 <= (msg.date - expected).total_seconds() <= 300
                       and getattr(getattr(msg, 'document', None), 'id', None) == part.get('document_id')]
            if len(matches) == 1:
                part.update(status='published', published_id=matches[0].id,
                            published_at=matches[0].date.isoformat())
        complete = complete and part['status'] == 'scheduled'
    status = 'scheduled' if complete else 'unconfirmed'
    if parts and len(parts) == state.get('part_count') and all(p['status'] == 'published' for p in parts):
        status = 'published'
    release.update('telegram', channel_id=channel_id, parts=parts, status=status,
                   checked_at=datetime.now(timezone.utc).isoformat())
    return status


async def schedule_telegram(release, client):
    release.require_approval('telegram')
    m = release.manifest
    entity, channel_id = await verify_channel(client, m['telegram_channel'])
    transport = telegram_vendor()
    access_error = transport.check_chat_access(channel_id, entity)
    if access_error:
        raise ReleaseError(access_error)
    expected = require_future(m['scheduled_at'], m.get('timezone', 'Europe/Moscow'))
    expected, schedule_error = transport.parse_schedule_date(expected.isoformat())
    if schedule_error:
        raise ReleaseError(schedule_error)
    url = release.youtube_url()
    text = release.text('telegram_text')
    if url not in text:
        text += '\n\n' + url
    from telethon.tl.functions.help import GetConfigRequest
    config = await client(GetConfigRequest())
    chunks = telegram_parts(text, url, config.caption_length_max, config.message_length_max)
    state = release.state.setdefault('telegram', {})
    if state.get('confirmation') == 'browser':
        raise ReleaseError('Telegram уже назначен через браузер Codex: только сверка в канале, повторная отправка запрещена.')
    parts = state.setdefault('parts', [])
    if state.get('channel_id') and state['channel_id'] != channel_id:
        raise ReleaseError('Изменился Telegram-канал. Нужна ручная сверка старой отложки.')
    if parts and any(p.get('attempted') and not p.get('id') for p in parts):
        raise ReleaseError('Неизвестен результат отправки Telegram. Проверьте отложку, не повторяйте вслепую.')
    if parts:
        await check_telegram(release, client)
        if any(p.get('status') != 'scheduled' for p in parts):
            raise ReleaseError('Существующие сообщения изменены или вышли из очереди. Нужна сверка.')
        if any(p['text'] != chunks[i] for i, p in enumerate(parts)):
            raise ReleaseError('Материалы отличаются от существующей отложки.')
    state.update(part_count=len(chunks), channel_id=channel_id)
    release.save()
    video = local_path(m['video_path'])
    duration = probe_video(video)
    me = await client.get_me()
    max_bytes = (4000 if getattr(me, 'premium', False) else 2000) * 1024 * 1024
    if video.stat().st_size > max_bytes:
        raise ReleaseError('Видео превышает поддерживаемый размер аккаунта. Нужна отдельная версия для Telegram.')
    uploaded = await client.upload_file(str(video)) if not parts else None
    # Recheck AFTER the potentially long upload, immediately before scheduling.
    for index in range(len(parts), len(chunks)):
        require_future(m['scheduled_at'], m.get('timezone', 'Europe/Moscow'))
        part = {'text': chunks[index], 'attempted': True, 'status': 'sending'}
        parts.append(part)
        state['materialized_revision'] = release.state['approved_revision']
        release.save()
        try:
            if index == 0:
                from telethon.tl.types import DocumentAttributeVideo
                attribute = transport._video_send_attributes(str(video))
                if attribute is None:
                    attribute = DocumentAttributeVideo(duration=duration, w=1920, h=1080,
                                                       supports_streaming=True)
                msg = await transport.send_scheduled_file(
                    client, entity, video, chunks[index], expected,
                    uploaded=uploaded, attributes=[attribute])
            else:
                msg = await transport.send_scheduled_text(client, entity, chunks[index], expected)
        except Exception as error:
            if transport._is_flood_wait(error):
                raise ReleaseError(
                    f'Telegram просит подождать {error.seconds} с. '
                    'Результат отправки требует сверки; не повторяйте вслепую.'
                ) from error
            raise
        part.update(id=msg.id, status='scheduled', document_id=getattr(getattr(msg, 'document', None), 'id', None))
        release.save()
    status = await check_telegram(release, client)
    if status != 'scheduled':
        raise ReleaseError('Telegram не подтвердил все сообщения в отложке.')
    release.audit('telegram', status)
    return status


async def reconcile_telegram(release, client, part_index, message_id):
    """Adopt a manually identified scheduled message after an uncertain response."""
    from telethon.tl.functions.messages import GetScheduledHistoryRequest
    release.require_approval('telegram')
    entity, channel_id = await verify_channel(client, release.manifest['telegram_channel'])
    state = release.state.get('telegram', {})
    parts = state.get('parts', [])
    if not 0 <= part_index < len(parts) or parts[part_index].get('id'):
        raise ReleaseError('Можно сверить только существующую незавершённую часть без ID.')
    if state.get('channel_id') != channel_id:
        raise ReleaseError('Канал не совпадает с исходной попыткой.')
    queue = (await client(GetScheduledHistoryRequest(entity, 0))).messages
    msg = next((item for item in queue if item.id == message_id), None)
    part = parts[part_index]
    expected = scheduled_time(release.manifest['scheduled_at'], release.manifest.get('timezone', 'Europe/Moscow'))
    if not msg or msg.message != part['text'] or msg.date != expected:
        raise ReleaseError('Сообщение не совпадает с текстом и временем исходной попытки.')
    document = getattr(msg, 'document', None)
    if part_index == 0:
        video = local_path(release.manifest['video_path'])
        if not document or document.size != video.stat().st_size or document.mime_type != 'video/mp4':
            raise ReleaseError('Медиа не соответствует видео выпуска.')
    elif document:
        raise ReleaseError('Ожидалась текстовая часть без медиа.')
    part.update(id=msg.id, document_id=getattr(document, 'id', None), status='scheduled')
    release.save()
    return await check_telegram(release, client)
