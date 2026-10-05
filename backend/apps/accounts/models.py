import uuid

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from .managers import UserManager, normalize_email_address


class Role(models.TextChoices):
    DOCTOR = "DOCTOR", "طبيب"
    ADMIN = "ADMIN", "مسؤول"


class User(AbstractBaseUser):
    """Signed-in identity. Doctors and admins both authenticate through Entra External ID.

    The admin role is granted only by `manage.py grant_admin`, never self-assigned.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(max_length=254)
    # From the Entra `name` claim (or the dev seed); the legal name is Doctor.full_name.
    display_name = models.CharField(max_length=200, blank=True, default="", db_default="")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.DOCTOR)
    # Entra object id + tenant id. Null for development users (DEV_AUTH_ENABLED).
    entra_oid = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
    entra_tid = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        constraints = [
            # Plain unique for Django's USERNAME_FIELD check (no extra LIKE index), plus a
            # functional index so writes that bypass save() stay case-insensitive.
            models.UniqueConstraint(fields=["email"], name="uniq_user_email"),
            models.UniqueConstraint(Lower("email"), name="uniq_user_email_ci"),
            models.UniqueConstraint(
                fields=["entra_oid", "entra_tid"],
                condition=Q(entra_oid__isnull=False),
                name="uniq_user_entra_identity",
            ),
            models.CheckConstraint(condition=Q(role__in=Role.values), name="user_role_valid"),
        ]

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs):
        self.email = normalize_email_address(self.email)
        super().save(*args, **kwargs)

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN
