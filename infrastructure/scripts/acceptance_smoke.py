#!/usr/bin/env python3
"""Automated part of the production acceptance checks (docs/production-acceptance.md). Read only:
GET requests with no credentials, so it can run against any environment at any time.

    acceptance_smoke.py --base-url https://neqabacare.com \
        --expect-client-id <id> [--direct-backend-url https://<container-app-fqdn>] \
        [--redirect-from https://<default-host>] [--json report.json]

A pass here is not production acceptance: signed-in journeys, MFA, documents and notifications are
checked by people and recorded in docs/production-acceptance.md. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

PASS, FAIL = "PASS", "FAIL"
STATIC_HEADERS = (
    "content-security-policy",
    "strict-transport-security",
    "x-content-type-options",
    "x-frame-options",
)
API_HEADERS = ("strict-transport-security", "x-content-type-options", "x-frame-options")


@dataclass
class Response:
    status: int
    headers: dict[str, list[str]]
    body: str

    def header(self, name: str) -> str:
        values = self.headers.get(name.lower(), [])
        return values[0] if values else ""


@dataclass
class Result:
    check: str
    outcome: str
    detail: str = ""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def fetch(url: str) -> Response:
    request = urllib.request.Request(url, headers={"User-Agent": "medical-acceptance-smoke"})
    try:
        response = _opener.open(request, timeout=30)
    except urllib.error.HTTPError as error:  # includes 3xx with redirects off
        response = error
    headers: dict[str, list[str]] = {}
    for name, value in response.headers.items():
        headers.setdefault(name.lower(), []).append(value)
    return Response(response.status, headers, response.read(1_000_000).decode("utf-8", "replace"))


@dataclass
class Smoke:
    base: str
    client_id: str
    get: Callable[[str], Response] = fetch
    results: list[Result] = field(default_factory=list)

    def record(self, check: str, ok: bool, detail: str = "") -> None:
        self.results.append(Result(check, PASS if ok else FAIL, detail))

    def url(self, path: str) -> str:
        return f"{self.base.rstrip('/')}{path}"

    def run(self) -> list[Result]:
        for check in (
            self.spa_is_arabic_rtl,
            self.deep_link_falls_back,
            self.static_security_headers,
            self.liveness,
            self.readiness_includes_schema,
            self.anonymous_session_is_refused,
            self.anonymous_data_is_refused,
            self.api_docs_are_off,
            self.api_security_headers,
            self.sign_in_redirect_is_correct,
        ):
            try:
                check()
            except (urllib.error.URLError, OSError, ValueError) as error:
                self.record(check.__name__, False, f"{type(error).__name__}: {error}")
        return self.results

    def spa_is_arabic_rtl(self) -> None:
        response = self.get(self.url("/"))
        ok = response.status == 200 and 'lang="ar"' in response.body and 'dir="rtl"' in response.body
        self.record("spa_is_arabic_rtl", ok, f"status {response.status}")

    def deep_link_falls_back(self) -> None:
        response = self.get(self.url("/doctor/form"))
        self.record("deep_link_falls_back", response.status == 200, f"status {response.status}")

    def static_security_headers(self) -> None:
        response = self.get(self.url("/"))
        missing = [name for name in STATIC_HEADERS if not response.header(name)]
        self.record("static_security_headers", not missing, f"missing {missing}" if missing else "")

    def liveness(self) -> None:
        response = self.get(self.url("/api/health/"))
        self.record("liveness", response.status == 200, f"status {response.status}")

    def readiness_includes_schema(self) -> None:
        response = self.get(self.url("/api/ready/"))
        body = json.loads(response.body) if response.status in (200, 503) else {}
        ok = response.status == 200 and body.get("database") == "ok" and body.get("schema") == "ok"
        self.record("readiness_includes_schema", ok, f"status {response.status} {body}")

    def anonymous_session_is_refused(self) -> None:
        response = self.get(self.url("/api/v1/auth/me/"))
        code = ""
        if response.status == 401:
            code = json.loads(response.body).get("error", {}).get("code", "")
        ok = response.status == 401 and code == "NOT_AUTHENTICATED"
        self.record("anonymous_session_is_refused", ok, f"status {response.status} {code}")

    def anonymous_data_is_refused(self) -> None:
        for path in ("/api/v1/applications/", "/api/v1/admin/applications/"):
            response = self.get(self.url(path))
            self.record(
                f"anonymous_refused {path}", response.status in (401, 403), f"status {response.status}"
            )

    def api_docs_are_off(self) -> None:
        response = self.get(self.url("/api/schema/"))
        # 404 from Django, or the SWA fallback never serves the schema.
        ok = response.status == 404 or "openapi" not in response.body[:200].lower()
        self.record("api_docs_are_off", ok, f"status {response.status}")

    def api_security_headers(self) -> None:
        response = self.get(self.url("/api/v1/auth/me/"))
        missing = [name for name in API_HEADERS if not response.header(name)]
        self.record("api_security_headers", not missing, f"missing {missing}" if missing else "")

    def sign_in_redirect_is_correct(self) -> None:
        response = self.get(self.url("/api/v1/auth/login/"))
        target = urllib.parse.urlsplit(response.header("location"))
        query = urllib.parse.parse_qs(target.query)
        expected_redirect = self.url("/api/v1/auth/callback/")
        problems = []
        if response.status != 302:
            problems.append(f"status {response.status}")
        if not target.hostname or not target.hostname.endswith(".ciamlogin.com"):
            problems.append("not an External ID authority")
        if query.get("client_id") != [self.client_id]:
            problems.append("wrong client id")
        if query.get("redirect_uri") != [expected_redirect]:
            problems.append(f"redirect_uri is not {expected_redirect}")
        if query.get("code_challenge_method") != ["S256"]:
            problems.append("no PKCE S256")
        for cookie in response.headers.get("set-cookie", []):
            flags = cookie.lower()
            if "secure" not in flags or "httponly" not in flags:
                problems.append("a sign-in cookie is not Secure and HttpOnly")
                break
        self.record("sign_in_redirect_is_correct", not problems, "; ".join(problems))


def check_direct_backend(url: str, get: Callable[[str], Response] = fetch) -> Result:
    """Static Web Apps authentication on the link makes the Container App refuse direct callers."""
    response = get(f"{url.rstrip('/')}/api/v1/auth/me/")
    return Result(
        "direct_backend_is_protected",
        PASS if response.status == 401 and "NOT_AUTHENTICATED" not in response.body else FAIL,
        f"status {response.status}",
    )


def check_redirect(source: str, base: str, get: Callable[[str], Response] = fetch) -> Result:
    """Another configured host answers by redirecting to the default domain, path kept."""
    response = get(f"{source.rstrip('/')}/doctor/form")
    location = response.header("location")
    ok = response.status in (301, 302, 307, 308) and location.startswith(base.rstrip("/"))
    return Result("old_host_redirects", PASS if ok else FAIL, f"status {response.status}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expect-client-id", required=True)
    parser.add_argument("--direct-backend-url", default="")
    parser.add_argument("--redirect-from", default="")
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)

    smoke = Smoke(args.base_url, args.expect_client_id)
    results = smoke.run()
    if args.direct_backend_url:
        results.append(check_direct_backend(args.direct_backend_url))
    if args.redirect_from:
        results.append(check_redirect(args.redirect_from, args.base_url))

    for result in results:
        print(f"{result.outcome} {result.check} {result.detail}".rstrip())
    failed = [result for result in results if result.outcome == FAIL]
    print(f"acceptance smoke: {len(results) - len(failed)} passed, {len(failed)} failed")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump([result.__dict__ for result in results], handle, indent=2)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
