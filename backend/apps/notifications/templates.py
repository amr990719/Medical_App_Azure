"""The one message table for both channels: event to Meta template name, email title and body.

Arabic text is copied from section 8 of the notifications design; change it there first.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.utils.html import escape

from apps.notifications.formatting import format_amount
from apps.notifications.models import DUES_EVENTS
from apps.reference.constants import NotificationEvent as E

CLOSING = "يرجى تسجيل الدخول إلى حسابك لمعرفة التفاصيل."
WHATSAPP_FOOTER = "لإيقاف الرسائل أرسل: إيقاف"
STOP_CONFIRMATION = (
    "تم إيقاف رسائل واتساب، وستصلك الإشعارات على بريدك الإلكتروني. "
    "يمكنك إعادة التفعيل من صفحة حسابك."
)
HELP_REPLY = "لإيقاف الرسائل أرسل: إيقاف. لأي استفسار يرجى تسجيل الدخول إلى حسابك."
OPEN_APPLICATION_LABEL = "فتح الطلب"


@dataclass(frozen=True)
class MessageTemplate:
    meta_name: str
    title: str
    body: str  # `{{1}}` reference number, `{{2}}` amount


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


MESSAGES: dict[str, MessageTemplate] = {
    E.APPLICATION_RECEIVED: MessageTemplate(
        "med_application_received",
        "تم استلام طلبك",
        "تم استلام طلبك رقم {{1}} في مشروع علاج الأعضاء وأسرهم، وسيتم مراجعته.",
    ),
    E.CORRECTION_NEEDED: MessageTemplate(
        "med_correction_needed",
        "مطلوب استكمال بيانات",
        "طلبك رقم {{1}} في مشروع علاج الأعضاء وأسرهم يحتاج إلى استكمال بعض البيانات.",
    ),
    E.APPROVED: MessageTemplate(
        "med_application_approved",
        "تم قبول طلبك",
        "تم قبول طلبك رقم {{1}} في مشروع علاج الأعضاء وأسرهم.",
    ),
    E.REJECTED: MessageTemplate(
        "med_application_rejected",
        "تم رفض طلبك",
        "تم رفض طلبك رقم {{1}} في مشروع علاج الأعضاء وأسرهم.",
    ),
    E.PAYMENT_CONFIRMED: MessageTemplate(
        "med_payment_confirmed",
        "تم تأكيد السداد",
        "تم تأكيد سداد الرسوم الخاصة بطلبك رقم {{1}}.",
    ),
    E.PAYMENT_RECEIPT_REJECTED: MessageTemplate(
        "med_payment_receipt_rejected",
        "لم يتم قبول الإيصال",
        "لم يتم قبول إيصال السداد الخاص بطلبك رقم {{1}}.",
    ),
    E.DUES_REQUESTED: MessageTemplate(
        "med_dues_requested",
        "مطلوب سداد مستحقات",
        "مطلوب سداد مستحقات نقابية بقيمة {{2}} لاستكمال طلبك رقم {{1}}.",
    ),
    E.DUES_CONFIRMED: MessageTemplate(
        "med_dues_confirmed",
        "تم تأكيد سداد المستحقات",
        "تم تأكيد سداد المستحقات النقابية بقيمة {{2}} الخاصة بطلبك رقم {{1}}.",
    ),
    E.DUES_RECEIPT_REJECTED: MessageTemplate(
        "med_dues_receipt_rejected",
        "لم يتم قبول إيصال المستحقات",
        "لم يتم قبول إيصال سداد المستحقات النقابية بقيمة {{2}} الخاصة بطلبك رقم {{1}}.",
    ),
    E.DUES_CANCELLED: MessageTemplate(
        "med_dues_cancelled",
        "تم إلغاء طلب المستحقات",
        "تم إلغاء طلب سداد المستحقات النقابية بقيمة {{2}} الخاص بطلبك رقم {{1}}.",
    ),
}


def template_parameters(event: str, *, reference: str, amount: Decimal | None = None) -> list[str]:
    """Meta body parameters in order: reference, then the amount for dues events."""
    if event not in DUES_EVENTS:
        return [reference]
    if amount is None:
        raise ValueError("a dues notification needs an amount")
    return [reference, format_amount(amount)]


def _fill(text: str, values: list[str], escape_values: bool) -> str:
    for index, value in enumerate(values, start=1):
        text = text.replace(f"{{{{{index}}}}}", escape(value) if escape_values else value)
    return text


def render_email(event: str, *, reference: str, amount: Decimal | None = None) -> RenderedEmail:
    message = MESSAGES[event]
    values = template_parameters(event, reference=reference, amount=amount)
    body_text = _fill(message.body, values, escape_values=False)
    body_html = _fill(escape(message.body), values, escape_values=True)
    url = escape(settings.NOTIFICATION_BASE_URL)
    html = (
        '<div dir="rtl" lang="ar">'
        f"<p>{body_html}</p><p>{escape(CLOSING)}</p>"
        f'<p><a href="{url}">{escape(OPEN_APPLICATION_LABEL)}</a></p>'
        "</div>"
    )
    return RenderedEmail(
        subject=f"طلبك رقم {reference}: {message.title}",
        html=html,
        text=f"{body_text}\n\n{CLOSING}\n{settings.NOTIFICATION_BASE_URL}",
    )
