"""Development data for the dev login and the admin pages (PROMPT.md §27, §32). Idempotent.
Refuses to run unless DEV_AUTH_ENABLED (development/test settings only — production refuses
that flag).

* FY 2026 fee schedule  ensured (normally already created by the fees seed migration)
* admin@dev.local       ADMIN role
* doctor@dev.local      complete profile, worked example 2 (WIFE, SON_MINOR, DAUGHTER) —
                        application SUBMITTED, receipt waiting for confirmation (3,025 EGP)
* doctor2@dev.local     female member with her MOTHER — application NEEDS_CORRECTION with
                        review notes from the admin (2,075 EGP)
* new.doctor@dev.local  empty profile, no application (first sign-in experience)

Every step goes through the domain services with the real actor (doctor or admin), so the
documents are real blobs (Azurite locally) and the audit log reads like a real review.
National IDs are synthetic (sequences 9998/9999) and only for local data.
"""

import importlib
from datetime import date
from io import BytesIO

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image, ImageDraw

from apps.accounts.models import Role, User
from apps.applications import services as applications
from apps.applications.models import InsuranceApplication
from apps.beneficiaries.services import upsert_beneficiary
from apps.doctors.models import Doctor
from apps.documents.services import store_document
from apps.fees.models import FeeSchedule
from apps.reference.constants import ApplicationStatus

DOCTOR_PROFILE = {
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
DOCTOR_BENEFICIARIES = [
    {"kinship": "WIFE", "full_name": "سارة محمود علي", "birth_year": 1988,
     "national_id": "28803150199982",
     "documents": ["BENEFICIARY_NATIONAL_ID", "MARRIAGE_CERTIFICATE", "INSURANCE_PRINT"]},
    {"kinship": "SON_MINOR", "full_name": "عمر أحمد محمد", "birth_year": 2015,
     "national_id": None, "documents": ["BIRTH_CERTIFICATE"]},
    {"kinship": "DAUGHTER", "full_name": "مريم أحمد محمد", "birth_year": 2018,
     "national_id": None, "documents": ["BIRTH_CERTIFICATE"]},
]  # fmt: skip

DOCTOR2_PROFILE = {
    "full_name": "منى حسن إبراهيم سالم",
    "national_id": "29003120199982",
    "date_of_birth": date(1990, 3, 12),
    "birth_year": 1990,
    "gender": "FEMALE",
    "religion": "MUSLIM",
    "phone_number": "01112345678",
    "syndicate_type": "PHARMACY",
    "sub_syndicate": "الجيزة",
    "syndicate_registration_number": "99002",
    "syndicate_registration_year": 2018,
    "governorate": "الجيزة",
    "neighborhood": "الدقي",
    "address": "شارع التحرير",
}
DOCTOR2_BENEFICIARIES = [
    {"kinship": "MOTHER", "full_name": "فاطمة علي أحمد", "birth_year": 1962,
     "national_id": "26205120199984", "documents": ["BENEFICIARY_NATIONAL_ID"]},
]  # fmt: skip
CORRECTION_NOTES = "صورة بطاقة الأم غير واضحة، يرجى رفع صورة أوضح ثم إعادة التقديم."

MEMBER_DOCUMENTS = ("NATIONAL_ID_FRONT", "NATIONAL_ID_BACK", "SYNDICATE_ID", "PAYMENT_RECEIPT")


def _fy2026_schedule() -> dict:
    """The one definition of the FY 2026 amounts lives in the fees seed migration."""
    migration = importlib.import_module("apps.fees.migrations.0002_seed_fy2026")
    return dict(migration.FY2026)


def _image(label: str) -> SimpleUploadedFile:
    """A synthetic 800×600 PNG (large enough for the receipt's 400×300 minimum)."""
    image = Image.new("RGB", (800, 600), "#FDFBE8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 780, 580), outline="#1A1A2E", width=6)
    draw.text((60, 60), f"DEV SAMPLE - {label}", fill="#1A1A2E")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return SimpleUploadedFile(f"{label.lower()}.png", buffer.getvalue(), content_type="image/png")


class Command(BaseCommand):
    help = "Create development users, the FY 2026 schedule and sample applications."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEV_AUTH_ENABLED:
            raise CommandError("seed_dev_data runs only with DEV_AUTH_ENABLED (development/test).")
        self._ensure_schedule()
        admin = self._user("admin@dev.local", "مسؤول المراجعة (تجريبي)", Role.ADMIN)

        doctor = self._doctor("doctor@dev.local", "د. أحمد محمد (تجريبي)", DOCTOR_PROFILE)
        self._submitted_application(doctor, DOCTOR_BENEFICIARIES)

        doctor2 = self._doctor("doctor2@dev.local", "د. منى حسن (تجريبي)", DOCTOR2_PROFILE)
        app2 = self._submitted_application(doctor2, DOCTOR2_BENEFICIARIES)
        if app2.status == ApplicationStatus.SUBMITTED:
            applications.transition(app2, to_status=ApplicationStatus.UNDER_REVIEW, actor=admin)
            applications.transition(
                app2,
                to_status=ApplicationStatus.NEEDS_CORRECTION,
                review_notes=CORRECTION_NOTES,
                actor=admin,
            )

        new_doctor = self._user("new.doctor@dev.local", "طبيب جديد (تجريبي)", Role.DOCTOR)
        Doctor.objects.get_or_create(user=new_doctor)

        for app in InsuranceApplication.objects.filter(
            doctor__user__email__in=["doctor@dev.local", "doctor2@dev.local"]
        ).select_related("doctor__user"):
            self.stdout.write(f"  {app.doctor.user.email}: {app.reference_number} {app.status}")
        self.stdout.write(
            self.style.SUCCESS(
                "Development data ready: admin, doctor, doctor2, new.doctor @dev.local"
            )
        )

    def _ensure_schedule(self) -> None:
        values = _fy2026_schedule()
        if FeeSchedule.objects.filter(fiscal_year=values["fiscal_year"], is_active=True).exists():
            return
        FeeSchedule.objects.create(**values)

    def _user(self, email: str, name: str, role: str) -> User:
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create_user(email, display_name=name, role=role)
        return user

    def _doctor(self, email: str, name: str, profile: dict) -> Doctor:
        user = self._user(email, name, Role.DOCTOR)
        doctor, _ = Doctor.objects.get_or_create(user=user)
        submitted = InsuranceApplication.objects.filter(doctor=doctor).exclude(
            status=ApplicationStatus.DRAFT
        )
        if not submitted.exists():
            # The profile is locked once submitted; before that the seed may (re)write it.
            Doctor.objects.filter(pk=doctor.pk).update(**profile)
            doctor.refresh_from_db()
        return doctor

    def _submitted_application(self, doctor: Doctor, beneficiaries: list[dict]):
        """The doctor's FY application, filled and submitted unless already past DRAFT."""
        actor = doctor.user
        app, _ = applications.get_or_create_draft(doctor, actor=actor)
        if app.status != ApplicationStatus.DRAFT:
            return app
        applications.update_draft(app, actor=actor, changes={"work_status": "WORKING"})
        for row_number, row in enumerate(beneficiaries, start=1):
            beneficiary = upsert_beneficiary(
                app,
                row_number=row_number,
                actor=actor,
                **{k: row[k] for k in ("kinship", "full_name", "birth_year", "national_id")},
            )
            for document_type in row["documents"]:
                store_document(
                    app,
                    document_type=document_type,
                    upload=_image(document_type),
                    beneficiary_id=beneficiary.pk,
                    actor=actor,
                )
        for document_type in MEMBER_DOCUMENTS:
            store_document(app, document_type=document_type, upload=_image(document_type),
                           actor=actor)  # fmt: skip
        applications.update_draft(
            app,
            actor=actor,
            changes={"declaration_name": doctor.full_name, "declaration_accepted": True},
        )
        return applications.submit(app, actor=actor)
