from rest_framework import serializers

from apps.common.fields import (
    CollapsedCharField,
    DigitsCharField,
    NationalIdField,
    PhoneField,
    YearField,
)
from apps.doctors.models import Doctor
from apps.reference.constants import GOVERNORATES, Gender, Religion, SyndicateType


def _choice(choices) -> serializers.ChoiceField:
    return serializers.ChoiceField(choices=choices, allow_blank=True, required=False)


class DoctorProfileSerializer(serializers.ModelSerializer):
    """The doctor's own profile. Derived fields (date of birth) and the Entra email are
    read-only; birth year and gender follow the national ID when one is present."""

    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = CollapsedCharField(max_length=200, allow_blank=True, required=False)
    national_id = NationalIdField()
    birth_year = YearField()
    gender = _choice(Gender.choices)
    religion = _choice(Religion.choices)
    phone_number = PhoneField()
    syndicate_type = _choice(SyndicateType.choices)
    sub_syndicate = CollapsedCharField(max_length=100, allow_blank=True, required=False)
    syndicate_registration_number = DigitsCharField(max_length=32, allow_blank=True, required=False)
    syndicate_registration_year = YearField()
    treatment_card_number = DigitsCharField(max_length=32, allow_blank=True, required=False)
    governorate = _choice([(g, g) for g in GOVERNORATES])
    neighborhood = CollapsedCharField(max_length=100, allow_blank=True, required=False)
    address = CollapsedCharField(max_length=300, allow_blank=True, required=False)

    class Meta:
        model = Doctor
        fields = [
            "id", "email", "full_name", "national_id", "date_of_birth", "birth_year", "gender",
            "religion", "phone_number", "syndicate_type", "sub_syndicate",
            "syndicate_registration_number", "syndicate_registration_year",
            "treatment_card_number", "governorate", "neighborhood", "address", "updated_at",
        ]  # fmt: skip
        read_only_fields = ["id", "email", "date_of_birth", "updated_at"]
