"""Ownership and editability guards shared by every service that mutates an application.

Views enforce object permissions too (Session 3); services check again so that no caller can
bypass them (defence in depth, PROMPT.md §28).
"""

from apps.common.exceptions import ApplicationNotEditable, PermissionDeniedError

from .models import InsuranceApplication


def lock_application(application_id) -> InsuranceApplication:
    """Fetch the application row with SELECT ... FOR UPDATE. Call inside transaction.atomic()."""
    return (
        InsuranceApplication.objects.select_for_update(of=("self",))
        .select_related("doctor", "doctor__user")
        .get(pk=application_id)
    )


def ensure_owner(application: InsuranceApplication, actor) -> None:
    if actor is None or application.doctor.user_id != actor.pk:
        raise PermissionDeniedError()


def ensure_editable_by_owner(application: InsuranceApplication, actor) -> None:
    ensure_owner(application, actor)
    if not application.is_editable:
        raise ApplicationNotEditable()
