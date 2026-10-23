"""Fee engine — worked examples (FY 2026 version 2), tier 0, eligibility, administrative fee,
boundaries, and legacy (version 1) schedules.

Pure functions: the schedule is an unsaved FeeSchedule instance, no database needed.
"""

import json

import pytest

from apps.fees.factories import fy2026_legacy_schedule, fy2026_schedule
from apps.fees.services import (
    ADMIN_FEE_LABEL,
    INVALID_REGISTRATION_YEAR_MESSAGE,
    MEMBER_LABEL,
    BeneficiaryInput,
    admin_fee_for,
    beneficiary_ineligibility_message,
    calculate_fees,
    get_tier,
)
from apps.reference.constants import Kinship, WorkStatus

SCHEDULE = fy2026_schedule()
LEGACY = fy2026_legacy_schedule()
W, P, D = WorkStatus.WORKING, WorkStatus.PENSIONER, WorkStatus.DECEASED


def quote(reg_year, birth_year, beneficiaries=(), work_status=W, schedule=SCHEDULE):
    return calculate_fees(
        schedule,
        registration_year=reg_year,
        work_status=work_status,
        birth_year=birth_year,
        beneficiaries=[BeneficiaryInput(*b) for b in beneficiaries],
    )


def lines(q):
    return [(line.label, line.fee) for line in q.breakdown]


# --- Worked examples (exact breakdown and totals) ---------------------------------------------

WORKED_EXAMPLES = [
    pytest.param(
        2026, 1990, W, [],
        0, [(MEMBER_LABEL, 400), (ADMIN_FEE_LABEL, 200)], 200, 600,
        id="tier0-member-only-600",
    ),
    pytest.param(
        2026, 1990, W, [(Kinship.SON_MINOR, "عمر", 2020)],
        0, [(MEMBER_LABEL, 400), ("عمر", 550), (ADMIN_FEE_LABEL, 375)], 375, 1325,
        id="tier0-one-son-minor-1325",
    ),
    pytest.param(
        2014, 1985, W, [(Kinship.WIFE, "سارة", 1988), (Kinship.SON_MINOR, "عمر", 2015)],
        3, [(MEMBER_LABEL, 825), ("سارة", 1100), ("عمر", 605), (ADMIN_FEE_LABEL, 550)], 550,
        3080,
        id="tier3-wife-son-3080",
    ),
    pytest.param(
        2023, 1995, W, [],
        1, [(MEMBER_LABEL, 660), (ADMIN_FEE_LABEL, 200)], 200, 860,
        id="ex1-member-only-tier1-860",
    ),
    pytest.param(
        2014, 1985, W,
        [(Kinship.WIFE, "سارة", 1988), (Kinship.SON_MINOR, "عمر", 2015),
         (Kinship.DAUGHTER, "مريم", 2018)],
        3, [(MEMBER_LABEL, 825), ("سارة", 1100), ("عمر", 605), ("مريم", 605),
            (ADMIN_FEE_LABEL, 725)], 725, 3860,
        id="ex2-family-tier3-3860",
    ),
    pytest.param(
        1990, 1950, P,
        [(Kinship.WIFE, "فاطمة", 1955), (Kinship.SON_GRADUATE, "خالد", 1995)],
        4, [(MEMBER_LABEL, 500), ("فاطمة", 500), ("خالد", 1925), (ADMIN_FEE_LABEL, 550)],
        550, 3475,
        id="ex3-pensioner-age-caps-3475",
    ),
    pytest.param(
        2018, 1990, W,
        [(Kinship.MOTHER, "زينب", 1960), (Kinship.SON_UNIVERSITY, "يوسف", 2005)],
        2, [(MEMBER_LABEL, 770), ("زينب", 1320), ("يوسف", 1540), (ADMIN_FEE_LABEL, 550)],
        550, 4180,
        id="ex4-mother-university-son-tier2-4180",
    ),
    pytest.param(
        2023, 1995, W, [(Kinship.WIFE, "", 1996), (Kinship.SON_MINOR, "   ", 2020)],
        1, [(MEMBER_LABEL, 660), (ADMIN_FEE_LABEL, 200)], 200, 860,
        id="ex8-kinship-without-name-ignored-admin-200",
    ),
    pytest.param(
        2023, 1995, W, [(Kinship.FATHER, "محمود", 1950)],
        1, [(MEMBER_LABEL, 660), ("محمود", 1155), (ADMIN_FEE_LABEL, 375)], 375, 2190,
        id="ex9-father-76-not-capped-2190",
    ),
]  # fmt: skip


@pytest.mark.parametrize(
    ("reg", "born", "status", "bens", "tier", "expected_lines", "admin_fee", "total"),
    WORKED_EXAMPLES,
)
def test_worked_examples(reg, born, status, bens, tier, expected_lines, admin_fee, total):
    q = quote(reg, born, bens, status)
    assert q.is_valid is True
    assert q.error_message == ""
    assert q.fiscal_year == 2026
    assert q.tier == tier
    assert lines(q) == expected_lines
    assert q.admin_fee == admin_fee
    assert q.total == total
    assert q.total == sum(line.fee for line in q.breakdown)


def test_example3_notes_name_the_ages():
    q = quote(1990, 1950, [(Kinship.WIFE, "فاطمة", 1955), (Kinship.SON_GRADUATE, "خالد", 1995)], P)
    notes = [line.note for line in q.breakdown]
    assert notes == ["تم تطبيق سقف 500 ج (عمر 76 سنة)", "تم تطبيق سقف 500 ج (عمر 71 سنة)", "", ""]


# --- Tiers: tier 0, boundaries, pensioner override ---------------------------------------------


@pytest.mark.parametrize(
    ("reg_year", "tier"),
    [(2026, 0), (2025, 1), (2021, 1), (2020, 2), (2016, 2), (2015, 3), (2011, 3), (2010, 4),
     (1950, 4)],
)  # fmt: skip
def test_tier_boundaries(reg_year, tier):
    assert get_tier(SCHEDULE, reg_year, W) == tier
    assert quote(reg_year, 1990).tier == tier


def test_tier_0_uses_the_schedule_fiscal_year_not_the_clock():
    fy2027 = fy2026_schedule(fiscal_year=2027)
    assert get_tier(fy2027, 2027, W) == 0
    assert get_tier(fy2027, 2026, W) == 1


def test_valid_tier_0_quote_is_distinct_from_an_invalid_quote():
    valid, invalid = quote(2026, 1990), quote(2027, 1990)
    assert (valid.tier, valid.is_valid, valid.total) == (0, True, 600)
    assert (invalid.tier, invalid.is_valid, invalid.total) == (0, False, 0)


def test_pensioner_is_always_tier_4_even_when_registered_this_year():
    assert get_tier(SCHEDULE, 2026, P) == 4
    assert get_tier(SCHEDULE, 2025, P) == 4
    assert quote(2025, 1990, work_status=P).breakdown[0].fee == 935


def test_deceased_is_priced_like_working():
    assert quote(2014, 1985, work_status=D).total == quote(2014, 1985, work_status=W).total
    assert quote(2026, 1985, work_status=D).tier == 0


def test_missing_work_status_is_priced_like_working():
    assert quote(2014, 1985, work_status=None).tier == 3


# --- Tier 0 eligibility (grad_son: null = NOT ELIGIBLE, never free) ---------------------------


@pytest.mark.parametrize("kinship", [Kinship.SON_UNIVERSITY, Kinship.SON_GRADUATE])
def test_tier_0_university_or_graduate_child_makes_the_quote_invalid(kinship):
    q = quote(2026, 1990, [(Kinship.WIFE, "سارة", 1992), (kinship, "يوسف", 2004)])
    assert q.is_valid is False
    assert q.tier == 0
    assert q.breakdown == []
    assert (q.admin_fee, q.total) == (0, 0)
    assert q.error_message == (
        f"المستفيد يوسف: لا يمكن الاشتراك بدرجة القرابة «{kinship.label}» للأعضاء المقيدين "
        "في نفس سنة الاشتراك."
    )


def test_tier_0_ineligible_row_without_a_name_is_ignored():
    q = quote(2026, 1990, [(Kinship.SON_UNIVERSITY, "  ", 2004)])
    assert (q.is_valid, q.total) == (True, 600)


def test_pensioner_registered_this_year_may_add_a_university_child():
    q = quote(2026, 1960, [(Kinship.SON_UNIVERSITY, "يوسف", 2004)], P)
    assert q.is_valid is True
    assert lines(q)[1] == ("يوسف", 1925)


def test_university_child_is_eligible_from_tier_1():
    assert lines(quote(2025, 1990, [(Kinship.SON_GRADUATE, "خالد", 2000)]))[1] == ("خالد", 1320)


def test_ineligibility_message_helper():
    assert beneficiary_ineligibility_message(SCHEDULE, 0, Kinship.SON_MINOR, "عمر") == ""
    assert beneficiary_ineligibility_message(SCHEDULE, 1, Kinship.SON_GRADUATE, "خالد") == ""
    assert beneficiary_ineligibility_message(SCHEDULE, 0, None, "x") == ""
    assert "خالد" in beneficiary_ineligibility_message(SCHEDULE, 0, Kinship.SON_GRADUATE, " خالد ")


# --- Administrative fee: 200 + 175 × active beneficiaries -------------------------------------


@pytest.mark.parametrize(("count", "fee"), [(0, 200), (1, 375), (2, 550), (3, 725), (10, 1950)])
def test_admin_fee_formula(count, fee):
    assert admin_fee_for(SCHEDULE, count) == fee
    bens = [(Kinship.DAUGHTER, f"ابنة {i}", 2015) for i in range(count)]
    assert quote(2023, 1995, bens).admin_fee == fee


def test_admin_fee_counts_only_active_rows():
    bens = [
        (Kinship.WIFE, "سارة", 1996),
        (Kinship.SON_MINOR, "", 2020),  # no name: inactive
        (None, "اسم بلا قرابة", 2020),  # no kinship: inactive
        (Kinship.DAUGHTER, "مريم", 2021),
    ]
    q = quote(2023, 1995, bens)
    assert q.admin_fee == 550
    assert lines(q) == [(MEMBER_LABEL, 660), ("سارة", 880), ("مريم", 550), (ADMIN_FEE_LABEL, 550)]


def test_admin_fee_amounts_come_from_the_schedule():
    custom = fy2026_schedule(admin_fee_base=250, admin_fee_per_beneficiary=100)
    assert quote(2023, 1995, [(Kinship.WIFE, "سارة", 1996)], schedule=custom).admin_fee == 350


# --- Member age cap boundary ------------------------------------------------------------------


def test_cap_applies_at_70():
    q = quote(2023, 1956)
    assert q.breakdown[0].fee == 500
    assert q.breakdown[0].note == "تم تطبيق سقف 500 ج (عمر 70 سنة)"
    assert q.total == 700


def test_cap_does_not_apply_at_69():
    q = quote(2023, 1957)
    assert q.breakdown[0].fee == 660
    assert q.breakdown[0].note == ""
    assert q.total == 860


def test_tier_0_member_fee_below_the_cap_is_not_raised():
    q = quote(2026, 1950)
    assert (q.breakdown[0].fee, q.breakdown[0].note) == (400, "")


def test_missing_member_birth_year_means_no_cap():
    assert quote(2023, None).breakdown[0].fee == 660


# --- Invalid registration year ----------------------------------------------------------------


@pytest.mark.parametrize("reg_year", [1949, 2027, None, 0, 99999])
def test_invalid_registration_year(reg_year):
    q = quote(reg_year, 1990, [(Kinship.WIFE, "سارة", 1990)])
    assert q.is_valid is False
    assert q.tier == 0
    assert q.breakdown == []
    assert q.admin_fee == 0
    assert q.total == 0
    assert q.error_message == INVALID_REGISTRATION_YEAR_MESSAGE
    assert (
        INVALID_REGISTRATION_YEAR_MESSAGE == "يرجى إدخال سنة قيد النقابة بشكل صحيح لحساب الاشتراك."
    )


def test_registration_year_1950_is_valid():
    assert quote(1950, 1990).is_valid is True


# --- Spouse / parent / child cap rules --------------------------------------------------------


def test_spouse_note_text():
    q = quote(2023, 1995, [(Kinship.HUSBAND, "علي", 1955)])
    assert q.breakdown[1].fee == 500
    assert q.breakdown[1].note == "تم تطبيق سقف 500 ج (عمر 71 سنة)"


def test_spouse_aged_69_is_not_capped():
    assert quote(2023, 1995, [(Kinship.WIFE, "سارة", 1957)]).breakdown[1].fee == 880


def test_spouse_is_capped_at_tier_0_too():
    assert quote(2026, 1990, [(Kinship.WIFE, "سارة", 1950)]).breakdown[1].fee == 500


@pytest.mark.parametrize("kinship", [Kinship.MOTHER, Kinship.FATHER])
def test_parents_are_never_capped(kinship):
    assert quote(2023, 1995, [(kinship, "والد", 1930)]).breakdown[1].fee == 1155


def test_beneficiary_without_birth_year_gets_tier_fee():
    # Review Focus 3: a kinship + name row with no birth year still gets a fee line, no cap.
    q = quote(2014, 1985, [(Kinship.WIFE, "سارة", None), (Kinship.DAUGHTER, "مريم", None)])
    assert lines(q)[1:3] == [("سارة", 1100), ("مريم", 605)]


def test_beneficiary_names_are_trimmed_in_labels():
    assert quote(2023, 1995, [(Kinship.FATHER, "  محمود  ", 1950)]).breakdown[1].label == "محمود"


def test_row_without_kinship_is_ignored():
    q = quote(2023, 1995, [(None, "اسم بلا قرابة", 1990)])
    assert q.total == 860


def test_fee_key_per_kinship_tier4():
    q = quote(2000, 1980, [
        (Kinship.WIFE, "a", 1980), (Kinship.HUSBAND, "b", 1980), (Kinship.SON_MINOR, "c", 2015),
        (Kinship.DAUGHTER, "d", 2015), (Kinship.SON_UNIVERSITY, "e", 2005),
        (Kinship.SON_GRADUATE, "f", 2000), (Kinship.MOTHER, "g", 1955),
        (Kinship.FATHER, "h", 1950),
    ])  # fmt: skip
    assert [line.fee for line in q.breakdown] == [
        935, 1155, 1155, 660, 660, 1925, 1925, 1540, 1540, 200 + 8 * 175,
    ]  # fmt: skip


def test_money_is_integer_never_float():
    q = quote(2014, 1985, [(Kinship.WIFE, "سارة", 1988)])
    assert all(type(line.fee) is int for line in q.breakdown)
    assert type(q.total) is int


# --- Legacy four-tier FLAT schedules (version 1) stay readable and priced as before ----------


@pytest.mark.parametrize(
    ("reg", "born", "bens", "tier", "total"),
    [
        (2023, 1995, [], 1, 750),
        (2026, 1995, [], 1, 750),  # no tier 0 in a legacy schedule
        (2014, 1985, [(Kinship.WIFE, "سارة", 1988), (Kinship.SON_MINOR, "عمر", 2015),
                      (Kinship.DAUGHTER, "مريم", 2018)], 3, 3025),
        (2023, 1995, [(Kinship.FATHER, "محمود", 1950)], 1, 1825),
    ],
)  # fmt: skip
def test_legacy_schedule_keeps_its_pricing(reg, born, bens, tier, total):
    q = quote(reg, born, bens, schedule=LEGACY)
    assert (q.is_valid, q.tier, q.total) == (True, tier, total)
    assert q.admin_fee == (175 if bens else 150)


# --- Output shape (PROMPT.md §17.3) -----------------------------------------------------------


def test_as_dict_shape():
    q = quote(2014, 1985, [(Kinship.WIFE, "سارة", 1988)])
    data = q.as_dict()
    json.dumps(data, ensure_ascii=False)
    assert set(data) == {
        "fiscal_year",
        "tier",
        "breakdown",
        "admin_fee",
        "total",
        "is_valid",
        "error_message",
        "schedule_id",
    }
    assert data["breakdown"][0] == {"label": "العضو الأصلي", "fee": 825, "note": ""}
    assert data["breakdown"][-1] == {"label": "رسوم إدارية", "fee": 375, "note": ""}
    assert data["schedule_id"] == str(SCHEDULE.id)
