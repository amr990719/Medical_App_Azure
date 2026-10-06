# Security and privacy

> **Reviewed in Session 9** (findings and fixes in §8). Lists the technical controls that exist in the code and the decisions
> that need the organization's legal / management approval. It does **not** claim compliance with
> Egypt's Personal Data Protection Law (Law 151 of 2020), GDPR, HIPAA or any other regulation
> (PROMPT.md §47). Items marked **NOT VERIFIED — requires Azure credentials** are implemented
> and unit-tested with mocks but have not run against real Azure resources.

## 0. Summary: technical controls vs. decisions that need legal approval (PROMPT.md §47)

The system implements the technical controls below. It is **not** declared compliant with Law
151/2020, GDPR, HIPAA or any other regulation: compliance also depends on the organizational and
legal decisions in the second table, which nobody has taken yet.

| §47 control | Where it is implemented | Verified |
|---|---|---|
| Least privilege | one user-assigned identity with six data-plane roles, each on one resource (`role-assignments.bicep`); PostgreSQL app role is not an admin; deployer identities scoped to one resource group with a restricted RBAC-admin condition | Bicep build + guard; Azure NOT VERIFIED |
| Object-level authorization | doctor querysets scoped to the requesting doctor; `IsAdmin` on admin endpoints; another doctor's id → 404 | IDOR tests per resource (§2) |
| HTTPS | SWA HTTPS only, Container Apps ingress `allowInsecure=false`, Django HTTPS redirect + HSTS, PostgreSQL `require_secure_transport`, storage HTTPS only / TLS 1.2 | `check --deploy`, guard |
| Private Blob containers | `allowBlobPublicAccess=false`, container `publicAccess=None`, shared keys disabled | guard + tests |
| Short-lived document URLs | authorized stream by default; user-delegation SAS read-only, one blob, ≤ 300 s | `test_storage.py` |
| Secure cookies | `HttpOnly`, `Secure`, `SameSite=Lax`, idle 2 h / absolute 12 h, session bound to the role | production settings tests |
| Security headers | API CSP `default-src 'none'`, nosniff, `Referrer-Policy`, COOP, `X-Frame-Options: DENY`; SWA CSP | live checks (Session 9) |
| Rate limiting | sign-in callback 20/min per client address, uploads 60/h, OCR 30/h per user; shared cache | throttle tests |
| Audit logs | append-only `AuditLog` (database trigger) for every action in §39 + national-ID reveals | audit tests |
| Environment separation | separate resource groups, identities, Key Vaults, Entra app registrations, GitHub environments | docs + scripts; Azure NOT VERIFIED |
| Backups | PostgreSQL PITR (7/14/35 days), geo-redundant backup in prod, Blob soft delete + versioning, Key Vault soft delete + purge protection | Bicep; restore drill NOT DONE (needs Azure) |
| Restricted production access | no shared or stored credentials; deploys only from `main` with reviewers for prod; operators named by decision L7 | NOT VERIFIED |
| No personal data in logs | 14+ digit masking filter, no bodies/headers/query strings, OCR payloads never logged | logging + telemetry tests |

| Decision that needs legal / organizational approval (§47) | Current technical default | Item |
|---|---|---|
| Religion field: collect it at all, who sees it, printed or not | collected (optional), visible to the doctor and admins | L1 |
| OCR processing of identity documents by an AI service | `OCR_ENABLED=false` in production | L2 |
| Data residency / region and cross-border transfer | region is a deployment parameter; not chosen | L3 |
| Retention periods and deletion on request | nothing deleted automatically except orphan / soft-deleted blobs and expired sessions | L4 |
| Admin access policy (who, MFA, reviews, unmasked printouts) | `grant_admin` by an operator; MFA required; reveals audited | L5 |
| Breach procedure | not defined | L6 |
| Production access (subscription, database, Key Vault, break-glass) | not defined beyond the CI/CD identities | L7 |
| Malware scanning of uploads | off (`MALWARE_SCAN_ENABLED=false`), `scan_status` ready | L8 |

Details of each decision: §6.

## 1. Data handled

Sensitive personal information (PROMPT.md §47): national IDs (members and beneficiaries),
syndicate registration data, addresses, phone numbers, e-mail, **religion**, family relationships
and birth years, identity-document images, personal photos and payment receipts.

| Where | What | Protection |
|---|---|---|
| Azure Database for PostgreSQL | all structured data, document *metadata*, audit log | TLS required (`DB_SSLMODE=require`+), Entra auth with managed identity (no password), Azure-internal firewall or VNet integration (`enablePrivateNetworking`) |
| Azure Blob Storage (private container) | document and photo files | no public access, no shared keys, managed identity, read SAS ≤ 5 min for one blob, soft delete + versioning |
| Key Vault | Django `SECRET_KEY`, Entra client secret, DB password (fallback only) | RBAC, managed identity, soft delete + purge protection |
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
  session requires `amr` to contain `mfa` (`ENTRA_ADMIN_REQUIRE_MFA=true`, Q-T7). The session is
  bound to the role (`User.get_session_auth_hash`), so granting or revoking ADMIN ends that
  user's open sessions: a session that never passed the MFA check cannot become an admin one.
- Object-level authorization on every endpoint; doctor querysets are scoped to the requesting
  doctor; protected fields (`status`, `payment_status`, `reference_number`, `fee_snapshot`,
  reviewer fields, …) are read-only for doctors and covered by tests. Status changes go through
  one transition service with row locks and audit entries.
- `DEV_AUTH_ENABLED` exists only in development/test settings; production settings refuse to
  import (the container does not start) when it is set.
- Rate limits (DRF scoped throttles): sign-in callback 20/min per client address, uploads 60/h
  and OCR 30/h per user; counters in a cache shared by all replicas (Q-T6). The client address
  is the `X-Forwarded-For` entry added by the trusted proxies only (`TRUSTED_PROXY_COUNT`: 2 in
  Azure = SWA linked backend + Container Apps ingress, 0 locally = header ignored), never the
  client-sent part; the audit log hashes the same address.

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
  minimum dimensions, server-generated blob names, sanitized display names. A request whose
  `Content-Length` exceeds `MAX_UPLOAD_BYTES` + 256 KB is refused with 413 before the body is
  read (`RequestBodyLimitMiddleware`); smaller multipart bodies above 2 MB are streamed to a
  temporary file, non-file bodies are capped at 2 MB.
- Document delivery: JPEG/PNG/WebP are sent `inline`, everything else (PDF, HEIC) as an
  `attachment` (stream and SAS alike), always with `X-Content-Type-Options: nosniff`, a
  `default-src 'none'; sandbox` CSP and `X-Frame-Options: DENY`. The admin viewer shows images
  and offers a download for anything else; no uploaded file is ever framed (SWA CSP
  `frame-src 'none'`).
- The SPA production build publishes no source maps.
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
- Expired sessions (user ids, OIDC flow state) are deleted by the scheduled cleanup job
  (`entrypoint.sh cleanup` runs `clearsessions` before `cleanup_blobs`).
- Audit log (append-only table) for submissions, status and payment changes, document
  uploads/views/deletions, OCR requests (field names only), admin views, notes, fee-schedule
  changes, admin grants and every reveal of a full national ID.

## 5. Azure integration controls

| Control | Implementation | Status |
|---|---|---|
| One managed identity for every Azure call | `config/azure.py` (`DefaultAzureCredential`, `AZURE_CLIENT_ID` selects the user-assigned identity; `AZURE_TOKEN_CREDENTIALS=prod` in Azure) | NOT VERIFIED — requires Azure credentials |
| Blob access + user-delegation SAS | `apps/documents/storage.py`; delegation key cached 1 h; SAS read-only, one blob, ≤ 300 s, content type/disposition pinned. Roles: Storage Blob Data Contributor + Storage Blob Delegator | NOT VERIFIED — requires Azure credentials |
| Key Vault secrets | `config/secrets.py`; environment (Container Apps Key Vault references) wins; names `django-secret-key`, `entra-client-secret`, `database-password`; role Key Vault Secrets User | NOT VERIFIED — requires Azure credentials |
| PostgreSQL Entra auth | `config/db/entra_postgres` — fresh token per new connection (cached until 5 min before expiry), TLS enforced, `CONN_MAX_AGE` ≤ 1800 s; `DB_AUTH_MODE=password` fallback | NOT VERIFIED — requires Azure credentials |
| Azure OpenAI OCR | managed identity bearer tokens, no API key, structured outputs, no payload logging | NOT VERIFIED — requires Azure credentials |

### 5.1 Infrastructure controls (Session 8, Bicep + CI/CD)

| Control | Implementation | Status |
|---|---|---|
| Template security guard | `infrastructure/scripts/check-template-security.py` runs in `infrastructure.yml` on the compiled `main.json`: storage (no public blob access, no shared keys, OAuth default, TLS 1.2, HTTPS only, private container), Key Vault (RBAC, soft delete, purge protection), PostgreSQL (Entra auth, password auth off by default, `require_secure_transport`, TLS 1.2), registry (no admin, no anonymous pull), OpenAI (no local auth), ingress (no HTTP), no secure parameter default, no secret-looking output; `--self-test` breaks each rule and checks that the guard fails | 0 problems, self-test 20/20 |
| No secrets in templates or Git | Key Vault secrets set out of band (`az keyvault secret set --file`, `create-entra-app` writes `entra-client-secret` without printing it); parameter files read tenant/principal ids from environment variables; no template output contains a secret or deployment token | build/lint verified |
| Key Vault | RBAC mode, soft delete, purge protection, audit logs to Log Analytics; app identity has *Key Vault Secrets User* on that vault only | NOT VERIFIED — requires Azure credentials |
| Blob Storage | `allowBlobPublicAccess=false`, **`allowSharedKeyAccess=false`**, OAuth default, TLS 1.2, HTTPS only, private container, soft delete + versioning, audit logs; *Blob Data Contributor* on the container only, *Blob Delegator* on the account (user-delegation SAS) | NOT VERIFIED — requires Azure credentials |
| PostgreSQL | Entra authentication, password authentication disabled, `require_secure_transport=on`, `ssl_min_protocol_version=TLSv1.2`, firewall = Azure services only (MVP) or VNet integration without public access; app role created with `pgaadauth_create_principal_with_oid`, not an admin, `CONNECT/CREATE/TEMP` + schema `public` only | SQL verified on local PostgreSQL 16; Azure NOT VERIFIED |
| Container Registry / Container Apps | no admin user, no anonymous pull, AcrPull via identity; HTTPS-only ingress; non-root image; probes; single-revision mode | NOT VERIFIED — requires Azure credentials |
| Azure OpenAI | deployed only with `enableOcr`; `disableLocalAuth=true`; *Cognitive Services OpenAI User* on that account only | NOT VERIFIED — requires Azure credentials |
| Static Web App | Standard + linked backend (same origin); `staticwebapp.config.json`: strict CSP (no inline/eval script, `frame-ancestors 'none'`, Google Fonts only external origin), HSTS, nosniff, `X-Frame-Options: DENY`, COOP, Permissions-Policy; PR preview environments disabled | CSP checked in Chromium against the production build (landing, doctor form with thumbnails, admin detail + viewer: no violation); SWA itself NOT VERIFIED |
| GitHub → Azure | OIDC federated credentials, no stored passwords or SWA tokens. Two trust levels per environment: `<env>` (deploy; GitHub environment restricted to `main`, reviewers for prod) and `<env>-plan` (pull requests / what-if only; Reader + a custom validate/what-if role). Deployer roles scoped to the resource group: custom *Deployer* (Contributor minus managed-identity federated-credential writes and storage key/SAS listing), AcrPush, RBAC Administrator with an ABAC condition limited to the six app roles **and the app identity's principal id** (it cannot grant itself or any other principal data access). `setup-github-oidc` verifies with `gh` that the deploy environment accepts protected branches only (reviewers for prod) before trusting it. Actions pinned to commit SHAs; `permissions: contents: read` by default. Residual: a deployer can run code as the app identity and reconfigure resources (Azure Policy deny rules not written yet, §7) | actionlint + shellcheck clean; NOT VERIFIED on GitHub/Azure |
| Private networking (optional) | `enablePrivateNetworking`: VNet-integrated Container Apps and PostgreSQL, private endpoints + DNS for Blob, Key Vault, OpenAI, public access disabled | build verified; NOT VERIFIED — requires Azure credentials |

## 6. Decisions requiring legal / organizational approval

| # | Decision | Current default | Owner |
|---|---|---|---|
| L1 | **Religion field.** The paper form asks for religion; it is sensitive data. Is collecting it necessary and lawful, who may see it, and must it be on the printed form? | Collected (optional in the API), shown to the doctor and admins, OCR may suggest it | Legal + syndicate management |
| L2 | **OCR by an AI service.** Sending identity-document images to Azure OpenAI (abuse monitoring may retain them up to 30 days unless modified abuse monitoring is approved). | `OCR_ENABLED=false` in production until approved; manual entry always works | Legal / DPO |
| L3 | **Data residency / region.** There is no Azure region in Egypt; choose the region(s) for PostgreSQL, Blob, Key Vault, Log Analytics and Azure OpenAI, and confirm cross-border transfer requirements under Law 151/2020. | Not chosen (Q-T1); Bicep will parameterize the region | Legal + IT |
| L4 | **Retention periods** for applications, documents, rejected/withdrawn applications, audit logs, telemetry (Log Analytics retention) and backups; deletion on request. | Nothing is deleted automatically except orphan/soft-deleted blobs (`cleanup_blobs`) | Legal + syndicate management |
| L5 | **Admin access policy:** who may be granted the admin role, MFA, periodic access review, who may reveal full national IDs (audited) and print unmasked forms (Q-B20). | `grant_admin` by an operator with production access; reveal is audited | Syndicate management + IT |
| L6 | **Breach procedure:** detection (Application Insights alerts, audit review), containment (revoke sessions, rotate Key Vault secrets, disable OCR/uploads by flag), notification duties and timelines, contacts. | Not defined | Legal / DPO + IT |
| L7 | **Production access:** who may access the Azure subscription, database and Key Vault; break-glass accounts; separation of environments (§49). | Separate resource groups, identities, Key Vaults and Entra app registrations per environment (Bicep parameters, `setup-github-oidc`) | IT |
| L8 | **Malware scanning** of uploads (Microsoft Defender for Storage malware scanning). | `scan_status` field exists, scanning off (`MALWARE_SCAN_ENABLED=false`) | IT (cost decision) |

## 7. Known gaps (tracked in docs/progress.md)

- Shared cache for rate limits across replicas: resolved in Session 8 (`CACHE_URL=dbcache://django_cache`,
  table created by the migrate job).
- Entra External ID claims (`email`, `amr`) not verified against a real tenant (Q-T7).
- Network isolation is implemented behind `enablePrivateNetworking` (off by default, MVP per §34);
  Defender for Storage/Cloud, alerts and the first restore drill remain operational tasks.
- Container Apps ingress is public so the Static Web Apps linked backend can reach it; users could
  call the Container App FQDN directly (same Django controls apply; cookies are scoped to the SWA
  host). Restricting ingress to the SWA is NOT VERIFIED (Q-T13).
- PostgreSQL without `enablePrivateNetworking` keeps the "Azure services" firewall rule
  (0.0.0.0): any Azure-hosted client, of any tenant, can open a TCP connection; sign-in still
  needs an Entra token mapped to a database role (password authentication off). Recommended for
  production: `ENABLE_PRIVATE_NETWORKING=true` (§5.1). Accepted for the MVP (PROMPT.md §34).
- Azure Policy deny rules for the deployer identity are not written: they need a subscription to
  test. The template guard checks the same properties at build time.
- Client address: `TRUSTED_PROXY_COUNT=2` assumes the SWA linked backend and the Container Apps
  ingress each append one `X-Forwarded-For` entry (Q-T13, NOT VERIFIED). A caller that reaches
  the Container App FQDN directly (Q-T18) can choose its own throttle bucket.

## 8. Session 9 security review

Scope (docs/plan.md Task 9.3): authentication and sessions, CSRF, object-level authorization,
protected fields, uploads, SAS scope and expiry, logging of personal data, secrets, rate limits,
production headers and cookies, Bicep, dependencies. Reviewed by reading the code, then proving
each finding with a failing test before fixing it. The `security-review` skill could not run here
(it needs a git remote; this repository has none, by design).

| Id | Severity | Finding | Fix (test) |
|---|---|---|---|
| F1 | Medium | `NUM_PROXIES` unset: DRF keyed anonymous throttles on the **whole** `X-Forwarded-For` header, so a new fake header per request bypassed the sign-in callback limit; the audit log hashed the client-sent first entry | `TRUSTED_PROXY_COUNT` → `NUM_PROXIES` (0 base, 2 production and Bicep); `apps/common/client_ip.py` shared with the audit log (`apps/common/tests/test_client_ip.py`: spoofed headers now get `[302, 302, 429]` and one audit hash) |
| F2 | Medium | Admin MFA is checked at sign-in only; a doctor session opened without MFA became an admin session when `grant_admin` promoted the user | role mixed into the session auth hash, so a role change ends open sessions (`test_grant_admin.py::test_granting_admin_ends_the_users_existing_sessions`, `::test_revoking_admin_ends_the_users_existing_sessions`). One-time effect: every user is signed out once after this deployment |
| F3 | Medium | Upload size was enforced after Django had parsed (and spooled to the replica's disk) the whole body: any signed-in doctor could send gigabytes | `RequestBodyLimitMiddleware` → 413 `FILE_TOO_LARGE` from `Content-Length` before reading (`config/tests/test_middleware.py`; the production image answers a declared 2 GiB body with 413 at once) |
| F4 | Low | Expired database sessions were never deleted (user ids, PKCE verifier, nonce) | the cleanup job runs `clearsessions` (production image: 107 expired → 0, live sessions kept; `--dry-run` deletes nothing) |
| F5 | Low | Q-T17: the admin PDF viewer framed `/content/`, which every environment answers with `X-Frame-Options: DENY` and a `sandbox` CSP, so PDFs could not be shown | nothing is framed: non-image documents are attachments and the viewer offers a download (`DocumentViewer.test.tsx`, `test_pdf_content_is_a_download_never_framed`, `test_sas_for_a_pdf_downloads_it`); SWA `frame-src 'none'` |
| F6 | Low | The production bundle published source maps (the full commented source) | `build.sourcemap = false`; `dist/` has 0 `.map` files |
| F7 | Low (availability) | In Entra DB mode every process start still read `database-password` from Key Vault; a Key Vault error stopped replicas | read only in password mode (`test_entra_mode_with_injected_secrets_never_calls_key_vault`) |
| F8 | Info | pytest 8.4.2 (dev only): PYSEC-2026-1845 | `pytest>=9.0.3,<10`; 960 tests green on 9.1.1 |

Checked and found sound: OIDC (PKCE/state/nonce through MSAL, independent RS256 + iss/aud/exp/
nonce/tid validation, (oid, tid) mapping, no e-mail takeover, flow consumed before use, session id
rotated at sign-in, safe `next`), CSRF on every unsafe method (DRF session auth, login CSRF on the
dev login), dev auth answers 404 in production (checked live), querysets scoped on every doctor
endpoint and `IsAdmin` on every admin endpoint (IDOR tests per resource), protected fields, SAS
(read-only, one blob, ≤ 300 s, user delegation), content sniffing and decompression-bomb limits,
server-generated blob names, logging (fixed messages, 14+ digit masking in messages, extras and
tracebacks, Gunicorn access log off), production cookies and headers (checked live), no XSS sinks
or browser storage in the SPA, SWA CSP `connect-src 'self'`, dependency audits clean, gitleaks
clean, Bicep security properties (now guarded in CI).
