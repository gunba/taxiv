from pathlib import Path

import pytest

from ingest.core import media


class DummyCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_detect_metafile_format_uses_extension() -> None:
    blob = b"random"
    assert media.detect_metafile_format(blob, source_extension=".wmf") == "wmf"
    assert media.detect_metafile_format(blob, source_extension=".EMF") == "emf"


def test_detect_metafile_format_uses_signature() -> None:
    wmf_blob = b"\xd7\xcd\xc6\x9a" + b"0" * 60
    emf_blob = b"X" * 40 + b" EMF" + b"0" * 20
    assert media.detect_metafile_format(wmf_blob) == "wmf"
    assert media.detect_metafile_format(emf_blob) == "emf"


def test_convert_metafile_to_png_imagemagick_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_find() -> tuple[str, ...]:
        return ("convert",)

    def fake_run(*args, **kwargs):
        output_path = args[0][-1]
        Path(output_path).write_bytes(b"PNGDATA")
        return DummyCompletedProcess()

    monkeypatch.setattr(media, "_find_imagemagick_executable", fake_find)
    monkeypatch.setattr(media.subprocess, "run", fake_run)

    outcome = media.convert_metafile_to_png(b"blob", "wmf")
    assert outcome.png_bytes == b"PNGDATA"
    assert outcome.messages == []


def test_convert_metafile_to_png_collects_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media, "_find_imagemagick_executable", lambda: None)
    monkeypatch.setattr(media.shutil, "which", lambda name: None)

    outcome = media.convert_metafile_to_png(b"blob", "emf")
    assert outcome.png_bytes is None
    assert any("ImageMagick" in message for message in outcome.messages)
