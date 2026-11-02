"""Meta's webhook endpoint. Public by design: the signature check in `webhook.py` is the guard."""

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from apps.notifications import webhook


@extend_schema(exclude=True)
class WhatsAppWebhookView(APIView):
    authentication_classes: list = []
    permission_classes: list = []
    throttle_classes: list = []

    def get(self, request):
        challenge = webhook.verify_subscription(request.query_params)
        if challenge is None:
            return HttpResponse(status=403)
        return HttpResponse(challenge, content_type="text/plain")

    def post(self, request):
        raw_body = request.body  # before `request.data`, which would consume and parse it
        try:
            webhook.process_webhook(raw_body, request.headers.get("X-Hub-Signature-256"))
        except webhook.InvalidSignature:
            return HttpResponse(status=403)
        return HttpResponse(status=200)
