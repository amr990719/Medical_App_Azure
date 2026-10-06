"""Platform probes and API security headers (PROMPT.md §30, §38)."""

import json

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from config.middleware import ContentSecurityPolicyMiddleware, HealthProbeMiddleware

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


def downstream(request):
    return HttpResponse("downstream")


@pytest.fixture
def rf():
    return RequestFactory()


def test_liveness_probe_answers_for_any_host_header(rf, settings):
    """Container Apps / Docker probes reach the replica by IP; ALLOWED_HOSTS stays strict."""
    settings.ALLOWED_HOSTS = ["api.example.test"]
    request = rf.get("/api/health/", HTTP_HOST="10.0.0.12:8000")
    response = HealthProbeMiddleware(downstream)(request)
    assert response.status_code == 200
    assert json.loads(response.content) == {"status": "ok"}


@pytest.mark.django_db
def test_readiness_probe_answers_for_any_host_header(rf, settings):
    settings.ALLOWED_HOSTS = ["api.example.test"]
    request = rf.get("/api/ready/", HTTP_HOST="10.0.0.12:8000")
    response = HealthProbeMiddleware(downstream)(request)
    assert response.status_code == 200
    assert json.loads(response.content)["database"] == "ok"


@pytest.mark.parametrize(
    ("method", "path"),
    [("POST", "/api/health/"), ("GET", "/api/health/extra"), ("GET", "/api/v1/auth/me/")],
)
def test_everything_else_goes_through_the_normal_stack(rf, method, path):
    request = rf.generic(method, path)
    assert HealthProbeMiddleware(downstream)(request).content == b"downstream"


def test_disallowed_host_still_rejected_for_the_api(client, settings):
    settings.ALLOWED_HOSTS = ["api.example.test"]
    response = client.get("/api/v1/reference-data/", HTTP_HOST="evil.example")
    assert response.status_code == 400


def test_api_responses_get_a_locked_down_csp(rf):
    response = ContentSecurityPolicyMiddleware(downstream)(rf.get("/api/v1/auth/me/"))
    assert response["Content-Security-Policy"] == API_CSP


def test_existing_csp_is_kept(rf):
    def custom(request):
        response = HttpResponse()
        response["Content-Security-Policy"] = "default-src 'self'"
        return response

    response = ContentSecurityPolicyMiddleware(custom)(rf.get("/x"))
    assert response["Content-Security-Policy"] == "default-src 'self'"
