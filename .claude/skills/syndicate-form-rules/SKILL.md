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
| `SON_MINOR` | ابن/ابنة (18 سنة أو أقل) | child |
| `SON_UNIVERSITY` | ابن/ابنة (طالب جامعي) | grad_son |
| `SON_GRADUATE` | ابن/ابنة (خريج) | grad_son |
| `DAUGHTER` | ابنة | child — **retired** from the dropdowns (2026-10-28) |
| `HUSBAND` | زوج | spouse |
| `WIFE` | زوجة | spouse |

Brother / sister / other are intentionally unsupported (no fee). Keep the enum extensible.
The `SON_*` labels changed on 2026-10-23 (values, fee keys and stored rows unchanged).
`DAUGHTER` is in `constants.RETIRED_KINSHIPS`: reference data sends every kinship with
`selectable` (`false` for DAUGHTER); the SPA offers a non-selectable kinship only as a row's stored
value. Stored DAUGHTER rows keep label, fee key, document rules and validation; never delete or
convert them. Every create or update that sends DAUGHTER is refused
(`WRITABLE_KINSHIP_CHOICES` on the write serializer, `upsert_beneficiary` never writes a retired
kinship as a new or changed value) — no exceptions, also for a stored DAUGHTER row.

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
- `is_first_time` («هل يشترك المستفيد لأول مرة؟») — nullable boolean per beneficiary, independent of the
  application type and never inferred. NULL = unanswered (drafts, pre-existing rows); every ACTIVE row needs
  an explicit answer to submit. Part of read/write serializers, `BENEFICIARY_FIELDS`, the submitted snapshot.

## 3. Required documents (`backend/apps/reference/document_rules.py` — the ONLY rules table)

Member:

| Type | Label | Required |
|---|---|---|
| `NATIONAL_ID_FRONT` | صورة البطاقة (وجه) | yes |
| `NATIONAL_ID_BACK` | صورة البطاقة (ظهر) | yes |
| `SYNDICATE_ID` | كارنيه النقابة | yes |
| `PERSONAL_PHOTO` | صورة العضو الأصلي | iff `application_type == FIRST_TIME` (optional for ADDITION / other types; always offered; no global setting); image only |
| `MEMBER_BIRTH_CERTIFICATE` | شهادة ميلاد العضو الأصلي لإثبات صلة القرابة بالأم | while an ACTIVE `MOTHER` exists; else hidden, or optional if already uploaded (never deleted) |
| `PAYMENT_RECEIPT` | إيصال الدفع | yes, at submission (step 4) |

The member list is application-specific: `apps/applications/requirements.py::member_requirements(app)`
→ `member_required_documents` on `ApplicationSerializer` and `AdminApplicationDetailSerializer`.
Reference data keeps the global list (photo optional) + `member_conditional:
{PERSONAL_PHOTO: {required_with_application_type: FIRST_TIME}, MEMBER_BIRTH_CERTIFICATE: {required_with_kinship: MOTHER}}`.
A type change refreshes the slot through the application PATCH response; an uploaded photo stays.
The member certificate is member-owned (no beneficiary), not OCR-capable, and the mother's/children's
`BIRTH_CERTIFICATE` never satisfies it.

Beneficiaries — `age = fiscal_year − birth_year`, thresholds `CHILD_NATIONAL_ID_AGE = 16`,
`PHOTO_EXEMPT_CHILD_AGE = 3` (configurable). **ID = both sides**: `BENEFICIARY_NATIONAL_ID` (front; value
kept so old uploads count) + `BENEFICIARY_NATIONAL_ID_BACK`; independent slots.

| Kinship | Required |
|---|---|
| HUSBAND / WIFE | ID (both), `MARRIAGE_CERTIFICATE`, `INSURANCE_PRINT` |
| MOTHER / FATHER | ID (both) |
| SON_MINOR / DAUGHTER | `BIRTH_CERTIFICATE` always offered, required **iff the member is female** (any age; the member's gender, never the child's); ID (both) if age ≥ 16 (both optional below 16) |
| SON_UNIVERSITY | child rule + `UNIVERSITY_ID` |
| SON_GRADUATE | child rule + `INSURANCE_PRINT` |
| every kinship | `BENEFICIARY_PERSONAL_PHOTO` (always offered) required iff `is_first_time is True` and NOT (child kinship and known age < 3) |

Unknown birth year for a child → treat as age < 16 (ID optional) and it never grants the photo
exemption. Female member → children's `BIRTH_CERTIFICATE` required at any age with hint
`شهادة ميلاد الابن/الابنة مطلوبة لإثبات صلة القرابة بالأم (العضوة) مهما كان العمر.`; male (or unknown)
member → optional at every age, also below 16, no hint (owner, 2026-10-28).
Photo hints: `صورة شخصية بخلفية بيضاء مطلوبة عند الاشتراك لأول مرة.` (+ `لا تُطلب صورة شخصية للأطفال أقل من 3 سنوات.`
for `SON_MINOR` only). No automatic white-background detection. Requirement dicts:
`{type, required, label, ocr_capable, stage, images_only, hints}`.
Labels: `BENEFICIARY_NATIONAL_ID` بطاقة الرقم القومي للمستفيد (وجه) · `BENEFICIARY_NATIONAL_ID_BACK`
بطاقة الرقم القومي للمستفيد (ظهر) · `BENEFICIARY_PERSONAL_PHOTO` صورة شخصية للمستفيد بخلفية بيضاء ·
`BIRTH_CERTIFICATE` شهادة ميلاد المستفيد · `MARRIAGE_CERTIFICATE` شهادة الزواج · `INSURANCE_PRINT` برينت تأميني ·
`UNIVERSITY_ID` كارنيه الجامعة · `OTHER` مستند آخر. Missing → `المستفيد {name}: مستند {label} مطلوب`.

OCR-capable types (only those with a working extraction): `NATIONAL_ID_FRONT`, `NATIONAL_ID_BACK`,
`SYNDICATE_ID`, `BENEFICIARY_NATIONAL_ID` (front), `BIRTH_CERTIFICATE`. One active document per
`(application, beneficiary, document_type)`; re-upload replaces. Ownership sets live in
`document_rules.MEMBER_DOCUMENT_TYPES` and `documents/models.BENEFICIARY_DOCUMENT_TYPES` (CHECK
`document_type_matches_owner`); image-only types in `document_rules.IMAGE_ONLY_TYPES`.

## 4. Fee engine (`backend/apps/fees/services.py`) — server authoritative, integers/Decimal only

FY 2026 **version 2** — the only FY 2026 version (`FeeSchedule`, DB-stored, versioned, read-only once used
by a submission; created by `fees.0004_fy2026_v2_schedule`):

| Tier | member | spouse | child | grad_son | parent |
|---|---|---|---|---|---|
| 0 | 400 | 880 | 550 | `null` (NOT ELIGIBLE) | 1155 |
| 1 | 660 | 880 | 550 | 1320 | 1155 |
| 2 | 770 | 1045 | 605 | 1540 | 1320 |
| 3 | 825 | 1100 | 605 | 1650 | 1430 |
| 4 | 935 | 1155 | 660 | 1925 | 1540 |

`admin_fee_base=200` · `admin_fee_per_beneficiary=175` ·
`age_cap_threshold=70` · `age_cap_amount=500` · `tier_boundaries=[5, 10, 15]` · `registration_year_min=1950`.
`null` is valid ONLY for tier "0" `grad_son`. Every schedule defines tiers 0–4 (a four-tier `tier_fees`
is rejected). Version 1 (four tiers, flat 150/175 admin fee) was **removed** by `fees.0005` and the flat
formula columns by `fees.0006` (2026-10-24): applications priced with it keep `fee_snapshot` and
`submitted_snapshot` exactly, `fee_schedule = null`; never re-price them or point them at v2.

Rules, in order:
1. Registration year missing / not 4 digits / < 1950 / > fiscal year → `is_valid=false`, `tier=0`,
   `breakdown=[]`, `total=0`, `error_message="يرجى إدخال سنة قيد النقابة بشكل صحيح لحساب الاشتراك."`.
2. `work_status == PENSIONER` (معاش) → tier 4 regardless of years. `DECEASED` is treated like `WORKING`.
3. `years = schedule.fiscal_year − registration_year` (never the clock): `0` → tier 0, then
   `≤5→1, ≤10→2, ≤15→3, else 4`.
4. Any ACTIVE beneficiary whose tier amount is `null` → invalid quote (`tier` kept, `breakdown=[]`, `total=0`,
   `المستفيد {name}: لا يمكن الاشتراك بدرجة القرابة «{kinship label}» للأعضاء المقيدين في نفس سنة الاشتراك.`).
   Never skip the row, never price it 0. Validation adds the same message (step 2, `NOT_ELIGIBLE_FOR_TIER`).
5. Member line `العضو الأصلي`: tier member fee, or `500` when `fiscal_year − birth_year ≥ 70` (and the fee is
   higher), note `تم تطبيق سقف 500 ج (عمر {age} سنة)`. Missing birth year → no cap.
6. One line per **active** beneficiary (kinship + non-empty name), label = name, fee by fee key.
7. Age cap (≥70 → 500 + same note) applies to **spouse only**; never to parents or children.
8. `رسوم إدارية` = `admin_fee_base + admin_fee_per_beneficiary × active` = `200 + 175 × active`
   (0 → 200, 1 → 375, 2 → 550).
9. `total` = sum of lines. `ADDITION` applications are priced exactly like `FIRST_TIME`.
10. Tell valid tier 0 from invalid quotes by `is_valid`, never by the truthiness of `tier`.

Output: `{fiscal_year, tier, breakdown:[{label, fee, note}], admin_fee, total, is_valid, error_message, schedule_id}`.

Worked examples (FY 2026 v2) — table-driven tests (`apps/fees/tests/test_engine.py`):

| # | Reg. year / status | Member birth | Beneficiaries | Expected |
|---|---|---|---|---|
| A | 2026 / WORKING | 1990 | — | tier 0: 400+200 = **600** |
| B | 2026 / WORKING | 1990 | SON_MINOR | tier 0: 400+550+375 = **1325** |
| C | 2014 / WORKING | 1985 | WIFE 1988, SON_MINOR 2015 | tier 3: 825+1100+605+550 = **3080** |
| 1 | 2023 / WORKING | 1995 | — | tier 1: 660+200 = **860** |
| 2 | 2014 / WORKING | 1985 | WIFE 1988, SON_MINOR 2015, DAUGHTER 2018 | tier 3: 825+1100+605+605+725 = **3860** |
| 3 | 1990 / PENSIONER | 1950 | WIFE 1955, SON_GRADUATE 1995 | tier 4: 500+500+1925+550 = **3475** |
| 4 | 2018 / WORKING | 1990 | MOTHER 1960, SON_UNIVERSITY 2005 | tier 2: 770+1320+1540+550 = **4180** |
| 5 | boundaries | — | — | 2026→0, 2025→1, 2021→1, 2020→2, 2016→2, 2015→3, 2011→3, 2010→4 |
| 6 | age boundary | 1956 (70) / 1957 (69) | — | cap at 70, not at 69 |
| 7 | 1949 or 2027 | — | — | `is_valid=false` |
| 8 | 2023 / WORKING | 1995 | kinship set, empty name | ignored; admin fee 200 |
| 9 | 2023 / WORKING | 1995 | FATHER 1950 | tier 1: 660+1155+375 = **2190** (no cap for parents) |
| 10 | 2026 / WORKING | 1990 | SON_UNIVERSITY / SON_GRADUATE | tier 0: **invalid** (not eligible) |
| 11 | 2026 / PENSIONER | 1960 | SON_UNIVERSITY | tier 4 override: valid, son 1925 |

At submission: recompute, store `fee_snapshot` + `fee_schedule_id`; admins always see the snapshot
(also when `fee_schedule_id` is null because the version was removed).
New admin versions: tiers 0–4, `admin_fee_base` + `admin_fee_per_beneficiary`; all of them are protected
by the version lock.

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

| 19 | active beneficiary answered first time (step 2) | المستفيد {name}: يرجى تحديد هل يشترك المستفيد لأول مرة |
| 20 | member birth certificate while an active MOTHER exists (step 3) | يرجى إرفاق شهادة ميلاد العضو الأصلي لإثبات صلة القرابة بالأم |
| 21 | beneficiary eligible at the tier (step 2, `NOT_ELIGIBLE_FOR_TIER`) | المستفيد {name}: لا يمكن الاشتراك بدرجة القرابة «{kinship}» للأعضاء المقيدين في نفس سنة الاشتراك. |

Additional messages (not in PROMPT.md §22; added in Session 2 for the §13/§14 consistency rules):
`سنة الميلاد لا تطابق الرقم القومي` (member birth year ≠ ID) ·
`المستفيد {name}: درجة القرابة لا تتوافق مع نوع العضو` (spouse/gender) ·
`المستفيد {name}: الابن القاصر يجب أن يكون 18 سنة أو أقل` (SON_MINOR age) ·
`المستفيد {name}: الرقم القومي للمستفيد لا يمكن أن يطابق الرقم القومي للعضو` ·
review notes required `يرجى كتابة ملاحظات المراجعة` · approve without confirmed payment
`لا يمكن قبول الطلب قبل تأكيد الدفع`.

Name normalization for rule 15: trim, collapse spaces, أ/إ/آ→ا, ة→ه, ى→ي.
Step grouping: 1 member (rules 1–7, 14, 18) · 2 beneficiaries (11, 12, 19, 21, 14-related) · 3 documents (8–10, 13, 20) ·
4 receipt (16) · 5 declaration (15, 17).

## 7. Error codes (PROMPT.md §46)

`VALIDATION_ERROR DUPLICATE_NATIONAL_ID ACTIVE_APPLICATION_EXISTS INVALID_STATUS_TRANSITION
APPLICATION_NOT_EDITABLE FILE_TOO_LARGE UNSUPPORTED_FILE_TYPE IMAGE_TOO_SMALL OCR_UNAVAILABLE
RATE_LIMITED NOT_FOUND PERMISSION_DENIED NOT_AUTHENTICATED`

Envelope: `{"error": {"code": "...", "message": "<Arabic>", "fields": {"field": ["<Arabic>"]}}}`.

## 8. Upload limits (receipt and documents)

Images `JPG, PNG, WEBP` (PDF per `ALLOW_PDF_DOCUMENTS`, HEIC per `ALLOW_HEIC`), max **8 MB**, receipt
minimum **400×300 px**, content type sniffed server-side (never trust the browser), filename sanitized,
decode failure → reject. `PERSONAL_PHOTO` and `BENEFICIARY_PERSONAL_PHOTO` are image only (JPG/PNG/WEBP),
even with PDFs enabled (reference data `upload.image_content_types`).
