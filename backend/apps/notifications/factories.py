from datetime import timedelta

import factory
from django.utils import timezone

from apps.applications.factories import ApplicationFactory
from apps.reference.constants import NotificationChannel, NotificationEvent, NotificationStatus

from .models import Notification


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    application = factory.SubFactory(ApplicationFactory)
    event = NotificationEvent.APPLICATION_RECEIVED
    channel = NotificationChannel.WHATSAPP
    status = NotificationStatus.PENDING
    next_attempt_at = factory.LazyFunction(timezone.now)
    expires_at = factory.LazyAttribute(lambda o: o.next_attempt_at + timedelta(hours=72))
