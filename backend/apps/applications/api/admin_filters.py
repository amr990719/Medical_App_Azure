"""Admin list filters, search and ordering (PROMPT.md §24, §44, §45)."""

import re

import django_filters
from django.db.models import Q

from apps.applications.models import InsuranceApplication
from apps.doctors.models import Doctor
from apps.reference.constants import (
    GOVERNORATES,
    ApplicationStatus,
    PaymentStatus,
    SyndicateType,
)
from apps.reference.digits import normalize_digits

_MASKED_ID = re.compile(r"^([0-9]{2})[•*.xX\-]{3,}([0-9]{3})$")
_SEPARATORS = re.compile(r"[\s\-()]+")


def national_id_or_phone_q(query: str, *, prefix: str) -> Q | None:
    """Q for a full 14-digit ID, a masked ID (`29•••••••••123`, `*`, `x` or `.` as mask) or a
    phone fragment. None when the query is not numeric-looking."""
    compact = _SEPARATORS.sub("", normalize_digits(query))
    if re.fullmatch(r"[0-9]{14}", compact):
        return Q(**{f"{prefix}national_id": compact})
    masked = _MASKED_ID.fullmatch(compact)
    if masked:
        return Q(**{f"{prefix}national_id__startswith": masked.group(1)}) & Q(
            **{f"{prefix}national_id__endswith": masked.group(2)}
        )
    if re.fullmatch(r"\+?[0-9]{4,13}", compact):
        return Q(**{f"{prefix}phone_number__contains": compact.lstrip("+")})
    return None


class AdminApplicationFilter(django_filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(choices=ApplicationStatus.choices)
    payment_status = django_filters.MultipleChoiceFilter(choices=PaymentStatus.choices)
    fiscal_year = django_filters.NumberFilter()
    governorate = django_filters.ChoiceFilter(
        field_name="doctor__governorate", choices=[(g, g) for g in GOVERNORATES]
    )
    syndicate_type = django_filters.ChoiceFilter(
        field_name="doctor__syndicate_type", choices=SyndicateType.choices
    )
    sub_syndicate = django_filters.CharFilter(
        field_name="doctor__sub_syndicate", lookup_expr="icontains"
    )
    submitted_from = django_filters.DateFilter(field_name="submitted_at", lookup_expr="date__gte")
    submitted_to = django_filters.DateFilter(field_name="submitted_at", lookup_expr="date__lte")
    search = django_filters.CharFilter(method="filter_search")
    ordering = django_filters.OrderingFilter(
        fields=(
            ("submitted_at", "submitted_at"),
            ("reference_number", "reference_number"),
            ("status", "status"),
            ("fee_snapshot__total", "total"),
        )
    )

    class Meta:
        model = InsuranceApplication
        fields: list[str] = []

    def filter_search(self, queryset, name, value):
        query = value.strip()
        if not query:
            return queryset
        q = national_id_or_phone_q(query, prefix="doctor__")
        if q is not None:
            digits = _SEPARATORS.sub("", normalize_digits(query))
            return queryset.filter(q | Q(reference_number__icontains=digits))
        return queryset.filter(
            Q(reference_number__icontains=query) | Q(doctor__full_name__icontains=query)
        )


class AdminDoctorFilter(django_filters.FilterSet):
    syndicate_type = django_filters.ChoiceFilter(choices=SyndicateType.choices)
    governorate = django_filters.ChoiceFilter(choices=[(g, g) for g in GOVERNORATES])
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Doctor
        fields: list[str] = []

    def filter_search(self, queryset, name, value):
        query = value.strip()
        if not query:
            return queryset
        q = national_id_or_phone_q(query, prefix="")
        digits = _SEPARATORS.sub("", normalize_digits(query))
        registration = Q(syndicate_registration_number=digits)
        if q is not None:
            return queryset.filter(q | registration)
        return queryset.filter(Q(full_name__icontains=query) | Q(user__email__iexact=query))
