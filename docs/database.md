# Database

PostgreSQL 16 (Azure Database for PostgreSQL Flexible Server in Azure, the `postgres:16-alpine`
container locally). PostgreSQL ≥ 15 is required: the one-document-per-slot index uses
`NULLS NOT DISTINCT`. Tests also run on PostgreSQL, never SQLite.

Every primary key is a UUID. National IDs are business identifiers with unique constraints,
never keys. Every foreign key is `ON DELETE PROTECT`: nothing that the audit trail refers to can
be deleted by a cascade. Documents and beneficiaries are soft-deleted or detached by services,
not by the database.

The schema below was read from a migrated database (`pg_constraint`, `pg_indexes`) on 2026-10-06,
not only from the models.

## 1. Entity-relationship diagram

```mermaid
erDiagram
    accounts_user ||--o| doctors_doctor : "user_id (1:1)"
    doctors_doctor ||--o{ applications_insuranceapplication : "doctor_id"
    fees_feeschedule ||--o{ applications_insuranceapplication : "fee_schedule_id (frozen at submission)"
    accounts_user ||--o{ applications_insuranceapplication : "reviewed_by_id"
    applications_insuranceapplication ||--o{ beneficiaries_beneficiary : "application_id"
    applications_insuranceapplication ||--o{ documents_document : "application_id"
    beneficiaries_beneficiary |o--o{ documents_document : "beneficiary_id (null = member document)"
    accounts_user ||--o{ documents_document : "uploaded_by_id"
    applications_insuranceapplication ||--o{ applications_adminnote : "application_id"
    accounts_user ||--o{ applications_adminnote : "author_id"
    accounts_user |o--o{ audit_auditlog : "user_id (actor)"
    accounts_user |o--o{ fees_feeschedule : "created_by_id"

    accounts_user {
        uuid id PK
        varchar email UK "unique, also case-insensitive"
        varchar display_name "Entra name claim"
        varchar role "DOCTOR | ADMIN"
        varchar entra_oid "unique with entra_tid when set"
        varchar entra_tid
        bool is_active
        timestamptz date_joined
        timestamptz last_login
        varchar password "always unusable (Entra only)"
    }
    doctors_doctor {
        uuid id PK
        uuid user_id FK,UK
        varchar full_name
        varchar national_id UK "14 digits, nullable until entered"
        date date_of_birth "derived from national_id"
        smallint birth_year "derived"
        varchar gender "derived: MALE | FEMALE"
        varchar religion "sensitive (decision L1)"
        varchar phone_number
        varchar syndicate_type "HUMAN_MEDICINE | PHARMACY | DENTISTRY | VETERINARY"
        varchar sub_syndicate
        varchar syndicate_registration_number "indexed with syndicate_type, not unique"
        smallint syndicate_registration_year
        varchar treatment_card_number
        varchar governorate
        varchar neighborhood
        varchar address
        timestamptz created_at
        timestamptz updated_at
    }
    applications_insuranceapplication {
        uuid id PK
        uuid doctor_id FK
        smallint fiscal_year
        varchar application_type "FIRST_TIME | ADDITION"
        varchar work_status "WORKING | PENSIONER | DECEASED"
        varchar status "DRAFT … REJECTED"
        varchar payment_status "NOT_UPLOADED | PENDING_REVIEW | CONFIRMED | REJECTED"
        varchar reference_number UK "MED-YYYY-NNNNNN, null while DRAFT"
        varchar declaration_name
        timestamptz declaration_accepted_at
        jsonb fee_snapshot "server quote frozen at submission"
        uuid fee_schedule_id FK
        jsonb submitted_snapshot "member + beneficiaries as submitted"
        text review_notes "doctor-visible"
        uuid reviewed_by_id FK
        timestamptz reviewed_at
        timestamptz submitted_at "latest submission"
        timestamptz created_at
        timestamptz updated_at
    }
    applications_referencecounter {
        uuid id PK
        smallint fiscal_year UK
        int last_sequence "row-locked at first submission"
    }
    applications_adminnote {
        uuid id PK
        uuid application_id FK
        uuid author_id FK
        text body "internal, never on doctor endpoints"
        timestamptz created_at
    }
    beneficiaries_beneficiary {
        uuid id PK
        uuid application_id FK
        smallint row_number "1..20, unique per application"
        varchar kinship "MOTHER FATHER SON_MINOR SON_UNIVERSITY SON_GRADUATE DAUGHTER HUSBAND WIFE"
        varchar full_name
        smallint birth_year
        varchar national_id "optional; unique per application"
        timestamptz created_at
        timestamptz updated_at
    }
    documents_document {
        uuid id PK
        uuid application_id FK
        uuid beneficiary_id FK "null for member documents"
        varchar document_type
        varchar blob_name UK "server-generated path in the private container"
        varchar original_filename "sanitized, display only"
        varchar content_type "sniffed from the bytes"
        bigint file_size
        varchar sha256
        varchar scan_status "PENDING | CLEAN | INFECTED | SKIPPED"
        uuid uploaded_by_id FK
        timestamptz created_at
        timestamptz deleted_at "soft delete"
        timestamptz blob_purged_at "set by cleanup_blobs"
    }
    fees_feeschedule {
        uuid id PK
        smallint fiscal_year
        smallint version "unique per fiscal_year"
        jsonb tier_fees "tier -> member/spouse/child/grad_son/parent"
        jsonb tier_boundaries "[5, 10, 15]"
        int admin_fee_member_only "150"
        int admin_fee_with_beneficiaries "175"
        smallint age_cap_threshold "70"
        int age_cap_amount "500"
        smallint registration_year_min "1950"
        bool is_active "one active version per year"
        uuid created_by_id FK
        timestamptz created_at
        timestamptz locked_at "set when first used by a submission"
    }
    audit_auditlog {
        uuid id PK
        uuid user_id FK "null for system actions"
        varchar action
        varchar object_type
        uuid object_id
        timestamptz timestamp
        varchar ip_hash "keyed hash of the client address"
        jsonb metadata "ids and field names, never sensitive values"
    }
```

Django's own tables: `django_migrations`, `django_content_type`, `auth_permission`,
`auth_group`, `auth_group_permissions` (unused), `django_session` (server-side sessions, purged by
the cleanup job's `clearsessions`) and, in Azure, `django_cache` (shared rate-limit counters,
created by the migrate job with `createcachetable`; `CACHE_URL=dbcache://django_cache`). There is
no Django admin site (D27).

## 2. Constraints that carry business rules

Rules are enforced by the database first and handled as `IntegrityError` in the services
(concurrent requests cannot slip past a pre-check).

| Table | Constraint | Definition | Rule / API error |
|---|---|---|---|
| `doctors_doctor` | `uniq_doctor_national_id` | `UNIQUE (national_id)` | one member per national ID → 409 `DUPLICATE_NATIONAL_ID` |
| `doctors_doctor` | `doctor_national_id_format` | `national_id IS NULL OR national_id ~ '^[23][0-9]{13}$'` | Western digits only are stored |
| `doctors_doctor` | `doctors_doctor_user_id_key` | `UNIQUE (user_id)` | one member profile per user |
| `accounts_user` | `uniq_user_email`, `uniq_user_email_ci` | `UNIQUE (email)`, `UNIQUE (lower(email))` | no account takeover by e-mail case |
| `accounts_user` | `uniq_user_entra_identity` | `UNIQUE (entra_oid, entra_tid) WHERE entra_oid IS NOT NULL` | users mapped by Entra `oid` + `tid` |
| `applications_insuranceapplication` | `uniq_active_application_per_year` | `UNIQUE (doctor_id, fiscal_year) WHERE status <> 'REJECTED'` | one active application per doctor per year → 409 `ACTIVE_APPLICATION_EXISTS`; a rejected applicant may start again |
| `applications_insuranceapplication` | `app_reference_number_iff_submitted` | DRAFT ⇔ `reference_number IS NULL`; otherwise `^MED-[0-9]{4}-[0-9]{6}$` | the number exists from the first submission on, never on create |
| `applications_insuranceapplication` | `applications_insuranceapplication_reference_number_key` | `UNIQUE (reference_number)` | numbers are never reused |
| `applications_insuranceapplication` | `app_status_valid`, `app_payment_status_valid`, `app_type_valid`, `app_work_status_valid` | `CHECK (… IN (…))` | enums |
| `applications_referencecounter` | `…_fiscal_year_key` | `UNIQUE (fiscal_year)` | one sequence per year (`SELECT … FOR UPDATE`) |
| `beneficiaries_beneficiary` | `uniq_beneficiary_national_id_per_application` | `UNIQUE (application_id, national_id) WHERE national_id IS NOT NULL` | no duplicate family member → 400 `VALIDATION_ERROR` |
| `beneficiaries_beneficiary` | `uniq_beneficiary_row` | `UNIQUE (application_id, row_number)` | paper-form rows |
| `beneficiaries_beneficiary` | `beneficiary_row_number_range` | `row_number BETWEEN 1 AND 20` | hard ceiling; the business limit is `MAX_BENEFICIARIES` (10) in the service |
| `beneficiaries_beneficiary` | `beneficiary_national_id_format`, `beneficiary_kinship_valid` | `CHECK` | format, enum |
| `documents_document` | `uniq_active_document_per_slot` | `UNIQUE (application_id, beneficiary_id, document_type) NULLS NOT DISTINCT WHERE deleted_at IS NULL` | one live document per slot; re-upload replaces |
| `documents_document` | `uniq_document_blob_name` | `UNIQUE (blob_name)` | one row per blob |
| `documents_document` | `document_type_matches_owner` | member types only without beneficiary, beneficiary types only with one (`OTHER` either), unless deleted | document rules table cannot be bypassed |
| `documents_document` | `document_scan_status_valid` | `CHECK` | enum |
| `fees_feeschedule` | `uniq_fee_schedule_version` | `UNIQUE (fiscal_year, version)` | versioned schedules |
| `fees_feeschedule` | `uniq_active_fee_schedule_per_year` | `UNIQUE (fiscal_year) WHERE is_active` | exactly one active version per year |
| `accounts_user` | `user_role_valid` | `CHECK (role IN ('DOCTOR','ADMIN'))` | roles |
| `audit_auditlog` | trigger `audit_auditlog_append_only` | `BEFORE UPDATE OR DELETE` raises | append-only at database level (also refused in `AuditLog.save/delete`) |

A locked fee schedule (`locked_at` set) refuses changes to its amounts in `FeeSchedule.save`;
only `is_active` may change, so a submitted application's `fee_schedule` never moves.

## 3. Indexes for queries

| Index | Columns | Used by |
|---|---|---|
| `app_status_submitted_idx` | `(status, submitted_at)` | admin list filtered by status, ordered by date |
| `app_year_status_idx` | `(fiscal_year, status)` | admin stats and fiscal-year filter |
| `app_payment_status_idx` | `(payment_status)` | "receipts waiting for confirmation" |
| `…_reference_number_08e636e4_like` | `reference_number varchar_pattern_ops` | admin search by reference prefix |
| `doctor_syndicate_regno_idx` | `(syndicate_type, syndicate_registration_number)` | lookup; deliberately not unique (business question 10) |
| `beneficiary_national_id_idx` | `(national_id) WHERE national_id IS NOT NULL` | admin duplicate warnings across applications |
| `document_deleted_idx` | `(deleted_at) WHERE deleted_at IS NOT NULL` | `cleanup_blobs` |
| `adminnote_app_created_idx` | `(application_id, created_at)` | notes timeline |
| `audit_object_idx` | `(object_type, object_id, timestamp)` | audit history of an application |
| `audit_action_idx`, `audit_user_idx` | `(action, timestamp)`, `(user_id, timestamp)` | audit review |

Plus Django's index on every foreign key. Admin lists are always paginated (25 per page, max 100).

## 4. JSON columns

| Column | Content |
|---|---|
| `fee_snapshot` | `FeeQuote.as_dict()` from `apps/fees/services.py`: `fiscal_year`, `tier`, `breakdown` (`label`, `fee`, `note`), `admin_fee`, `total`, `is_valid`, `error_message`, `schedule_id`. Written only by the submit service. |
| `submitted_snapshot` | member and beneficiary data as submitted (audit and printing), refreshed on resubmission |
| `tier_fees` | `{"1": {"member": 600, "spouse": 800, "child": 500, "grad_son": 1200, "parent": 1050}, …}` whole pounds, validated on save |
| `audit_auditlog.metadata` | ids, status values, changed field names; never national IDs, names, tokens or document content |

Money is stored as whole Egyptian pounds (integers), never floats.

## 5. Sensitive columns (PROMPT.md §47)

`doctors_doctor.national_id`, `religion`, `phone_number`, `address`, `date_of_birth`;
`beneficiaries_beneficiary.national_id`, `full_name`, `birth_year`; the `submitted_snapshot`
copies of the same; document metadata (the files themselves are in Blob Storage, never in
PostgreSQL). Admin API responses mask national IDs (`29•••••••••123`) unless a reviewer reveals
one (audited `NATIONAL_ID_REVEALED`). Logs never contain them (masking filter).

## 6. Migrations

26 migrations on a clean database: 11 project migrations plus Django's `contenttypes`, `auth` and
`sessions`.

| App | Migrations |
|---|---|
| accounts | `0001_initial`, `0002_user_display_name` |
| doctors | `0001_initial` |
| fees | `0001_initial`, `0002_seed_fy2026` (FY 2026 schedule, version 1, active) |
| applications | `0001_initial` |
| beneficiaries | `0001_initial` |
| documents | `0001_initial`, `0002_document_blob_purged_at` |
| audit | `0001_initial`, `0002_append_only_trigger` |

Commands:

```bash
docker compose exec backend python manage.py makemigrations          # after a model change
docker compose exec backend python manage.py makemigrations --check --dry-run   # CI: no missing migration
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py showmigrations
```

Rules (PROMPT.md §37, `django-safe-migration`):

- Migrations run **once per deployment** in the Container Apps `migrate` job, before the new
  revision gets traffic. Replicas never migrate (`entrypoint.sh web` refuses
  `RUN_MIGRATIONS_ON_START`). Locally the compose container migrates on start for convenience.
- The previous revision keeps serving while the job runs, so every migration is backward
  compatible: **expand** (new nullable column / table / index), deploy code that uses it,
  **contract** (drop the old column) in a later release. Example in this repo:
  `documents.0002_document_blob_purged_at` adds a nullable column only.
- New indexes on large tables: `AddIndexConcurrently` in a non-atomic migration. `NOT NULL`
  columns: `db_default`. Foreign keys on large tables: `NOT VALID` then `VALIDATE`.
- Never edit an applied migration; fix forward. Rollback = previous image on the newer schema
  (`docs/azure-deployment.md`, *Rolling back*), not `migrate <app> <previous>`.

## 7. Connection and authentication

- Local: `DATABASE_URL=postgres://medical:medical@postgres:5432/medical`, `DB_SSLMODE=prefer`.
- Azure: `DB_AUTH_MODE=entra` — `config/db/entra_postgres` requests a Microsoft Entra access token
  for the user-assigned managed identity as the password of every new connection (cached until
  5 minutes before expiry); `sslmode=require` or stricter is enforced by production settings and
  `CONN_MAX_AGE` is capped at 1800 s. Password authentication is disabled on the server by
  default; `DB_AUTH_MODE=password` (secret `database-password` in Key Vault) is the fallback.
- The application role is created by `infrastructure/scripts/setup-postgres-entra.sh`
  (`pgaadauth_create_principal_with_oid`), is not an administrator, and holds
  `CONNECT, CREATE, TEMPORARY` on the database and `USAGE, CREATE` on schema `public`.
  **NOT VERIFIED — requires Azure credentials** (the SQL was run on local PostgreSQL 16).

Backups, point-in-time restore and the restore drill: `docs/azure-deployment.md`,
*Backups and recovery*.
