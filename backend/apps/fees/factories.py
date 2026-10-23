import factory

from .models import AdminFeeFormula, FeeSchedule

# Test copies of the FY 2026 schedules. The data migrations carry their own copies on purpose:
# migrations must not import application code that can change later.

# FY 2026 version 2 (the active schedule): tier 0, PER_BENEFICIARY administrative fee.
FY2026_TIER_FEES = {
    "0": {"member": 400, "spouse": 880, "child": 550, "grad_son": None, "parent": 1155},
    "1": {"member": 660, "spouse": 880, "child": 550, "grad_son": 1320, "parent": 1155},
    "2": {"member": 770, "spouse": 1045, "child": 605, "grad_son": 1540, "parent": 1320},
    "3": {"member": 825, "spouse": 1100, "child": 605, "grad_son": 1650, "parent": 1430},
    "4": {"member": 935, "spouse": 1155, "child": 660, "grad_son": 1925, "parent": 1540},
}

# FY 2026 version 1 (PROMPT.md §17.1 as first seeded): four tiers, FLAT administrative fee.
FY2026_V1_TIER_FEES = {
    "1": {"member": 600, "spouse": 800, "child": 500, "grad_son": 1200, "parent": 1050},
    "2": {"member": 700, "spouse": 950, "child": 550, "grad_son": 1400, "parent": 1200},
    "3": {"member": 750, "spouse": 1000, "child": 550, "grad_son": 1500, "parent": 1300},
    "4": {"member": 850, "spouse": 1050, "child": 600, "grad_son": 1750, "parent": 1400},
}


def _copy(tier_fees: dict) -> dict:
    return {tier: dict(row) for tier, row in tier_fees.items()}


def fy2026_schedule(**overrides) -> FeeSchedule:
    """Unsaved FY 2026 (version 2) schedule for pure fee-engine tests."""
    fields = {
        "fiscal_year": 2026,
        "version": 2,
        "tier_fees": _copy(FY2026_TIER_FEES),
        "tier_boundaries": [5, 10, 15],
        "admin_fee_formula": AdminFeeFormula.PER_BENEFICIARY,
        "admin_fee_base": 200,
        "admin_fee_per_beneficiary": 175,
        "admin_fee_member_only": None,
        "admin_fee_with_beneficiaries": None,
        "age_cap_threshold": 70,
        "age_cap_amount": 500,
        "registration_year_min": 1950,
        "is_active": True,
    }
    return FeeSchedule(**{**fields, **overrides})


def fy2026_legacy_schedule(**overrides) -> FeeSchedule:
    """Unsaved FY 2026 version 1 (four tiers, FLAT admin fee) — legacy-compatibility tests."""
    fields = {
        "version": 1,
        "tier_fees": _copy(FY2026_V1_TIER_FEES),
        "admin_fee_formula": AdminFeeFormula.FLAT,
        "admin_fee_member_only": 150,
        "admin_fee_with_beneficiaries": 175,
        "admin_fee_base": None,
        "admin_fee_per_beneficiary": None,
        "is_active": False,
    }
    return fy2026_schedule(**{**fields, **overrides})


class FeeScheduleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FeeSchedule

    fiscal_year = 2027
    version = 1
    tier_fees = factory.LazyFunction(lambda: _copy(FY2026_TIER_FEES))
    tier_boundaries = factory.LazyFunction(lambda: [5, 10, 15])
    is_active = True
