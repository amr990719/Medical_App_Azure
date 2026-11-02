"""Doctor notifications (WhatsApp first, email fallback). One `Notification` row per channel
attempt chain; statuses change only through `apps.notifications.services`.

Rows hold no message text, full phone number or full email address: `recipient_masked` is the
only recipient trace.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.reference.constants import NotificationChannel, NotificationEvent, NotificationStatus

DUES_EVENTS = frozenset(
    {
        NotificationEvent.DUES_REQUESTED,
        NotificationEvent.DUES_CONFIRMED,
        NotificationEvent.DUES_RECEIPT_REJECTED,
        NotificationEvent.DUES_CANCELLED,
    }
)


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        "applications.InsuranceApplication",
        on_delete=models.PROTECT,
        related_name="notifications",
        db_index=False,  # covered by notification_app_created_idx
    )
    # Events DUES_*; supplies the amount at send time.
    dues_request = models.ForeignKey(
        "dues.SyndicateDuesRequest",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="notifications",
    )
    event = models.CharField(max_length=32, choices=NotificationEvent.choices)
    channel = models.CharField(max_length=16, choices=NotificationChannel.choices)
    status = models.CharField(
        max_length=16, choices=NotificationStatus.choices, default=NotificationStatus.PENDING
    )
    # Meta `wamid` or SES `MessageId`.
    provider_message_id = models.CharField(max_length=255, null=True, blank=True)  # noqa: DJ001
    # Also identifies the current claim.
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField()
    # Set only while SENDING; detects interrupted sends.
    sending_started_at = models.DateTimeField(null=True, blank=True)
    # Set once at enqueue; a fallback copies it.
    expires_at = models.DateTimeField()
    # Provider code or internal code; never provider free text.
    error_code = models.CharField(max_length=40, blank=True)
    # Filled at send: `010•••••678` or `a•••@example.com`.
    recipient_masked = models.CharField(max_length=64, blank=True)
    # The WhatsApp row this email replaces.
    fallback_of = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="fallback"
    )
    # The admin for a resend; null for automatic rows.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["next_attempt_at"],
                condition=Q(status=NotificationStatus.PENDING),
                name="notification_due_idx",
            ),
            models.Index(
                fields=["sent_at"],
                condition=Q(channel=NotificationChannel.WHATSAPP, status=NotificationStatus.SENT),
                name="notification_wa_sent_idx",
            ),
            models.Index(fields=["application", "created_at"], name="notification_app_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(event__in=NotificationEvent.values), name="notification_event_valid"
            ),
            models.CheckConstraint(
                condition=Q(channel__in=NotificationChannel.values),
                name="notification_channel_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=NotificationStatus.values), name="notification_status_valid"
            ),
            models.CheckConstraint(
                condition=(
                    Q(event__in=DUES_EVENTS, dues_request__isnull=False)
                    | ~Q(event__in=DUES_EVENTS) & Q(dues_request__isnull=True)
                ),
                name="notification_dues_request_iff_dues_event",
            ),
            models.CheckConstraint(
                condition=Q(fallback_of__isnull=True) | Q(channel=NotificationChannel.EMAIL),
                name="notification_fallback_is_email",
            ),
            models.UniqueConstraint(
                fields=["channel", "provider_message_id"],
                condition=Q(provider_message_id__isnull=False),
                name="uniq_notification_provider_id",
            ),
        ]

    def __str__(self) -> str:
        return f"notification {self.pk}"
