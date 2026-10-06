# REST API

Django REST Framework under `/api/v1/` (PROMPT.md §24). snake_case JSON. Interactive docs at
`/api/docs/` and the schema at `/api/schema/` when `API_DOCS_ENABLED` (on in development, off in
production). Generate the schema file with:

```bash
cd backend
python manage.py spectacular --file openapi.yaml --validate --fail-on-warn
cd ../frontend && npm run gen:api     # regenerates src/api/schema.d.ts
```

OpenAPI schema: **http://localhost:8000/api/schema/** (YAML) and Swagger UI at
**http://localhost:8000/api/docs/** with the compose stack running. `backend/openapi.yaml` is
generated, not committed (CI regenerates and validates it in `backend.yml`); the typed client in
`frontend/src/api/schema.d.ts` is generated from it.

## Authentication (BFF)

The browser never holds tokens. Django is the confidential OIDC client and issues an HttpOnly
`SameSite=Lax` session cookie (`Secure` in production). Idle timeout 2 h (renewed per request),
absolute timeout 12 h (`SESSION_*_TIMEOUT_SECONDS`).

- **CSRF:** every unsafe request (POST/PATCH/DELETE) sends `X-CSRFToken` with the value of the
  `csrftoken` cookie. `GET /api/v1/auth/me/` sets the cookie (also on its 401) and returns the
  token in the body when signed in.
- **Roles:** `DOCTOR` (default) and `ADMIN` (only via `python manage.py grant_admin <email|oid>`).
  Doctor endpoints refuse admins (403) and vice versa. Another doctor's object id is always 404.

| Method | Path | Notes |
|---|---|---|
| GET | `/auth/login/?next=/dashboard` | 302 to Entra External ID (code flow + PKCE). `next` must be a relative path. 503 `AUTH_UNAVAILABLE` if Entra is not configured |
| GET | `/auth/callback/` | validates the ID token (signature/JWKS, issuer, audience, nonce, expiry, tenant), maps the user by `(oid, tid)`, starts the session, 302 to `next`. Failures 302 to `/?auth_error=<CODE>` (`AUTH_FAILED`, `MFA_REQUIRED`, `EMAIL_IN_USE`, `ACCOUNT_DISABLED`, `EMAIL_CLAIM_MISSING`). 20/min per IP |
| POST | `/auth/logout/` | ends the session; returns `{"entra_logout_url"}` |
| GET | `/auth/me/` | `{"user": {"id","email","role","display_name","has_profile"}, "csrf_token"}` or 401 |
| GET | `/auth/dev/users/` | **development/test only** (`DEV_AUTH_ENABLED`), else 404 |
| POST | `/auth/dev/login/` | **development/test only** `{"email"}`; CSRF enforced |

## Reference data and profile

| Method | Path | Notes |
|---|---|---|
| GET | `/reference-data/` | fiscal year, `max_beneficiaries`, 27 governorates, every enum with Arabic labels, kinships with `fee_key`, the document-rules table, `ocr_enabled`, feature flags, upload limits |
| GET | `/profile/` | the doctor's own member data (created empty on first visit) |
| PATCH | `/profile/` | Arabic digits accepted everywhere; national ID derives date of birth, birth year and gender (a conflicting typed value is 400); `DUPLICATE_NATIONAL_ID` 409; 409 `APPLICATION_NOT_EDITABLE` while the current application is submitted / under review / approved |

## Applications (doctor, own objects only)

| Method | Path | Notes |
|---|---|---|
| GET | `/applications/` | paginated |
| POST | `/applications/` | `{"application_type"?}` → 201 new draft for the current fiscal year, or 200 with the active one |
| GET | `/applications/{id}/` | nested `beneficiaries` (with `required_documents` from the rules table) and `documents` |
| PATCH | `/applications/{id}/` | only `application_type`, `work_status`, `declaration_name`, `declaration_accepted`; every other field is read-only and ignored. 409 when not editable |
| GET | `/applications/{id}/fees/` | live server quote while editable; the frozen `fee_snapshot` afterwards |
| GET | `/applications/{id}/validation/` | `{is_valid, errors, by_step, steps_complete, warnings, submit_ready}` |
| POST | `/applications/{id}/submit/` | DRAFT → SUBMITTED (reference number generated) or NEEDS_CORRECTION → SUBMITTED (same number). 400 with every error grouped by step; 409 `INVALID_STATUS_TRANSITION` otherwise |
| GET/POST | `/applications/{id}/beneficiaries/` | POST takes the lowest free row unless `row_number` is given |
| PATCH/DELETE | `/applications/{id}/beneficiaries/{beneficiary_id}/` | a kinship change soft-deletes that row's documents |

## Documents

| Method | Path | Notes |
|---|---|---|
| POST | `/applications/{id}/documents/` | multipart `file`, `document_type`, `beneficiary_id?`. Type sniffed from the bytes, images fully decoded, 8 MB max, receipt ≥ 400×300, executables refused; re-upload replaces the slot. Receipt → `payment_status=PENDING_REVIEW`. 60/hour per user |
| GET | `/documents/{id}/` | metadata (owner, or admin for submitted applications) |
| GET | `/documents/{id}/content/` | authorized stream (`DOCUMENT_CONTENT_DELIVERY=stream`, default) or 302 to a read-only SAS valid ≤ 5 minutes (`sas`); audited |
| DELETE | `/documents/{id}/` | owner, only while editable |
| POST | `/documents/{id}/extract/` | OCR suggestions `{document_id, document_type, fields}`; nothing is saved. 503 `OCR_UNAVAILABLE` when disabled/PDF; 30/hour per user |

## Admin (role ADMIN)

Drafts are not visible to admins. National IDs are masked (`29•••••••••123`) except on an
application detail requested with `?reveal_national_id=1` (audited `NATIONAL_ID_REVEALED`).

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/stats/?fiscal_year=` | counts per status and payment status, `receipts_pending` |
| GET | `/admin/applications/` | filters `status`, `payment_status`, `fiscal_year`, `governorate`, `syndicate_type`, `sub_syndicate`, `submitted_from`, `submitted_to`; `search` (name, reference, phone, full or masked national ID, Arabic digits OK); `ordering` (`submitted_at`, `reference_number`, `status`, `total`, prefix `-`); `page`, `page_size` ≤ 100 |
| GET | `/admin/applications/{id}/` | full detail, `allowed_transitions`, `beneficiary_warnings`; audited |
| POST | `/admin/applications/{id}/transition/` | `{to_status, review_notes}` through the single transition service |
| POST | `/admin/applications/{id}/payment/` | `{payment_status: CONFIRMED|REJECTED, note?}` |
| GET/POST | `/admin/applications/{id}/notes/` | internal notes, never on doctor endpoints |
| GET | `/admin/applications/{id}/audit/` | audit history of the application and its documents |
| GET | `/admin/doctors/`, `/admin/doctors/{id}/` | members (masked IDs), search, filters |
| GET/POST | `/admin/fee-schedules/` | POST creates the next version for a fiscal year and deactivates the previous one |
| GET | `/admin/fee-schedules/{id}/` | |

## Probes

`GET /api/health/` (liveness, no database) and `GET /api/ready/` (`SELECT 1`, 503 when the
database is unreachable). Public, no session.

## Errors (PROMPT.md §46)

```json
{"error": {"code": "VALIDATION_ERROR", "message": "يرجى تصحيح الأخطاء المشار إليها",
           "fields": {"member.phone_number": ["رقم الهاتف المحمول غير صحيح"]},
           "errors": [{"step": 1, "field": "member.phone_number", "code": "INVALID",
                       "message": "رقم الهاتف المحمول غير صحيح"}]}}
```

`errors` (with wizard steps) is present on submission validation failures only.

| Code | HTTP |
|---|---|
| `VALIDATION_ERROR` | 400 |
| `IMAGE_TOO_SMALL` | 400 |
| `NOT_AUTHENTICATED` | 401 |
| `PERMISSION_DENIED` (incl. CSRF failures) | 403 |
| `NOT_FOUND` | 404 |
| `METHOD_NOT_ALLOWED` | 405 |
| `DUPLICATE_NATIONAL_ID`, `ACTIVE_APPLICATION_EXISTS`, `INVALID_STATUS_TRANSITION`, `APPLICATION_NOT_EDITABLE` | 409 |
| `FILE_TOO_LARGE` | 413 |
| `UNSUPPORTED_FILE_TYPE`, `UNSUPPORTED_MEDIA_TYPE` | 415 |
| `RATE_LIMITED` (with `Retry-After`) | 429 |
| `SERVER_ERROR` (generic Arabic message, never a traceback) | 500 |
| `OCR_UNAVAILABLE`, `AUTH_UNAVAILABLE` | 503 |

## Local smoke test

`backend/scripts/smoke_api.py` drives the whole doctor flow over real HTTP against `runserver`
(development settings, docker compose PostgreSQL + Azurite). `backend/tests/test_e2e_flow.py`
does the same inside pytest (marker `azurite`, skipped when Azurite is not running).
