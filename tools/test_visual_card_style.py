from unittest.mock import patch

from PIL import Image, ImageDraw

from tools import render_video_visuals as rv


def assert_white_header_and_edges(image):
    assert image.size == (1920, 1080)
    # The entire former service-label area must remain empty and white.
    assert image.crop((0, 0, 1920, 150)).getextrema() == ((255, 255),) * 3
    assert image.getpixel((20, 600)) == (255, 255, 255)
    assert image.getpixel((1900, 600)) == (255, 255, 255)


def test_docx_card_has_white_canvas_no_service_label_and_preserves_transparency(tmp_path):
    source = tmp_path / "diagram.png"
    diagram = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    ImageDraw.Draw(diagram).rectangle((160, 60, 240, 140), fill="#cddff2")
    diagram.save(source)
    with patch.object(ImageDraw.ImageDraw, "text", autospec=True) as text:
        output = rv.render_docx_image_card(
            {"id": "docx_visual_001", "source_image_path": str(source)}, tmp_path / "cards"
        )
    labels = [call.args[2] for call in text.call_args_list]
    assert not any(label.upper() == "VISUAL" for label in labels)
    with Image.open(output) as image:
        assert_white_header_and_edges(image)
        # Transparent source edges become white; the central data block survives.
        assert image.getpixel((770, 400)) == (255, 255, 255)
        assert image.getpixel((960, 490)) == (205, 223, 242)


def test_fallback_card_has_no_type_badge_and_uses_pastel_accent(tmp_path):
    slide = {"id": "card", "kind": "problem", "title": "Цена ожидания", "bullets": ["Один час"]}
    original_text = ImageDraw.ImageDraw.text
    with patch.object(ImageDraw.ImageDraw, "text", autospec=True, side_effect=original_text) as text:
        output = rv.render_slide_card(slide, tmp_path)
    labels = [call.args[2] for call in text.call_args_list]
    assert "Цена ожидания" in labels
    assert "PROBLEM" not in labels
    assert "VISUAL" not in labels
    with Image.open(output) as image:
        assert_white_header_and_edges(image)
        assert image.getpixel((163, 343)) == (239, 208, 201)
