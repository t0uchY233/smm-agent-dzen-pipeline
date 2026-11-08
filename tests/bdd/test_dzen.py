import asyncio
from pathlib import Path
import hashlib
import io
from xml.sax.saxutils import escape
import json
import zipfile
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from tools import publishing_core as core
from tools import publishing_dzen as dzen
from tools.dzen_content import clean_blocks, footer_text, validate_footer


def test_dzen_localized_schedule_date_is_verified_exactly():
    transport = dzen.transport_module()
    when = datetime(2026, 9, 29, 10, 0, tzinfo=ZoneInfo('Europe/Moscow'))
    assert transport.schedule_date_matches('29 сентября 2026', when)
    assert transport.schedule_date_matches('29.09.2026', when)
    assert not transport.schedule_date_matches('29 сентября 2027', when)
    assert not transport.schedule_date_matches('30 сентября 2026', when)

@pytest.mark.parametrize('change', ['article', 'sequence', 'image', 'footer'])
def test_dzen_revision_binds_all_materials(release, tmp_path, monkeypatch, change):
    context = article(release, tmp_path)
    if change == 'article':
        release.manifest['dzen_article'] += '\nИзменение'
    elif change == 'sequence':
        path = Path(release.manifest['dzen_sequence_path'])
        payload = core.read_json(path)
        payload['blocks'].reverse()
        core.write_json(path, payload)
    elif change == 'image':
        (tmp_path / 'source.png').write_bytes(b'changed')
    else:
        from tools import dzen_content
        footer = tmp_path / 'footer.md'
        footer.write_text(dzen_content.FOOTER.read_text(encoding='utf-8') + '\nchange', encoding='utf-8')
        monkeypatch.setattr(dzen_content, 'FOOTER', footer)
    with pytest.raises(core.ReleaseError, match='OK'):
        release.require_approval('dzen')
    assert not context['transport'].calls


@pytest.mark.parametrize('change', ['missing-sequence', 'missing-image', 'extra-image'])
def test_docx_image_count_is_required_before_browser(release, tmp_path, change):
    context = article(release, tmp_path)
    if change == 'missing-sequence':
        del release.manifest['dzen_sequence_path']
    else:
        path = release.manifest['dzen_sequence_path']
        payload = core.read_json(path)
        if change == 'missing-image':
            payload['blocks'].pop(1)
        else:
            payload['blocks'].insert(1, dict(payload['blocks'][1]))
        core.write_json(path, payload)
    release.state['approved_revision'] = core.revision(release.manifest)
    with pytest.raises(core.ReleaseError, match='изображени'):
        asyncio.run(dzen.schedule_dzen(release, context['transport']))
    assert not context['transport'].calls


@pytest.mark.parametrize('action', ['prepare-dzen', 'schedule-dzen', 'check-dzen'])
def test_all_dzen_actions_require_approval_before_cdp(release, monkeypatch, action):
    release.state.pop('approved_revision')
    monkeypatch.setattr(dzen, 'CDPTransport', lambda: pytest.fail('must not connect'))
    with pytest.raises(core.ReleaseError, match='OK'):
        asyncio.run(dzen.dzen_action(action, release))


@pytest.mark.parametrize('action', ['prepare-dzen', 'schedule-dzen', 'check-dzen'])
@pytest.mark.parametrize('status,code', [('prepared', 0), ('scheduled', 0), ('published', 0), ('unconfirmed', 2)])
def test_dzen_cli_dispatch_and_exit_code(release, monkeypatch, action, status, code):
    from tools.publish_release import main

    async def fake_action(actual_action, actual_release):
        assert actual_action == action
        actual_release.update('dzen', status=status)
        return status

    monkeypatch.setattr(dzen, 'dzen_action', fake_action)
    assert main([action, '--release', str(release.directory)]) == code


@pytest.mark.parametrize('platforms', [['youtube'], ['telegram'], ['youtube', 'telegram']])
@pytest.mark.parametrize('sequence', ['absent', 'present', 'missing'])
def test_non_dzen_revision_matches_legacy_formula(release, tmp_path, platforms, sequence):
    article(release, tmp_path)
    manifest = dict(release.manifest, platforms=platforms,
                    dzen_images=[str(tmp_path / 'source.png')])
    if sequence == 'absent':
        del manifest['dzen_sequence_path']
    elif sequence == 'missing':
        manifest['dzen_sequence_path'] = str(tmp_path / 'not-present.json')
    # Formula from HEAD before T4: additional Dzen fields are still in manifest,
    # but neither sequence files nor the footer were added to files.
    files = {}
    for key in ('docx_path', 'video_path', 'thumbnail_path', 'render_report_path'):
        if manifest.get(key):
            files[key] = core.file_hash(core.local_path(manifest[key]))
    for name in manifest.get('dzen_images', []):
        files[name] = core.file_hash(core.local_path(name))
    raw = json.dumps({'manifest': manifest, 'files': files}, sort_keys=True, ensure_ascii=False)
    legacy = hashlib.sha256(raw.encode()).hexdigest()
    assert core.revision(manifest) == legacy
    release.manifest = manifest
    release.state['approved_revision'] = legacy
    for platform in platforms:
        release.require_approval(platform)


@pytest.mark.parametrize('change', ['swapped', 'replaced', 'moved', 'source-text'])
def test_docx_sequence_identity_is_checked_after_reapproval(release, tmp_path, change):
    context = article(release, tmp_path)
    path = release.manifest['dzen_sequence_path']
    payload = core.read_json(path)
    blocks = payload['blocks']
    if change == 'swapped':
        blocks[1]['path'], blocks[3]['path'] = blocks[3]['path'], blocks[1]['path']
    elif change == 'replaced':
        from PIL import Image
        Image.new('RGB', (2, 2), 'green').save(tmp_path / 'second.png')
    elif change == 'moved':
        blocks.insert(2, blocks.pop(1))
    else:
        blocks[0]['text'] = 'Изменённый исходный абзац'
        release.manifest['dzen_article'] = '\n\n'.join(b['text'] for b in blocks if b['type'] == 'text')
    core.write_json(path, payload)
    release.state['approved_revision'] = core.revision(release.manifest)
    with pytest.raises(core.ReleaseError, match='отличается от DOCX'):
        asyncio.run(dzen.schedule_dzen(release, context['transport']))
    assert not context['transport'].calls


def test_extractor_preserves_docx_image_bytes_and_context(release, tmp_path):
    from tools.extract_docx_dzen_sequence import extract_blocks
    from tools.dzen_content import sequence_signature
    article(release, tmp_path)
    with zipfile.ZipFile(release.manifest['docx_path']) as archive:
        source = clean_blocks(extract_blocks(archive, tmp_path / 'extracted'), 'Тема', footer_text())
        images = [b for b in source if b['type'] == 'image']
        assert len(images) == 2
        for number, block in enumerate(images, 1):
            assert Path(block['path']).read_bytes() == archive.read(f'word/media/image{number}.png')
    assert Path(images[0]['path']).read_bytes() != Path(images[1]['path']).read_bytes()
    assert sequence_signature(source) == sequence_signature(dzen.material(release)['blocks'])


@pytest.mark.parametrize('remaining,submitted', [(59, False), (60, True)])
def test_minute_guard_is_rechecked_after_filling(release, tmp_path, monkeypatch, remaining, submitted):
    context = article(release, tmp_path)
    when = core.scheduled_time(release.manifest['scheduled_at'])

    class Clock(datetime):
        current = when - timedelta(seconds=120)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)

    monkeypatch.setattr(core, 'datetime', Clock)
    transport = context['transport']
    original_fill = transport.fill

    async def slow_fill(content, manifest):
        await original_fill(content, manifest)
        Clock.current = when - timedelta(seconds=remaining)

    transport.fill = slow_fill
    if submitted:
        assert asyncio.run(dzen.schedule_dzen(release, transport)) == 'scheduled'
    else:
        with pytest.raises(core.ReleaseError, match='меньше минуты'):
            asyncio.run(dzen.schedule_dzen(release, transport))
    assert 'fill' in transport.calls and 'verify' in transport.calls
    assert ('submit' in transport.calls) is submitted
    saved = core.Release(release.directory).state['dzen']
    assert saved['draft_attempted'] is True
    assert bool(saved.get('attempted')) is submitted


def rewrite_docx(path, transform):
    with zipfile.ZipFile(path) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    transform(members)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    Path(path).write_bytes(output.getvalue())


@pytest.mark.parametrize('substitute', [False, True])
def test_same_basename_docx_members_keep_distinct_identity(release, tmp_path, substitute):
    from tools.extract_docx_dzen_sequence import extract_blocks

    article(release, tmp_path)
    docx = release.manifest['docx_path']

    def nested_members(members):
        rels = members['word/_rels/document.xml.rels'].decode()
        for number, directory in ((1, 'a'), (2, 'b')):
            old = f'media/image{number}.png'
            new = f'media/{directory}/image.png'
            members['word/' + new] = members.pop('word/' + old)
            rels = rels.replace(old, new)
        members['word/_rels/document.xml.rels'] = rels.encode()

    rewrite_docx(docx, nested_members)
    with zipfile.ZipFile(docx) as archive:
        blocks = clean_blocks(extract_blocks(archive, tmp_path / 'nested'), 'Тема', footer_text())
        images = [b for b in blocks if b['type'] == 'image']
        assert images[0]['path'] != images[1]['path']
        for block, directory in zip(images, ('a', 'b')):
            assert Path(block['path']).read_bytes() == archive.read(f'word/media/{directory}/image.png')
    if substitute:
        images[0]['path'] = images[1]['path']
    core.write_json(release.manifest['dzen_sequence_path'], {'title': 'Тема', 'blocks': blocks})
    release.state['approved_revision'] = core.revision(release.manifest)
    release.require_approval('dzen')
    if substitute:
        with pytest.raises(core.ReleaseError, match='отличается от DOCX'):
            dzen.material(release)
    else:
        assert dzen.material(release)['blocks'] == blocks


@pytest.mark.parametrize('change', ['title', 'footer', 'both'])
def test_material_accepts_docx_whitespace_normalization(release, tmp_path, change):
    article(release, tmp_path)
    payload = core.read_json(release.manifest['dzen_sequence_path'])
    if change in ('title', 'both'):
        release.manifest['title'] = payload['title'] = 'Экономика сети'

    def normalized_source(members):
        xml = members['word/document.xml'].decode()
        if change in ('title', 'both'):
            xml = xml.replace('<w:t>Тема</w:t>', '<w:t>Экономика\u00a0  сети</w:t>')
        if change in ('footer', 'both'):
            footer = footer_text().replace(' ', '\u00a0')
            paragraph = '<w:p><w:r><w:t>' + escape(footer) + '</w:t></w:r></w:p>'
            xml = xml.replace('<w:sectPr/>', paragraph + '<w:sectPr/>')
        members['word/document.xml'] = xml.encode()

    rewrite_docx(release.manifest['docx_path'], normalized_source)
    core.write_json(release.manifest['dzen_sequence_path'], payload)
    release.state['approved_revision'] = core.revision(release.manifest)
    release.require_approval('dzen')
    assert dzen.material(release)['title'] == release.manifest['title']


def test_clean_blocks_does_not_normalize_quotes():
    with pytest.raises(core.ReleaseError, match='заголовок'):
        clean_blocks([{'type': 'text', 'text': '«Тема»'}], '"Тема"', footer_text())


@pytest.mark.parametrize('approved,actual,equal', [
    ('https://EXAMPLE.org', 'https://example.org/', True),
    ('https://example.org/данные?ключ=значение',
     'https://example.org/%D0%B4%D0%B0%D0%BD%D0%BD%D1%8B%D0%B5?%D0%BA%D0%BB%D1%8E%D1%87=%D0%B7%D0%BD%D0%B0%D1%87%D0%B5%D0%BD%D0%B8%D0%B5', True),
    ('https://example.org/A', 'https://example.org/a', False),
    ('https://example.org/?', 'https://example.org/', False),
    ('https://example.org/?a=1', 'https://example.org/?a=2', False),
    ('https://example.org/a%2Fb', 'https://example.org/a/b', False),
    ('https://example.org/?a=1&b=2', 'https://example.org/?b=2&a=1', False),
    ('https://example.org/?a=1%26b=2', 'https://example.org/?a=1&b=2', False),
])
def test_article_link_url_serialization(approved, actual, equal):
    from tools.dzen_content import LINK, article_links_match
    text = f'[Источник]({approved})\n\n' + footer_text()
    links = [{'text': 'Источник', 'href': actual}]
    links += [{'text': label, 'href': href} for label, href in LINK.findall(footer_text())]
    assert article_links_match(links, text) is equal


scenarios('features/dzen.feature')

class FakeTransport:
    def __init__(self, content):
        self.calls=[]
        self.fail=None
        self.partial=False
        self.observation={'channel':content['channel'],'url':'https://dzen.ru/profile/editor/id/test/edit/one',
                          'status':'scheduled','scheduled_at':'2035-01-20T14:00:00+03:00','content_verified':True}
    async def preflight(self,channel):
        self.calls.append('preflight')
        if self.fail=='auth': raise core.ReleaseError('Нет прав')
    async def create_draft(self):
        self.calls.append('create')
        if self.fail=='create': raise TimeoutError()
        return self.observation['url']
    async def open_draft(self,url): self.calls.append('open')
    async def fill(self,content,manifest):
        self.calls.append('fill')
        if self.fail=='fill': self.partial=True; raise TimeoutError()
    async def verify(self,content):
        self.calls.append('verify')
        if self.partial: raise core.ReleaseError('Неполный черновик')
    async def resume_first_text(self,content):
        self.calls.append('resume')
        if self.fail=='fill':
            raise core.ReleaseError('Сохранённый черновик не совпадает с первым абзацем')
        self.partial=False
    async def submit(self,when):
        self.calls.append('submit')
        if self.fail=='submit': raise TimeoutError()
    async def observe(self,url,content):
        self.calls.append('observe')
        return self.observation

@given('утверждённая статья с последовательностью DOCX', target_fixture='context')
def article(release,tmp_path):
    article='До изображения\n\nМежду изображениями\n\nПосле изображения\n\n'+footer_text()
    sequence=tmp_path/'sequence.json'
    core.write_json(sequence,{'title':'Тема','blocks':[
        {'type':'text','text':'До изображения'},
        {'type':'image','path':str(tmp_path/'source.png')},
        {'type':'text','text':'Между изображениями'},
        {'type':'image','path':str(tmp_path/'second.png')},
        {'type':'text','text':'После изображения'},
        {'type':'text','text':footer_text()}]})
    release.manifest.update(dzen_article=article,dzen_channel='https://dzen.ru/profile/editor/id/test',dzen_sequence_path=str(sequence))
    core.write_json(release.directory/'manifest.json',release.manifest)
    release.state['approved_revision']=core.revision(release.manifest)
    release.state['youtube']={'status':'scheduled','id':'existing'}
    release.save()
    return {'release':release,'transport':FakeTransport(dzen.material(release))}

@given('утверждение отсутствует')
def no_approval(context):
    context['release'].state.pop('approved_revision')

@given(parsers.parse('таймаут на этапе "{stage}"'))
def timeout(context,stage):
    context['transport'].fail=stage

@given('независимая проверка не нашла расписание')
def missing(context):
    context['transport'].observation['status']='unconfirmed'

@given('сервер показывает другое время')
def wrong_time(context):
    context['transport'].observation['scheduled_at']='2035-01-20T15:00:00+03:00'

@given('доступ к каналу отсутствует')
def no_rights(context):
    context['transport'].fail='auth'

@given('последовательность содержит другой текст')
def other_text(context):
    path=context['release'].manifest['dzen_sequence_path']
    data=core.read_json(path); data['blocks'][0]['text']='Другой текст'
    core.write_json(path,data)
    # Even approval of mismatching inputs cannot cause publishing of an unpreviewed body.
    context['release'].state['approved_revision']=core.revision(context['release'].manifest)

@when('назначается публикация через транспорт dzen-publish')
def schedule(context):
    try:
        context['result']=asyncio.run(dzen.schedule_dzen(context['release'],context['transport']))
    except (core.ReleaseError,TimeoutError) as error:
        context['error']=error

@when('публикация вызывается повторно')
def twice(context):
    schedule(context)
    context['release']=core.Release(context['release'].directory)
    schedule(context)

@then('подтверждена отложка после независимого чтения')
def scheduled(context):
    assert context.get('error') is None
    assert context['result']=='scheduled'
    assert context['transport'].calls==['preflight','create','fill','verify','submit','preflight','observe']
    assert (context['release'].directory/'dzen-observation.json').is_file()

@then('сохранено состояние остальных площадок')
def preserved(context):
    assert context['release'].state['youtube']=={'status':'scheduled','id':'existing'}

@then('браузер не изменён')
def untouched(context):
    assert isinstance(context.get('error'),core.ReleaseError)
    assert not context['transport'].calls

@then('черновик не создан')
def no_draft(context):
    assert 'create' not in context['transport'].calls
    assert context.get('error')

@then(parsers.parse('этап "{stage}" не выполнен дважды'))
def once(context,stage):
    assert Counter(context['transport'].calls)[stage]==1
    assert context['release'].state['youtube']['id']=='existing'

@then('результат остаётся unconfirmed')
def unconfirmed(context):
    assert context['result']=='unconfirmed'
    assert core.Release(context['release'].directory).state['dzen']['status']=='unconfirmed'

@given('DOCX уже заканчивается обязательным блоком',target_fixture='context')
def with_footer():
    return {'blocks':[{'type':'text','text':'Тема'},{'type':'text','text':'Публикация: 2035-01-20 14:00 MSK'},
                      {'type':'text','text':'Тело'},{'type':'text','text':footer_text()}]}

@when('готовится последовательность статьи')
def clean(context):
    context['blocks']=clean_blocks(context['blocks'],'Тема',footer_text())

@then('финальный блок добавлен ровно один раз')
def unique_footer(context):
    text='\n\n'.join(b['text'] for b in context['blocks'])
    validate_footer(text)
    assert text.count(footer_text())==1
    assert 'Публикация:' not in text

@given('исходный скрипт dzen-publish',target_fixture='context')
def script():
    return {'script':Path(__file__).resolve().parents[2]/'dzen-publish/publish_dzen.py'}

@when('он запускается без утверждённого выпуска')
def no_args(context,tmp_path):
    context['process']=subprocess.run([sys.executable,str(context['script'])],cwd=tmp_path,
                                      capture_output=True,text=True,encoding='utf-8',timeout=15)

@given('отправка уже выполнена и время назначения истекло')
def already_sent(context,monkeypatch):
    release=context['release']
    release.update('dzen',attempted=True,draft_url=context['transport'].observation['url'])
    def expired(*args,**kwargs):
        raise core.ReleaseError('До публикации меньше минуты')
    monkeypatch.setattr(core,'require_future',expired)

@then('выполняется только независимая сверка')
def only_read(context):
    assert context.get('error') is None
    assert context['transport'].calls==['preflight','observe']

@then('выполнение прекращается до подключения Chrome')
def before_chrome(context):
    proc=context['process']
    assert proc.returncode==2
    assert 'Connecting' not in proc.stderr


def test_cdp_connection_failure_is_actionable_before_any_draft(monkeypatch):
    import tools.chrome_cdp as cdp
    calls = []

    def offline():
        calls.append(1)
        raise RuntimeError('Chrome not installed; set CHROME_BINARY or install Google Chrome.')

    monkeypatch.setattr(cdp, 'endpoint', lambda: 'http://127.0.0.1:9222')
    monkeypatch.setattr(cdp, 'ensure_chrome', offline)

    async def enter():
        async with dzen.CDPTransport():
            pytest.fail('must not open the editor')

    with pytest.raises(core.ReleaseError, match='черновик не создавался.*Chrome not installed'):
        asyncio.run(enter())
    assert len(calls) == 2  # bounded recovery, then a clear stop
