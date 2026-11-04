"""Admin read model of a notification row. Safe fields only: no provider message id."""

from rest_framework import serializers

from apps.notifications.models import Notification

HISTORY_FIELDS = [
    "id",
    "event",
    "channel",
    "status",
    "recipient_masked",
    "error_code",
    "attempts",
    "fallback_of",
    "created_by_email",
    "created_at",
    "sent_at",
    "delivered_at",
]


class NotificationHistorySerializer(serializers.ModelSerializer):
    fallback_of = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = Notification
        fields = HISTORY_FIELDS
        read_only_fields = fields
