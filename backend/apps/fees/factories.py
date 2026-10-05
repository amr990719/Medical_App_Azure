import factory

from .models import FeeSchedule

# Test copy of the FY 2026 schedule (PROMPT.md §17.1). The seed migration carries its own copy
# on purpose: migrations must not import application code that can change later.
FY2026_TIER_FEES = {
    "1": {"member": 600, "spouse": 800, "child": 500, "grad_son": 1200, "parent": 1050},
    "2": {"member": 700, "spouse": 950, "child": 550, "grad_son": 1400, "parent": 1200},
    "3": {"member": 750, "spouse": 1000, "child": 550, "grad_son": 1500, "parent": 1300},
    "4": {"member": 850, "spouse": 1050, "child": 600, "grad_son": 1750, "parent": 1400},
}


def fy2026_schedule(**overrides) -> FeeSchedule:
    """Unsaved FY 2026 schedule for pure fee-engine tests."""
    fields = {
        "fiscal_year": 2026,
        "version": 1,
        "tier_fees": FY2026_TIER_FEES,
        "tier_boundaries": [5, 10, 15],
        "admin_fee_member_only": 150,
        "admin_fee_with_beneficiaries": 175,
        "age_cap_threshold": 70,
        "age_cap_amount": 500,
        "registration_year_min": 1950,
        "is_active": True,
    }
    return FeeSchedule(**{**fields, **overrides})


class FeeScheduleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FeeSchedule

    fiscal_year = 2027
    version = 1
    tier_fees = factory.LazyFunction(lambda: {k: dict(v) for k, v in FY2026_TIER_FEES.items()})
    tier_boundaries = factory.LazyFunction(lambda: [5, 10, 15])
    is_active = True
