from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction
from apps.audit.services import record


class Command(BaseCommand):
    help = "Revoke the ADMIN role from a user, by email or Entra object id (oid)."

    def add_arguments(self, parser):
        parser.add_argument("identifier", help="email address or Entra object id")

    @transaction.atomic
    def handle(self, *args, identifier: str, **options):
        identifier = identifier.strip()
        users = list(
            User.objects.select_for_update().filter(
                Q(email=identifier.lower()) | Q(entra_oid=identifier)
            )
        )
        if len(users) != 1:
            raise CommandError("No single user matches that email or object id.")
        user = users[0]
        if user.role != Role.ADMIN:
            self.stdout.write("User is not an administrator; nothing changed.")
            return
        # Lock every active admin so two concurrent revokes cannot both pass this check.
        active_admins = list(
            User.objects.select_for_update().filter(role=Role.ADMIN, is_active=True)
        )
        if user.is_active and len(active_admins) <= 1:
            raise CommandError(
                "Refusing to revoke the last administrator; grant another admin first."
            )
        user.role = Role.DOCTOR
        user.save(update_fields=["role"])  # the role change also ends the user's sessions
        record(actor=None, action=AuditAction.ADMIN_ROLE_REVOKED, obj=user)
        self.stdout.write(self.style.SUCCESS(f"Revoked ADMIN from user {user.pk}."))
