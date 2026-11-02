from django.urls import path

from .views import (
    AdminNotificationHistoryView,
    AdminNotificationResendView,
    WhatsAppWebhookView,
)

admin_urlpatterns = [
    path(
        "applications/<uuid:application_id>/notifications/",
        AdminNotificationHistoryView.as_view(),
        name="admin-notification-history",
    ),
    path(
        "applications/<uuid:application_id>/notifications/<uuid:notification_id>/resend/",
        AdminNotificationResendView.as_view(),
        name="admin-notification-resend",
    ),
]

urlpatterns = [
    path(
        "notifications/whatsapp/webhook/",
        WhatsAppWebhookView.as_view(),
        name="whatsapp-webhook",
    ),
]
