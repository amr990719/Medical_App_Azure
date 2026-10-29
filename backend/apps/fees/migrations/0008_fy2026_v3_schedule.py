"""FY 2026 schedule version 3 (owner requirements of 2026-10-29) and every stored quote re-priced.

Version 3 keeps the version 2 tier amounts and adds the service fee (800, once per application).
The rules that changed with it live in the engine: the administrative fee counts the member
(`200 + 175 × (active beneficiaries + 1)`) and a university child is priced like a minor child.

By owner decision, earlier quotes are NOT preserved: every FY 2026 application holding a
`fee_snapshot` is re-priced on version 3 and points at it (version 3 is then locked), and every
other FY 2026 version is deleted. The price is computed from the data the application was
SUBMITTED with (`submitted_snapshot`: member, application and beneficiaries), never from the
current rows — an application sent back for correction holds unfinished edits (a cleared
registration year would give an invalid zero quote). Every replacement quote is checked before
anything is written. If any application lacks complete submitted data or does not give a valid,
consistent quote, the migration raises with the list of applications and reasons, and the whole
migration rolls back: nothing is re-priced, version 2 stays. Nothing else changes — no other
column (not even `updated_at`), beneficiaries, documents, audit entries or `submitted_snapshot`.
Other fiscal years are not touched.

The pricing below is a frozen copy of `apps.fees.services.calculate_fees` as of this migration
(migrations must not import application code that can change later). Idempotent: with version 3
already active it only re-prices snapshots that are not on it. Reverse is a no-op: the removed
versions and quotes are not restored.
"""

from django.db import migrations
from django.db.models import Max
from django.utils import timezone

FY2026_V3 = {
    "fiscal_year": 2026,
    "tier_fees": {
        "0": {"member": 400, "spouse": 880, "child": 550, "grad_son": None, "parent": 1155},
        "1": {"member": 660, "spouse": 880, "child": 550, "grad_son": 1320, "parent": 1155},
        "2": {"member": 770, "spouse": 1045, "child": 605, "grad_son": 1540, "parent": 1320},
        "3": {"member": 825, "spouse": 1100, "child": 605, "grad_son": 1650, "parent": 1430},
        "4": {"member": 935, "spouse": 1155, "child": 660, "grad_son": 1925, "parent": 1540},
    },
    "tier_boundaries": [5, 10, 15],
    "admin_fee_base": 200,
    "admin_fee_per_beneficiary": 175,
    "service_fee": 800,
    "age_cap_threshold": 70,
    "age_cap_amount": 500,
    "registration_year_min": 1950,
}

_IDENTITY = ("fiscal_year", "tier_fees", "admin_fee_base", "admin_fee_per_beneficiary",
             "service_fee")  # fmt: skip

# Frozen pricing rules (2026-10-29).
FEE_KEY = {
    "MOTHER": "parent", "FATHER": "parent", "SON_MINOR": "child", "SON_UNIVERSITY": "child",
    "SON_GRADUATE": "grad_son", "HUSBAND": "spouse", "WIFE": "spouse",
}  # fmt: skip
KINSHIP_LABEL = {
    "MOTHER": "أم", "FATHER": "أب", "SON_MINOR": "ابن/ابنة (18 سنة أو أقل)",
    "SON_UNIVERSITY": "ابن/ابنة (طالب جامعي)", "SON_GRADUATE": "ابن/ابنة (خريج)",
    "HUSBAND": "زوج", "WIFE": "زوجة",
}  # fmt: skip
SPOUSES = {"HUSBAND", "WIFE"}
MEMBER_LABEL = "العضو الأصلي"
ADMIN_FEE_LABEL = "رسوم إدارية"
SERVICE_FEE_LABEL = "رسوم الخدمة"
AGE_CAP_NOTE = "تم تطبيق سقف {amount} ج (عمر {age} سنة)"
INVALID_REGISTRATION_YEAR = "يرجى إدخال سنة قيد النقابة بشكل صحيح لحساب الاشتراك."
NOT_ELIGIBLE = (
    "المستفيد {name}: لا يمكن الاشتراك بدرجة القرابة «{kinship}» للأعضاء المقيدين "
    "في نفس سنة الاشتراك."
)

REFUSED = (
    "fees.0008 stopped: {count} FY {fiscal_year} application(s) cannot be re-priced from the "
    "data they were submitted with, so nothing was changed (the migration rolled back and "
    "version 2 is still active). For each application below, restore a complete "
    "submitted_snapshot (member, application and beneficiaries exactly as submitted) or, if it "
    "was never really submitted, clear its fee_snapshot and fee_schedule; then run migrate "
    "again.\n{problems}"
)
_SUBMITTED_ROW_KEYS = ("row_number", "kinship", "full_name", "birth_year")


class SubmittedDataError(Exception):
    """The application's submitted data cannot be priced; the message never holds personal data."""


def _year_or_none(value) -> bool:
    return value is None or type(value) is int


def submitted_inputs(application) -> dict:
    """The pricing inputs exactly as submitted, checked for completeness and types."""
    snapshot = application.submitted_snapshot
    if not isinstance(snapshot, dict) or not snapshot:
        raise SubmittedDataError("no submitted_snapshot")
    for part, kind in (("member", dict), ("application", dict), ("beneficiaries", list)):
        if not isinstance(snapshot.get(part), kind):
            raise SubmittedDataError(f"submitted_snapshot lacks {part}")
    member, submitted = snapshot["member"], snapshot["application"]
    for key in ("syndicate_registration_year", "birth_year"):
        if key not in member:
            raise SubmittedDataError(f"submitted_snapshot lacks member.{key}")
    if "work_status" not in submitted:
        raise SubmittedDataError("submitted_snapshot lacks application.work_status")
    if submitted.get("fiscal_year") != application.fiscal_year:
        raise SubmittedDataError(
            f"submitted_snapshot is for fiscal year {submitted.get('fiscal_year')}, "
            f"not {application.fiscal_year}"
        )
    if not _year_or_none(member["birth_year"]):
        raise SubmittedDataError("member.birth_year must be a whole number or empty")
    rows = snapshot["beneficiaries"]
    for row in rows:
        if not isinstance(row, dict) or any(key not in row for key in _SUBMITTED_ROW_KEYS):
            raise SubmittedDataError(
                "a submitted beneficiary lacks one of " + ", ".join(_SUBMITTED_ROW_KEYS)
            )
        if type(row["row_number"]) is not int:
            raise SubmittedDataError("a submitted beneficiary has no whole-number row_number")
        number = row["row_number"]
        if not _year_or_none(row["birth_year"]):
            raise SubmittedDataError(f"row {number}: birth_year must be a whole number or empty")
        if row["kinship"] and row["kinship"] not in FEE_KEY:
            raise SubmittedDataError(f"row {number}: unknown kinship {row['kinship']!r}")
    return {
        "registration_year": member["syndicate_registration_year"],
        "member_birth_year": member["birth_year"],
        "work_status": submitted["work_status"],
        "beneficiaries": sorted(rows, key=lambda row: row["row_number"]),
    }


def _invalid(schedule, tier: int, message: str) -> dict:
    return {
        "fiscal_year": schedule.fiscal_year, "tier": tier, "breakdown": [], "admin_fee": 0,
        "service_fee": 0, "total": 0, "is_valid": False, "error_message": message,
        "schedule_id": str(schedule.pk),
    }  # fmt: skip


def _tier(schedule, registration_year: int, work_status: str) -> int:
    if work_status == "PENSIONER":
        return 4
    years = schedule.fiscal_year - registration_year
    if years == 0:
        return 0
    for tier, upper in enumerate(schedule.tier_boundaries, start=1):
        if years <= upper:
            return tier
    return 4


def _capped(schedule, fee: int, birth_year) -> tuple[int, str]:
    if birth_year is None:
        return fee, ""
    age = schedule.fiscal_year - birth_year
    if age >= schedule.age_cap_threshold and fee > schedule.age_cap_amount:
        return schedule.age_cap_amount, AGE_CAP_NOTE.format(amount=schedule.age_cap_amount, age=age)
    return fee, ""


def _active(submitted) -> list[dict]:
    return [
        row
        for row in submitted["beneficiaries"]
        if row["kinship"] and isinstance(row["full_name"], str) and row["full_name"].strip()
    ]


def _registration_year_valid(schedule, year) -> bool:
    return type(year) is int and schedule.registration_year_min <= year <= schedule.fiscal_year


def quote(schedule, submitted) -> dict:
    year = submitted["registration_year"]
    if not _registration_year_valid(schedule, year):
        return _invalid(schedule, 0, INVALID_REGISTRATION_YEAR)
    tier = _tier(schedule, year, submitted["work_status"])
    fees = schedule.tier_fees[str(tier)]
    active = _active(submitted)
    for row in active:
        if fees[FEE_KEY[row["kinship"]]] is None:
            message = NOT_ELIGIBLE.format(
                name=row["full_name"].strip(), kinship=KINSHIP_LABEL[row["kinship"]]
            )
            return _invalid(schedule, tier, message)

    member_fee, member_note = _capped(schedule, fees["member"], submitted["member_birth_year"])
    breakdown = [{"label": MEMBER_LABEL, "fee": member_fee, "note": member_note}]
    for row in active:
        fee, note = fees[FEE_KEY[row["kinship"]]], ""
        if row["kinship"] in SPOUSES:
            fee, note = _capped(schedule, fee, row["birth_year"])
        breakdown.append({"label": row["full_name"].strip(), "fee": fee, "note": note})
    admin_fee = schedule.admin_fee_base + schedule.admin_fee_per_beneficiary * (len(active) + 1)
    breakdown.append({"label": ADMIN_FEE_LABEL, "fee": admin_fee, "note": ""})
    breakdown.append({"label": SERVICE_FEE_LABEL, "fee": schedule.service_fee, "note": ""})
    return {
        "fiscal_year": schedule.fiscal_year, "tier": tier, "breakdown": breakdown,
        "admin_fee": admin_fee, "service_fee": schedule.service_fee,
        "total": sum(line["fee"] for line in breakdown), "is_valid": True, "error_message": "",
        "schedule_id": str(schedule.pk),
    }  # fmt: skip


def quote_problem(schedule, submitted, priced: dict) -> str | None:
    """Why `priced` must not be saved, or None. Reasons name rows and kinships, never people."""
    if not priced.get("is_valid"):
        year = submitted["registration_year"]
        if not _registration_year_valid(schedule, year):
            return (
                f"submitted registration year {year!r} is missing or outside "
                f"{schedule.registration_year_min}..{schedule.fiscal_year}"
            )
        ineligible = [f"row {row['row_number']} ({row['kinship']})" for row in _active(submitted)
                      if schedule.tier_fees[str(priced.get("tier"))][FEE_KEY[row["kinship"]]]
                      is None]  # fmt: skip
        return f"not eligible at tier {priced.get('tier')}: " + ", ".join(ineligible)
    breakdown = priced.get("breakdown") or []
    fees = [line.get("fee") for line in breakdown]
    active = len(_active(submitted))
    expected_admin = schedule.admin_fee_base + schedule.admin_fee_per_beneficiary * (active + 1)
    consistent = (
        priced.get("fiscal_year") == schedule.fiscal_year
        and priced.get("schedule_id") == str(schedule.pk)
        and priced.get("tier") in (0, 1, 2, 3, 4)
        and len(breakdown) == active + 3
        and all(type(fee) is int and fee >= 0 for fee in fees)
        and breakdown[0].get("label") == MEMBER_LABEL
        and breakdown[-2] == {"label": ADMIN_FEE_LABEL, "fee": expected_admin, "note": ""}
        and breakdown[-1] == {"label": SERVICE_FEE_LABEL, "fee": schedule.service_fee, "note": ""}
        and priced.get("admin_fee") == expected_admin
        and priced.get("service_fee") == schedule.service_fee
        and priced.get("total") == sum(fees) > 0
    )
    return None if consistent else "inconsistent quote (lines, fees or total do not add up)"


def forwards(apps, schema_editor):
    FeeSchedule = apps.get_model("fees", "FeeSchedule")
    InsuranceApplication = apps.get_model("applications", "InsuranceApplication")
    fiscal_year = FY2026_V3["fiscal_year"]

    # Version 2 has the same amounts once 0007 gave it the column default: never reuse it.
    identity = {k: FY2026_V3[k] for k in _IDENTITY}
    v3 = FeeSchedule.objects.filter(**identity, is_active=True, version__gt=2).first()
    if v3 is None:
        existing = FeeSchedule.objects.select_for_update().filter(fiscal_year=fiscal_year)
        latest = existing.aggregate(v=Max("version"))["v"] or 0
        existing.filter(is_active=True).update(is_active=False)
        v3 = FeeSchedule.objects.create(**FY2026_V3, version=latest + 1, is_active=True)

    priced = (
        InsuranceApplication.objects.select_for_update()
        .filter(fiscal_year=fiscal_year, fee_snapshot__isnull=False)
        .exclude(fee_schedule=v3, fee_snapshot__schedule_id=str(v3.pk))
        .order_by("pk")
    )
    # Price and check everything first; write only when every application passes.
    replacements, problems = [], []
    for application in priced:
        try:
            submitted = submitted_inputs(application)
            replacement = quote(v3, submitted)
            problem = quote_problem(v3, submitted, replacement)
        except SubmittedDataError as error:
            problem = str(error)
        label = f"- {application.pk} ({application.reference_number}, {application.status}): "
        if problem:
            problems.append(label + problem)
        else:
            replacements.append((application.pk, replacement))
    if problems:
        raise RuntimeError(
            REFUSED.format(
                count=len(problems), fiscal_year=fiscal_year, problems="\n".join(problems)
            )
        )

    for pk, replacement in replacements:
        InsuranceApplication.objects.filter(pk=pk).update(fee_snapshot=replacement, fee_schedule=v3)
    if replacements and v3.locked_at is None:
        FeeSchedule.objects.filter(pk=v3.pk).update(locked_at=timezone.now())

    others = FeeSchedule.objects.filter(fiscal_year=fiscal_year).exclude(pk=v3.pk)
    # Applications without a snapshot never reference a version; clear any stray reference so
    # the delete is never blocked by the PROTECT foreign key.
    InsuranceApplication.objects.filter(fee_schedule__in=others).update(fee_schedule=None)
    others.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("fees", "0007_feeschedule_service_fee"),
        ("applications", "0001_initial"),
        ("beneficiaries", "0004_validate_kinship_constraint"),
        ("doctors", "0001_initial"),
    ]

    operations = [migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop)]
