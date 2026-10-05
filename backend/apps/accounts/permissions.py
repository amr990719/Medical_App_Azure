"""Role permissions (PROMPT.md §28). Object-level scoping lives in each view's queryset."""

from rest_framework.permissions import BasePermission

from .models import Role


def _active_user(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.is_active:
        return None
    return user


class IsAuthenticatedActive(BasePermission):
    def has_permission(self, request, view) -> bool:
        return _active_user(request) is not None


class IsDoctor(BasePermission):
    """Doctor-facing endpoints: only the DOCTOR role, and only their own objects."""

    def has_permission(self, request, view) -> bool:
        user = _active_user(request)
        return user is not None and user.role == Role.DOCTOR


class IsAdmin(BasePermission):
    """Admin endpoints. The role is granted only by `manage.py grant_admin`."""

    def has_permission(self, request, view) -> bool:
        user = _active_user(request)
        return user is not None and user.role == Role.ADMIN
