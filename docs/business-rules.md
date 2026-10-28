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
  member and beneficiary data (`submitted_snapshot`) for audit. (Application printing was retired
  on 2026-10-28: there is no doctor or admin print view.)
- Payment status: `NOT_UPLOADED` → `PENDING_REVIEW` (automatically when a receipt is uploaded) →
  `CONFIRMED` or `REJECTED` (admin only). A rejected receipt normally comes with `NEEDS_CORRECTION`.
- Doctors can never set status, payment status, reference number, fee snapshot or reviewer fields.

## 5. Beneficiaries [`apps/beneficiaries`]

Up to `MAX_BENEFICIARIES` (default 10) per application. Supported kinships and the fee column each
maps to:

| Kinship | Arabic | Fee column |
|---|---|---|
| MOTHER / FATHER | أم / أب | parent |
| SON_MINOR | ابن/ابنة (18 سنة أو أقل) | child |
| SON_UNIVERSITY | ابن/ابنة (طالب جامعي) | grad_son |
| SON_GRADUATE | ابن/ابنة (خريج) | grad_son |
| HUSBAND / WIFE | زوج / زوجة | spouse |

The `SON_*` labels were changed on 2026-10-23 (owner); values and fee columns are unchanged and
stored rows are not migrated. **The standalone `DAUGHTER` («ابنة») was removed (owner,
2026-10-28)**: daughters use the combined `ابن/ابنة (...)` options. Every beneficiary create or
update that sends `DAUGHTER` is refused (400, `درجة القرابة غير صحيحة`) and the database CHECK
constraint no longer allows it (`beneficiaries.0003`/`0004`). A read-only check of the dev database
found none left (after the owner's cleanup of the dev applications); `0004` fails, without
converting anything, if one appears before deployment.

Brothers, sisters and "other" are not supported because the schedule has no fee for them.

Rules: a row counts only when it has a kinship *and* a name; national ID is optional (young
children) but unique within the application and different from the member's; birth year
1920..fiscal year; `HUSBAND` needs a female member and `WIFE` a male member (configurable);
`SON_MINOR` must be 18 or younger in the fiscal year (configurable); the same child under two
member parents is an admin warning, not a block. Changing a kinship discards that row's documents
because the required set changes.

**First time (`is_first_time`, «هل يشترك المستفيد لأول مرة؟»)** — a yes/no answer stored per
beneficiary, independent of the application type (an `ADDITION` can add a first-time beneficiary)
and never inferred from it. Drafts may leave it empty (NULL; also every row created before the
question existed); each active beneficiary needs an explicit answer before submission. It is kept in
the submitted snapshot and shown to reviewers (`غير محدد` when unanswered).

## 6. Required documents [`apps/reference/document_rules.py`]

Member: ID front, ID back, syndicate card (always); **personal photo (`PERSONAL_PHOTO`, image
only) required for a `FIRST_TIME` («أول مرة») application and optional for `ADDITION` («إضافة») or any
other type** (owner, 2026-10-28; the former global `REQUIRE_MEMBER_PHOTO` switch was removed so it
cannot contradict this — the slot is always offered and an uploaded photo stays attached when it
becomes optional); payment receipt (before submission); **the member's own birth certificate
(`MEMBER_BIRTH_CERTIFICATE`, «شهادة ميلاد العضو الأصلي لإثبات صلة القرابة بالأم») while an active
MOTHER is listed** — it proves the relation, so the mother's (or a child's) certificate never
satisfies it. One member-owned upload per application, no OCR, never deleted when the mother is
removed (it just becomes optional). Because these slots depend on the application (its type, its
beneficiaries), the server returns the application's own member list (`member_required_documents`
on the doctor and admin application APIs); reference data keeps the global list (photo optional)
plus `member_conditional` (`PERSONAL_PHOTO` → `required_with_application_type: FIRST_TIME`,
`MEMBER_BIRTH_CERTIFICATE` → `required_with_kinship: MOTHER`). The member photo is separate from the
beneficiary photos, which keep their own `is_first_time` rule below.

Beneficiaries, where age = fiscal year − birth year and the thresholds are configurable.
"National ID" always means **both sides**: `BENEFICIARY_NATIONAL_ID` (front — the old value, so
earlier uploads still count) and `BENEFICIARY_NATIONAL_ID_BACK`, each uploaded, replaced and
validated on its own:

| Kinship | Required |
|---|---|
| Spouse | national ID (both sides), marriage certificate, insurance print (برينت تأميني) |
| Parent | national ID (both sides) |
| Son (minor) / daughter | birth certificate required **only when the member is female** (any age), otherwise offered as optional; national ID (both sides) if age ≥ 16 (both optional below) |
| Son (university) | child rule + university card |
| Son (graduate) | child rule + insurance print |
| Any kinship, first time | white-background personal photo (`BENEFICIARY_PERSONAL_PHOTO`), except children younger than `PHOTO_EXEMPT_CHILD_AGE` (3); an unknown age never exempts |

- A **female member's** children (minor, daughter, university, graduate) need their own birth
  certificate at any age — on top of both ID sides from 16 and the kinship's documents — with the
  guidance «شهادة ميلاد الابن/الابنة مطلوبة لإثبات صلة القرابة بالأم (العضوة) مهما كان العمر.»
- A **male member's** children never need it (owner, 2026-10-28), also below the ID age: the slot is
  always listed as optional, so an uploaded certificate stays visible and attached. The rule uses the
  member's stored gender, never the child's; a member gender change refreshes the children's slots
  without a reload (D167). An unknown member gender does not require it (the gender itself is a
  submission error).
- Photo guidance next to the upload: «صورة شخصية بخلفية بيضاء مطلوبة عند الاشتراك لأول مرة.»;
  for `SON_MINOR` only also «لا تُطلب صورة شخصية للأطفال أقل من 3 سنوات.». The white background is
  checked by the reviewer — there is no automatic background detection or image editing.
- The member photo and the beneficiary photo are separate slots; both accept images only (JPG, PNG,
  WEBP) even when PDF documents are enabled.

The same table feeds the validator, the document dialog and the documents checklist, so labels and
enforcement cannot drift (prototype defect 11). Each requirement carries `images_only` and `hints`.

Upload limits: JPG/PNG/WEBP (PDF and HEIC behind flags, never for photos), max 8 MB, receipt at
least 400×300 px, server-side type sniffing and image decoding; one active document per slot,
re-upload replaces.

## 7. Fees [`apps/fees/services.py`]

FY 2026 schedule, **version 2** (active since 2026-10-23; whole Egyptian pounds):

| Tier | member | spouse | child | grad_son | parent |
|---|---|---|---|---|---|
| 0 (registered in the fiscal year itself) | 400 | 880 | 550 | **not eligible** | 1155 |
| 1 (1–5 years since registration) | 660 | 880 | 550 | 1320 | 1155 |
| 2 (6–10) | 770 | 1045 | 605 | 1540 | 1320 |
| 3 (11–15) | 825 | 1100 | 605 | 1650 | 1430 |
| 4 (>15, or pensioner) | 935 | 1155 | 660 | 1925 | 1540 |

- Tier 0: registration year = the application's fiscal year (never the server clock). Boundaries stay
  [5, 10, 15]. A university/graduate son at tier 0 is **not eligible** (stored as `null`, never 0):
  the quote is invalid with an Arabic message, drafts can still be saved, and submission is refused.
  Only tier 0's `grad_son` may be `null`.
- Administrative fee (رسوم إدارية): **200 + 175 × active beneficiaries** (200 / 375 / 550 / …). Only
  active rows (kinship and name) count. Both amounts are stored in the versioned schedule.
- Age cap: a member or spouse aged 70 or more in the fiscal year pays 500 instead of a higher tier
  fee (note `تم تطبيق سقف 500 ج (عمر N سنة)`). Parents and children are never capped.
- Pensioners (معاش) are always tier 4. Deceased members' families are priced like working members.
- Version 2 is the only FY 2026 version. **Version 1** (the original four-tier seed with a flat
  150 / 175 administrative fee) **was removed on 2026-10-24** (owner; migration `fees.0005`), and
  `fees.0006` removed the four-tier and flat-fee support. Applications priced with it keep their
  `fee_snapshot` and `submitted_snapshot` unchanged — their `fee_schedule` reference is `null` — and
  are shown from the snapshot; they are never re-priced or attached to version 2. Every schedule
  (and every new admin version) defines tiers 0–4 and `admin_fee_base` / `admin_fee_per_beneficiary`.
- An invalid registration year (missing, <1950, > fiscal year) makes the quote invalid with
  `يرجى إدخال سنة قيد النقابة بشكل صحيح لحساب الاشتراك.`
- `ADDITION` applications are priced like `FIRST_TIME`.
- Schedules are stored per fiscal year, versioned and audited; a version used by any submitted
  application becomes read-only.

Worked examples (used as tests): see `.claude/skills/syndicate-form-rules/SKILL.md` §4, e.g.
registration 2026 → tier 0: 400 + 200 = **600**; with one SON_MINOR 400 + 550 + 375 = **1325**;
registration 2014 with WIFE and SON_MINOR → tier 3: 825 + 1100 + 605 + 550 = **3080**.

## 8. Validation [`apps/applications/validation.py`]

Two levels: *draft* (formats, lengths, enums, digit normalization — incomplete is fine) on every
autosave, and *submission* (all 21 rules in SKILL.md §6, returned together, grouped by wizard step).
The declaration name must equal the member name after normalization (trim, collapse spaces,
أ/إ/آ→ا, ة→ه, ى→ي), and the doctor must tick the acceptance checkbox on the review page.

## 9. Error format

`{"error": {"code": "<STABLE_CODE>", "message": "<Arabic>", "fields": {"<field>": ["<Arabic>"]}}}`
with the codes listed in SKILL.md §7. The UI never shows stack traces.

## 10. Open business questions (implemented default → question)

| # | Question | Default implemented | Where configured |
|---|---|---|---|
| 1 | Are the FY 2026 amounts, tiers, admin fees and 70+ cap final? | Version 2 values above (owner, 2026-10-23), in an editable `FeeSchedule` | admin fee-schedules page |
| 2 | How are fees calculated for a deceased (متوفى) member's family? | Same as WORKING | `fees/services.py` |
| 3 | Fees for an `ADDITION` application — only the new beneficiaries? | Same as FIRST_TIME | `fees/services.py` |
| 4 | Children's documents: national ID (both sides) from 16; birth certificate only for a female member's children? | Age-aware ID rule, threshold configurable; birth certificate required iff the member is female, optional otherwise (owner, 2026-10-28) | `CHILD_NATIONAL_ID_AGE`, `document_rules.py` |
| 5 | Maximum beneficiaries: 10 (prototype) or 11 (paper rows)? | 10 | `MAX_BENEFICIARIES` |
| 6 | Must `SON_MINOR` be ≤18, and must spouse kinship match the member's gender? | Both enforced | `ENFORCE_SON_MINOR_AGE`, `ENFORCE_SPOUSE_GENDER` |
| 7 | Can a rejected applicant re-apply in the same fiscal year? | Yes, a new application | partial unique constraint |
| 8 | How do members pay (bank, Fawry, office)? What instructions to show? | Placeholder text on the receipt page (Q-B19); the organization must supply the real text | `frontend/src/i18n/ar.ts` → `payment.instructions` (one place; an admin-editable setting would need a new model) |
| 9 | Is the member photo mandatory? | Required for `FIRST_TIME`, optional otherwise (owner, 2026-10-28; no global switch) | `document_rules.py::member_document_requirements` |
| 10 | Is `(syndicate_type, registration_number)` unique? | Indexed, not unique | `doctors/models.py` |
| 11 | Is sending ID images to Azure OpenAI for OCR legally approved, and in which region? | OCR behind `OCR_ENABLED`, off in production until approved | settings / Bicep `enableOcr` |
| 12 | Data retention period for applications and documents? | Not auto-deleted; documented as a decision | `docs/security.md` |
| 13 | National ID check digit algorithm — should position 14 be validated? | Not validated | `national_id.py` |
| 14 | Governorate-of-birth codes — hard validation or warning? | Warning only | `national_id.py` |
| 15 | Arabic payment-status labels (`لم يتم رفع الإيصال / بانتظار التأكيد / مؤكد / مرفوض`), and may an admin change a payment decision after APPROVED? (Q-B15) | Labels as listed; payment changes refused after APPROVED | `apps/reference/constants.py`, `applications/services.py::set_payment_status` |
| 16 | Should admins see drafts before submission? (Q-B16) | No — review starts at SUBMITTED | admin querysets |
| 17 | Receipt minimum size: width ≥ 400 **and** height ≥ 300 (a portrait 300×400 photo is refused), or either orientation? (Q-B17) | Prototype rule (landscape minimum) | `RECEIPT_MIN_WIDTH` / `RECEIPT_MIN_HEIGHT` settings, `apps/documents/validators.py` |
| 18 | Should `إنشاء حساب` open Entra's sign-up page directly (`prompt=create`)? (Q-B18) | Both buttons use the combined sign-up/sign-in flow | `LandingPage.tsx`, `/auth/login/` |
| 19 | Must official printouts always carry the full national ID? (Q-B20) | Moot since 2026-10-28: application printing (doctor and admin) was retired; the admin detail still masks IDs unless revealed (audited) | — |
| 20 | When a correction is requested and the doctor resubmits, does a CONFIRMED payment stay confirmed? (Q-B21) | Yes, unless the doctor replaces the receipt (→ `PENDING_REVIEW`) | `applications/services.py` |
| 21 | Legal / organizational decisions L1–L8 (religion field, OCR by an AI service, region, retention, admin access, breach procedure, production access, malware scanning) (Q-B22) | See `docs/security.md` §6 | — |
| 22 | The under-3 photo note says "3"; if `PHOTO_EXEMPT_CHILD_AGE` changes, should the note follow? | Note text fixed as given by the owner; threshold configurable | `document_rules.py` `HINT_PHOTO_CHILD_EXEMPT`, `PHOTO_EXEMPT_CHILD_AGE` |
| 23 | Should the under-3 note also appear on other child rows? | Shown for `SON_MINOR` only (as specified); the exemption itself applies to every child kinship | `document_rules.py` |
