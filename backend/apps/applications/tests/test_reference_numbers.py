"""Reference numbers (PROMPT.md §16.3) — format, sequence, and real concurrency on PostgreSQL."""

import threading

import pytest
from django.db import connection, transaction
from django.db.transaction import TransactionManagementError

from apps.applications.factories import build_submittable_application
from apps.applications.models import InsuranceApplication
from apps.applications.services import generate_reference_number, submit
from apps.audit.models import AuditAction, AuditLog


@pytest.mark.django_db
def test_reference_number_format_and_sequence():
    with transaction.atomic():
        assert generate_reference_number(2026) == "MED-2026-000001"
    with transaction.atomic():
        assert generate_reference_number(2026) == "MED-2026-000002"


@pytest.mark.django_db
def test_sequences_are_per_fiscal_year():
    with transaction.atomic():
        generate_reference_number(2026)
        assert generate_reference_number(2027) == "MED-2027-000001"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_must_run_inside_a_transaction():
    with pytest.raises(TransactionManagementError):
        generate_reference_number(2026)


@pytest.mark.django_db
def test_rolled_back_submission_does_not_consume_a_number():
    with pytest.raises(RuntimeError), transaction.atomic():
        generate_reference_number(2026)
        raise RuntimeError
    with transaction.atomic():
        assert generate_reference_number(2026) == "MED-2026-000001"


def run_concurrently(*callables):
    """Start every callable at the same moment, each on its own database connection."""
    barrier = threading.Barrier(len(callables))
    results: list = [None] * len(callables)

    def worker(index, fn):
        try:
            barrier.wait(timeout=10)
            results[index] = fn()
        except Exception as exc:
            results[index] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, fn)) for i, fn in enumerate(callables)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_concurrent_submits_of_different_applications_get_distinct_numbers():
    apps = [build_submittable_application() for _ in range(4)]
    results = run_concurrently(*[lambda a=a: submit(a, actor=a.doctor.user) for a in apps])
    assert all(isinstance(r, InsuranceApplication) for r in results), results
    numbers = sorted(r.reference_number for r in results)
    assert numbers == [f"MED-2026-{n:06d}" for n in range(1, 5)]


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_concurrent_submits_of_the_same_application_produce_one_number():
    # Review Focus 2: exactly one reference number and one APPLICATION_SUBMITTED entry.
    app = build_submittable_application()
    results = run_concurrently(
        lambda: submit(app, actor=app.doctor.user), lambda: submit(app, actor=app.doctor.user)
    )
    successes = [r for r in results if isinstance(r, InsuranceApplication)]
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(successes) == 1, results
    assert len(failures) == 1
    assert failures[0].code == "INVALID_STATUS_TRANSITION"
    assert InsuranceApplication.objects.get(pk=app.pk).reference_number == "MED-2026-000001"
    assert AuditLog.objects.filter(action=AuditAction.APPLICATION_SUBMITTED).count() == 1
