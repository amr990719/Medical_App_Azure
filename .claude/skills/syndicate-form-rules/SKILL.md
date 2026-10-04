---
name: syndicate-form-rules
description: Business rules of the medical syndicates treatment-project subscription form — fee engine (FY 2026 schedule, tiers, age cap, admin fee), Egyptian national ID parsing, kinship enum, required-document rules, application status transitions, validation messages and error codes. Load before implementing or changing anything in backend/apps/fees, reference, applications, beneficiaries, documents, or the matching frontend features.
---

# Syndicate Form Rules

Source of truth: `PROMPT.md` §13–§17, §22, §46, §57. Every rule is implemented in ONE configurable
place on the server; the frontend consumes it through `GET /api/v1/reference-data/` and
`GET /api/v1/applications/{id}/fees/`. Uncertain rules are implemented as written here, kept
configurable, and listed in `docs/business-rules.md` → Open questions.

## 1. Egyptian national ID (`backend/apps/reference/national_id.py`)

14 digits. Accept Eastern Arabic digits (٠١٢٣٤٥٦٧٨٩), normalize to Western, strip spaces.

| Position | Meaning |
|---|---|
| 1 | century: `2` = 1900–1999, `3` = 2000–2099 (anything else → invalid) |
| 2–7 | `YYMMDD` date of birth — must be a real calendar date and not in the future |
| 8–9 | governorate-of-birth code (table below). Unknown code = **warning**, not a block |
| 10–13 | sequence; **position 13 odd = male, even = female** |
| 14 | check digit — **do NOT validate** (algorithm unconfirmed) |

Derive `date_of_birth`, `birth_year`, `gender`. If the doctor typed a different birth year or gender,
raise a validation error (gender message: `يرجى تحديد النوع (ذكر/أنثى)`).

Governorate-of-birth codes:
`01 القاهرة 02 الإسكندرية 03 بورسعيد 04 السويس 11 دمياط 12 الدقهلية 13 الشرقية 14 القليوبية 15 كفر الشيخ
16 الغربية 17 المنوفية 18 البحيرة 19 الإسماعيلية 21 الجيزة 22 بني سويف 23 الفيوم 24 المنيا 25 أسيوط
26 سوهاج 27 قنا 28 أسوان 29 الأقصر 31 البحر الأحمر 32 الوادي الجديد 33 مطروح 34 شمال سيناء 35 جنوب سيناء
88 خارج الجمهورية`

Residence governorates (the 27 in the select): القاهرة، الجيزة، الإسكندرية، الدقهلية، البحر الأحمر، البحيرة،
الفيوم، الغربية، الإسماعيلية، المنوفية، المنيا، القليوبية، الوادي الجديد، السويس، أسوان، أسيوط، بني سويف،
بورسعيد، دمياط، الشرقية، جنوب سيناء، كفر الشيخ، مطروح، الأقصر، قنا، شمال سيناء، سوهاج.

**Masking:** logs and admin lists show first 2 + last 3 only: `29•••••••••123`. Never log a full ID.
**Uniqueness:** `Doctor.national_id` UNIQUE → `DUPLICATE_NATIONAL_ID` / `الرقم القومي مسجل لعضو آخر`.
Never a primary key.

## 2. Kinship enum (`Beneficiary.kinship`)

| Value | Arabic label (exact) | Fee key |
|---|---|---|
| `MOTHER` | أم | parent |
| `FATHER` | أب | parent |
| `SON_MINOR` | ابن (18 سنة أو أقل) | child |
| `SON_UNIVERSITY` | ابن (طالب جامعي) | gradSon |
| `SON_GRADUATE` | ابن (خريج) | gradSon |
| `DAUGHTER` | ابنة | child |
| `HUSBAND` | زوج | spouse |
| `WIFE` | زوجة | spouse |

Brother / sister / other are intentionally unsupported (no fee). Keep the enum extensible.

Beneficiary rules:
- Belongs to one application. `row_number` 1..`MAX_BENEFICIARIES` (default **10**, configurable), unique per application.
- `national_id` nullable (young children). Unique `(application_id, national_id)` when present; must differ
  from the member's.
- `birth_year` in 1920..fiscal_year → `المستفيد {name}: سنة الميلاد غير صحيحة`.
- `HUSBAND` requires a female member, `WIFE` a male member (`ENFORCE_SPOUSE_GENDER`, default on).
- `SON_MINOR` must be ≤ 18 in the fiscal year (`ENFORCE_SON_MINOR_AGE`, default on).
- A row is **active** (counted for fees and validation) only when it has a kinship AND a non-empty name.
- Same child listed by two member parents across applications = admin **warning**, never a block.
- Changing a row's kinship removes that row's documents (after confirmation) because the required set changes.

## 3. Required documents (`backend/apps/reference/document_rules.py` — the ONLY rules table)

Member (always):

| Type | Label | Required |
|---|---|---|
| `NATIONAL_ID_FRONT` | صورة البطاقة (وجه) | yes |
| `NATIONAL_ID_BACK` | صورة البطاقة (ظهر) | yes |
| `SYNDICATE_ID` | كارنيه النقابة | yes |
| `PERSONAL_PHOTO` | صورة العضو الأصلي | `REQUIRE_MEMBER_PHOTO` (default false) |
| `PAYMENT_RECEIPT` | إيصال الدفع | yes, at submission (step 4) |

Beneficiaries — `age = fiscal_year − birth_year`, threshold `CHILD_NATIONAL_ID_AGE = 16` (configurable):

| Kinship | Required |
|---|---|
| HUSBAND / WIFE | `BENEFICIARY_NATIONAL_ID`, `MARRIAGE_CERTIFICATE`, `INSURANCE_PRINT` |
| MOTHER / FATHER | `BENEFICIARY_NATIONAL_ID` |
| SON_MINOR / DAUGHTER | `BIRTH_CERTIFICATE` if age < 16 **or** member is female; `BENEFICIARY_NATIONAL_ID` if age ≥ 16 (optional below 16) |
| SON_UNIVERSITY | child rule + `UNIVERSITY_ID` |
| SON_GRADUATE | child rule + `INSURANCE_PRINT` |

Unknown birth year for a child → treat as age < 16 (birth certificate required, national ID optional).
Labels: `BENEFICIARY_NATIONAL_ID` بطاقة الرقم القومي · `BIRTH_CERTIFICATE` شهادة الميلاد ·
`MARRIAGE_CERTIFICATE` شهادة الزواج · `INSURANCE_PRINT` برينت تأميني · `UNIVERSITY_ID` كارنيه الجامعة ·
`OTHER` مستند آخر. Missing → `المستفيد {name}: مستند {label} مطلوب`.

OCR-capable types: `NATIONAL_ID_FRONT`, `NATIONAL_ID_BACK`, `SYNDICATE_ID`, `BENEFICIARY_NATIONAL_ID`,
`BIRTH_CERTIFICATE`. One active document per `(application, beneficiary, document_type)`; re-upload replaces.

## 4. Fee engine (`backend/apps/fees/services.py`) — server authoritative, integers/Decimal only

FY 2026 schedule (`FeeSchedule`, DB-stored, versioned, read-only once used by a submission):

| Tier | member | spouse | child | gradSon | parent |
|---|---|---|---|---|---|
| 1 | 600 | 800 | 500 | 1200 | 1050 |
| 2 | 700 | 950 | 550 | 1400 | 1200 |
| 3 | 750 | 1000 | 550 | 1500 | 1300 |
| 4 | 850 | 1050 | 600 | 1750 | 1400 |

`admin_fee_member_only=150` · `admin_fee_with_beneficiaries=175` · `age_cap_threshold=70` ·
`age_cap_amount=500` · tiers by `years = fiscal_year − registration_year`: ≤5→1, ≤10→2, ≤15→3, else 4 ·
`registration_year_min=1950`.

Rules, in order:
1. Registration year missing / not 4 digits / < 1950 / > fiscal year → `is_valid=false`, `tier=0`,
   `breakdown=[]`, `total=0`, `error_message="يرجى إدخال سنة قيد النقابة بشكل صحيح لحساب الاشتراك."`.
2. `work_status == PENSIONER` (معاش) → tier 4 regardless of years. `DECEASED` is treated like `WORKING`.
3. Member line `العضو الأصلي`: tier member fee, or `500` when `fiscal_year − birth_year ≥ 70`, with note
   `تم تطبيق سقف 500 ج (عمر {age} سنة)`. Missing birth year → no cap.
4. One line per **active** beneficiary (kinship + non-empty name), label = name, fee by fee key.
5. Age cap (≥70 → 500 + same note) applies to **spouse only**; never to parents or children.
6. `رسوم إدارية` = 175 if any active beneficiary else 150.
7. `total` = sum of lines. `ADDITION` applications are priced exactly like `FIRST_TIME`.

Output: `{fiscal_year, tier, breakdown:[{label, fee, note}], admin_fee, total, is_valid, error_message, schedule_id}`.

Worked examples (FY 2026) — table-driven tests:

| # | Reg. year / status | Member birth | Beneficiaries | Expected |
|---|---|---|---|---|
| 1 | 2023 / WORKING | 1995 | — | tier 1: 600+150 = **750** |
| 2 | 2014 / WORKING | 1985 | WIFE 1988, SON_MINOR 2015, DAUGHTER 2018 | tier 3: 750+1000+550+550+175 = **3025** |
| 3 | 1990 / PENSIONER | 1950 | WIFE 1955, SON_GRADUATE 1995 | tier 4: 500+500+1750+175 = **2925** |
| 4 | 2018 / WORKING | 1990 | MOTHER 1960, SON_UNIVERSITY 2005 | tier 2: 700+1200+1400+175 = **3475** |
| 5 | boundaries | — | — | 2021→1, 2016→2, 2011→3, 2010→4 |
| 6 | age boundary | 1956 (70) / 1957 (69) | — | cap at 70, not at 69 |
| 7 | 1949 or 2027 | — | — | `is_valid=false` |
| 8 | 2023 / WORKING | 1995 | kinship set, empty name | ignored; admin fee 150 |
| 9 | 2023 / WORKING | 1995 | FATHER 1950 | tier 1: 600+1050+175 = **1825** (no cap for parents) |

At submission: recompute, store `fee_snapshot` + `fee_schedule_id`; admins always see the snapshot.

## 5. Application statuses and transitions (`applications/services.py::transition`)

Editable by doctor: `DRAFT`, `NEEDS_CORRECTION`. Read-only: `SUBMITTED`, `UNDER_REVIEW`, `APPROVED`, `REJECTED`.

| From | To | Who | Condition |
|---|---|---|---|
| DRAFT | SUBMITTED | doctor | full validation passes, receipt uploaded, declaration accepted → generates reference number |
| SUBMITTED | UNDER_REVIEW | admin | — |
| SUBMITTED / UNDER_REVIEW | NEEDS_CORRECTION | admin | `review_notes` required |
| UNDER_REVIEW | APPROVED | admin | `payment_status == CONFIRMED` |
| SUBMITTED / UNDER_REVIEW | REJECTED | admin | `review_notes` required |
| NEEDS_CORRECTION | SUBMITTED | doctor | full validation passes again; keeps the same reference number |

Anything else → `INVALID_STATUS_TRANSITION`. Implement with `select_for_update`, permission check,
audit entry. `REJECTED` is final; the doctor may create a new application for the same fiscal year.
Partial unique: one application per doctor per fiscal year with status ≠ REJECTED → `ACTIVE_APPLICATION_EXISTS`.

Payment status: `NOT_UPLOADED → PENDING_REVIEW` (set by server on receipt upload) → `CONFIRMED | REJECTED`
(admin only; rejecting normally goes with `NEEDS_CORRECTION` + note). Doctors never write `status`,
`payment_status`, `reference_number`, `fee_snapshot`, `review_notes`, `reviewed_by`, `reviewed_at`.

Reference number: `MED-{fiscal_year}-{6-digit sequence}` (e.g. `MED-2026-000123`) from a per-year
`ReferenceCounter` row locked with `select_for_update` inside the submission transaction. Never reused;
kept on resubmission.

Status labels: DRAFT مسودة · SUBMITTED مقدم · UNDER_REVIEW قيد المراجعة · NEEDS_CORRECTION يحتاج تصحيح ·
APPROVED مقبول · REJECTED مرفوض (colours in PROMPT.md §7.3).

## 6. Submission validation messages (`applications/validation.py`; return ALL, grouped by step)

| # | Rule | Message |
|---|---|---|
| 1 | syndicate type required | يرجى اختيار نوع النقابة |
| 2 | member name ≥ 5 chars | اسم العضو يجب أن يكون 5 أحرف على الأقل |
| 3 | national ID valid | الرقم القومي يجب أن يكون 14 رقماً صحيحاً |
| 4 | gender required & consistent with ID | يرجى تحديد النوع (ذكر/أنثى) |
| 5 | work status required | يرجى تحديد حالة العمل |
| 6 | registration year 1950..FY | سنة قيد النقابة غير صحيحة |
| 7 | mobile `^(\+20|0020|0)?1[0125]\d{8}$` | رقم الهاتف المحمول غير صحيح |
| 8 | ID front attached | يرجى إرفاق صورة وجه البطاقة الشخصية |
| 9 | ID back attached | يرجى إرفاق صورة ظهر البطاقة الشخصية |
| 10 | syndicate ID attached | يرجى إرفاق صورة كارنيه النقابة |
| 11 | named beneficiary needs kinship | المستفيد رقم {n}: يرجى تحديد درجة القرابة |
| 12 | beneficiary birth year 1920..FY | المستفيد {name}: سنة الميلاد غير صحيحة |
| 13 | beneficiary required documents | المستفيد {name}: مستند {label} مطلوب |
| 14 | governorate, address, sub-syndicate, registration number, birth year | يرجى إدخال {field} |
| 15 | declaration name matches member name (normalized) | اسم المقر يجب أن يطابق اسم العضو |
| 16 | receipt uploaded (submit only) | يرجى رفع إيصال الدفع |
| 17 | declaration accepted (submit only) | يرجى الموافقة على الإقرار |
| 18 | national ID not used by another doctor | الرقم القومي مسجل لعضو آخر |

Name normalization for rule 15: trim, collapse spaces, أ/إ/آ→ا, ة→ه, ى→ي.
Step grouping: 1 member (rules 1–7, 14, 18) · 2 beneficiaries (11, 12, 14-related) · 3 documents (8–10, 13) ·
4 receipt (16) · 5 declaration (15, 17).

## 7. Error codes (PROMPT.md §46)

`VALIDATION_ERROR DUPLICATE_NATIONAL_ID ACTIVE_APPLICATION_EXISTS INVALID_STATUS_TRANSITION
APPLICATION_NOT_EDITABLE FILE_TOO_LARGE UNSUPPORTED_FILE_TYPE IMAGE_TOO_SMALL OCR_UNAVAILABLE
RATE_LIMITED NOT_FOUND PERMISSION_DENIED NOT_AUTHENTICATED`

Envelope: `{"error": {"code": "...", "message": "<Arabic>", "fields": {"field": ["<Arabic>"]}}}`.

## 8. Upload limits (receipt and documents)

Images `JPG, PNG, WEBP` (PDF per `ALLOW_PDF_DOCUMENTS`, HEIC per `ALLOW_HEIC`), max **8 MB**, receipt
minimum **400×300 px**, content type sniffed server-side (never trust the browser), filename sanitized,
decode failure → reject. `PERSONAL_PHOTO` is image only.
