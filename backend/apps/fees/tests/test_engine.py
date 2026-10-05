"""Fee engine — every worked example of PROMPT.md §17.4 (FY 2026), plus boundaries.

Pure functions: the schedule is an unsaved FeeSchedule instance, no database needed.
"""

import json

import pytest

from apps.fees.factories import fy2026_schedule
from apps.fees.services import (
    ADMIN_FEE_LABEL,
    INVALID_REGISTRATION_YEAR_MESSAGE,
    MEMBER_LABEL,
    BeneficiaryInput,
    calculate_fees,
    get_tier,
)
from apps.reference.constants import Kinship, WorkStatus

SCHEDULE = fy2026_schedule()
W, P, D = WorkStatus.WORKING, WorkStatus.PENSIONER, WorkStatus.DECEASED


def quote(reg_year, birth_year, beneficiaries=(), work_status=W):
    return calculate_fees(
        SCHEDULE,
        registration_year=reg_year,
        work_status=work_status,
        birth_year=birth_year,
        beneficiaries=[BeneficiaryInput(*b) for b in beneficiaries],
    )


def lines(q):
    return [(line.label, line.fee) for line in q.breakdown]


# --- Worked examples 1-4, 8, 9 (exact breakdown and totals) -----------------------------------

WORKED_EXAMPLES = [
    pytest.param(
        2023, 1995, W, [],
        1, [(MEMBER_LABEL, 600), (ADMIN_FEE_LABEL, 150)], 150, 750,
        id="ex1-member-only-tier1-750",
    ),
    pytest.param(
        2014, 1985, W,
        [(Kinship.WIFE, "سارة", 1988), (Kinship.SON_MINOR, "عمر", 2015),
         (Kinship.DAUGHTER, "مريم", 2018)],
        3, [(MEMBER_LABEL, 750), ("سارة", 1000), ("عمر", 550), ("مريم", 550),
            (ADMIN_FEE_LABEL, 175)], 175, 3025,
        id="ex2-family-tier3-3025",
    ),
    pytest.param(
        1990, 1950, P,
        [(Kinship.WIFE, "فاطمة", 1955), (Kinship.SON_GRADUATE, "خالد", 1995)],
        4, [(MEMBER_LABEL, 500), ("فاطمة", 500), ("خالد", 1750), (ADMIN_FEE_LABEL, 175)],
        175, 2925,
        id="ex3-pensioner-age-caps-2925",
    ),
    pytest.param(
        2018, 1990, W,
        [(Kinship.MOTHER, "زينب", 1960), (Kinship.SON_UNIVERSITY, "يوسف", 2005)],
        2, [(MEMBER_LABEL, 700), ("زينب", 1200), ("يوسف", 1400), (ADMIN_FEE_LABEL, 175)],
        175, 3475,
        id="ex4-mother-university-son-tier2-3475",
    ),
    pytest.param(
        2023, 1995, W, [(Kinship.WIFE, "", 1996), (Kinship.SON_MINOR, "   ", 2020)],
        1, [(MEMBER_LABEL, 600), (ADMIN_FEE_LABEL, 150)], 150, 750,
        id="ex8-kinship-without-name-ignored-admin-150",
    ),
    pytest.param(
        2023, 1995, W, [(Kinship.FATHER, "محمود", 1950)],
        1, [(MEMBER_LABEL, 600), ("محمود", 1050), (ADMIN_FEE_LABEL, 175)], 175, 1825,
        id="ex9-father-76-not-capped-1825",
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


# --- Example 5: tier boundaries ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("reg_year", "tier"),
    [(2026, 1), (2021, 1), (2020, 2), (2016, 2), (2015, 3), (2011, 3), (2010, 4), (1950, 4)],
)
def test_ex5_tier_boundaries(reg_year, tier):
    assert get_tier(SCHEDULE, reg_year, W) == tier
    assert quote(reg_year, 1990).tier == tier


def test_pensioner_is_always_tier_4():
    assert get_tier(SCHEDULE, 2025, P) == 4
    assert quote(2025, 1990, work_status=P).breakdown[0].fee == 850


def test_deceased_is_priced_like_working():
    assert quote(2014, 1985, work_status=D).total == quote(2014, 1985, work_status=W).total


def test_missing_work_status_is_priced_like_working():
    assert quote(2014, 1985, work_status=None).tier == 3


# --- Example 6: member age cap boundary -------------------------------------------------------


def test_ex6_cap_applies_at_70():
    q = quote(2023, 1956)
    assert q.breakdown[0].fee == 500
    assert q.breakdown[0].note == "تم تطبيق سقف 500 ج (عمر 70 سنة)"
    assert q.total == 650


def test_ex6_cap_does_not_apply_at_69():
    q = quote(2023, 1957)
    assert q.breakdown[0].fee == 600
    assert q.breakdown[0].note == ""
    assert q.total == 750


def test_missing_member_birth_year_means_no_cap():
    assert quote(2023, None).breakdown[0].fee == 600


# --- Example 7: invalid registration year -----------------------------------------------------


@pytest.mark.parametrize("reg_year", [1949, 2027, None, 0, 99999])
def test_ex7_invalid_registration_year(reg_year):
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
    assert quote(2023, 1995, [(Kinship.WIFE, "سارة", 1957)]).breakdown[1].fee == 800


@pytest.mark.parametrize("kinship", [Kinship.MOTHER, Kinship.FATHER])
def test_parents_are_never_capped(kinship):
    assert quote(2023, 1995, [(kinship, "والد", 1930)]).breakdown[1].fee == 1050


def test_beneficiary_without_birth_year_gets_tier_fee():
    # Review Focus 3: a kinship + name row with no birth year still gets a fee line, no cap.
    q = quote(2014, 1985, [(Kinship.WIFE, "سارة", None), (Kinship.DAUGHTER, "مريم", None)])
    assert lines(q)[1:3] == [("سارة", 1000), ("مريم", 550)]


def test_beneficiary_names_are_trimmed_in_labels():
    assert quote(2023, 1995, [(Kinship.FATHER, "  محمود  ", 1950)]).breakdown[1].label == "محمود"


def test_row_without_kinship_is_ignored():
    q = quote(2023, 1995, [(None, "اسم بلا قرابة", 1990)])
    assert q.total == 750


def test_fee_key_per_kinship_tier4():
    q = quote(2000, 1980, [
        (Kinship.WIFE, "a", 1980), (Kinship.HUSBAND, "b", 1980), (Kinship.SON_MINOR, "c", 2015),
        (Kinship.DAUGHTER, "d", 2015), (Kinship.SON_UNIVERSITY, "e", 2005),
        (Kinship.SON_GRADUATE, "f", 2000), (Kinship.MOTHER, "g", 1955),
        (Kinship.FATHER, "h", 1950),
    ])  # fmt: skip
    assert [line.fee for line in q.breakdown] == [
        850,
        1050,
        1050,
        600,
        600,
        1750,
        1750,
        1400,
        1400,
        175,
    ]


def test_money_is_integer_never_float():
    q = quote(2014, 1985, [(Kinship.WIFE, "سارة", 1988)])
    assert all(type(line.fee) is int for line in q.breakdown)
    assert type(q.total) is int


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
    assert data["breakdown"][0] == {"label": "العضو الأصلي", "fee": 750, "note": ""}
    assert data["breakdown"][-1] == {"label": "رسوم إدارية", "fee": 175, "note": ""}
    assert data["schedule_id"] == str(SCHEDULE.id)
