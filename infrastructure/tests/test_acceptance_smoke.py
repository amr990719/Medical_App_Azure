"""The smoke check must fail on each thing it claims to check, not only pass on a healthy site."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infrastructure" / "scripts"))

import acceptance_smoke as smoke  # noqa: E402

BASE = "https://app.example.test"
CLIENT = "00000000-0000-0000-0000-0000000000c1"
SAFE = {
    "strict-transport-security": ["max-age=31536000"],
    "x-content-type-options": ["nosniff"],
    "x-frame-options": ["DENY"],
}
STATIC = {**SAFE, "content-security-policy": ["default-src 'self'"]}
SPA = '<html lang="ar" dir="rtl"></html>'
UNAUTHENTICATED = json.dumps({"error": {"code": "NOT_AUTHENTICATED", "message": "x", "fields": {}}})
LOGIN = "https://tenant.ciamlogin.com/authorize?" + urlencode(
    {
        "client_id": CLIENT,
        "redirect_uri": f"{BASE}/api/v1/auth/callback/",
        "code_challenge_method": "S256",
    }
)


def healthy() -> dict[str, smoke.Response]:
    return {
        "/": smoke.Response(200, STATIC, SPA),
        "/doctor/form": smoke.Response(200, STATIC, SPA),
        "/api/health/": smoke.Response(200, SAFE, '{"status": "ok"}'),
        "/api/ready/": smoke.Response(
            200, SAFE, json.dumps({"status": "ok", "database": "ok", "schema": "ok"})
        ),
        "/api/v1/auth/me/": smoke.Response(401, SAFE, UNAUTHENTICATED),
        "/api/v1/applications/": smoke.Response(401, SAFE, UNAUTHENTICATED),
        "/api/v1/admin/applications/": smoke.Response(401, SAFE, UNAUTHENTICATED),
        "/api/schema/": smoke.Response(404, SAFE, "not found"),
        "/api/v1/auth/login/": smoke.Response(
            302,
            {**SAFE, "location": [LOGIN], "set-cookie": ["sessionid=x; Secure; HttpOnly"]},
            "",
        ),
    }


def run(site: dict[str, smoke.Response]) -> dict[str, str]:
    def get(url: str) -> smoke.Response:
        return site[url.removeprefix(BASE)]

    results = smoke.Smoke(BASE, CLIENT, get=get).run()
    return {result.check: result.outcome for result in results}


class Smoke(unittest.TestCase):
    def failed_when(self, path: str, response: smoke.Response) -> set[str]:
        site = healthy()
        site[path] = response
        return {check for check, outcome in run(site).items() if outcome == smoke.FAIL}

    def test_a_healthy_site_passes_every_check(self):
        self.assertEqual({check for check, o in run(healthy()).items() if o == smoke.FAIL}, set())

    def test_a_pending_schema_fails_readiness(self):
        body = json.dumps({"status": "unavailable", "database": "ok", "schema": "pending"})
        failed = self.failed_when("/api/ready/", smoke.Response(503, SAFE, body))
        self.assertEqual(failed, {"readiness_includes_schema"})

    def test_select_1_style_readiness_without_schema_fails(self):
        body = json.dumps({"status": "ok", "database": "ok"})
        failed = self.failed_when("/api/ready/", smoke.Response(200, SAFE, body))
        self.assertEqual(failed, {"readiness_includes_schema"})

    def test_anonymous_data_access_fails(self):
        failed = self.failed_when("/api/v1/admin/applications/", smoke.Response(200, SAFE, "[]"))
        self.assertEqual(failed, {"anonymous_refused /api/v1/admin/applications/"})

    def test_a_missing_header_fails(self):
        failed = self.failed_when("/", smoke.Response(200, SAFE, SPA))
        self.assertEqual(failed, {"static_security_headers"})

    def test_a_left_to_right_page_fails(self):
        failed = self.failed_when("/", smoke.Response(200, STATIC, '<html lang="en"></html>'))
        self.assertEqual(failed, {"spa_is_arabic_rtl"})

    def test_open_api_docs_fail(self):
        failed = self.failed_when("/api/schema/", smoke.Response(200, SAFE, "openapi: 3.0.3"))
        self.assertEqual(failed, {"api_docs_are_off"})

    def login_with(self, **changes) -> set[str]:
        values = {
            "client_id": CLIENT,
            "redirect_uri": f"{BASE}/api/v1/auth/callback/",
            "code_challenge_method": "S256",
        }
        values.update(changes)
        location = "https://tenant.ciamlogin.com/authorize?" + urlencode(values)
        return self.failed_when(
            "/api/v1/auth/login/", smoke.Response(302, {**SAFE, "location": [location]}, "")
        )

    def test_a_dev_client_id_on_production_fails(self):
        self.assertEqual(self.login_with(client_id="dev-client"), {"sign_in_redirect_is_correct"})

    def test_a_redirect_uri_for_another_host_fails(self):
        failed = self.login_with(redirect_uri="https://other.example.test/api/v1/auth/callback/")
        self.assertEqual(failed, {"sign_in_redirect_is_correct"})

    def test_sign_in_without_pkce_fails(self):
        self.assertEqual(self.login_with(code_challenge_method="plain"), {"sign_in_redirect_is_correct"})

    def test_an_insecure_session_cookie_fails(self):
        failed = self.failed_when(
            "/api/v1/auth/login/",
            smoke.Response(302, {**SAFE, "location": [LOGIN], "set-cookie": ["sessionid=x"]}, ""),
        )
        self.assertEqual(failed, {"sign_in_redirect_is_correct"})

    def test_two_cookies_cannot_pass_by_having_one_flag_each(self):
        failed = self.failed_when(
            "/api/v1/auth/login/",
            smoke.Response(
                302, {**SAFE, "location": [LOGIN], "set-cookie": ["a=1; Secure", "b=2; HttpOnly"]}, ""
            ),
        )
        self.assertEqual(failed, {"sign_in_redirect_is_correct"})

    def test_a_directly_reachable_backend_fails(self):
        open_backend = smoke.check_direct_backend(
            "https://backend.example.test",
            get=lambda url: smoke.Response(401, SAFE, UNAUTHENTICATED),
        )
        self.assertEqual(open_backend.outcome, smoke.FAIL)
        protected = smoke.check_direct_backend(
            "https://backend.example.test", get=lambda url: smoke.Response(401, {}, "")
        )
        self.assertEqual(protected.outcome, smoke.PASS)

    def test_the_old_host_must_redirect_to_the_final_host(self):
        moved = smoke.check_redirect(
            "https://old.example.test",
            BASE,
            get=lambda url: smoke.Response(301, {"location": [f"{BASE}/doctor/form"]}, ""),
        )
        self.assertEqual(moved.outcome, smoke.PASS)
        served = smoke.check_redirect(
            "https://old.example.test", BASE, get=lambda url: smoke.Response(200, {}, SPA)
        )
        self.assertEqual(served.outcome, smoke.FAIL)


if __name__ == "__main__":
    unittest.main()
