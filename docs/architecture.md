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
        SVC --> OCR[ocr/providers/<br/>mock · azure_openai]
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
    DJ->>DJ: validate signature, iss, aud, nonce, exp · map by (oid, tid) · refuse admin without amr=mfa
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
    DJ-->>B: DocumentSummary (id, type, size · bytes only via /documents/{id}/content/)
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
    DJ->>DJ: validate_for_submission → all errors (400 VALIDATION_ERROR if any)
    DJ->>DJ: fee engine → fee_snapshot + fee_schedule_id
    DJ->>PG: first submission only: SELECT reference_counter FOR UPDATE, +1 → MED-2026-000123
    DJ->>PG: lock the fee schedule version (locked_at)
    DJ->>PG: status=SUBMITTED, submitted_snapshot, submitted_at · AuditLog
    DJ->>PG: COMMIT
    DJ-->>B: application with reference_number
```

## 4. Data model (summary; columns, constraints and indexes in `docs/database.md`)

```mermaid
erDiagram
    USER ||--o| DOCTOR : "1:1"
    DOCTOR ||--o{ INSURANCE_APPLICATION : "1:* (one active per fiscal year)"
    FEE_SCHEDULE ||--o{ INSURANCE_APPLICATION : "version frozen at submission"
    INSURANCE_APPLICATION ||--o{ BENEFICIARY : "1:* (≤ MAX_BENEFICIARIES)"
    INSURANCE_APPLICATION ||--o{ DOCUMENT : "1:*"
    BENEFICIARY |o--o{ DOCUMENT : "0..* (null = member document)"
    INSURANCE_APPLICATION ||--o{ ADMIN_NOTE : "1:* (internal)"
    USER |o--o{ AUDIT_LOG : "actor"
    REFERENCE_COUNTER ||--o{ INSURANCE_APPLICATION : "MED-{fy}-{seq} at first submission"
```

All primary keys are UUIDs; every foreign key is `ON DELETE PROTECT`. Constraints that carry
business rules: `Doctor.national_id` unique; partial unique `(doctor, fiscal_year) WHERE status <>
'REJECTED'`; partial unique `(application, national_id)` on beneficiaries; unique
`(application, row_number)`; one live document per `(application, beneficiary, document_type)`
(`NULLS NOT DISTINCT`); reference number present exactly when the status is not `DRAFT`;
one active fee schedule per fiscal year; audit log append-only (database trigger).

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
- MVP network posture (`enablePrivateNetworking=false`, the default): public HTTPS ingress on
  SWA and the Container App (the linked backend needs it); PostgreSQL accepts only Azure-internal
  connections (firewall rule "Azure services") with Entra tokens over TLS and password
  authentication off; Blob Storage and Key Vault keep public endpoints but refuse anonymous and
  shared-key access (Entra RBAC only); Azure OpenAI has key authentication disabled. Upgrade
  path, one parameter: `enablePrivateNetworking=true` adds a VNet-integrated Container Apps
  environment, a VNet-integrated PostgreSQL server without public access and private endpoints +
  private DNS for Blob, Key Vault and Azure OpenAI (`docs/azure-deployment.md`, *Production
  upgrade path*).

## 7. Scaling (PROMPT.md §35)

Django scales on Container Apps independently of the static frontend: HTTP-concurrency rule
(`httpConcurrency` concurrent requests per replica), `minReplicas`/`maxReplicas` per environment
(dev 0–2, staging 1–3, prod 1–5), `containerCpu`/`containerMemory` and `gunicornWorkers` all in
`infrastructure/parameters/<env>.bicepparam`. Replicas are stateless: sessions and rate-limit
counters live in PostgreSQL, files in Blob Storage, secrets in Key Vault, so any replica can be
destroyed at any time. The migrate and cleanup jobs run in the same environment with the same
image and identity.

```text
              Container Apps ingress (HTTPS, load balancing)
                    │
         ┌──────────┼──────────┐
         ▼          ▼          ▼
      Django     Django     Django      (Gunicorn, non-root, no local state)
      replica    replica    replica
         └──────────┼──────────┘
                    ▼
     PostgreSQL + Blob + Key Vault + Azure OpenAI (managed identity)
```

## 8. Deployment pipeline

```mermaid
flowchart LR
    PR[Pull request] --> CI1[frontend.yml: npm ci → lint → tsc → vitest → rtl_check → build]
    PR --> CI2[backend.yml: ruff → check → migrations check → OpenAPI → pytest on PostgreSQL → docker build]
    PR --> CI3[infrastructure.yml: bicep build + lint → template guard, no Azure access]
    PR --> CI4[e2e.yml: compose stack + Playwright]
    main[merge to main] --> D1[SWA deploy dev → staging → prod]
    main --> D2[image → ACR → migrate job → cleanup job → new ACA revision → smoke test]
    main --> D3[bicep what-if + deploy dev → staging → prod]
```

GitHub OIDC federated credentials, no stored Azure passwords or deployment tokens. One GitHub
environment per Azure environment: `<env>` (deploy and manual what-if, `main` only, required
reviewers on `prod`). Pull requests get no Azure credential: ARM what-if needs write permission on
every resource, so a read-only preview identity is impossible (D145). Details: `docs/github-setup.md`.
