"""Release state around Andrrreyiv/dzen-publish; all editor work uses its CDP code."""
import asyncio
from datetime import datetime, timedelta
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile
from urllib.parse import urlparse, urljoin
from zoneinfo import ZoneInfo

from tools import publishing_core as core
from tools.dzen_content import (editor_channel, footer_text, validate_footer, plain,
                                clean_blocks, sequence_signature, article_links_match)

ROOT = Path(__file__).resolve().parents[1]

_SHORT_MONTHS = ('янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сент', 'окт', 'ноя', 'дек')
_LONG_MONTHS = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря')


def _text_runs(blocks):
    """Paragraph splits are immaterial; image boundaries are not."""
    runs = []
    texts = []
    for block in blocks:
        if block['type'] == 'text':
            texts.append(block['text'])
        else:
            if texts:
                runs.append(('text', plain(' '.join(texts))))
                texts = []
            runs.append((block['type'], ''))
    if texts:
        runs.append(('text', plain(' '.join(texts))))
    return runs


def _article_id(url, channel):
    """Recognize only public URLs or an article editor under this channel.

    A matching title is not object identity. Unknown URL shapes fail closed.
    """
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc != 'dzen.ru':
        return None
    path = parsed.path.rstrip('/')
    public = re.fullmatch(r'/a/([A-Za-z0-9_-]+)', path)
    if public:
        return public[1]
    prefix = urlparse(channel).path.rstrip('/') + '/'
    if not path.startswith(prefix):
        return None
    editor = re.fullmatch(r'([A-Za-z0-9_-]+)/edit', path[len(prefix):])
    return editor[1] if editor else None


def _queue_date_matches(text, expected, observed, object_bound=False):
    pattern = (rf'(?<!\w)0?{expected.day} {_SHORT_MONTHS[expected.month - 1]} '
               rf'(?:(\d{{4}}) )?{expected:%H:%M}(?![\w:])')
    for match in re.finditer(pattern, plain(text)):
        # No documented UI rule establishes the year from this label alone.
        # Require the persisted draft identity, in addition to the date guard.
        if match[1]:
            if int(match[1]) == expected.year:
                return True
        elif object_bound and expected.year == observed.year and expected.date() >= observed.date():
            return True
    return False


def _owner_schedule_label(text, expected, observed, object_bound=False):
    pattern = (r'Будет опубликовано (сегодня|завтра|\d{1,2} [а-я]+(?: \d{4})?)'
               r' в (\d{2}:\d{2})(?![\w:])')
    for match in re.finditer(pattern, plain(text)):
        date, time = match.groups()
        if time != expected.strftime('%H:%M'):
            continue
        if date in ('сегодня', 'завтра'):
            day = observed.date() + timedelta(days=date == 'завтра')
            valid = object_bound and expected.date() == day
        else:
            full_dates = (
                f'{expected.day} {_LONG_MONTHS[expected.month - 1]} {expected.year}',
                f'{expected.day:02} {_LONG_MONTHS[expected.month - 1]} {expected.year}',
            )
            yearless_dates = (
                f'{expected.day} {_LONG_MONTHS[expected.month - 1]}',
                f'{expected.day:02} {_LONG_MONTHS[expected.month - 1]}',
            )
            valid = date in full_dates or (
                object_bound and expected.year == observed.year and expected.date() >= observed.date()
                and date in yearless_dates)
        if valid:
            return match.group(0)
    return None


def transport_module():
    spec = importlib.util.spec_from_file_location('dzen_transport', ROOT / 'dzen-publish/publish_dzen.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def material(release):
    m = release.manifest
    channel = editor_channel(m['dzen_channel'])
    article = release.text('dzen_article')
    validate_footer(article)
    blocks = None
    if m.get('dzen_sequence_path'):
        payload = core.read_json(core.local_path(m['dzen_sequence_path']))
        if payload['title'] != m['title']:
            raise core.ReleaseError('Заголовок последовательности не совпадает с утверждённым.')
        blocks = []
        for original in payload['blocks']:
            block = dict(original)
            if block['type'] == 'text':
                if '{youtube_url}' in block['text']:
                    block['text'] = block['text'].replace('{youtube_url}', release.youtube_url())
            elif block['type'] == 'image':
                block['path'] = str(core.local_path(block['path']).resolve())
                if not Path(block['path']).is_file():
                    raise core.ReleaseError('Не найдено изображение последовательности.')
            else:
                raise core.ReleaseError('Неизвестный блок последовательности.')
            blocks.append(block)
        if plain(' '.join(b['text'] for b in blocks if b['type'] == 'text')) != plain(article):
            raise core.ReleaseError('Текст последовательности отличается от утверждённой статьи.')
    from tools.dzen_content import image_occurrences
    occurrences = image_occurrences(core.local_path(m['docx_path']))
    if occurrences and blocks is None:
        raise core.ReleaseError('DOCX с изображениями требует dzen_sequence_path для проверки порядка.')
    if blocks is not None and sum(b['type'] == 'image' for b in blocks) != occurrences:
        raise core.ReleaseError('Последовательность потеряла или добавила изображения DOCX.')
    if blocks is not None:
        from tools.extract_docx_dzen_sequence import extract_blocks
        with tempfile.TemporaryDirectory() as temp:
            with zipfile.ZipFile(core.local_path(m['docx_path'])) as archive:
                source = clean_blocks(extract_blocks(archive, Path(temp)), m['title'], footer_text())
            for block in source:
                if block['type'] == 'text' and '{youtube_url}' in block['text']:
                    block['text'] = block['text'].replace('{youtube_url}', release.youtube_url())
            if sequence_signature(source) != sequence_signature(blocks):
                raise core.ReleaseError('Последовательность отличается от DOCX: текст, порядок или содержимое изображений.')
    if blocks is not None and m.get('dzen_images'):
        raise core.ReleaseError('Изображения DOCX передаются в последовательности, без отдельного списка dzen_images.')
    from PIL import Image
    image_paths = [b['path'] for b in blocks if b['type'] == 'image'] if blocks else [str(core.local_path(p)) for p in m.get('dzen_images', [])]
    for path in image_paths:
        if Path(path).suffix.lower() not in {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif'}:
            raise core.ReleaseError('Неподдерживаемый формат изображения Дзена.')
        try:
            with Image.open(path) as image:
                image.verify()
        except (OSError, ValueError) as error:
            raise core.ReleaseError('Изображение повреждено; редактор не открывался.') from error
    return {'channel': channel, 'title': m['title'], 'article': article, 'blocks': blocks,
            'images': [str(core.local_path(p)) for p in m.get('dzen_images', [])],
            'scheduled_at': m['scheduled_at'], 'timezone': m.get('timezone', 'Europe/Moscow')}


async def schedule_dzen(release, transport, prepare_only=False):
    release.require_approval('dzen')
    content = material(release)
    state = release.state.get('dzen', {})
    if state.get('attempted') or state.get('status') in ('scheduled', 'published'):
        return await check_dzen(release, transport)
    core.require_future(release.manifest['scheduled_at'], release.manifest.get('timezone', 'Europe/Moscow'))
    await transport.preflight(content['channel'])
    # Persist intent before the first editor mutation, even if creating the draft times out.
    if state.get('draft_attempted'):
        if not state.get('draft_url'):
            raise core.ReleaseError('Результат создания черновика неизвестен. Сначала найдите существующий черновик.')
        await transport.open_draft(state['draft_url'])
        # Never clear/rebuild a partially written draft on a retry. Only the
        # exact approved first-paragraph prefix can be resumed automatically.
        try:
            await transport.verify(content)
        except core.ReleaseError:
            if (state.get('materialized_revision') != release.state['approved_revision']
                    or not content['blocks']):
                raise
            await transport.resume_first_text(content)
            await transport.verify(content)
    else:
        release.update('dzen', draft_attempted=True, status='unconfirmed',
                       materialized_revision=release.state['approved_revision'])
        draft = await transport.create_draft()
        release.update('dzen', draft_url=draft)
        await transport.fill(content, release.manifest)
        await transport.verify(content)
    if prepare_only:
        release.update('dzen', status='prepared', content_verified=True)
        return 'prepared'
    # Rehash the actual inputs after a potentially long import.
    release.require_approval('dzen')
    when = core.require_future(release.manifest['scheduled_at'], release.manifest.get('timezone', 'Europe/Moscow'))
    release.update('dzen', attempted=True, status='sending')
    try:
        await transport.submit(when)
    except Exception:
        release.update('dzen', status='unconfirmed')
        raise
    release.update('dzen', status='unconfirmed')
    return await check_dzen(release, transport)


async def check_dzen(release, transport):
    release.require_approval('dzen')
    state = release.state.get('dzen', {})
    if not state.get('draft_url'):
        raise core.ReleaseError('Нет URL черновика: нужна сверка существующего объекта.')
    content = material(release)
    await transport.preflight(content['channel'])
    observation = await transport.observe(state['draft_url'], content)
    expected = core.scheduled_time(release.manifest['scheduled_at'], release.manifest.get('timezone', 'Europe/Moscow'))
    status = 'unconfirmed'
    if observation.get('channel') == content['channel'] and observation.get('content_verified') is True:
        if observation.get('status') == 'scheduled' and observation.get('scheduled_at'):
            if core.scheduled_time(observation['scheduled_at']) == expected:
                status = 'scheduled'
        elif observation.get('status') == 'published' and observation.get('public_verified') is True:
            status = 'published'
    evidence = release.directory / 'dzen-observation.json'
    core.write_json(evidence, observation)
    release.update('dzen', status=status, url=observation.get('url', state['draft_url']),
                   checked_at=datetime.now(ZoneInfo('UTC')).isoformat(), evidence_path=str(evidence),
                   published_at=observation.get('published_at'),
                   last_error=None if status in ('scheduled', 'published') else state.get('last_error'))
    if status in ('scheduled', 'published'):
        release.audit('dzen', status)
    return status


class CDPTransport:
    def __init__(self):
        self.module = transport_module()
        self.playwright = None
        self.page = None

    async def __aenter__(self):
        from tools.chrome_cdp import ensure_chrome, endpoint
        self.module.CDP_URL = endpoint()
        # Recovery is bounded and occurs before opening an editor.
        for attempt in range(2):
            try:
                await asyncio.to_thread(ensure_chrome)
                self.playwright = await self.module.async_playwright().start()
                self.browser = await self.module.connect_cdp(self.playwright)
                self.context = self.browser.contexts[0]
                self.page = await self.new_page()
                return self
            except Exception:
                if self.playwright:
                    await self.playwright.stop()
                    self.playwright = None
                if attempt:
                    raise
        return self

    async def __aexit__(self, *exc):
        if self.playwright:
            await self.playwright.stop()  # Disconnect; retain the authorized Chrome profile.

    async def new_page(self):
        page = await self.context.new_page()
        session = await self.context.new_cdp_session(page)
        await session.send('Emulation.setTimezoneOverride', {'timezoneId': 'Europe/Moscow'})
        return page

    async def preflight(self, channel):
        self.module.CHANNEL_URL = editor_channel(channel)
        check = await self.new_page()
        try:
            await self.module.open_channel(check)
            if check.url.rstrip('/') != channel.rstrip('/'):
                raise core.ReleaseError('Дзен перенаправил с целевого канала: проверьте вход и URL редактора.')
            # Only the channel owner/editor sees the create-article control.
            create = check.locator('[data-testid="add-publication-button"]:visible')
            try:
                await create.first.wait_for(state='visible', timeout=15000)
            except self.module.PlaywrightTimeoutError:
                pass
            if not await create.count():
                create = check.get_by_role('button', name=re.compile(r'Создать|Написать|Добавить|\+', re.I))
            if not await create.count() or not await create.first.is_visible():
                raise core.ReleaseError('Не подтверждены права редактора Дзена. Проверьте вход и доступ к каналу.')
        finally:
            await check.close()

    async def create_draft(self):
        await self.module.open_new_article(self.page)
        if self.page.url.rstrip('/') == self.module.CHANNEL_URL.rstrip('/') or urlparse(self.page.url).hostname != 'dzen.ru':
            raise core.ReleaseError('Дзен не подтвердил открытие нового черновика; нужна сверка редактора.')
        return self.page.url

    async def open_draft(self, url):
        if urlparse(url).hostname != 'dzen.ru':
            raise core.ReleaseError('Неверный URL черновика.')
        await self.page.goto(url, wait_until='domcontentloaded', timeout=25000)

    async def fill(self, content, manifest):
        blocks = content['blocks']
        if blocks and os.name == 'nt' and manifest.get('dzen_docx_mode', 'auto') != 'sequence':
            # Word availability is checked before changing the editor. A failed paste is not retried blindly.
            command = ['powershell', '-NoProfile', '-NonInteractive', '-Command',
                       '$w = New-Object -ComObject Word.Application; $w.Quit()']
            available = await asyncio.to_thread(subprocess.run, command, capture_output=True, timeout=30)
            if available.returncode == 0:
                # Rich paste is valid only when the Word body is exactly the approved sequence.
                from tools.extract_docx_dzen_sequence import extract_blocks
                from tools.dzen_content import clean_blocks
                with tempfile.TemporaryDirectory() as temp:
                    with zipfile.ZipFile(core.local_path(manifest['docx_path'])) as archive:
                        source = clean_blocks(extract_blocks(archive, Path(temp)), content['title'], footer_text())
                    if plain(' '.join(b['text'] for b in source if b['type'] == 'text')) != plain(content['article']):
                        raise core.ReleaseError('Word DOCX отличается от утверждённой статьи; выберите dzen_docx_mode=sequence до утверждения.')
                copied = await asyncio.to_thread(subprocess.run,
                    ['powershell', '-NoProfile', '-NonInteractive', '-File', str(ROOT / 'tools/copy_docx_body_to_clipboard.ps1'),
                     '-DocxPath', str(core.local_path(manifest['docx_path']))], capture_output=True, timeout=60)
                if copied.returncode:
                    raise core.ReleaseError('Word не подготовил rich clipboard; проверьте документ локально.')
                await self.module.fill_article_from_rich_clipboard(self.page, content['title'], footer_text(),
                                                                  sum(b['type'] == 'image' for b in blocks))
                return
            if manifest.get('dzen_docx_mode') == 'word':
                raise core.ReleaseError('Microsoft Word недоступен.')
        await self.module.fill_article(self.page, content['title'], content['article'],
                                       media_paths=content['images'], sequence_blocks=blocks)

    async def resume_first_text(self, content):
        await self.module.fill_article_sequence(self.page, content['title'], content['blocks'],
                                                resume_first_text=True)

    async def verify(self, content):
        editors = self.page.locator('[contenteditable]')
        await editors.nth(1).wait_for(timeout=15000)
        if plain(await editors.first.inner_text()) != plain(content['title']):
            raise core.ReleaseError('Заголовок в редакторе не совпадает с комплектом.')
        body = editors.nth(1)
        actual_blocks = await self.module.article_blocks(self.page, body)
        if plain(' '.join(b['text'] for b in actual_blocks if b['type'] == 'text')) != plain(content['article']):
            raise core.ReleaseError('Текст в редакторе не совпадает с комплектом.')
        links = await body.locator('a[href]').evaluate_all(
            'els => els.map(e => ({text:e.innerText,href:e.href}))')
        if not article_links_match(links, content['article']):
            raise core.ReleaseError('Ссылки статьи или пять активных ссылок финального блока не совпадают с комплектом.')
        images = body.locator('[data-testid="article-image-item"] img')
        expected = sum(b['type'] == 'image' for b in content['blocks']) if content['blocks'] else len(content['images'])
        sizes = await images.evaluate_all('els => els.map(e => [e.naturalWidth, e.naturalHeight])')
        if len(sizes) != expected or any(w <= 0 or h <= 0 for w, h in sizes):
            raise core.ReleaseError('Изображения Дзена не загружены полностью.')
        if content['blocks']:
            expected = [(b['type'], plain(self.module.split_markdown_links(b['text'])[0])
                         if b['type'] == 'text' else '') for b in content['blocks']]
            actual = [(b['type'], plain(b.get('text', ''))) for b in actual_blocks]
            if actual != expected:
                raise core.ReleaseError('Изображения стоят вне утверждённого контекста.')
        return True

    async def submit(self, when):
        await self.module.publish(self.page, when.astimezone(ZoneInfo('Europe/Moscow')))

    async def observe(self, draft_url, content):
        # A fresh page/read is mandatory; the submit click is never evidence.
        page = await self.new_page()
        try:
            observation = {'channel': content['channel'], 'url': draft_url, 'status': 'unconfirmed',
                           'observed_at': datetime.now(ZoneInfo('UTC')).isoformat(),
                           'content_verified': False}
            expected = core.scheduled_time(content['scheduled_at'], content['timezone']).astimezone(ZoneInfo('Europe/Moscow'))
            observed = datetime.now(ZoneInfo('Europe/Moscow'))
            queue_url = content['channel'] + '/publications?state=pending'
            await page.goto(queue_url, wait_until='domcontentloaded', timeout=25000)
            try:
                await page.locator('tr[aria-label="Публикация"]').first.wait_for(timeout=15000)
            except self.module.PlaywrightTimeoutError:
                observation['queue_url'] = queue_url
                observation['matching_pending_rows'] = 0
                return observation
            rows = page.locator('tr[aria-label="Публикация"]')
            matches = []
            for i in range(await rows.count()):
                row = rows.nth(i)
                link = row.locator('a[href^="/a/"]')
                if await link.count() == 1:
                    title = next((line for line in (await link.inner_text()).splitlines() if line.strip()), '')
                    if plain(title) == plain(content['title']):
                        matches.append((row, link))
            observation['queue_url'] = queue_url
            observation['matching_pending_rows'] = len(matches)
            if len(matches) != 1:
                return observation
            row, link = matches[0]
            row_text = plain(await row.inner_text())
            observation['queue_status'] = row_text[-160:]
            public_url = urljoin('https://dzen.ru', await link.get_attribute('href'))
            draft_id = _article_id(draft_url, content['channel'])
            queue_id = _article_id(public_url, content['channel'])
            object_bound = draft_id is not None and draft_id == queue_id
            if draft_id is not None and queue_id != draft_id:
                return observation
            if 'Ожидает публикации' not in row_text or not _queue_date_matches(
                    row_text, expected, observed, object_bound):
                return observation
            await page.goto(public_url, wait_until='domcontentloaded', timeout=25000)
            heading = page.locator('h1')
            article = page.locator('[class*="article-render__container"]')
            try:
                await heading.first.wait_for(state='visible', timeout=15000)
                await article.first.wait_for(state='visible', timeout=15000)
            except self.module.PlaywrightTimeoutError:
                return observation
            if await heading.count() != 1 or plain(await heading.inner_text()) != plain(content['title']) or await article.count() != 1:
                return observation
            preview_id = _article_id(page.url, content['channel'])
            if preview_id != queue_id:
                return observation
            object_bound = object_bound and preview_id == draft_id
            observation['object_bound'] = object_bound
            scheduled_label = _owner_schedule_label(
                await page.locator('body').inner_text(), expected, observed, object_bound)
            if not scheduled_label:
                return observation
            wanted = content['blocks']
            expected_images = sum(b['type'] == 'image' for b in wanted) if wanted else len(content['images'])
            try:
                # Dzen defers off-screen image URLs; waiting without scrolling never loads them.
                async with asyncio.timeout(15):
                    for image in await article.locator('img').all():
                        await image.scroll_into_view_if_needed(timeout=5000)
                    await page.wait_for_function('''expected => {
                      const root = document.querySelector('[class*="article-render__container"]');
                      if (!root) return false;
                      const images = Array.from(root.querySelectorAll('img'));
                      return images.length >= expected && images.every(
                        image => image.complete && image.naturalWidth > 0 && image.naturalHeight > 0);
                    }''', arg=expected_images, timeout=15000)
            except (TimeoutError, self.module.PlaywrightTimeoutError):
                return observation
            actual = await article.evaluate('''root => {
              const blocks = [];
              function visit(node) {
                if (node.nodeType === Node.TEXT_NODE) {
                  if (node.textContent.trim()) blocks.push({type:'text', text:node.textContent});
                } else if (node.nodeType === Node.ELEMENT_NODE) {
                  if (node.tagName === 'IMG') blocks.push({type:'image'});
                  else if (!node.querySelector('img')) {
                    if (node.innerText.trim()) blocks.push({type:'text', text:node.innerText});
                  } else Array.from(node.childNodes).forEach(visit);
                }
              }
              Array.from(root.childNodes).forEach(visit);
              return blocks;
            }''')
            # Adjacent preview paragraphs may split one approved DOCX text block.
            if wanted:
                if _text_runs(actual) != _text_runs(wanted):
                    return observation
            elif plain(' '.join(b['text'] for b in actual if b['type'] == 'text')) != plain(content['article']):
                return observation
            pictures = await article.locator('img').evaluate_all('els => els.map(e => [e.naturalWidth,e.naturalHeight])')
            if len(pictures) != expected_images or any(w <= 0 or h <= 0 for w, h in pictures):
                return observation
            links = await article.locator('a[href]').evaluate_all('els => els.map(e => ({text:e.innerText,href:e.href}))')
            if not article_links_match(links, content['article']):
                return observation
            observation.update(status='scheduled', url=public_url, scheduled_at=expected.isoformat(),
                               content_verified=True, image_count=expected_images, link_count=len(links),
                               owner_schedule_text=scheduled_label)
            return observation
        finally:
            await page.close()


async def dzen_action(action, release):
    release.require_approval('dzen')
    if action != 'check-dzen':
        material(release)
        state = release.state.get('dzen', {})
        if not state.get('attempted') and state.get('status') not in ('scheduled', 'published'):
            core.require_future(release.manifest['scheduled_at'], release.manifest.get('timezone', 'Europe/Moscow'))
    async with CDPTransport() as transport:
        if action == 'check-dzen':
            return await check_dzen(release, transport)
        return await schedule_dzen(release, transport, prepare_only=action == 'prepare-dzen')
