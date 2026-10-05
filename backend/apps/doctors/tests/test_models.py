import pytest
from django.db import IntegrityError

from apps.doctors.factories import DoctorFactory
from apps.doctors.models import Doctor


@pytest.mark.django_db
class TestDoctor:
    def test_factory_builds_a_complete_profile(self):
        doctor = DoctorFactory()
        assert len(doctor.national_id) == 14
        assert doctor.birth_year == doctor.date_of_birth.year
        assert doctor.user.email

    def test_primary_key_is_uuid_not_national_id(self):
        doctor = DoctorFactory()
        assert str(doctor.pk) != doctor.national_id
        assert len(str(doctor.pk)) == 36

    def test_duplicate_national_id_raises_integrity_error(self):
        first = DoctorFactory()
        with pytest.raises(IntegrityError):
            DoctorFactory(national_id=first.national_id)

    def test_incomplete_profiles_may_have_no_national_id(self):
        DoctorFactory(national_id=None)
        DoctorFactory(national_id=None)
        assert Doctor.objects.filter(national_id__isnull=True).count() == 2

    def test_database_rejects_malformed_national_id(self):
        with pytest.raises(IntegrityError):
            DoctorFactory(national_id="12345")

    def test_one_profile_per_user(self):
        doctor = DoctorFactory()
        with pytest.raises(IntegrityError):
            DoctorFactory(user=doctor.user)

    def test_masked_national_id(self):
        doctor = DoctorFactory(national_id="29501230101234")
        assert doctor.masked_national_id == "29•••••••••234"

    def test_str_never_contains_the_full_national_id(self):
        doctor = DoctorFactory(national_id="29501230101234")
        assert "29501230101234" not in str(doctor)
        assert "29501230101234" not in repr(doctor)

    def test_email_comes_from_the_user(self):
        doctor = DoctorFactory()
        assert doctor.email == doctor.user.email

    def test_registration_number_is_indexed_not_unique(self):
        a = DoctorFactory(syndicate_registration_number="555")
        DoctorFactory(syndicate_type=a.syndicate_type, syndicate_registration_number="555")
        index_names = {i.name for i in Doctor._meta.indexes}
        assert "doctor_syndicate_regno_idx" in index_names
