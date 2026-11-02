"""Local release contract. No network calls or credentials in release state."""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import subprocess
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = ('youtube', 'telegram', 'dzen')


class ReleaseError(Exception):
    pass


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.new')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    # Windows scanners can briefly hold the previous state file open.
    for attempt in range(5):
        try:
            os.replace(temp, path)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


def local_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def file_hash(path):
    digest = sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def scheduled_time(value, zone='Europe/Moscow'):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(zone))
    return dt.astimezone(timezone.utc)


def require_future(value, zone='Europe/Moscow', now=None):
    dt = scheduled_time(value, zone)
    if (dt - (now or datetime.now(timezone.utc))).total_seconds() < 60:
        raise ReleaseError('До публикации меньше минуты. Согласуйте новое время.')
    return dt


def revision(manifest):
    files = {}
    for key in ('docx_path', 'video_path', 'thumbnail_path', 'render_report_path'):
        if manifest.get(key):
            files[key] = file_hash(local_path(manifest[key]))
    for name in manifest.get('dzen_images', []):
        files[name] = file_hash(local_path(name))
    raw = json.dumps({'manifest': manifest, 'files': files}, sort_keys=True, ensure_ascii=False)
    return sha256(raw.encode()).hexdigest()


def validate_manifest(m):
    required = ('docx_path', 'scheduled_at', 'platforms', 'title')
    if any(not m.get(key) for key in required):
        raise ReleaseError('Нужны docx_path, scheduled_at, platforms, title.')
    if not set(m['platforms']) <= set(PLATFORMS) or len(set(m['platforms'])) != len(m['platforms']):
        raise ReleaseError('Неизвестная или повторная площадка.')
    require_future(m['scheduled_at'], m.get('timezone', 'Europe/Moscow'))
    docx = local_path(m['docx_path'])
    if docx.suffix.lower() != '.docx' or not docx.is_file():
        raise ReleaseError('Не найден исходный DOCX.')
    needs_video = 'telegram' in m['platforms'] or ('youtube' in m['platforms'] and not m.get('youtube_id'))
    if needs_video:
        video = local_path(m.get('video_path', ''))
        if not video.is_file() or video.suffix.lower() != '.mp4' or video.stem != docx.stem:
            raise ReleaseError('Нужен rendered MP4 с base-name исходного DOCX.')
        if not m.get('render_report_path') or not local_path(m['render_report_path']).is_file():
            raise ReleaseError('Приложите отчёт проверки монтажа в render_report_path.')
    for platform in m['platforms']:
        if not m.get(platform + '_channel'):
            raise ReleaseError('Укажите целевой канал: ' + platform + '_channel')
    if 'youtube' in m['platforms']:
        if not m.get('description') or not m.get('thumbnail_path'):
            raise ReleaseError('Подготовьте описание и локальную обложку YouTube.')
        if not isinstance(m.get('made_for_kids'), bool):
            raise ReleaseError('Явно задайте made_for_kids по содержанию.')
        if len(m['title']) > 100 or len(m['description']) > 5000:
            raise ReleaseError('Превышен лимит заголовка или описания YouTube.')
        if not m.get('youtube_id'):
            from tools.publishing_youtube import release_plan, validate_plan
            validate_plan(release_plan(m))
    for platform, key in [('telegram', 'telegram_text'), ('dzen', 'dzen_article')]:
        if platform in m['platforms'] and not m.get(key):
            raise ReleaseError('Подготовьте ' + key)
    revision(m)  # Verify every referenced artifact exists before recording approval.


@contextmanager
def release_lock(directory):
    path = Path(directory) / '.lock'
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ReleaseError('Выпуск занят. После аварии проверьте процесс перед удалением .lock.')
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


class Release:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.manifest = read_json(self.directory / 'manifest.json')
        self.state = read_json(self.directory / 'state.json')

    def save(self):
        write_json(self.directory / 'state.json', self.state)

    def require_approval(self, platform):
        if platform not in self.manifest['platforms']:
            raise ReleaseError('Площадка не входит в согласованный выпуск.')
        if self.state.get('approved_revision') != revision(self.manifest):
            raise ReleaseError('Нужен OK для текущей версии материалов и расписания.')
        bound = self.state.get(platform, {}).get('materialized_revision')
        if bound and bound != self.state['approved_revision']:
            raise ReleaseError('Материалы уже переданы площадке в другой версии. Сначала сверить и изменить существующий объект.')

    def update(self, platform, **values):
        self.state.setdefault(platform, {}).update(values)
        self.save()

    def audit(self, platform, status):
        record = {'at': datetime.now(timezone.utc).isoformat(), 'release': self.state['release_id'],
                  'platform': platform, 'status': status}
        with (self.directory / 'events.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        with (ROOT / 'publish-log.md').open('a', encoding='utf-8') as stream:
            stream.write(f"\n- {record['at']} | {record['release']} | {platform} | {status}\n")

    def youtube_url(self):
        video_id = self.state.get('youtube', {}).get('id') or self.manifest.get('youtube_id')
        if not video_id:
            raise ReleaseError('Сначала получите подтверждённый YouTube ID.')
        return 'https://www.youtube.com/watch?v=' + video_id

    def text(self, key):
        text = self.manifest[key]
        if '{youtube_url}' in text:
            text = text.replace('{youtube_url}', self.youtube_url())
        return text


def prepare(manifest, directory=None):
    validate_manifest(manifest)
    directory = Path(directory or ROOT / '.tmp/publishing' / local_path(manifest['docx_path']).stem)
    directory.mkdir(parents=True, exist_ok=True)
    with release_lock(directory):
        if (directory / 'state.json').exists():
            raise ReleaseError('Выпуск уже существует. Используйте его состояние, не создавайте копию.')
        # Import known legacy IDs, never infer absence from the old log.
        legacy = ROOT / '.tmp/youtube' / local_path(manifest['docx_path']).stem / 'upload-state.json'
        if legacy.exists():
            old = read_json(legacy)
            known = old.get('youtube_id') or old.get('video_id') or old.get('id')
            if known and not manifest.get('youtube_id'):
                raise ReleaseError('В старом состоянии есть YouTube ID. Укажите youtube_id в комплекте.')
            if not known and not manifest.get('youtube_id'):
                raise ReleaseError('Найдено старое состояние YouTube. Сначала проверьте существующий ролик.')
        write_json(directory / 'manifest.json', manifest)
        write_json(directory / 'state.json', {'release_id': sha256(str(directory.resolve()).encode()).hexdigest()[:20],
                                             **{p: {'status': 'prepared'} for p in manifest['platforms']}})
    return directory


def telegram_parts(text, url, caption_limit=1024, message_limit=4096):
    # Telegram limits count UTF-16 code units, not Python code points.
    units = lambda s: len(s.encode('utf-16-le')) // 2
    if units(text) <= caption_limit:
        return [text]
    chunks, current = [], ''
    for char in text:
        if units(current + char) > message_limit:
            chunks.append(current)
            current = ''
        current += char
    if current:
        chunks.append(current)
    return [url] + chunks


def probe_video(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                             '-of', 'json', str(path)], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    video = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
    audio = next((s for s in data['streams'] if s['codec_type'] == 'audio'), None)
    duration = float(data['format']['duration'])
    if not video or not audio or duration <= 0:
        raise ReleaseError('MP4 должен содержать видео и звук ненулевой длительности.')
    if (video.get('width'), video.get('height'), video.get('codec_name'), video.get('pix_fmt')) != (1920, 1080, 'h264', 'yuv420p'):
        raise ReleaseError('Ожидается проверенный рендер 1920x1080 H.264/yuv420p.')
    for stream in (video, audio):
        if abs(float(stream.get('duration', duration)) - duration) > 1:
            raise ReleaseError('Длительности звука и видео расходятся более чем на секунду.')
    return duration
