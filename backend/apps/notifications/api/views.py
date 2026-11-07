"""Meta's webhook endpoint. Public by design: the signature check in `webhook.py` is the guard."""

from django.core.exceptions import RequestDataTooBig
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdmin
from apps.applications.api.admin_views import reviewable_applications
from apps.common.throttling import ScopedRateThrottle
from apps.notifications import services, webhook
from apps.notifications.models import Notification

from .serializers import NotificationHistorySerializer


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


def _rows():
    return Notification.objects.select_related("created_by")


class AdminNotificationHistoryView(APIView):
    """`GET /admin/applications/{id}/notifications/` - newest first, safe fields only.
    Not paginated: one application has few rows."""

    permission_classes = [IsAdmin]

    @extend_schema(
        responses=NotificationHistorySerializer(many=True),
        operation_id="admin_notifications_list",
    )
    def get(self, request, application_id):
        app = get_object_or_404(reviewable_applications(), pk=application_id)
        rows = _rows().filter(application=app).order_by("-created_at", "-id")
        return Response(NotificationHistorySerializer(rows, many=True).data)


class AdminNotificationResendView(APIView):
    """`POST /admin/applications/{id}/notifications/{nid}/resend/` - a new row, 201."""

    permission_classes = [IsAdmin]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "notification_resend"

    @extend_schema(
        request=None,
        responses={201: NotificationHistorySerializer},
        operation_id="admin_notifications_resend",
    )
    def post(self, request, application_id, notification_id):
        app = get_object_or_404(reviewable_applications(), pk=application_id)
        source = get_object_or_404(Notification, pk=notification_id, application=app)
        new = services.resend(source, actor=request.user, request=request)
        return Response(
            NotificationHistorySerializer(_rows().get(pk=new.pk)).data,
            status=status.HTTP_201_CREATED,
        )
