import subprocess
import sys
import types

import pytest
from PIL import Image

from tools import render_video_visuals as rv


def _make_raw_video(path, duration="1.2"):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=700:sample_rate=44100",
            "-t",
            duration,
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _make_card(path):
    Image.new("RGB", rv.CARD_SIZE, "#ffffff").save(path, "PNG")


def test_parse_env_strips_quotes_and_ignores_comments(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "PLAIN=value",
                "DOUBLE=\"quoted value\"",
                "SINGLE='single quoted'",
                "BROKEN",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert rv.parse_env(env_path) == {
        "PLAIN": "value",
        "DOUBLE": "quoted value",
        "SINGLE": "single quoted",
    }


def test_read_docx_via_tool_raises_render_error_on_subprocess_failure(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="bad docx")

    monkeypatch.setattr(rv.subprocess, "run", fake_run)

    with pytest.raises(rv.RenderVisualsError, match="bad docx"):
        rv.read_docx_via_tool("missing.docx")


def test_transcribe_with_whisper_returns_ms_word_timestamps_and_retries_cpu(monkeypatch, tmp_path):
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")
    model_calls = []

    class FakeWhisperModel:
        def __init__(self, model_size, device, compute_type):
            model_calls.append((model_size, device, compute_type))
            if device == "cuda":
                raise RuntimeError("GPU memory unavailable")

        def transcribe(self, path, **kwargs):
            assert path == str(audio_path)
            assert kwargs["language"] == "ru"
            assert kwargs["word_timestamps"] is True
            word = types.SimpleNamespace(word=" готово", start=1.25, end=1.75, probability=0.98)
            segment = types.SimpleNamespace(text="Готово.", start=1.0, end=2.0, words=[word])
            return iter([segment]), types.SimpleNamespace(language="ru")

    faster_whisper = types.ModuleType("faster_whisper")
    faster_whisper.WhisperModel = FakeWhisperModel
    ctranslate2 = types.ModuleType("ctranslate2")
    ctranslate2.get_cuda_device_count = lambda: 1
    monkeypatch.setitem(sys.modules, "faster_whisper", faster_whisper)
    monkeypatch.setitem(sys.modules, "ctranslate2", ctranslate2)

    result = rv.transcribe_with_whisper(audio_path, language="ru", device="auto")

    assert model_calls == [("large-v3", "cuda", "int8_float16"), ("large-v3", "cpu", "int8")]
    assert result["model"] == "large-v3"
    assert result["text"] == "Готово."
    assert result["words"] == [{"text": "готово", "start": 1250, "end": 1750, "confidence": 0.98}]


def test_extract_audio_writes_mono_mp3_for_asr(tmp_path):
    raw = tmp_path / "raw.mp4"
    audio = tmp_path / "audio.mp3"
    _make_raw_video(raw)

    rv.extract_audio(raw, audio)

    assert audio.exists()
    assert audio.stat().st_size > 0


def test_render_video_with_enabled_overlays_creates_output_mp4(tmp_path):
    raw = tmp_path / "raw.mp4"
    card = tmp_path / "card.png"
    output = tmp_path / "overlay.mp4"
    _make_raw_video(raw)
    _make_card(card)

    rv.render_video_with_enabled_overlays(
        raw,
        [{"image_path": str(card), "start_sec": 0.2, "end_sec": 0.9}],
        output,
    )

    assert output.exists()
    assert output.stat().st_size > 0


