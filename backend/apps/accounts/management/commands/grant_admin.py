from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction
from apps.audit.services import record


class Command(BaseCommand):
    help = "Grant the ADMIN role to an existing user, by email or Entra object id (oid)."

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
        if user.role == Role.ADMIN:
            self.stdout.write("User is already an administrator; nothing changed.")
            return
        user.role = Role.ADMIN
        user.save(update_fields=["role"])
        record(actor=None, action=AuditAction.ADMIN_ROLE_GRANTED, obj=user)
        self.stdout.write(self.style.SUCCESS(f"Granted ADMIN to user {user.pk}."))
