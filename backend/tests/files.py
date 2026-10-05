"""Upload fixtures generated at test time — no binary files are committed."""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

# Windows PE header ("MZ" + DOS stub) — enough for any sniffer to call it an executable.
EXE_BYTES = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + b"\x00" * 200
ELF_BYTES = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 200
SCRIPT_BYTES = b"#!/bin/sh\nrm -rf /\n"
HTML_BYTES = b"<html><script>alert(1)</script></html>"


def image_bytes(fmt: str = "PNG", size: tuple[int, int] = (800, 600), color="white") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def pdf_bytes(extra: bytes = b"") -> bytes:
    return (
        b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj\n"
        + extra
        + b"\ntrailer << /Root 1 0 R >>\n%%EOF\n"
    )


def upload(
    data: bytes, name: str = "scan.png", content_type: str = "image/png"
) -> SimpleUploadedFile:
    """`content_type` is what the browser CLAIMS; the server must ignore it."""
    return SimpleUploadedFile(name, data, content_type=content_type)


def png_upload(size=(800, 600), name="scan.png") -> SimpleUploadedFile:
    return upload(image_bytes("PNG", size), name, "image/png")
