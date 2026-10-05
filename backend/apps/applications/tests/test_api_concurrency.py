"""Concurrent submissions through the HTTP API (Review Focus 2, PROMPT.md §16.3, §42)."""

import re
import threading

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.applications.factories import build_submittable_application
from apps.applications.models import InsuranceApplication, ReferenceCounter
from apps.audit.models import AuditAction, AuditLog
from apps.doctors.factories import DoctorFactory

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)


def run_concurrently(calls):
    barrier = threading.Barrier(len(calls))
    results = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait()
            results[index] = call()
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, c)) for i, c in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def submit_call(app):
    def call():
        client = APIClient()
        client.force_authenticate(app.doctor.user)
        return client.post(f"/api/v1/applications/{app.pk}/submit/")

    return call


def test_double_submit_same_application_yields_one_reference_and_one_audit():
    app = build_submittable_application()
    responses = run_concurrently([submit_call(app), submit_call(app)])
    assert sorted(r.status_code for r in responses) == [200, 409]
    app.refresh_from_db()
    assert app.reference_number == "MED-2026-000001"
    assert AuditLog.objects.filter(action=AuditAction.APPLICATION_SUBMITTED).count() == 1
    assert ReferenceCounter.objects.get(fiscal_year=2026).last_sequence == 1


def test_parallel_submissions_get_unique_sequential_reference_numbers():
    apps = [build_submittable_application(doctor=DoctorFactory()) for _ in range(5)]
    responses = run_concurrently([submit_call(a) for a in apps])
    assert all(r.status_code == 200 for r in responses), [r.json() for r in responses]
    numbers = sorted(r.json()["reference_number"] for r in responses)
    assert numbers == [f"MED-2026-{n:06d}" for n in range(1, 6)]
    assert all(re.fullmatch(r"MED-2026-\d{6}", n) for n in numbers)
    assert InsuranceApplication.objects.filter(status="SUBMITTED").count() == 5
