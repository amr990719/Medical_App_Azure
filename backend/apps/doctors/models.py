import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.reference.constants import Gender, Religion, SyndicateType
from apps.reference.national_id import mask_national_id

NATIONAL_ID_REGEX = r"^[23][0-9]{13}$"


class Doctor(models.Model):
    """Member profile (العضو الأصلي), 1:1 with User (PROMPT.md §12).

    Created at first sign-in and completed in the form, so profile fields may be blank while the
    application is a draft; completeness is enforced by `applications.validation`, not here.
    `national_id` is a UNIQUE business identifier, never the primary key.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="doctor"
    )
    full_name = models.CharField(max_length=200, blank=True)
    # Unique (see Meta) but nullable: NULL keeps the constraint free for blank drafts.
    national_id = models.CharField(max_length=14, null=True, blank=True)  # noqa: DJ001
    date_of_birth = models.DateField(null=True, blank=True)
    birth_year = models.PositiveSmallIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=8, choices=Gender.choices, blank=True)
    religion = models.CharField(max_length=16, choices=Religion.choices, blank=True)
    phone_number = models.CharField(max_length=16, blank=True)
    syndicate_type = models.CharField(max_length=16, choices=SyndicateType.choices, blank=True)
    sub_syndicate = models.CharField(max_length=100, blank=True)
    syndicate_registration_number = models.CharField(max_length=32, blank=True)
    syndicate_registration_year = models.PositiveSmallIntegerField(null=True, blank=True)
    treatment_card_number = models.CharField(max_length=32, blank=True)
    governorate = models.CharField(max_length=32, blank=True)
    neighborhood = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["syndicate_type", "syndicate_registration_number"],
                name="doctor_syndicate_regno_idx",
            ),
        ]
        constraints = [
            # UniqueConstraint rather than unique=True: exact lookups only, no LIKE index.
            models.UniqueConstraint(fields=["national_id"], name="uniq_doctor_national_id"),
            models.CheckConstraint(
                condition=Q(national_id__isnull=True) | Q(national_id__regex=NATIONAL_ID_REGEX),
                name="doctor_national_id_format",
            ),
            models.CheckConstraint(
                condition=Q(gender="") | Q(gender__in=Gender.values), name="doctor_gender_valid"
            ),
            models.CheckConstraint(
                condition=Q(syndicate_type="") | Q(syndicate_type__in=SyndicateType.values),
                name="doctor_syndicate_type_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.full_name or '—'} ({self.masked_national_id or 'بدون رقم قومي'})"

    def __repr__(self) -> str:
        return f"<Doctor {self.pk}>"

    @property
    def masked_national_id(self) -> str:
        return mask_national_id(self.national_id)

    @property
    def email(self) -> str:
        return self.user.email
