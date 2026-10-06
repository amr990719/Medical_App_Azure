# Security and privacy

> **Draft (Session 7).** Lists the technical controls that exist in the code and the decisions
> that need the organization's legal / management approval. It does **not** claim compliance with
> Egypt's Personal Data Protection Law (Law 151 of 2020), GDPR, HIPAA or any other regulation
> (PROMPT.md §47). Items marked **NOT VERIFIED — requires Azure credentials** are implemented
> and unit-tested with mocks but have not run against real Azure resources.

## 1. Data handled

Sensitive personal information (PROMPT.md §47): national IDs (members and beneficiaries),
syndicate registration data, addresses, phone numbers, e-mail, **religion**, family relationships
and birth years, identity-document images, personal photos and payment receipts.

| Where | What | Protection |
|---|---|---|
| Azure Database for PostgreSQL | all structured data, document *metadata*, audit log | TLS required (`DB_SSLMODE=require`+), Entra auth with managed identity (no password), private networking (Session 8) |
| Azure Blob Storage (private container) | document and photo files | no public access, managed identity, read SAS ≤ 5 min for one blob, soft delete + versioning (Session 8) |
| Key Vault | Django `SECRET_KEY`, Entra client secret, DB password (fallback only) | RBAC, managed identity, soft delete + purge protection (Session 8) |
| Application Insights / Log Analytics | requests, dependencies, exceptions, logs | national IDs masked before export (§4 below) |
| Azure OpenAI (only if OCR is enabled) | one identity-document image per OCR request | see §5 and `docs/ocr.md` |

## 2. Identity, sessions and authorization

- Microsoft Entra External ID, **BFF pattern**: Django is the confidential OIDC client
  (authorization code + PKCE, nonce, state); ID tokens are validated independently (signature
  against JWKS, issuer, audience, expiry, nonce); users are mapped by `oid` + `tid`, never by
  e-mail. No tokens and no password forms in the browser.
- Session cookie `HttpOnly`, `Secure`, `SameSite=Lax`; idle timeout 2 h
  (`SESSION_IDLE_TIMEOUT_SECONDS`) and absolute timeout 12 h
  (`SESSION_ABSOLUTE_TIMEOUT_SECONDS`). CSRF token required on every unsafe method;
  `CSRF_TRUSTED_ORIGINS` must list the Static Web Apps origin.
- Admin role only via `python manage.py grant_admin` (audited `ADMIN_ROLE_GRANTED`); an admin
  session requires `amr` to contain `mfa` (`ENTRA_ADMIN_REQUIRE_MFA=true`, Q-T7).
- Object-level authorization on every endpoint; doctor querysets are scoped to the requesting
  doctor; protected fields (`status`, `payment_status`, `reference_number`, `fee_snapshot`,
  reviewer fields, …) are read-only for doctors and covered by tests. Status changes go through
  one transition service with row locks and audit entries.
- `DEV_AUTH_ENABLED` exists only in development/test settings; production settings refuse to
  import (the container does not start) when it is set.
- Rate limits (DRF scoped throttles): sign-in callback 20/min, uploads 60/h, OCR 30/h per user.
  Counters need a cache shared by all replicas (Q-T6).

## 3. Application and transport hardening (production settings)

- Startup check: import of `config.settings.production` fails on `DEBUG`, `DEV_AUTH_ENABLED`, a
  missing or short `DJANGO_SECRET_KEY`, missing/wildcard `ALLOWED_HOSTS`, missing
  `CSRF_TRUSTED_ORIGINS` / `DATABASE_URL` / Entra settings, non-TLS `DB_SSLMODE`, an unknown
  `DB_AUTH_MODE`, Blob account keys (only managed identity; the Azurite emulator string is the
  sole exception, for local production-like runs), the in-memory blob backend, mock OCR, or
  incomplete Azure OpenAI settings when OCR is on.
- HTTPS redirect (probes exempt), HSTS 1 year + `includeSubDomains` + `preload`
  (`SECURE_HSTS_PRELOAD` can turn the preload flag off), `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin`,
  `X-Frame-Options: DENY`, and an API CSP `default-src 'none'; frame-ancestors 'none';
  base-uri 'none'; form-action 'none'`. No CORS (same origin through the SWA linked backend).
- `manage.py check --deploy` with production settings reports no issues.
- Uploads: content sniffing by signature (not extension), images fully decoded by Pillow,
  decompression-bomb cap (`DOCUMENT_MAX_PIXELS`), size cap (`MAX_UPLOAD_BYTES`, 8 MB), receipt
  minimum dimensions, server-generated blob names, sanitized display names; multipart bodies
  above 2 MB are streamed to a temporary file, non-file bodies are capped at 2 MB.
- Container: multi-stage image, non-root user (uid 10001), code owned by root and read-only to
  the app, no state in the container, Gunicorn access log off (query strings could carry a
  national ID), Gunicorn control socket disabled, health probes answered before host validation
  (they return no data). Migrations never run on replica start.

## 4. Logging, telemetry and audit

- JSON logs to stdout with request id, internal user UUID, method, path (no query string),
  status and latency. Never cookies, headers, bodies, tokens, passwords or document bytes.
- `NationalIdMaskingFilter` masks every run of 14+ digits (Western or Eastern Arabic) as
  `29•••••••••123` in messages and `extra` fields; the JSON formatter masks again (tracebacks).
- Application Insights (`config/telemetry.py`, Azure Monitor OpenTelemetry distro): the log
  handler carries the same filter; a log-record processor masks bodies and attributes
  (exception messages and stack traces); a span processor drops query strings and fragments
  from URL attributes (`url.query`, `url.full`, `http.url`, `http.target` — search terms, phone
  numbers, e-mails, OIDC `code`/`state`), drops cookie/authorization/CSRF header attributes if
  header capture is ever enabled, and masks span names, attributes and exception events before
  export. Free text in exception messages is only masked for 14+ digit runs. Ingestion can be
  authenticated with the managed identity (`APPLICATIONINSIGHTS_AUTHENTICATION=entra`).
  **NOT VERIFIED — requires Azure credentials.**
- Audit log (append-only table) for submissions, status and payment changes, document
  uploads/views/deletions, OCR requests (field names only), admin views, notes, fee-schedule
  changes, admin grants and every reveal of a full national ID.

## 5. Azure integration controls (Session 7)

| Control | Implementation | Status |
|---|---|---|
| One managed identity for every Azure call | `config/azure.py` (`DefaultAzureCredential`, `AZURE_CLIENT_ID` selects the user-assigned identity; `AZURE_TOKEN_CREDENTIALS=prod` in Azure) | NOT VERIFIED — requires Azure credentials |
| Blob access + user-delegation SAS | `apps/documents/storage.py`; delegation key cached 1 h; SAS read-only, one blob, ≤ 300 s, content type/disposition pinned. Roles: Storage Blob Data Contributor + Storage Blob Delegator | NOT VERIFIED — requires Azure credentials |
| Key Vault secrets | `config/secrets.py`; environment (Container Apps Key Vault references) wins; names `django-secret-key`, `entra-client-secret`, `database-password`; role Key Vault Secrets User | NOT VERIFIED — requires Azure credentials |
| PostgreSQL Entra auth | `config/db/entra_postgres` — fresh token per new connection (cached until 5 min before expiry), TLS enforced, `CONN_MAX_AGE` ≤ 1800 s; `DB_AUTH_MODE=password` fallback | NOT VERIFIED — requires Azure credentials |
| Azure OpenAI OCR | managed identity bearer tokens, no API key, structured outputs, no payload logging | NOT VERIFIED — requires Azure credentials |

## 6. Decisions requiring legal / organizational approval

| # | Decision | Current default | Owner |
|---|---|---|---|
| L1 | **Religion field.** The paper form asks for religion; it is sensitive data. Is collecting it necessary and lawful, who may see it, and must it be on the printed form? | Collected (optional in the API), shown to the doctor and admins, OCR may suggest it | Legal + syndicate management |
| L2 | **OCR by an AI service.** Sending identity-document images to Azure OpenAI (abuse monitoring may retain them up to 30 days unless modified abuse monitoring is approved). | `OCR_ENABLED=false` in production until approved; manual entry always works | Legal / DPO |
| L3 | **Data residency / region.** There is no Azure region in Egypt; choose the region(s) for PostgreSQL, Blob, Key Vault, Log Analytics and Azure OpenAI, and confirm cross-border transfer requirements under Law 151/2020. | Not chosen (Q-T1); Bicep will parameterize the region | Legal + IT |
| L4 | **Retention periods** for applications, documents, rejected/withdrawn applications, audit logs, telemetry (Log Analytics retention) and backups; deletion on request. | Nothing is deleted automatically except orphan/soft-deleted blobs (`cleanup_blobs`) | Legal + syndicate management |
| L5 | **Admin access policy:** who may be granted the admin role, MFA, periodic access review, who may reveal full national IDs (audited) and print unmasked forms (Q-B20). | `grant_admin` by an operator with production access; reveal is audited | Syndicate management + IT |
| L6 | **Breach procedure:** detection (Application Insights alerts, audit review), containment (revoke sessions, rotate Key Vault secrets, disable OCR/uploads by flag), notification duties and timelines, contacts. | Not defined | Legal / DPO + IT |
| L7 | **Production access:** who may access the Azure subscription, database and Key Vault; break-glass accounts; separation of environments (§49). | Separate resources per environment planned (Session 8) | IT |
| L8 | **Malware scanning** of uploads (Microsoft Defender for Storage malware scanning). | `scan_status` field exists, scanning off (`MALWARE_SCAN_ENABLED=false`) | IT (cost decision) |

## 7. Known gaps (tracked in docs/progress.md)

- Shared cache for rate limits across replicas (Q-T6).
- Entra External ID claims (`email`, `amr`) not verified against a real tenant (Q-T7).
- Network isolation (private endpoints, VNet integration), Defender, alerts and backup/restore
  drills belong to Session 8 (Bicep) and Session 9 (security review).
