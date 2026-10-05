# Business Rules

Human-readable version of the rules in `PROMPT.md` §12–§18, §22, §40, §46, §57. The implementation
contract for Claude sessions is `.claude/skills/syndicate-form-rules/SKILL.md`; the two must stay in
sync. Every rule is implemented once, on the server, in the module named in brackets.

## 1. Actors and roles

- **Doctor / member (العضو الأصلي)** — a member of one of the four syndicates: بشري (human medicine),
  صيدلي (pharmacy), أسنان (dentistry), بيطري (veterinary). Signs in with Entra External ID, owns
  exactly one *active* application per fiscal year, can edit it only while it is `DRAFT` or
  `NEEDS_CORRECTION`.
- **Administrator** — Django role `ADMIN`, granted only with `manage.py grant_admin`. Reviews all
  applications, confirms payments, changes statuses through the allowed transitions, writes notes,
  maintains fee schedules. Must use MFA.

## 2. Member profile [`apps/doctors`]

Fields: full name, national ID (14 digits, unique), date of birth / birth year / gender (derived from
the ID), religion (مسلم / مسيحي — collected because the paper form requires it; see
`docs/security.md`), Egyptian mobile, email (from Entra), syndicate type, sub-syndicate (النقابة
الفرعية), registration number (رقم قيد النقابة), registration year (سنة قيد النقابة), treatment card
number (رقم بطاقة العلاج; empty for first-time members), residence governorate (one of 27),
neighborhood (الحي), address.

- `(syndicate_type, registration_number)` is indexed, **not** unique (open question 10).
- Mobile regex: `^(\+20|0020|0)?1[0125]\d{8}$`, normalized to a canonical form before storage.

## 3. Egyptian national ID [`apps/reference/national_id.py`]

| Position | Meaning |
|---|---|
| 1 | century: `2` = 1900s, `3` = 2000s |
| 2–7 | `YYMMDD` date of birth; must be a real date and not in the future |
| 8–9 | governorate-of-birth code (unknown code = warning, not a block) |
| 10–13 | sequence; digit 13 odd = male, even = female |
| 14 | check digit — not validated (algorithm unconfirmed) |

Eastern Arabic digits are accepted and normalized everywhere. The system derives birth year and
gender from the ID and flags a mismatch with what the doctor typed. The full ID is never logged;
display outside the doctor's own form is masked `29•••••••••123`.

## 4. Applications and statuses [`apps/applications`]

An application is a per-fiscal-year snapshot (type `FIRST_TIME` أول مرة or `ADDITION` إضافة; work
status `WORKING` يعمل / `PENSIONER` معاش / `DECEASED` متوفى lives on the application because it
changes the fee).

| Status | Arabic | Doctor can edit |
|---|---|---|
| DRAFT | مسودة | yes |
| SUBMITTED | مقدم | no |
| UNDER_REVIEW | قيد المراجعة | no |
| NEEDS_CORRECTION | يحتاج تصحيح | yes |
| APPROVED | مقبول | no |
| REJECTED | مرفوض | no (final) |

Allowed transitions (anything else is rejected with `INVALID_STATUS_TRANSITION`):

| From | To | Who | Condition |
|---|---|---|---|
| DRAFT | SUBMITTED | doctor | full validation passes, receipt uploaded, declaration accepted |
| SUBMITTED | UNDER_REVIEW | admin | — |
| SUBMITTED, UNDER_REVIEW | NEEDS_CORRECTION | admin | review note required (visible to doctor) |
| UNDER_REVIEW | APPROVED | admin | payment status is CONFIRMED |
| SUBMITTED, UNDER_REVIEW | REJECTED | admin | review note required |
| NEEDS_CORRECTION | SUBMITTED | doctor | full validation passes again |

- One application per doctor per fiscal year that is not `REJECTED` (database partial unique
  constraint → `ACTIVE_APPLICATION_EXISTS`). After a rejection the doctor may start a new one.
- **Reference number** `MED-{year}-{000123}` is assigned atomically at the *first* submission and
  kept on resubmission. Numbers are never reused.
- At submission the server recomputes and freezes the fee (`fee_snapshot`) and stores a copy of the
  member and beneficiary data (`submitted_snapshot`) for audit and printing.
- Payment status: `NOT_UPLOADED` → `PENDING_REVIEW` (automatically when a receipt is uploaded) →
  `CONFIRMED` or `REJECTED` (admin only). A rejected receipt normally comes with `NEEDS_CORRECTION`.
- Doctors can never set status, payment status, reference number, fee snapshot or reviewer fields.

## 5. Beneficiaries [`apps/beneficiaries`]

Up to `MAX_BENEFICIARIES` (default 10) per application. Supported kinships and the fee column each
maps to:

| Kinship | Arabic | Fee column |
|---|---|---|
| MOTHER / FATHER | أم / أب | parent |
| SON_MINOR | ابن (18 سنة أو أقل) | child |
| DAUGHTER | ابنة | child |
| SON_UNIVERSITY | ابن (طالب جامعي) | grad_son |
| SON_GRADUATE | ابن (خريج) | grad_son |
| HUSBAND / WIFE | زوج / زوجة | spouse |

Brothers, sisters and "other" are not supported because the schedule has no fee for them.

Rules: a row counts only when it has a kinship *and* a name; national ID is optional (young
children) but unique within the application and different from the member's; birth year
1920..fiscal year; `HUSBAND` needs a female member and `WIFE` a male member (configurable);
`SON_MINOR` must be 18 or younger in the fiscal year (configurable); the same child under two
member parents is an admin warning, not a block. Changing a kinship discards that row's documents
because the required set changes.

## 6. Required documents [`apps/reference/document_rules.py`]

Member: ID front, ID back, syndicate card (always); personal photo (optional unless
`REQUIRE_MEMBER_PHOTO`); payment receipt (before submission).

Beneficiaries, where age = fiscal year − birth year and the threshold (16) is configurable:

| Kinship | Required |
|---|---|
| Spouse | national ID, marriage certificate, insurance print (برينت تأميني) |
| Parent | national ID |
| Son (minor) / daughter | birth certificate if age < 16 **or** the member is female; national ID if age ≥ 16 (optional below) |
| Son (university) | child rule + university card |
| Son (graduate) | child rule + insurance print |

The same table feeds the validator, the document dialog and the documents checklist, so labels and
enforcement cannot drift (prototype defect 11).

Upload limits: JPG/PNG/WEBP (PDF and HEIC behind flags), max 8 MB, receipt at least 400×300 px,
server-side type sniffing and image decoding; one active document per slot, re-upload replaces.

## 7. Fees [`apps/fees/services.py`]

FY 2026 schedule (whole Egyptian pounds):

| Tier | member | spouse | child | grad_son | parent |
|---|---|---|---|---|---|
| 1 (≤5 years since registration) | 600 | 800 | 500 | 1200 | 1050 |
| 2 (≤10) | 700 | 950 | 550 | 1400 | 1200 |
| 3 (≤15) | 750 | 1000 | 550 | 1500 | 1300 |
| 4 (>15, or pensioner) | 850 | 1050 | 600 | 1750 | 1400 |

- Administrative fee (رسوم إدارية): 150 with no beneficiaries, 175 with at least one.
- Age cap: a member or spouse aged 70 or more in the fiscal year pays 500 instead of the tier fee
  (note `تم تطبيق سقف 500 ج (عمر N سنة)`). Parents and children are never capped.
- Pensioners (معاش) are always tier 4. Deceased members' families are priced like working members.
- An invalid registration year (missing, <1950, > fiscal year) makes the quote invalid with
  `يرجى إدخال سنة قيد النقابة بشكل صحيح لحساب الاشتراك.`
- `ADDITION` applications are priced like `FIRST_TIME`.
- Schedules are stored per fiscal year, versioned and audited; a version used by any submitted
  application becomes read-only.

Worked examples (used as tests): see `.claude/skills/syndicate-form-rules/SKILL.md` §4
(e.g. registration 2014, member born 1985, wife 1988, son 2015, daughter 2018 → tier 3 →
750 + 1000 + 550 + 550 + 175 = **3025**).

## 8. Validation [`apps/applications/validation.py`]

Two levels: *draft* (formats, lengths, enums, digit normalization — incomplete is fine) on every
autosave, and *submission* (all 18 rules in SKILL.md §6, returned together, grouped by wizard step).
The declaration name must equal the member name after normalization (trim, collapse spaces,
أ/إ/آ→ا, ة→ه, ى→ي), and the doctor must tick the acceptance checkbox on the review page.

## 9. Error format

`{"error": {"code": "<STABLE_CODE>", "message": "<Arabic>", "fields": {"<field>": ["<Arabic>"]}}}`
with the codes listed in SKILL.md §7. The UI never shows stack traces.

## 10. Open business questions (implemented default → question)

| # | Question | Default implemented | Where configured |
|---|---|---|---|
| 1 | Are the FY 2026 amounts, tiers, admin fees and 70+ cap final? | Values above, in an editable `FeeSchedule` | admin fee-schedules page |
| 2 | How are fees calculated for a deceased (متوفى) member's family? | Same as WORKING | `fees/services.py` |
| 3 | Fees for an `ADDITION` application — only the new beneficiaries? | Same as FIRST_TIME | `fees/services.py` |
| 4 | Children's documents: is the age-16 rule right (birth certificate <16, national ID ≥16, birth certificate always if member is female)? | Age-aware rule, threshold configurable | `CHILD_NATIONAL_ID_AGE` |
| 5 | Maximum beneficiaries: 10 (prototype) or 11 (paper rows)? | 10 | `MAX_BENEFICIARIES` |
| 6 | Must `SON_MINOR` be ≤18, and must spouse kinship match the member's gender? | Both enforced | `ENFORCE_SON_MINOR_AGE`, `ENFORCE_SPOUSE_GENDER` |
| 7 | Can a rejected applicant re-apply in the same fiscal year? | Yes, a new application | partial unique constraint |
| 8 | How do members pay (bank, Fawry, office)? What instructions to show? | Configurable placeholder text | `PAYMENT_INSTRUCTIONS` setting / admin |
| 9 | Is the member photo mandatory? | Optional | `REQUIRE_MEMBER_PHOTO=false` |
| 10 | Is `(syndicate_type, registration_number)` unique? | Indexed, not unique | `doctors/models.py` |
| 11 | Is sending ID images to Azure OpenAI for OCR legally approved, and in which region? | OCR behind `OCR_ENABLED`, off in production until approved | settings / Bicep `enableOcr` |
| 12 | Data retention period for applications and documents? | Not auto-deleted; documented as a decision | `docs/security.md` |
| 13 | National ID check digit algorithm — should position 14 be validated? | Not validated | `national_id.py` |
| 14 | Governorate-of-birth codes — hard validation or warning? | Warning only | `national_id.py` |
