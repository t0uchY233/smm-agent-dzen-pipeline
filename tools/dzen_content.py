"""Content contracts shared by the upstream-derived Dzen transport and CLI."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile
from urllib.parse import urlparse, urlsplit, urlunsplit, quote

from tools.publishing_core import ReleaseError, file_hash

FOOTER = Path(__file__).resolve().parents[1] / '.agents/skills/dzen/references/required-footer.md'
LINK = re.compile(r'\[([^\]]+)\]\((https?://[^\s)]+)\)')


def image_occurrences(docx):
    with zipfile.ZipFile(docx) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
    return sum(bool(node.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed'))
               for node in root.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}blip'))


def footer_text():
    return ('📌' + FOOTER.read_text(encoding='utf-8').split('📌', 1)[1]).strip()


def plain(text):
    return ' '.join(LINK.sub(r'\1', text).split())


def sequence_signature(blocks):
    """Compare text runs and exact embedded media, retaining every image boundary.

    extract_blocks copies ZIP members verbatim, so no pixel conversion is needed.
    """
    result, texts = [], []
    for block in blocks:
        if block['type'] == 'text':
            texts.append(block['text'])
        else:
            if texts:
                result.append(('text', plain(' '.join(texts))))
                texts = []
            result.append(('image', file_hash(block['path'])))
    if texts:
        result.append(('text', plain(' '.join(texts))))
    return result


def serialized_url(url):
    """Use the same URL spelling for Markdown and browser-serialized hrefs.

    Preserve path case, encoded reserved characters, query order and fragments.
    Never unquote: %2F and / (or %26 and &) are not interchangeable.
    """
    parts = urlsplit(url)
    host = (parts.hostname or '').encode('idna').decode('ascii').lower()
    if ':' in host:
        host = '[' + host + ']'
    userinfo = parts.netloc.rsplit('@', 1)[0] + '@' if '@' in parts.netloc else ''
    port = parts.port
    scheme = parts.scheme.lower()
    authority = userinfo + host
    if port is not None and (scheme, port) not in {('http', 80), ('https', 443)}:
        authority += ':' + str(port)

    def encode(value, safe):
        return re.sub(r'%[0-9a-fA-F]{2}', lambda m: m[0].upper(),
                      quote(value, safe=safe + '%'))

    result = urlunsplit((scheme, authority,
                        encode(parts.path or '/', "/:@!$&'()*+,;=-._~"), '', ''))
    # urlunsplit alone drops empty query/fragment delimiters; retain them.
    if '?' in url.split('#', 1)[0]:
        result += '?' + encode(parts.query, "/?:@!$&'()*+,;=-._~")
    if '#' in url:
        result += '#' + encode(parts.fragment, "/?:@!$&'()*+,;=-._~")
    return result


def article_links_match(links, article):
    """All approved body links plus exactly the five terminal footer links."""
    expected = [(plain(label), serialized_url(href)) for label, href in LINK.findall(article)]
    footer = [(plain(label), serialized_url(href)) for label, href in LINK.findall(footer_text())]
    actual = [(plain(link['text']), serialized_url(link['href'])) for link in links]
    return len(footer) == 5 and actual == expected and actual[-5:] == footer


def editor_channel(url):
    parsed = urlparse(url)
    if (parsed.scheme != 'https' or parsed.hostname != 'dzen.ru' or parsed.query or parsed.fragment
            or not parsed.path.startswith('/profile/editor/') or not parsed.path.removeprefix('/profile/editor/').strip('/')):
        raise ReleaseError('Укажите точный URL редактора канала https://dzen.ru/profile/editor/…')
    return url.rstrip('/')


def validate_footer(article):
    footer = footer_text()
    if not article.rstrip().endswith(footer) or article.count(footer) != 1:
        raise ReleaseError('Статья должна заканчиваться одним обязательным финальным блоком с пятью ссылками.')
    if len(LINK.findall(footer)) != 5:
        raise ReleaseError('В обязательном финальном блоке ожидается пять ссылок.')
    if article.count('📌 Подписывайтесь на наш') != footer.count('📌 Подписывайтесь на наш'):
        raise ReleaseError('Финальный блок продублирован.')


def clean_blocks(blocks, title, footer):
    result = []
    removed_title = False
    for block in blocks:
        if block['type'] == 'text':
            value = block['text'].strip()
            if not removed_title and plain(value) == plain(title):
                removed_title = True
                continue
            if value.startswith(('Публикация:', 'ВИЗУАЛ НА ЭКРАН', 'СХЕМА НА ЭКРАН', 'КАРТИНКА НА ЭКРАН')) or value == '— — —':
                continue
        result.append(block)
    if not removed_title:
        raise ReleaseError('В DOCX не найден соответствующий заголовок.')
    footer_start = next((i for i, block in enumerate(result)
                         if block['type'] == 'text' and plain(block['text']).startswith('📌 Подписывайтесь на наш')), None)
    if footer_start is not None:
        tail = result[footer_start:]
        if any(b['type'] != 'text' for b in tail) or plain(' '.join(b['text'] for b in tail)) != plain(footer):
            raise ReleaseError('Неоднозначный или повторный финальный блок в DOCX.')
        result = result[:footer_start]
    return result + [{'type': 'text', 'text': footer}]
