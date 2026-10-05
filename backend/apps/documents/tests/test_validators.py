"""Server-side upload validation: sniffing, decoding, size, receipt dimensions (PROMPT.md §18–19).

Everything the browser says (filename, extension, Content-Type) is ignored."""

import hashlib

import pytest

from apps.common.exceptions import FileTooLarge, ImageTooSmall, UnsupportedFileType
from apps.documents.validators import sanitize_filename, validate_upload
from apps.reference.constants import DocumentType as T
from tests.files import (
    ELF_BYTES,
    EXE_BYTES,
    HTML_BYTES,
    SCRIPT_BYTES,
    image_bytes,
    pdf_bytes,
    png_upload,
    upload,
)


@pytest.mark.parametrize(
    ("fmt", "content_type", "extension"),
    [("JPEG", "image/jpeg", "jpg"), ("PNG", "image/png", "png"), ("WEBP", "image/webp", "webp")],
)
def test_accepts_supported_images(fmt, content_type, extension):
    data = image_bytes(fmt, (640, 480))
    info = validate_upload(
        upload(data, "x.bin", "application/octet-stream"), document_type=T.SYNDICATE_ID
    )
    assert info.content_type == content_type
    assert info.extension == extension
    assert (info.width, info.height) == (640, 480)
    assert info.size == len(data)
    assert info.sha256 == hashlib.sha256(data).hexdigest()
    assert info.data == data


def test_type_comes_from_content_not_from_the_name_or_claimed_type():
    info = validate_upload(
        upload(image_bytes("PNG"), "photo.jpg", "image/jpeg"), document_type=T.NATIONAL_ID_FRONT
    )
    assert info.content_type == "image/png"
    assert info.extension == "png"


@pytest.mark.parametrize(
    "payload", [EXE_BYTES, ELF_BYTES, SCRIPT_BYTES, HTML_BYTES], ids=["exe", "elf", "sh", "html"]
)
def test_exe_renamed_jpg_rejected_by_sniffing(payload):
    with pytest.raises(UnsupportedFileType):
        validate_upload(
            upload(payload, "receipt.jpg", "image/jpeg"), document_type=T.PAYMENT_RECEIPT
        )


def test_executable_appended_to_nothing_but_jpeg_magic_is_rejected_by_decoding():
    fake = b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF" + EXE_BYTES
    with pytest.raises(UnsupportedFileType):
        validate_upload(upload(fake, "x.jpg", "image/jpeg"), document_type=T.SYNDICATE_ID)


def test_truncated_image_rejected():
    data = image_bytes("JPEG", (800, 600))
    with pytest.raises(UnsupportedFileType):
        validate_upload(upload(data[: len(data) // 3], "x.jpg"), document_type=T.SYNDICATE_ID)


def test_zip_rejected():
    with pytest.raises(UnsupportedFileType):
        validate_upload(
            upload(b"PK\x03\x04" + b"\x00" * 100, "x.jpg"), document_type=T.SYNDICATE_ID
        )


def test_empty_file_rejected():
    with pytest.raises(UnsupportedFileType):
        validate_upload(upload(b"", "x.png"), document_type=T.SYNDICATE_ID)


def test_pdf_rejected_unless_flag(settings):
    settings.ALLOW_PDF_DOCUMENTS = False
    with pytest.raises(UnsupportedFileType):
        validate_upload(
            upload(pdf_bytes(), "x.pdf", "application/pdf"), document_type=T.SYNDICATE_ID
        )


def test_pdf_accepted_with_flag(settings):
    settings.ALLOW_PDF_DOCUMENTS = True
    info = validate_upload(upload(pdf_bytes(), "x.pdf"), document_type=T.BIRTH_CERTIFICATE)
    assert (info.content_type, info.extension) == ("application/pdf", "pdf")
    assert info.width is None


def test_pdf_with_active_content_rejected(settings):
    settings.ALLOW_PDF_DOCUMENTS = True
    with pytest.raises(UnsupportedFileType):
        validate_upload(
            upload(pdf_bytes(b"<< /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >>")),
            document_type=T.BIRTH_CERTIFICATE,
        )


def test_personal_photo_is_image_only_even_with_pdf_flag(settings):
    settings.ALLOW_PDF_DOCUMENTS = True
    with pytest.raises(UnsupportedFileType):
        validate_upload(upload(pdf_bytes(), "x.pdf"), document_type=T.PERSONAL_PHOTO)


def test_oversize_rejected(settings):
    settings.MAX_UPLOAD_BYTES = 1000
    with pytest.raises(FileTooLarge):
        validate_upload(png_upload((800, 600)), document_type=T.SYNDICATE_ID)


def test_too_many_pixels_rejected(settings):
    settings.DOCUMENT_MAX_PIXELS = 100
    with pytest.raises(UnsupportedFileType):
        validate_upload(png_upload((20, 20)), document_type=T.SYNDICATE_ID)


def test_tiny_receipt_rejected():
    with pytest.raises(ImageTooSmall) as exc:
        validate_upload(png_upload((10, 10)), document_type=T.PAYMENT_RECEIPT)
    assert "400×300" in exc.value.message


@pytest.mark.parametrize(
    ("size", "ok"), [((400, 300), True), ((399, 300), False), ((400, 299), False)]
)
def test_receipt_minimum_is_400_by_300(size, ok):
    if ok:
        validate_upload(png_upload(size), document_type=T.PAYMENT_RECEIPT)
    else:
        with pytest.raises(ImageTooSmall):
            validate_upload(png_upload(size), document_type=T.PAYMENT_RECEIPT)


def test_minimum_size_applies_only_to_the_receipt():
    validate_upload(png_upload((10, 10)), document_type=T.BIRTH_CERTIFICATE)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("scan.jpg", "scan.jpg"),
        ("../../etc/passwd.jpg", "passwd.jpg"),
        ("C:\\Users\\me\\بطاقة الرقم.png", "بطاقة_الرقم.png"),
        ("<script>alert(1)</script>.png", "script_.png"),  # basename after the "/"
        ("my <photo> (1).png", "my_photo_1_.png"),
        ("...hidden", "hidden"),
        ("", "document"),
        ("\x00\x01.png", "png"),
        ("a" * 300 + ".jpeg", "a" * 95 + ".jpeg"),
    ],
)
def test_filename_sanitized(raw, expected):
    result = sanitize_filename(raw)
    assert result == expected
    assert 1 <= len(result) <= 100
