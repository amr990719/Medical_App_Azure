from django.urls import path

from .views import WhatsAppWebhookView

urlpatterns = [
    path(
        "notifications/whatsapp/webhook/",
        WhatsAppWebhookView.as_view(),
        name="whatsapp-webhook",
    ),
]
