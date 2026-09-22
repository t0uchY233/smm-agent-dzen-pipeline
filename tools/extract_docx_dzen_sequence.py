#!/usr/bin/env python
"""Build an ordered Dzen payload from a DOCX document.

The Word XML body is walked in document order.  Each text fragment and embedded
image becomes an explicit block, which lets the Dzen CDP publisher put an image
next to the paragraph that introduced it instead of bulk-uploading all media.
"""
from __future__ import annotations

import argparse
import json
import posixpath
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
W = f"{{{W_NS}}}"
A = f"{{{A_NS}}}"
R = f"{{{R_NS}}}"
REL = f"{{{REL_NS}}}"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def docx_relationships(archive: zipfile.ZipFile) -> dict[str, str]:
    root = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
    relations: dict[str, str] = {}
    for relation in root.findall(f"{REL}Relationship"):
        if relation.get("Type", "").endswith("/image"):
            relations[relation.get("Id", "")] = relation.get("Target", "")
    return relations


def extract_blocks(archive: zipfile.ZipFile, media_dir: Path) -> list[dict[str, str]]:
    document = ET.fromstring(archive.read("word/document.xml"))
    relationships = docx_relationships(archive)
    body = document.find(f"{W}body")
    if body is None:
        raise ValueError("DOCX не содержит word/body.")

    media_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, Path] = {}
    blocks: list[dict[str, str]] = []

    def add_image(rel_id: str) -> None:
        target = relationships.get(rel_id)
        if not target:
            raise ValueError(f"В DOCX не найдена image-связь {rel_id}.")
        source_name = posixpath.normpath(posixpath.join("word", target))
        if source_name not in copied:
            destination = media_dir / Path(target).name
            destination.write_bytes(archive.read(source_name))
            copied[source_name] = destination
        blocks.append({"type": "image", "path": str(copied[source_name].resolve())})

    def add_paragraph(paragraph: ET.Element) -> None:
        text: list[str] = []

        def flush_text() -> None:
            value = "".join(text).strip()
            if value:
                blocks.append({"type": "text", "text": value})
            text.clear()

        # ElementTree.iter follows the source XML order, including a drawing
        # that appears between two text runs in the same Word paragraph.
        for item in paragraph.iter():
            if item.tag == f"{W}t":
                text.append(item.text or "")
            elif item.tag in {f"{W}br", f"{W}cr"}:
                text.append("\n")
            elif item.tag == f"{W}tab":
                text.append("\t")
            elif item.tag == f"{A}blip":
                flush_text()
                rel_id = item.get(f"{R}embed")
                if rel_id:
                    add_image(rel_id)
        flush_text()

    for child in body:
        if child.tag == f"{W}p":
            add_paragraph(child)
        elif child.tag == f"{W}tbl":
            # Keep a table's readable text in document position. The Dzen
            # editor has no Word-table upload; embedded images in table cells
            # still retain their original anchors.
            for paragraph in child.findall(f".//{W}p"):
                add_paragraph(paragraph)
    return blocks


def main() -> None:
    parser = argparse.ArgumentParser(description="Извлечь DOCX в последовательность для Дзена.")
    parser.add_argument("--docx", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--footer-file", required=True)
    parser.add_argument("--media-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    docx = Path(args.docx).resolve()
    footer_source = Path(args.footer_file).read_text(encoding="utf-8")
    # The reference file contains human instructions followed by the public
    # block. Only the first pin marker and everything after it belongs in an
    # article.
    footer_start = footer_source.find("📌")
    footer = (footer_source[footer_start:] if footer_start >= 0 else footer_source).strip()
    if not docx.is_file():
        raise FileNotFoundError(f"DOCX не найден: {docx}")
    if not footer:
        raise ValueError("Обязательный footer пуст.")

    media_dir = Path(args.media_dir).resolve()
    if media_dir.exists():
        shutil.rmtree(media_dir)
    with zipfile.ZipFile(docx) as archive:
        blocks = extract_blocks(archive, media_dir)

    # The Word title is represented by the Dzen title field, not a duplicate
    # first paragraph in the article body.
    for index, block in enumerate(blocks):
        if block["type"] == "text" and block["text"].strip() == args.title.strip():
            blocks.pop(index)
            break
    else:
        raise ValueError("В DOCX не найден заголовок, совпадающий с --title.")

    blocks.append({"type": "text", "text": footer})
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "title": args.title.strip(),
        "source_docx": str(docx),
        "blocks": blocks,
        "source_images": sum(block["type"] == "image" for block in blocks),
        "footer_appended": True,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output}: {len(blocks)} blocks, {payload['source_images']} images")


if __name__ == "__main__":
    main()
