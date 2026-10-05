"""Absolute session lifetime (PROMPT.md §27): the idle timeout is SESSION_COOKIE_AGE renewed on
every request; this caps the total lifetime from sign-in, whatever the activity."""

import time

from django.conf import settings
from django.contrib.auth import logout

SESSION_STARTED_KEY = "auth_started_at"


class AbsoluteSessionTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            started = request.session.get(SESSION_STARTED_KEY)
            if started is None:
                request.session[SESSION_STARTED_KEY] = time.time()
            elif time.time() - started > settings.SESSION_ABSOLUTE_TIMEOUT_SECONDS:
                logout(request)
        return self.get_response(request)
