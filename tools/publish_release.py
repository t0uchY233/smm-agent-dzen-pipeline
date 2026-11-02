"""CLI used by Codex. Authoring and browser actions remain in the publishing skill."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.publishing_core import (ROOT, Release, ReleaseError, prepare, read_json,
    release_lock, require_future, revision, validate_manifest)


async def telegram_action(action, release=None, part_index=None, message_id=None):
    from tools.publishing_telegram import telegram_client, schedule_telegram, check_telegram, reconcile_telegram
    client = telegram_client()
    try:
        if action == 'auth-telegram':
            await client.start()
            return {'authorized': True}
        await client.connect()
        if action == 'reconcile-telegram':
            return await reconcile_telegram(release, client, part_index, message_id)
        if action == 'schedule-telegram':
            return await schedule_telegram(release, client)
        return await check_telegram(release, client)
    finally:
        await client.disconnect()


def record_browser(release, platform, evidence):
    """Persist observed browser evidence, never fabricate a successful browser operation."""
    release.require_approval(platform)
    required = ('url', 'channel', 'status', 'observed_at', 'evidence_path')
    if any(not evidence.get(k) for k in required):
        raise ReleaseError('Нужны url, channel, status, observed_at, evidence_path.')
    from tools.publishing_core import local_path, scheduled_time
    from urllib.parse import urlparse
    host = urlparse(evidence['url']).hostname
    allowed = ('dzen.ru',) if platform == 'dzen' else ('youtube.com', 'www.youtube.com', 'studio.youtube.com')
    if host not in allowed:
        raise ReleaseError('Неверный домен доказательства публикации.')
    if evidence['channel'] != release.manifest[platform + '_channel']:
        raise ReleaseError('Канал в доказательстве не совпадает с комплектом.')
    if not local_path(evidence['evidence_path']).is_file():
        raise ReleaseError('Сохраните скриншот или текст наблюдения браузера.')
    if evidence['status'] not in ('uploaded', 'scheduled', 'published', 'failed'):
        raise ReleaseError('Недопустимый статус браузерной проверки.')
    if evidence['status'] == 'scheduled':
        target = scheduled_time(release.manifest['scheduled_at'], release.manifest.get('timezone', 'Europe/Moscow'))
        if scheduled_time(evidence.get('scheduled_at', '')) != target:
            raise ReleaseError('Назначенное время не совпадает с согласованным.')
    if platform == 'youtube' and not evidence.get('id'):
        raise ReleaseError('Сохраните YouTube ID.')
    known_id = release.state.get(platform, {}).get('id') or release.manifest.get('youtube_id')
    if platform == 'youtube' and known_id and evidence['id'] != known_id:
        raise ReleaseError('Доказательство относится к другому YouTube ID.')
    release.update(platform, **evidence, confirmation='browser',
                   materialized_revision=release.state['approved_revision'])
    release.audit(platform, evidence['status'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--manifest', required=True)
    p.add_argument('--directory')
    for action in ('approve', 'status', 'schedule-youtube', 'check-youtube', 'preview-youtube',
                   'schedule-telegram', 'check-telegram', 'render-texts',
                   'prepare-dzen', 'schedule-dzen', 'check-dzen'):
        p = sub.add_parser(action)
        p.add_argument('--release', required=True)
        if action == 'approve':
            p.add_argument('--revision', required=True, help='Exact revision shown in the approved preview')
    for action in ('auth-youtube', 'auth-telegram'):
        sub.add_parser(action)
    p = sub.add_parser('reconcile-telegram')
    p.add_argument('--release', required=True)
    p.add_argument('--part-index', type=int, required=True)
    p.add_argument('--message-id', type=int, required=True)
    p = sub.add_parser('record-browser')
    p.add_argument('--release', required=True)
    p.add_argument('--platform', choices=('youtube', 'dzen'), required=True)
    p.add_argument('--evidence', required=True)
    args = parser.parse_args(argv)
    try:
        # Offline YouTube preview must not load credentials or depend on .env.
        if args.action != 'preview-youtube':
            from dotenv import load_dotenv
            load_dotenv(ROOT / '.env', override=False)
        if args.action == 'prepare':
            m = read_json(args.manifest)
            m.setdefault('timezone', os.getenv('PUBLISH_TIMEZONE', 'Europe/Moscow'))
            print(prepare(m, args.directory))
            return 0
        if args.action == 'auth-youtube':
            from tools.publishing_youtube import youtube_service
            youtube_service(login=True)
            print('YouTube authorized')
            return 0
        if args.action == 'auth-telegram':
            print(asyncio.run(telegram_action(args.action)))
            return 0
        with release_lock(args.release):
            release = Release(args.release)
            if args.action == 'status':
                print(json.dumps({'revision': revision(release.manifest), 'state': release.state}, ensure_ascii=False, indent=2))
            elif args.action == 'approve':
                validate_manifest(release.manifest)
                current = revision(release.manifest)
                if args.revision != current:
                    raise ReleaseError('Превью устарело. Покажите новую версию перед OK.')
                release.state['approved_revision'] = current
                release.save()
                print('Approved revision ' + current)
            elif args.action == 'render-texts':
                for key, filename in [('telegram_text', 'telegram.txt'), ('dzen_article', 'dzen.md')]:
                    if key in release.manifest:
                        (release.directory / filename).write_text(release.text(key), encoding='utf-8')
            elif args.action == 'record-browser':
                record_browser(release, args.platform, read_json(args.evidence))
            elif args.action.endswith('dzen'):
                from tools.publishing_dzen import dzen_action
                status = asyncio.run(dzen_action(args.action, release))
                print(json.dumps(release.state['dzen'], ensure_ascii=False))
                if status not in ('prepared', 'scheduled', 'published'):
                    return 2
            elif args.action == 'preview-youtube':
                from tools.publishing_youtube import preview_youtube
                preview_youtube(release)
            elif args.action.endswith('youtube'):
                from tools.publishing_youtube import youtube_service, schedule_youtube, check_youtube
                service = youtube_service()
                fn = schedule_youtube if args.action.startswith('schedule') else check_youtube
                fn(release, service)
                print(json.dumps(release.state['youtube'], ensure_ascii=False))
            else:
                print(asyncio.run(telegram_action(args.action, release,
                    getattr(args, 'part_index', None), getattr(args, 'message_id', None))))
        return 0
    except Exception as error:
        # HTTP/SDK exceptions can contain tokens, request bodies and resumable URLs.
        # Only our own actionable errors are safe to display.
        message = str(error) if isinstance(error, ReleaseError) else type(error).__name__ + ': проверьте подключение, настройки и сохранённое состояние; секреты скрыты.'
        # Preserve IDs and per-part progress; failure must never reset a successful platform.
        if 'release' in locals() and args.action.startswith('schedule-'):
            platform = args.action.removeprefix('schedule-')
            try:
                with release_lock(args.release):
                    current = Release(args.release)
                    current.update(platform, last_error=message)
            except (OSError, ReleaseError):
                pass  # Never mask the original failure or steal another process's lock.
        print(json.dumps({'error': message}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
