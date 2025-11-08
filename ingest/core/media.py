"""Utilities for handling ingestion media assets."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Callable, Optional, Sequence


@dataclass
class ConversionOutcome:
    """Represents the result of attempting to convert a vector metafile."""

    png_bytes: Optional[bytes]
    messages: list[str]


def detect_metafile_format(
    blob: bytes,
    *,
    source_extension: Optional[str] = None,
    content_type: Optional[str] = None,
) -> Optional[str]:
    """Return the detected metafile format if the blob looks like WMF/EMF."""

    normalized_extension = (source_extension or "").lower()
    if normalized_extension in {".wmf", "wmf"}:
        return "wmf"
    if normalized_extension in {".emf", "emf"}:
        return "emf"

    if content_type:
        lowered = content_type.lower()
        if "wmf" in lowered:
            return "wmf"
        if "emf" in lowered:
            return "emf"

    header = blob[:64]
    if len(header) >= 4:
        # Aldus placeable WMF files start with the magic key 0x9AC6CDD7 (little endian)
        if header[:4] == b"\xd7\xcd\xc6\x9a":
            return "wmf"
        # Standard WMF without the placeable header often starts with the type value 0x0001
        # followed by the header size and a magic number 0x9AC6.
        if header[:2] == b"\x01\x00" and header[2:4] in {b"\t\x00", b"\x00\t"}:
            return "wmf"

    if len(header) >= 44 and header[40:44] == b" EMF":
        return "emf"

    return None


def convert_metafile_to_png(blob: bytes, fmt: str) -> ConversionOutcome:
    """Attempt to convert a WMF/EMF blob to PNG using available system tools."""

    format_key = fmt.lower()
    messages: list[str] = []

    for converter in _CONVERTERS:
        if format_key not in converter.formats:
            continue
        result, message = converter.function(blob, format_key)
        if result is not None:
            return ConversionOutcome(png_bytes=result, messages=messages)
        if message:
            messages.append(message)

    return ConversionOutcome(png_bytes=None, messages=messages)


@dataclass
class _Converter:
    name: str
    formats: frozenset[str]
    function: "ConverterFunction"


ConverterFunction = Callable[[bytes, str], tuple[Optional[bytes], Optional[str]]]


def _convert_with_imagemagick(blob: bytes, fmt: str) -> tuple[Optional[bytes], Optional[str]]:
    executable = _find_imagemagick_executable()
    if executable is None:
        return None, "ImageMagick executable not available"

    with tempfile.TemporaryDirectory(prefix="taxiv_wmf_") as tmpdir:
        input_path = os.path.join(tmpdir, f"source.{fmt}")
        output_path = os.path.join(tmpdir, "output.png")
        with open(input_path, "wb") as handle:
            handle.write(blob)

        command = list(executable)
        command.extend([input_path, output_path])

        try:
            completed = subprocess.run(
                command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
        except FileNotFoundError:
            return None, "ImageMagick executable vanished during execution"
        except subprocess.TimeoutExpired:
            return None, "ImageMagick conversion timed out"

        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="ignore").strip()
            return None, (
                "ImageMagick conversion failed"
                + (f": {stderr}" if stderr else "")
            )

        if not os.path.exists(output_path):
            if completed.stdout:
                return completed.stdout, None
            return None, "ImageMagick conversion produced no output"

        with open(output_path, "rb") as output_file:
            data = output_file.read()
        if not data:
            return None, "ImageMagick conversion produced an empty file"

        return data, None


def _convert_with_wmf2svg(blob: bytes, fmt: str) -> tuple[Optional[bytes], Optional[str]]:
    if fmt != "wmf":
        return None, None

    wmf2svg = shutil.which("wmf2svg")
    if not wmf2svg:
        return None, "wmf2svg executable not available"

    rsvg_convert = shutil.which("rsvg-convert")
    if not rsvg_convert:
        return None, "rsvg-convert executable not available"

    with tempfile.TemporaryDirectory(prefix="taxiv_wmf_") as tmpdir:
        input_path = os.path.join(tmpdir, "source.wmf")
        svg_path = os.path.join(tmpdir, "intermediate.svg")
        output_path = os.path.join(tmpdir, "output.png")
        with open(input_path, "wb") as handle:
            handle.write(blob)

        convert_command = [wmf2svg, "-o", svg_path, input_path]
        try:
            convert_completed = subprocess.run(
                convert_command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
        except FileNotFoundError:
            return None, "wmf2svg executable vanished during execution"
        except subprocess.TimeoutExpired:
            return None, "wmf2svg conversion timed out"

        if convert_completed.returncode != 0 or not os.path.exists(svg_path):
            stderr = convert_completed.stderr.decode("utf-8", errors="ignore").strip()
            return None, (
                "wmf2svg conversion failed"
                + (f": {stderr}" if stderr else "")
            )

        raster_command = [rsvg_convert, "-f", "png", "-o", output_path, svg_path]
        try:
            raster_completed = subprocess.run(
                raster_command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
        except FileNotFoundError:
            return None, "rsvg-convert executable vanished during execution"
        except subprocess.TimeoutExpired:
            return None, "rsvg-convert conversion timed out"

        if raster_completed.returncode != 0:
            stderr = raster_completed.stderr.decode("utf-8", errors="ignore").strip()
            return None, (
                "rsvg-convert conversion failed"
                + (f": {stderr}" if stderr else "")
            )

        if not os.path.exists(output_path):
            if raster_completed.stdout:
                return raster_completed.stdout, None
            return None, "rsvg-convert conversion produced no output"

        with open(output_path, "rb") as output_file:
            data = output_file.read()
        if not data:
            return None, "rsvg-convert conversion produced an empty file"
        return data, None


def _find_imagemagick_executable() -> Optional[Sequence[str]]:
    """Return the command list needed to invoke ImageMagick if available."""

    magick = shutil.which("magick")
    if magick:
        return (magick, "convert")

    convert = shutil.which("convert")
    if convert:
        return (convert,)

    return None


_CONVERTERS: tuple[_Converter, ...] = (
    _Converter(
        name="imagemagick",
        formats=frozenset({"wmf", "emf"}),
        function=_convert_with_imagemagick,
    ),
    _Converter(
        name="wmf2svg",
        formats=frozenset({"wmf"}),
        function=_convert_with_wmf2svg,
    ),
)
