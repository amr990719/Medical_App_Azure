"""Authentication backend for the BFF session.

There is no password sign-in (Entra External ID, or the development login). `authenticate()`
always returns None; the backend only restores the user stored in the session and refuses
inactive accounts.
"""

from .models import User


class SessionOnlyBackend:
    def authenticate(self, request, **credentials):
        return None

    def get_user(self, user_id):
        try:
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError):
            return None
        return user if user.is_active else None
