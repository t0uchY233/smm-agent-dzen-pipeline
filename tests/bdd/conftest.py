"""Minimal Dzen release artifacts; no render pipeline or production accounts."""
import zipfile
from xml.sax.saxutils import escape

from PIL import Image
import pytest

from tools import publishing_core as core
from tools.dzen_content import footer_text


def paragraph(text):
    return '<w:p><w:r><w:t>' + escape(text) + '</w:t></w:r></w:p>'


def drawing(number):
    return f'''<w:p><w:r><w:drawing><wp:inline>
      <wp:extent cx="19050" cy="19050"/><wp:docPr id="{number}" name="Image {number}"/>
      <a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
        <pic:pic><pic:nvPicPr><pic:cNvPr id="{number}" name="image{number}.png"/>
          <pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="rId{number}"/>
          <a:stretch><a:fillRect/></a:stretch></pic:blipFill>
          <pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="19050" cy="19050"/></a:xfrm>
            <a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
        </pic:pic></a:graphicData></a:graphic>
    </wp:inline></w:drawing></w:r></w:p>'''


@pytest.fixture
def release(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    images = [tmp_path / 'source.png', tmp_path / 'second.png']
    for image, color in zip(images, ('red', 'blue')):
        Image.new('RGB', (2, 2), color).save(image)
    docx = tmp_path / '2035-01-20-1400-Тема.docx'
    body = (paragraph('Тема') + paragraph('До изображения') + drawing(1)
            + paragraph('Между изображениями') + drawing(2) + paragraph('После изображения'))
    with zipfile.ZipFile(docx, 'w') as archive:
        archive.writestr('[Content_Types].xml', '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
          <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
          <Default Extension="xml" ContentType="application/xml"/>
          <Default Extension="png" ContentType="image/png"/>
          <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
        </Types>''')
        archive.writestr('_rels/.rels', '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
        </Relationships>''')
        archive.writestr('word/document.xml', f'''<w:document
          xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
          xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
          xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body>{body}<w:sectPr/></w:body></w:document>''')
        relationships = []
        for number, image in enumerate(images, 1):
            archive.writestr(f'word/media/image{number}.png', image.read_bytes())
            relationships.append(f'<Relationship Id="rId{number}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image{number}.png"/>')
        archive.writestr('word/_rels/document.xml.rels',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + ''.join(relationships) + '</Relationships>')
    manifest = dict(docx_path=str(docx), title='Тема', platforms=['dzen'],
                    scheduled_at='2035-01-20 14:00', timezone='Europe/Moscow',
                    dzen_channel='https://dzen.ru/profile/editor/id/test',
                    dzen_article='До изображения\n\nМежду изображениями\n\nПосле изображения\n\n' + footer_text())
    result = core.Release(core.prepare(manifest, tmp_path / 'release'))
    result.state['approved_revision'] = core.revision(manifest)
    result.save()
    return result
