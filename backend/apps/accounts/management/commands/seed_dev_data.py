"""Development users for the dev login (PROMPT.md §27, §32). Idempotent. Refuses to run unless
DEV_AUTH_ENABLED (development/test settings only — production refuses that flag).

* doctor@dev.local      complete profile (worked example 2 member: born 1985, registered 2014)
* new.doctor@dev.local  empty profile (first sign-in experience)
* admin@dev.local       ADMIN role

The national ID is synthetic (sequence 9999) and only for local data.
"""

from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role, User
from apps.doctors.models import Doctor

COMPLETE_PROFILE = {
    "full_name": "أحمد محمد علي حسن",
    "national_id": "28506150199991",
    "date_of_birth": date(1985, 6, 15),
    "birth_year": 1985,
    "gender": "MALE",
    "religion": "MUSLIM",
    "phone_number": "01012345678",
    "syndicate_type": "HUMAN_MEDICINE",
    "sub_syndicate": "القاهرة",
    "syndicate_registration_number": "99001",
    "syndicate_registration_year": 2014,
    "governorate": "القاهرة",
    "neighborhood": "مدينة نصر",
    "address": "شارع عباس العقاد",
}


class Command(BaseCommand):
    help = "Create development users (doctor, new doctor, admin) for the dev login."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEV_AUTH_ENABLED:
            raise CommandError("seed_dev_data runs only with DEV_AUTH_ENABLED (development/test).")
        doctor = self._user("doctor@dev.local", "د. أحمد محمد (تجريبي)", Role.DOCTOR)
        Doctor.objects.update_or_create(user=doctor, defaults=COMPLETE_PROFILE)
        new_doctor = self._user("new.doctor@dev.local", "طبيب جديد (تجريبي)", Role.DOCTOR)
        Doctor.objects.get_or_create(user=new_doctor)
        self._user("admin@dev.local", "مسؤول المراجعة (تجريبي)", Role.ADMIN)
        self.stdout.write(
            self.style.SUCCESS("Development users ready: doctor, new.doctor, admin @dev.local")
        )

    def _user(self, email: str, name: str, role: str) -> User:
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create_user(email, display_name=name, role=role)
        return user
