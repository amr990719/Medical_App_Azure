"""Meta's webhook endpoint. Public by design: the signature check in `webhook.py` is the guard."""

from django.core.exceptions import RequestDataTooBig
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
        try:
            # Read before `request.data`, which would consume and parse it. Reading can raise
            # before any signature check, so an oversized body is refused here, not as a 500
            # (a 500 tells Meta to retry for days).
            raw_body = request.body
        except RequestDataTooBig:
            return HttpResponse(status=413)
        try:
            webhook.process_webhook(raw_body, request.headers.get("X-Hub-Signature-256"))
        except webhook.InvalidSignature:
            return HttpResponse(status=403)
        return HttpResponse(status=200)
