# Architecture

Production target: everything on Microsoft Azure. The browser talks to one origin (Azure Static Web
Apps); `/api/*` is proxied to Django on Azure Container Apps through the SWA **linked backend**, so
the HttpOnly session cookie is first-party. Django is the only component that touches PostgreSQL,
Blob Storage, Key Vault and Azure OpenAI, always through a user-assigned managed identity.

## 1. Azure target architecture

```mermaid
flowchart TB
    subgraph Users
        D[Doctor browser]
        A[Admin browser]
    end

    subgraph Azure["Azure (one resource group per environment)"]
        SWA["Azure Static Web Apps (Standard)<br/>React + TS + Vite + Tailwind<br/>Arabic RTL SPA"]
        ACA["Azure Container Apps<br/>Django + DRF + Gunicorn<br/>BFF: session cookies"]
        JOB_M["Container Apps Job<br/>migrate (once per deploy)"]
        JOB_C["Container Apps Job<br/>blob cleanup (scheduled)"]
        PG[("Azure Database for PostgreSQL<br/>Flexible Server<br/>Entra auth, TLS")]
        BLOB[("Blob Storage<br/>private container<br/>soft delete + versioning")]
        KV["Key Vault<br/>SECRET_KEY, Entra client secret"]
        AOAI["Azure OpenAI<br/>vision model (OCR, optional, flag)"]
        AI["Application Insights<br/>+ Log Analytics"]
        ACR["Container Registry"]
        MI["User-assigned managed identity"]
    end

    ENTRA["Microsoft Entra External ID<br/>sign-up / sign-in / MFA (admins)"]
    GH["GitHub Actions (OIDC federated)"]

    D & A -- HTTPS --> SWA
    SWA -- "/api/* linked backend (same origin)" --> ACA
    ACA <-- "OIDC code flow + PKCE" --> ENTRA
    ACA --> PG
    ACA --> BLOB
    ACA --> KV
    ACA -. "if OCR_ENABLED" .-> AOAI
    ACA --> AI
    JOB_M --> PG
    JOB_C --> BLOB & PG
    MI -. "Blob Data Contributor · KV Secrets User · AcrPull · OpenAI User · PG Entra role" .-> ACA
    ACR --> ACA & JOB_M & JOB_C
    GH -- "frontend.yml" --> SWA
    GH -- "backend.yml: build → ACR → migrate job → revision" --> ACR
    GH -- "infrastructure.yml: bicep what-if / deploy" --> Azure
```

**Same-origin decision (PROMPT.md §4.1, option 1):** SWA Standard with the Container App as linked
backend. The SPA calls relative `/api/v1/...`; cookies are `HttpOnly; Secure; SameSite=Lax`. Fallback
(option 2, custom domains on one registrable domain) is documented in `docs/azure-deployment.md`
but not the default. Locally the Vite dev-server proxies `/api` to Django, same effect.

**Hard rules honoured:** PostgreSQL is a managed service, never a container; documents live in Blob,
never in the container filesystem or PostgreSQL; OCR is never called from the browser.

## 2. Application layers

```mermaid
flowchart LR
    subgraph SPA["frontend/ (React + TypeScript)"]
        PAGES[pages/ routes §8] --> FEAT[features/*]
        FEAT --> COMP[components/form + ui]
        FEAT --> API[api/ typed client<br/>CSRF header, error envelope]
        FEAT --> I18N[i18n/ar.ts]
        API --> TQ[TanStack Query cache]
    end

    subgraph Django["backend/ (Django + DRF)"]
        VIEWS[views + serializers<br/>authn, authz, read-only fields] --> SVC[services.py per app<br/>business logic]
        SVC --> FEES[fees/services.py<br/>authoritative fee engine]
        SVC --> VAL[applications/validation.py<br/>authoritative validation]
        SVC --> TRANS[applications/services.py::transition<br/>status table + select_for_update]
        SVC --> RULES[reference/document_rules.py<br/>reference/national_id.py]
        SVC --> STOR[documents/storage.py<br/>Blob abstraction, Azurite locally]
        SVC --> OCR[ocr/providers.py<br/>Mock · AzureOpenAI]
        SVC --> AUD[audit/services.py<br/>append-only log]
    end

    API -- "/api/v1 JSON, snake_case" --> VIEWS
```

The frontend owns presentation only. Fees, validation, status transitions, document rules and
reference data are computed on the server and fetched; the SPA never duplicates them.

## 3. Key request flows

### 3.1 Sign-in (BFF, Entra External ID)

```mermaid
sequenceDiagram
    participant B as Browser (SPA)
    participant S as SWA (/api proxy)
    participant DJ as Django (accounts.auth.oidc)
    participant E as Entra External ID
    B->>S: GET /api/v1/auth/login/?next=/dashboard
    S->>DJ: proxy
    DJ->>DJ: create state, nonce, PKCE verifier (server session)
    DJ-->>B: 302 to Entra authorize URL
    B->>E: sign-up / sign-in (hosted Arabic pages, MFA for admins)
    E-->>B: 302 /api/v1/auth/callback/?code&state
    B->>DJ: GET callback
    DJ->>E: exchange code (+ client secret from Key Vault, PKCE)
    E-->>DJ: id_token
    DJ->>DJ: validate signature, iss, aud, nonce, exp; map by (oid, tid); refuse admin without amr=mfa
    DJ-->>B: Set-Cookie sessionid (HttpOnly, Secure, Lax) + 302 next
    B->>DJ: GET /api/v1/auth/me/ → user, role, CSRF token
```

Browser never holds tokens. `DEV_AUTH_ENABLED` replaces Entra only in development/test settings.

### 3.2 Upload → OCR suggestion → autosave

```mermaid
sequenceDiagram
    participant B as Browser
    participant DJ as Django
    participant BL as Blob (Azurite locally)
    participant O as OCR provider
    B->>DJ: POST /applications/{id}/documents/ (multipart, document_type)
    DJ->>DJ: authz (owner, editable) · sniff type · size · Pillow decode · dims · sha256
    DJ->>BL: upload applications/{app}/doctor/national-id-front-{uuid}.jpg
    DJ-->>B: DocumentSummary (id, type, thumbnail URL ≤5 min)
    B->>DJ: POST /documents/{id}/extract/
    DJ->>DJ: rate limit (30/h/user) · OCR_ENABLED
    DJ->>BL: read bytes (managed identity)
    DJ->>O: image + Arabic prompt → JSON schema
    O-->>DJ: raw fields
    DJ->>DJ: normalizers (digits, ID, year, triple name) → enums
    DJ-->>B: suggestions (nothing saved)
    B->>B: merge into EMPTY fields only
    B->>DJ: PATCH /applications/{id}/ (debounced autosave)
    DJ-->>B: 200 → B refetches GET /applications/{id}/fees/
```

### 3.3 Submission

```mermaid
sequenceDiagram
    participant B as Browser
    participant DJ as Django (applications.services.submit)
    participant PG as PostgreSQL
    B->>DJ: POST /applications/{id}/submit/
    DJ->>PG: BEGIN · SELECT application FOR UPDATE
    DJ->>DJ: status in (DRAFT, NEEDS_CORRECTION)? else INVALID_STATUS_TRANSITION
    DJ->>DJ: validate_for_submission → all errors (422 VALIDATION_ERROR if any)
    DJ->>DJ: fee engine → fee_snapshot + fee_schedule_id
    DJ->>PG: first submission: SELECT reference_counter FOR UPDATE, +1 → MED-2026-000123
    DJ->>PG: status=SUBMITTED, submitted_snapshot, submitted_at · AuditLog
    DJ->>PG: COMMIT
    DJ-->>B: application with reference_number
```

## 4. Data model (summary; full ER diagram in `docs/database.md`)

```mermaid
erDiagram
    USER ||--o| DOCTOR : "1:1"
    DOCTOR ||--o{ INSURANCE_APPLICATION : "1:*"
    FEE_SCHEDULE ||--o{ INSURANCE_APPLICATION : "snapshot from"
    INSURANCE_APPLICATION ||--o{ BENEFICIARY : "1:* (row_number ≤ MAX)"
    INSURANCE_APPLICATION ||--o{ DOCUMENT : "1:*"
    BENEFICIARY ||--o{ DOCUMENT : "0..*"
    INSURANCE_APPLICATION ||--o{ ADMIN_NOTE : "1:*"
    USER ||--o{ AUDIT_LOG : "actor"
    REFERENCE_COUNTER {
        int fiscal_year PK
        int last_sequence
    }
    DOCTOR {
        uuid id PK
        string national_id UK
        enum gender
        enum religion
    }
    INSURANCE_APPLICATION {
        uuid id PK
        int fiscal_year
        enum status
        enum payment_status
        string reference_number UK
        json fee_snapshot
        json submitted_snapshot
    }
    DOCUMENT {
        uuid id PK
        enum document_type
        string blob_name
        string sha256
        enum scan_status
        datetime deleted_at
    }
```

Constraints that carry business rules: `Doctor.national_id` unique; partial unique
`(doctor, fiscal_year) WHERE status <> 'REJECTED'`; unique `(application, national_id)` on
beneficiaries; unique `(application, row_number)`; one active document per
`(application, beneficiary, document_type)`; `ON DELETE PROTECT` on everything audit-relevant.

## 5. Environments and local development

```mermaid
flowchart LR
    subgraph Local["docker compose + Vite"]
        V[Vite dev server :5173<br/>proxy /api → :8000] --> DJL[Django :8000<br/>development settings<br/>DEV_AUTH_ENABLED=true<br/>OCR_PROVIDER=mock]
        DJL --> PGL[(PostgreSQL 16 container)]
        DJL --> AZ[(Azurite blob emulator)]
    end
    Local -. "same code, different settings module + env" .-> Dev[Azure dev<br/>scale-to-zero, Burstable PG]
    Dev --> Staging --> Prod
```

Three Azure environments (`development`, `staging`, `production`) with separate resource groups,
identities, Key Vaults and Entra app registrations (or redirect URIs). Settings modules:
`config/settings/{base,development,test,production}.py`; configuration only via environment
variables / Key Vault references.

## 6. Security architecture (summary; details in `docs/security.md`)

- Authn: Entra External ID, BFF, PKCE, token validation, `(oid, tid)` mapping, MFA required for admins.
- Authz: Django-only; object-level checks on every endpoint; querysets scoped to the doctor;
  protected fields read-only on serializers; admin role granted via `manage.py grant_admin`.
- Data: private Blob container, ≤5-minute SAS or authorized stream, sha256, soft delete; national
  ID masked everywhere it is displayed or logged; logging filter masks 14-digit runs.
- Transport/config: HTTPS, HSTS, secure cookies, CSRF, security headers, CORS off in production,
  startup check refuses `DEV_AUTH_ENABLED` or missing settings in production.
- Secrets: Key Vault via managed identity; `.env.example` holds names only.
- MVP network posture: public ingress on SWA/ACA, PostgreSQL and Storage firewalls restricted to
  Azure services / ACA outbound, no public blob access. Upgrade path: VNet-integrated ACA
  environment + private endpoints (documented, parameterized in Bicep).

## 7. Deployment pipeline

```mermaid
flowchart LR
    PR[Pull request] --> CI1[frontend.yml: npm ci → lint → tsc → vitest → rtl_check → build]
    PR --> CI2[backend.yml: ruff → pytest on PostgreSQL service → docker build]
    PR --> CI3[infrastructure.yml: bicep build → what-if]
    main[merge to main] --> D1[SWA deploy]
    main --> D2[push image to ACR → run migrate job → update ACA revision]
    main --> D3[bicep deploy, prod needs environment approval]
```

GitHub OIDC federated credentials, no stored Azure passwords; GitHub environments `dev`, `staging`,
`prod` with required reviewers on `prod`.
