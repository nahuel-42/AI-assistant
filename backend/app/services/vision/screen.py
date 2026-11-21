"""Screen capture + text recognition with the OCR engine built into Windows (free, offline).

Only the recognized text is kept: the image never leaves memory and is never written to disk.
"""

from __future__ import annotations

import asyncio
import ctypes
import struct
import sys

# Upscaling helps Windows OCR with small UI and code fonts (tested: brackets and "=" survive at 2x).
_SCALE = 2.0
_MAX_CHARS = 8000


class ScreenReadError(RuntimeError):
    pass


def read_screen(language: str = "") -> str:
    """Capture the monitor under the mouse cursor and return its text. Blocking; run in a thread."""
    if sys.platform != "win32":
        raise ScreenReadError("Screen reading is only available on Windows.")
    width, height, bgra = _capture_monitor_under_cursor()
    text = asyncio.run(_ocr(width, height, bgra, language))
    return text[:_MAX_CHARS]


def _capture_monitor_under_cursor() -> tuple[int, int, bytes]:
    import mss

    class _Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    cursor = _Point()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(cursor))
    with mss.MSS() as screen:
        monitors = screen.monitors[1:]  # [0] is the union of all monitors
        target = next(
            (
                m for m in monitors
                if m["left"] <= cursor.x < m["left"] + m["width"] and m["top"] <= cursor.y < m["top"] + m["height"]
            ),
            monitors[0],
        )
        shot = screen.grab(target)
        return shot.width, shot.height, bytes(shot.bgra)


def _bmp(width: int, height: int, bgra: bytes) -> bytes:
    """Wrap raw BGRA pixels in a 32-bit top-down BMP so the Windows decoder can scale them."""
    header = struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, len(bgra), 2835, 2835, 0, 0)
    file_header = struct.pack("<2sIHHI", b"BM", 14 + len(header) + len(bgra), 0, 0, 14 + len(header))
    return file_header + header + bgra


def _pick_language(requested: str):
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine

    available = [lang.language_tag for lang in OcrEngine.available_recognizer_languages]
    if not available:
        raise ScreenReadError("No Windows OCR language is installed (Settings > Time & language > Language).")
    # Spanish engines also read English well, and keep accents and "¿", so prefer them for mixed use.
    preference = [requested] if requested else []
    preference += ["es-ES", "es-MX", "en-US", "en-GB"]
    tag = next((t for t in preference if t in available), available[0])
    return OcrEngine.try_create_from_language(Language(tag))


async def _ocr(width: int, height: int, bgra: bytes, language: str) -> str:
    from winrt.windows.graphics.imaging import (
        BitmapAlphaMode,
        BitmapDecoder,
        BitmapInterpolationMode,
        BitmapPixelFormat,
        BitmapTransform,
        ColorManagementMode,
        ExifOrientationMode,
    )
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(_bmp(width, height, bgra))
    await writer.store_async()
    writer.detach_stream()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    scale = min(_SCALE, OcrEngine.max_image_dimension / max(width, height))
    transform = BitmapTransform()
    transform.scaled_width = int(width * scale)
    transform.scaled_height = int(height * scale)
    transform.interpolation_mode = BitmapInterpolationMode.FANT
    bitmap = await decoder.get_software_bitmap_async(
        BitmapPixelFormat.BGRA8,
        BitmapAlphaMode.PREMULTIPLIED,
        transform,
        ExifOrientationMode.IGNORE_EXIF_ORIENTATION,
        ColorManagementMode.DO_NOT_COLOR_MANAGE,
    )
    result = await _pick_language(language).recognize_async(bitmap)
    return "\n".join(line.text for line in result.lines).strip()
