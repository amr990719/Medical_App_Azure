"""Server-side upload validation (PROMPT.md §18–19, Review Focus 4). Browser checks are UX only.

The filename, extension and claimed Content-Type are ignored. The type comes from the bytes
(signature sniffing with `filetype`, executables refused outright), images must decode fully with
Pillow and match the sniffed format, PDFs (behind ALLOW_PDF_DOCUMENTS) must not carry active
content, and the receipt must be at least 400×300 px.
"""

import hashlib
import re
import unicodedata
import warnings
from dataclasses import dataclass
from io import BytesIO

import filetype
from django.conf import settings
from PIL import Image

from apps.common.exceptions import FileTooLarge, ImageTooSmall, UnsupportedFileType
from apps.reference.constants import DocumentType

IMAGE_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")
PDF_CONTENT_TYPE = "application/pdf"
HEIC_CONTENT_TYPE = "image/heic"
EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    PDF_CONTENT_TYPE: "pdf",
}
PILLOW_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "HEIF": "image/heic",
}
IMAGE_ONLY_TYPES = frozenset({DocumentType.PERSONAL_PHOTO})

# Signatures refused before anything else: PE/DOS, ELF, Mach-O (32/64/fat), scripts, archives.
EXECUTABLE_SIGNATURES = (
    b"MZ", b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe",
    b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"#!", b"PK\x03\x04",
)  # fmt: skip
# Scripted / launching / embedding PDFs. (/OpenAction alone is common in scanner output.)
PDF_ACTIVE_CONTENT = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFiles?|RichMedia|XFA)\b")

MAX_FILENAME_LENGTH = 100
_UNSAFE_FILENAME_CHARS = re.compile(r"[^\w.-]")

MSG_TOO_LARGE = "حجم الملف يجب أن يكون أقل من {mb} ميجابايت"
MSG_CORRUPT = "تعذر قراءة الملف — يرجى رفع صورة سليمة"


@dataclass(frozen=True)
class UploadInfo:
    data: bytes
    content_type: str
    extension: str
    size: int
    sha256: str
    filename: str
    width: int | None = None
    height: int | None = None


def accepted_content_types(document_type: str | None = None) -> list[str]:
    types = list(IMAGE_CONTENT_TYPES)
    if document_type in IMAGE_ONLY_TYPES:
        return types
    if settings.ALLOW_PDF_DOCUMENTS:
        types.append(PDF_CONTENT_TYPE)
    if settings.ALLOW_HEIC:
        types.append(HEIC_CONTENT_TYPE)
    return types


def _unsupported_message(document_type) -> str:
    labels = {"image/jpeg": "JPG", "image/png": "PNG", "image/webp": "WEBP",
              PDF_CONTENT_TYPE: "PDF", HEIC_CONTENT_TYPE: "HEIC"}  # fmt: skip
    allowed = ", ".join(labels[t] for t in accepted_content_types(document_type))
    return f"نوع الملف غير مدعوم — الأنواع المسموح بها: {allowed}"


def sanitize_filename(raw: str | None) -> str:
    """Display-only name: basename, NFC, `[\\w.-]` (Arabic letters kept), at most 100 chars."""
    name = unicodedata.normalize("NFC", (raw or "").replace("\\", "/").split("/")[-1])
    name = re.sub(r"_+", "_", _UNSAFE_FILENAME_CHARS.sub("_", name)).lstrip("._-")
    if not name:
        return "document"
    if len(name) > MAX_FILENAME_LENGTH:
        stem, dot, ext = name.rpartition(".")
        if dot and 0 < len(ext) <= 10:
            name = stem[: MAX_FILENAME_LENGTH - len(ext) - 1] + "." + ext
        else:
            name = name[:MAX_FILENAME_LENGTH]
    return name


def _read(upload) -> bytes:
    if upload.size is not None and upload.size > settings.MAX_UPLOAD_BYTES:
        raise _too_large()
    data = b"".join(upload.chunks())
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise _too_large()
    return data


def _too_large() -> FileTooLarge:
    return FileTooLarge(MSG_TOO_LARGE.format(mb=settings.MAX_UPLOAD_BYTES // (1024 * 1024)))


def _sniff(data: bytes, document_type) -> str:
    if not data or data.startswith(EXECUTABLE_SIGNATURES):
        raise UnsupportedFileType(_unsupported_message(document_type))
    kind = filetype.guess(data)
    content_type = kind.mime if kind else ""
    if content_type == "image/heif":
        content_type = HEIC_CONTENT_TYPE
    if content_type not in accepted_content_types(document_type):
        raise UnsupportedFileType(_unsupported_message(document_type))
    return content_type


def _decode_image(data: bytes, content_type: str) -> tuple[int, int]:
    if content_type == HEIC_CONTENT_TYPE:
        try:
            import pillow_heif  # optional; only when ALLOW_HEIC is enabled

            pillow_heif.register_heif_opener()
        except ImportError:
            raise UnsupportedFileType(MSG_CORRUPT) from None
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(BytesIO(data)) as image:
                if PILLOW_FORMATS.get(image.format or "") != content_type:
                    raise UnsupportedFileType(MSG_CORRUPT)
                width, height = image.size
                if width * height > settings.DOCUMENT_MAX_PIXELS:
                    raise UnsupportedFileType(MSG_CORRUPT)
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()  # full decode: truncated or polyglot files fail here
        except UnsupportedFileType:
            raise
        except (OSError, SyntaxError, ValueError, Image.DecompressionBombWarning,
                Image.DecompressionBombError):  # fmt: skip
            raise UnsupportedFileType(MSG_CORRUPT) from None
    return width, height


def _check_pdf(data: bytes) -> None:
    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
        raise UnsupportedFileType(MSG_CORRUPT)
    if PDF_ACTIVE_CONTENT.search(data):
        raise UnsupportedFileType(MSG_CORRUPT)


def validate_upload(upload, *, document_type) -> UploadInfo:
    data = _read(upload)
    content_type = _sniff(data, document_type)
    width = height = None
    if content_type == PDF_CONTENT_TYPE:
        _check_pdf(data)
    else:
        width, height = _decode_image(data, content_type)
        if document_type == DocumentType.PAYMENT_RECEIPT and (
            width < settings.RECEIPT_MIN_WIDTH or height < settings.RECEIPT_MIN_HEIGHT
        ):
            raise ImageTooSmall()
    return UploadInfo(
        data=data,
        content_type=content_type,
        extension=EXTENSIONS[content_type],
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        filename=sanitize_filename(getattr(upload, "name", "")),
        width=width,
        height=height,
    )
