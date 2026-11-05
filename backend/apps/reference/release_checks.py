"""What a release must prove before traffic shifts (`manage.py release_check`).

`/api/ready/` says the database answers and the schema is current. These checks prove the rest:
the shared cache table, the fee schedule of the fiscal year, Blob access and Entra discovery. A
detail never holds a value from the environment: a failure names the exception class only.
"""

import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.accounts.models import Role
from apps.accounts.oidc.claims import discovery_document
from apps.documents.storage import get_storage
from apps.fees.services import NoActiveFeeSchedule, active_schedule
from apps.reference.api.views import reference_data
from config.health import unapplied_migrations

OK, FAIL, SKIPPED = "ok", "fail", "skipped"
# Outside `applications/`, so `cleanup_blobs` and `reconcile_documents` never see the probe.
BLOB_PROBE_PREFIX = "release-check/"
CACHE_PROBE_TTL_SECONDS = 30


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str


def _result(name: str, passed: bool, detail: str) -> CheckResult:
    return CheckResult(name, OK if passed else FAIL, detail)


def check_migrations() -> CheckResult:
    pending = len(unapplied_migrations())
    return _result("migrations", pending == 0, f"pending={pending}")


def check_cache() -> CheckResult:
    key = f"release-check-{uuid.uuid4()}"
    value = str(uuid.uuid4())
    cache.set(key, value, CACHE_PROBE_TTL_SECONDS)
    read_back = cache.get(key)
    cache.delete(key)
    return _result("cache", read_back == value, "round-trip")


def check_fiscal_year_explicit(*, year_given: bool) -> CheckResult:
    """Production must name the year itself; a year passed by hand is a rehearsal for next year."""
    name = "fiscal_year_explicit"
    if year_given:
        return CheckResult(name, SKIPPED, "year-given")
    if not os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith(".production"):
        return CheckResult(name, SKIPPED, "not-production-settings")
    return _result(name, bool(os.environ.get("CURRENT_FISCAL_YEAR")), "environment")


def check_fee_schedule(fiscal_year: int) -> CheckResult:
    try:
        schedule = active_schedule(fiscal_year)
    except NoActiveFeeSchedule:
        return _result("fee_schedule", False, f"fiscal_year={fiscal_year},no-active-schedule")
    return _result("fee_schedule", True, f"fiscal_year={fiscal_year},version={schedule.version}")


def check_reference_data() -> CheckResult:
    payload = reference_data()
    return _result("reference_data", bool(payload["document_rules"]), "built")


def check_blob_storage() -> CheckResult:
    storage = get_storage()
    name = f"{BLOB_PROBE_PREFIX}{uuid.uuid4()}.txt"
    data = b"release-check"
    try:
        storage.upload(name, data, content_type="text/plain")
        return _result("blob_storage", storage.download(name) == data, "round-trip")
    finally:
        storage.delete(name)


def check_entra_discovery() -> CheckResult:
    if not settings.ENTRA_AUTHORITY:
        return CheckResult("entra_discovery", SKIPPED, "no-authority")
    return _result("entra_discovery", bool(discovery_document().get("issuer")), "issuer")


def check_admin() -> CheckResult:
    count = get_user_model().objects.filter(role=Role.ADMIN, is_active=True).count()
    return _result("admin", count > 0, f"count={count}")


def _guarded(name: str, check: Callable[[], CheckResult]) -> CheckResult:
    try:
        return check()
    except Exception as exc:
        # Class name only: a driver or SDK message can hold a connection string or a host.
        return CheckResult(name, FAIL, type(exc).__name__)


def run_checks(
    *, fiscal_year: int | None = None, skip_blob: bool = False, require_admin: bool = False
) -> list[CheckResult]:
    """Every check, in order. A failing one never stops the others: the report stays complete."""
    year = fiscal_year if fiscal_year is not None else settings.CURRENT_FISCAL_YEAR
    checks: list[tuple[str, Callable[[], CheckResult]]] = [
        ("migrations", check_migrations),
        ("cache", check_cache),
        (
            "fiscal_year_explicit",
            lambda: check_fiscal_year_explicit(year_given=fiscal_year is not None),
        ),
        ("fee_schedule", lambda: check_fee_schedule(year)),
        ("reference_data", check_reference_data),
        (
            "blob_storage",
            (lambda: CheckResult("blob_storage", SKIPPED, "requested"))
            if skip_blob
            else check_blob_storage,
        ),
        ("entra_discovery", check_entra_discovery),
    ]
    if require_admin:
        checks.append(("admin", check_admin))
    return [_guarded(name, check) for name, check in checks]
