"""Independent queue/author-preview reads; no CDP profile or live Dzen traffic."""
import asyncio
from datetime import datetime
from html import escape
import json
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright
import pytest

from tools import publishing_dzen as dzen
from tools.dzen_content import LINK, footer_text

pytestmark = pytest.mark.browser


@pytest.fixture(scope='module')
def chromium():
    loop = asyncio.new_event_loop()

    async def start():
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch()
        return playwright, browser

    playwright, browser = loop.run_until_complete(start())
    yield loop, browser
    loop.run_until_complete(browser.close())
    loop.run_until_complete(playwright.stop())
    loop.close()


@pytest.mark.parametrize('case,confirmed', [
    ('today', True),
    ('unpadded', True),
    ('lazy-image', True),
    ('tomorrow', True),
    ('full-date', True),
    ('full-date-year', True),
    ('future-explicit-year', True),
    ('future-queue-yearless', False),
    ('future-owner-yearless', False),
    ('future-both-yearless', False),
    ('past-both-yearless', False),
    ('current-year-unbound', False),
    ('current-year-wrong-object', False),
    ('current-year-owner-unbound', False),
    ('preview-wrong-object', False),
    ('body-link', True),
    ('changed-body-link', False),
    ('wrong-day', False),
    ('wrong-month', False),
    ('wrong-queue-time', False),
    ('wrong-title', False),
    ('title-substring', False),
    ('wrong-heading', False),
    ('today-wrong-date', False),
    ('tomorrow-wrong-date', False),
    ('wrong-owner-time', False),
    ('wrong-owner-year', False),
    ('moved-image', False),
    ('missing-image', False),
    ('extra-image', False),
    ('unloaded-image', False),
    ('changed-footer-link', False),
    ('missing-footer-text', False),
    ('extra-image-wrapper-text', False),
    ('duplicate-queue-rows', False),
])
def test_observe_localized_queue_and_split_preview(chromium, monkeypatch, case, confirmed):
    class ObservedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            # UTC is still September 30; relative labels must use Moscow's October 1.
            current = cls(2026, 10, 1, 0, 30, tzinfo=ZoneInfo('Europe/Moscow'))
            return current.astimezone(tz) if tz else current.replace(tzinfo=None)

    monkeypatch.setattr(dzen, 'datetime', ObservedDatetime)
    day = 2 if case in ('tomorrow', 'today-wrong-date') else 3 if case in ('full-date', 'full-date-year', 'tomorrow-wrong-date') else 1
    year = 2035 if case.startswith('future-') else 2025 if case == 'past-both-yearless' else 2026
    title = 'Экономика\u00a0сети АЗС'
    content = {
        'channel': 'https://dzen.ru/profile/editor/id/isolated',
        'title': title,
        'scheduled_at': f'{year}-10-{day:02}T14:00:00+03:00',
        'timezone': 'Europe/Moscow',
        'article': 'До изображения\n\nПосле изображения\n\n' + footer_text(),
        'blocks': [
            {'type': 'text', 'text': 'До изображения'},
            {'type': 'image', 'path': 'approved.png'},
            {'type': 'text', 'text': 'После изображения'},
            {'type': 'text', 'text': footer_text()},
        ],
        'images': [],
    }
    if case in ('body-link', 'changed-body-link'):
        linked_text = 'До изображения [Источник](https://example.org/source)'
        content['blocks'][0]['text'] = linked_text
        content['article'] = content['article'].replace('До изображения', linked_text, 1)
    queue_title = title.replace('\u00a0', ' ')
    if case == 'wrong-title':
        queue_title = 'Другая экономика сети АЗС'
    elif case == 'title-substring':
        queue_title += ' — новая версия'
    queue_date = f'{day:02} окт 14:00'
    if case in ('future-explicit-year', 'future-owner-yearless', 'current-year-owner-unbound'):
        queue_date = f'{day:02} окт {year} 14:00'
    if case == 'unpadded':
        queue_date = '1 окт 14:00'
    elif case == 'wrong-day':
        queue_date = '11 окт 14:00'
    elif case == 'wrong-month':
        queue_date = '01 ноя 14:00'
    elif case == 'wrong-queue-time':
        queue_date = '01 окт 14:01'
    row = (f'<tr aria-label="Публикация"><td><a href="/a/isolated">'
           f'<div>{escape(queue_title)}</div><div>Статистика публикации</div></a></td>'
           f'<td>Ожидает публикации {queue_date}</td></tr>')
    queue_html = '<table>' + row * (2 if case == 'duplicate-queue-rows' else 1) + '</table>'
    label = 'Будет опубликовано сегодня в 14:00'
    if case in ('tomorrow', 'tomorrow-wrong-date'):
        label = 'Будет опубликовано завтра в 14:00'
    elif case == 'full-date':
        label = 'Будет опубликовано 3 октября в 14:00'
    elif case == 'full-date-year':
        label = 'Будет опубликовано 03 октября 2026 в 14:00'
    elif case == 'wrong-owner-year':
        label = 'Будет опубликовано 1 октября 2027 в 14:00'
    elif case == 'wrong-owner-time':
        label = 'Будет опубликовано сегодня в 14:01'
    elif case in ('future-explicit-year', 'future-queue-yearless'):
        label = f'Будет опубликовано {day} октября {year} в 14:00'
    elif case in ('future-owner-yearless', 'future-both-yearless', 'past-both-yearless',
                  'current-year-unbound', 'current-year-wrong-object', 'current-year-owner-unbound'):
        label = f'Будет опубликовано {day} октября в 14:00'

    footer = LINK.sub(lambda match: f'<a href="{escape(match[2], quote=True)}">{escape(match[1])}</a>',
                      escape(footer_text()))
    paragraphs = footer.split('\n\n')
    if case == 'changed-footer-link':
        paragraphs[0] = paragraphs[0].replace('href="', 'href="https://example.org/changed?original=', 1)
    elif case == 'missing-footer-text':
        paragraphs[0] = paragraphs[0].replace('Подписывайтесь на наш ', '')
    image = '<figure><img src="/test-image.png"></figure>'
    if case == 'lazy-image':
        image = '<figure style="margin-top:6000px"><img src="/test-image.png" loading="lazy"></figure>'
    if case == 'extra-image-wrapper-text':
        image = '<figure><img src="/test-image.png"><span>Неутверждённая подпись</span></figure>'
    before = '<p>До изображения</p>'
    if case in ('body-link', 'changed-body-link'):
        href = 'https://example.org/source' if case == 'body-link' else 'https://example.org/changed'
        before = f'<p>До изображения <a href="{href}">Источник</a></p>'
    after = '<p>После изображения</p>'
    if case == 'moved-image':
        body = before + after + image
    elif case == 'missing-image':
        body = before + after
    else:
        body = before + image + after
    if case == 'extra-image':
        body += image
    body += ''.join(f'<p>{paragraph}</p>' for paragraph in paragraphs)
    heading = 'Не тот заголовок' if case == 'wrong-heading' else title
    preview = (f'<h1>{escape(heading)}</h1><div>{label}</div>'
               f'<article class="article-render__container">{body}</article>')
    # The fresh navigation initially has no h1/article; then its image loads later.
    author_html = '<script>setTimeout(() => { document.body.innerHTML = ' + json.dumps(preview) + '; }, 100)</script>'
    image_bytes = '<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"><rect width="2" height="2"/></svg>'

    async def check(browser):
        context = await browser.new_context()
        transport = dzen.CDPTransport()
        transport.context = context

        async def respond(route):
            url = route.request.url
            if url == content['channel'] + '/publications?state=pending':
                await route.fulfill(content_type='text/html; charset=utf-8', body=queue_html)
            elif url == 'https://dzen.ru/a/isolated':
                if case == 'preview-wrong-object':
                    await route.fulfill(status=302, headers={'Location': 'https://dzen.ru/a/other'})
                else:
                    await route.fulfill(content_type='text/html; charset=utf-8', body=author_html)
            elif url == 'https://dzen.ru/a/other':
                await route.fulfill(content_type='text/html; charset=utf-8', body=author_html)
            elif url == 'https://dzen.ru/test-image.png':
                await asyncio.sleep(0.15)
                if case == 'unloaded-image':
                    await route.fulfill(status=404, body='not an image')
                else:
                    await route.fulfill(content_type='image/svg+xml', body=image_bytes)
            else:
                await route.abort()

        await context.route('**/*', respond)
        try:
            draft_url = content['channel'] + '/isolated/edit'
            if case in ('current-year-unbound', 'current-year-owner-unbound'):
                # No known object ID: a title/date match cannot establish the year.
                draft_url = content['channel'] + '/unknown-route'
            elif case == 'current-year-wrong-object':
                draft_url = content['channel'] + '/other/edit'
            return await transport.observe(draft_url, content)
        finally:
            await context.close()

    loop, browser = chromium
    observation = loop.run_until_complete(check(browser))
    if confirmed:
        assert observation['status'] == 'scheduled'
        assert observation['content_verified'] is True
        assert observation['scheduled_at'] == content['scheduled_at']
        assert observation['owner_schedule_text'] == label
        assert observation['url'] == 'https://dzen.ru/a/isolated'
        assert observation['image_count'] == 1
        assert observation['link_count'] == (6 if case == 'body-link' else 5)
    else:
        assert observation['status'] == 'unconfirmed'
        assert observation['content_verified'] is False
    if case == 'duplicate-queue-rows':
        assert observation['matching_pending_rows'] == 2


@pytest.mark.parametrize('change', ['none', 'bare-url', 'cyrillic-url', 'body-href', 'footer-href', 'extra-link'])
def test_editor_verifies_body_and_footer_links(chromium, change):
    from tools import publishing_core as core

    href = {'bare-url': 'https://EXAMPLE.org',
            'cyrillic-url': 'https://example.org/данные?ключ=значение'}.get(
                change, 'https://example.org/source')
    first = f'Источник: [данные]({href})'
    footer = footer_text()
    content = {'title': 'Тема', 'article': first + '\n\n' + footer,
               'blocks': [{'type': 'text', 'text': first}, {'type': 'text', 'text': footer}],
               'images': []}

    def html(text):
        return LINK.sub(lambda m: f'<a href="{escape(m[2], quote=True)}">{escape(m[1])}</a>', text)

    first_html, footer_html = html(first), html(footer)
    if change == 'body-href':
        first_html = first_html.replace('https://example.org/source', 'https://example.org/other')
    elif change == 'footer-href':
        footer_html = footer_html.replace('href="', 'href="https://example.org/other?original=', 1)
    elif change == 'extra-link':
        # Same visible text, but an unapproved link.
        first_html = first_html.replace('Источник:', '<a href="https://example.org/extra">Источник:</a>')

    async def check(browser):
        context = await browser.new_context(service_workers='block')
        await context.route('**/*', lambda route: route.abort())
        transport = dzen.CDPTransport()
        transport.context = context
        transport.page = await context.new_page()
        try:
            await transport.page.set_content(
                '<div contenteditable="true">Тема</div><div contenteditable="true">'
                f'<p data-block="true">{first_html}</p><p data-block="true">{footer_html}</p></div>')
            if change in ('none', 'bare-url', 'cyrillic-url'):
                assert await transport.verify(content) is True
            else:
                with pytest.raises(core.ReleaseError, match='Ссылки статьи'):
                    await transport.verify(content)
        finally:
            await context.close()

    loop, browser = chromium
    loop.run_until_complete(check(browser))
