"""Офлайн-контракт навыков и CLI: без .env, сети и внешних действий."""
import argparse
from pathlib import Path
import re

import pytest

from tools import publish_release

ROOT = Path(__file__).resolve().parents[1]
CORE_SKILLS = (
    'video-script', 'ru-text', 'slop-stop-main',
    'render-docx-visuals', 'render-with-visuals',
)
ACTION = re.compile(r'publish_release\.py\s+(?:\\\s*)?([a-z][a-z0-9-]*)\b')
# Только явные пути репозитория, не части URL и не произвольные слова.
REPO_PATH = re.compile(
    r'(?<![\w./:\\-])(?:\./)?'
    r'(?:tools|youtube-publish|telegram-publish|dzen-publish|\.agents|docs)/'
    r'[^\s`\"\'<>|()\[\]{},;]*'
)
# Явные Markdown-ссылки и одиночные пути в inline-code, не shell-команды.
EXPLICIT_PATH = re.compile(r'\[[^\]\n]*\]\(([^\s)]+)\)|(?<!`)`([^`\n]+)`(?!`)')
REPO_DIRS = {'tools', 'youtube-publish', 'telegram-publish', 'dzen-publish', '.agents', 'docs'}
SLASH_COMMAND = re.compile(r'(?<![\w./:])\/([a-z][a-z0-9-]*)(?=[\s`\"<]|$)')


def documents():
    paths = set((ROOT / '.agents/skills').glob('*/SKILL.md'))
    paths.update((ROOT / '.agents/commands').glob('*.md'))
    paths.update((ROOT / 'docs/specs').glob('*.md'))
    paths.update(ROOT / name for name in (
        'README.md', 'AGENTS.md', 'docs/dzen-publication-route.md',
        '.agents/skills/dzen/references/cdp-recovery.md',
    ))
    return sorted(paths)


def repo_paths(text):
    # Нормализация также позволяет проверять Windows-примеры команд.
    text = text.replace('\\', '/')
    for match in REPO_PATH.finditer(text):
        value = match.group().removeprefix('./').rstrip('.,:;')
        yield value


def document_paths(text, document, root=ROOT):
    """Корневые пути — от root, ./ и ../ и прочие Markdown-ссылки — от документа."""
    text = text.replace('\\', '/')
    remainder = list(text)
    for match in EXPLICIT_PATH.finditer(text):
        link, code = match.groups()
        reference = link or code
        if (re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', reference)
                or reference.startswith(('#', '/'))):
            continue  # URL, якорь или абсолютный путь вне контракта репозитория.
        reference = reference.split('#', 1)[0]
        if not reference or any(c.isspace() for c in reference):
            continue
        relative = reference.startswith(('./', '../'))
        root_markdown = '/' not in reference and reference.endswith('.md')
        rooted = reference.split('/', 1)[0] in REPO_DIRS
        if not (relative or root_markdown or rooted or (link and Path(reference).suffix)):
            continue
        # Не проверяем тот же ./tools/... второй раз относительно корня.
        remainder[match.start():match.end()] = ' ' * (match.end() - match.start())
        base = document.parent if relative or not (rooted or root_markdown) else root
        yield base, reference
    # Сохраняем прежнюю проверку путей в командах и обычном тексте.
    for reference in repo_paths(''.join(remainder)):
        yield root, reference


@pytest.fixture
def cli_actions(monkeypatch):
    """Перехватываем parse_args ДО dispatch, читаем реальные subparsers."""
    captured = []

    class ParserCaptured(Exception):
        pass

    def capture(parser, *args, **kwargs):
        captured.append(parser)
        raise ParserCaptured

    monkeypatch.setattr(argparse.ArgumentParser, 'parse_args', capture)
    # main импортирован, но ни один handler (включая dotenv) не выполняется.
    with pytest.raises(ParserCaptured):
        publish_release.main([])
    assert len(captured) == 1
    subparsers = [action for action in captured[0]._actions
                 if isinstance(action, argparse._SubParsersAction)]
    assert len(subparsers) == 1
    return set(subparsers[0].choices)


def test_documented_actions_exist(cli_actions):
    errors = []
    mentions = set()
    for path in documents():
        for action in ACTION.findall(path.read_text(encoding='utf-8')):
            mentions.add(action)
            if action not in cli_actions:
                errors.append(f'{path.relative_to(ROOT)}: неизвестное действие {action}')
    assert mentions, 'Не найдено ни одной команды: проверьте извлечение примеров.'
    assert not errors, '\n'.join(errors)


def test_documented_repo_paths_exist():
    errors = []
    for path in documents():
        for base, reference in document_paths(path.read_text(encoding='utf-8'), path, ROOT):
            # <placeholder> обрезан регулярным выражением: проверяем его каталог.
            # Для glob нужна хотя бы одна реальная цель, а не только её родитель.
            exists = (any(base.glob(reference)) if any(c in reference for c in '*?')
                      else (base / reference).exists())
            if not exists:
                errors.append(f'{path.relative_to(ROOT)}: отсутствует {reference}')
    assert not errors, '\n'.join(errors)


@pytest.mark.parametrize('vendor,upstream,adapter', [
    ('youtube-publish', 'https://github.com/hassancs91/claude-youtube-editor',
     'tools/publishing_youtube.py'),
    ('telegram-publish', 'https://github.com/chigwell/telegram-mcp',
     'tools/publishing_telegram.py'),
    ('dzen-publish', 'https://github.com/Andrrreyiv/dzen-publish',
     'tools/publishing_dzen.py'),
])
def test_transport_table_matches_upstream(vendor, upstream, adapter):
    provenance = (ROOT / vendor / 'UPSTREAM.md').read_text(encoding='utf-8')
    pinned = re.search(r'(?:upstream commit|Pinned commit):\s*`([0-9a-f]{40})`',
                       provenance, flags=re.IGNORECASE)
    assert pinned, f'{vendor}: нет зафиксированного commit'
    specification = (ROOT / 'docs/specs/content-release.md').read_text(encoding='utf-8')
    rows = [line for line in specification.splitlines()
            if line.startswith('|') and f'{vendor}/UPSTREAM.md' in line]
    assert len(rows) == 1, f'{vendor}: нужна ровно одна строка таблицы'
    assert re.findall(r'`([0-9a-f]{40})`', rows[0]) == [pinned.group(1)]
    assert upstream in rows[0]
    assert f'`{adapter}`' in rows[0]


def test_core_skills_do_not_reference_removed_commands(cli_actions):
    active_commands = {path.stem for path in (ROOT / '.agents/commands').glob('*.md')}
    retired_tools = {
        path.name for path in (ROOT / 'archive/retired-2026-09-18/tools').glob('*.py')
        if not path.name.startswith('test_') and not (ROOT / 'tools' / path.name).exists()
    }
    errors = []
    for skill in CORE_SKILLS:
        path = ROOT / '.agents/skills' / skill / 'SKILL.md'
        text = path.read_text(encoding='utf-8')
        for command in SLASH_COMMAND.findall(text):
            if command not in active_commands:
                errors.append(f'{skill}: удалённая slash-команда /{command}')
        for action in ACTION.findall(text):
            if action not in cli_actions:
                errors.append(f'{skill}: удалённое действие CLI {action}')
        for filename in retired_tools:
            if re.search(r'(?<![\w-])' + re.escape(filename) + r'\b', text):
                errors.append(f'{skill}: архивная утилита {filename}')
    assert not errors, '\n'.join(errors)


@pytest.mark.parametrize('text,expected', [
    ('python tools/publish_release.py schedule-dzen --release DIR', ['schedule-dzen']),
    ('python tools/publish_release.py removed-action --release DIR', ['removed-action']),
    ('`tools/publish_release.py` — общий CLI', []),
])
def test_action_extraction(text, expected):
    assert ACTION.findall(text) == expected


def test_path_extraction_ignores_urls_and_keeps_local_paths():
    text = ('`tools/read_docx.py`, [путь](docs/specs/content-release.md). '
            'https://example.org/tools/not-local.py '
            r'python .\dzen-publish\publish_dzen.py --healthcheck')
    assert list(repo_paths(text)) == [
        'tools/read_docx.py', 'docs/specs/content-release.md',
        'dzen-publish/publish_dzen.py',
    ]


@pytest.mark.parametrize('reference,target', [
    ('`../other/SKILL.md`', 'skills/other/SKILL.md'),
    ('[навык](../other/SKILL.md#route)', 'skills/other/SKILL.md'),
    ('`./references/guide.md`', 'skills/current/references/guide.md'),
    ('[гайд](./references/guide.md)', 'skills/current/references/guide.md'),
    ('[гайд](references/guide.md)', 'skills/current/references/guide.md'),
    ('`tone-of-voice.md`', 'tone-of-voice.md'),
    ('[тон](tone-of-voice.md)', 'tone-of-voice.md'),
    ('`./tools/local.py`', 'skills/current/tools/local.py'),
    ('`tools/root.py`', 'tools/root.py'),
])
def test_documented_paths_detect_removed_file(tmp_path, monkeypatch, reference, target):
    document = tmp_path / 'skills/current/SKILL.md'
    document.parent.mkdir(parents=True)
    document.write_text(reference, encoding='utf-8')
    destination = tmp_path / target
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text('content', encoding='utf-8')
    monkeypatch.setitem(globals(), 'ROOT', tmp_path)
    monkeypatch.setitem(globals(), 'documents', lambda: [document])
    test_documented_repo_paths_exist()
    destination.unlink()
    # Проверяем всю проверку документов, не только результат regex.
    with pytest.raises(AssertionError, match='отсутствует'):
        test_documented_repo_paths_exist()


def test_document_paths_ignore_external_links_and_prose(tmp_path):
    document = tmp_path / 'skills/current/SKILL.md'
    text = ('[сайт](https://example.org/guide.md) '
            '`https://example.org/tools/remote.py` [почта](mailto:user@example.org) '
            '[раздел](#route) `status` обычные слова')
    assert list(document_paths(text, document, tmp_path)) == []
