# Build Prompt — Medical Syndicates Treatment Project Platform (Azure)

You are acting as a senior software architect, full-stack engineer, Django engineer, React/TypeScript engineer, PostgreSQL database architect, Azure cloud architect, DevOps engineer, and application security engineer.

Your task is to DESIGN, BUILD, CONFIGURE, TEST, CONTAINERIZE, and PREPARE FOR DEPLOYMENT a complete, production-ready web application that digitizes the paper subscription form of the Egyptian Union of Medical Professions Syndicates treatment project:

```text
اتحاد نقابات المهن الطبية — مشروع علاج الأعضاء وأسرهم
استمارة اشتراك بمشروع العلاج ( أول مرة - إضافة )
```

Do not create only boilerplate or mock screens. Build a functional end-to-end application.

The entire production system must run on Microsoft Azure.

---

# 0. How to Read This Prompt

- This prompt is the specification. Where two sections appear to conflict, the more specific section wins (for example, section 9 on the form layout wins over the generic page list).
- Section 2 points to a working Firebase prototype of the same product. Port its user experience and business rules; do not port its architecture or its defects.
- Where a business rule is uncertain, implement the rule described here, keep it in ONE configurable place, and list it under "Open business questions" in your final report (section 57). Do not stop to ask; keep building.
- Never invent Azure credentials, subscription IDs, tenant IDs, or secrets.

---

# 1. High-Level Goal

Build a web application used to collect and manage treatment-project subscription applications for members of the Egyptian medical syndicates (human medicine, pharmacy, dentistry, veterinary). In this prompt "doctor" and "member" mean the same person: العضو الأصلي.

A doctor should be able to:

- Create an account and sign in (Microsoft Entra External ID).
- Fill a digital replica of the paper subscription form, in Arabic, right-to-left.
- Upload the mandatory ID documents and let the system read them automatically (OCR) to pre-fill the form.
- Enter personal and syndicate information.
- Add up to 10 beneficiaries (family members) with the documents their relationship requires.
- See the subscription fee calculated live by the server.
- Save an incomplete application as a draft automatically, close the browser, and continue later.
- Upload the payment receipt.
- Review and submit the application with a declaration.
- Receive a reference number (for example `MED-2026-000123`).
- Track the application status and read reviewer notes.
- Correct and resubmit when the reviewer asks for corrections.
- Print the completed form on A4 paper.

An administrator should be able to:

- Sign in securely (with MFA).
- View all applications with server-side search, filters, sorting and pagination.
- Open an application and see the member, beneficiaries, fee snapshot, payment receipt and all documents.
- Access uploaded documents securely.
- Confirm or reject the payment receipt.
- Change application status according to the allowed transitions.
- Write doctor-visible review notes and internal administrative notes.
- Print an application.
- View basic audit history.
- Maintain the fee schedule for a fiscal year.

This application processes national IDs, family information, religion and identity documents. Security must be treated as a primary architectural requirement.

---

# 2. Reference Implementation (Firebase Prototype)

A working prototype of the same product exists:

```text
https://github.com/amr990719/medical-form
```

It is a React 19 + Vite + Tailwind 4 SPA on Firebase (Auth, Firestore, Storage, Cloud Functions, Gemini OCR). Its UI and business logic are the agreed product behavior. Its architecture is NOT what we are building.

## 2.1 How to use it

1. In Phase 1, clone it read-only OUTSIDE the new monorepo, for example:

   ```bash
   git clone --depth 1 https://github.com/amr990719/medical-form ../reference/medical-form
   ```

2. Read these files before designing anything:

   ```text
   src/context/FormContext.jsx            form state shape and behaviors
   src/pages/FormPage.jsx                 paper-form page, validation panel, action bar, A4 print
   src/components/form/MemberSection.jsx  header, attachments panel, member field grid
   src/components/form/BeneficiaryTable.jsx
   src/components/form/DeclarationSection.jsx
   src/components/form/FeeSummaryPanel.jsx
   src/components/shared/*                NidInput, BoxStringInput, DashedField, RadioBoxGroup,
                                          DocumentModal, ProgressStepper
   src/components/SmartUpload.jsx         upload + "مسح تلقائي" OCR button
   src/services/CalculationService.js     fee engine (FY 2026)
   src/services/OcrService.js             OCR prompts, field mapping and normalization
   src/utils/validateForm.js              submission validation + Arabic messages
   src/utils/validateReceiptImage.js      receipt checks
   src/pages/ReceiptPage.jsx, WaitingPage.jsx, DashboardPage.jsx
   src/index.css                          design tokens
   functions/index.js                     reference number generation
   ```

3. Port behavior, not code: convert JSX to strict TSX, inline styles to Tailwind theme tokens, Firebase calls to the Django API client, client-side business logic to Django services.

4. Do NOT copy into the new repo: `src/firebase.js`, `functions/`, `firestore.rules`, `storage.rules`, `firebase.json`, `.firebaserc`, `.firebase/`, `diff.patch`, `test_extract.js`, or any Firebase configuration value.

## 2.2 File mapping

| Prototype | New location |
|---|---|
| `context/FormContext.jsx` | `frontend/src/features/application-form/ApplicationFormProvider.tsx` + `useApplicationDraft.ts` |
| `pages/FormPage.jsx` | `frontend/src/pages/application/FormPage.tsx` |
| `components/form/MemberSection.jsx` | `frontend/src/features/application-form/MemberSection.tsx` |
| `components/form/BeneficiaryTable.jsx` | `frontend/src/features/beneficiaries/BeneficiaryTable.tsx` (+ mobile card view) |
| `components/form/DeclarationSection.jsx` | `frontend/src/features/application-form/DeclarationSection.tsx` |
| `components/form/FeeSummaryPanel.jsx` | `frontend/src/features/fees/FeeSummaryPanel.tsx` (shows the SERVER quote) |
| `components/shared/*` | `frontend/src/components/form/*` |
| `components/SmartUpload.jsx` | `frontend/src/features/documents/SmartUpload.tsx` (uploads to API, OCR via API) |
| `services/CalculationService.js` | `backend/apps/fees/services.py` (authoritative) |
| `services/OcrService.js` | `backend/apps/ocr/` (providers, prompts, normalizers) |
| `utils/validateForm.js` | `backend/apps/applications/validation.py` (authoritative) + frontend Zod schemas |
| `utils/validateReceiptImage.js` | `backend/apps/documents/validators.py` + frontend pre-check |
| `pages/ReceiptPage.jsx` | `frontend/src/pages/application/PaymentPage.tsx` |
| `pages/WaitingPage.jsx` | `frontend/src/pages/application/StatusPage.tsx` |
| `pages/DashboardPage.jsx` | `frontend/src/pages/doctor/DashboardPage.tsx` |
| `hooks/useSubmissionStatus.js` | TanStack Query hook with polling |
| `functions/index.js` (reference number) | `backend/apps/applications/services.py` (generated at submission) |
| `auth/AuthPage.jsx` | Replaced by Entra External ID hosted sign-in + `LandingPage.tsx` |
| `index.css` tokens | `frontend/tailwind` theme |

## 2.3 Known prototype defects — do NOT reproduce

1. The owner could edit `paymentStatus` (rules allowed it). Payment and application status must be server-controlled; doctors can never set them.
2. Resubmitting after "needs revision" failed because the client tried to change `applicationStatus`. Implement an explicit `NEEDS_CORRECTION → SUBMITTED` transition through the API.
3. Files were stored with permanent public download URLs (`getDownloadURL`). Documents must be private and served only through an authorized endpoint or short-lived SAS URLs.
4. The fee was calculated in the browser and saved as `feeSnapshot`. The server must calculate and snapshot the fee.
5. Validation ran only in the browser. Django validation is authoritative.
6. No uniqueness on national ID; the same person could submit many times. Enforce database constraints.
7. All files uploaded at the very end; a failed database write orphaned them, and a page refresh lost the whole form. Use draft autosave, upload-on-select, and orphan cleanup.
8. `NidInput` silently dropped Eastern Arabic digits (٠-٩). Normalize them to Western digits instead.
9. OCR ran from the browser with the AI key path exposed and no abuse protection. OCR must run server-side, authenticated and rate-limited.
10. A Firebase config was committed in `diff.patch`; Cloud Functions targeted end-of-life Node 18. Commit no secrets; use current supported runtimes (Python 3.12+, Node 22 LTS).
11. Required documents for children differed between the upload dialog labels and the validator. Use ONE rules table (section 15) for both.
12. The reference number was generated by a trigger on create. Generate it atomically at first submission.

---

# 3. Skills and Plugins to Use

These Claude Code skills/plugins are installed. Use them at the matching phase; load a skill before the work it covers, not all at once.

| When | Use |
|---|---|
| Whole project (planning and discipline) | **superpowers** — `writing-plans`, `executing-plans`, `test-driven-development`, `systematic-debugging`, `verification-before-completion`, `requesting-code-review`. The spec is complete, so skip interactive brainstorming unless something is genuinely contradictory. |
| Phase 3 (Django) | **django-expert** for models, DRF, permissions, tests; **django-safe-migration** for migrations and the deploy-time migration strategy |
| Phase 3 (schema) | The installed **Postgres** skill for schema, constraints, indexes and query review |
| Phase 4 (UI) | **frontend-design** for visual quality; **rtl-ui** (rtl plugin) for every RTL decision; run its `rtl_check.py` on `frontend/src` before finishing Phase 4 |
| Phase 6 (Azure SDK code) | **azure-storage-blob-py**, **azure-identity-py**, **azure-keyvault-py**, **azure-monitor-opentelemetry-py** |
| Phase 6–7 (Azure resources) | **azure** plugin: `azure-prepare`, `azure-validate`, `entra-app-registration`, `azure-diagnostics`. Use `azure-deploy` only after I confirm, because it creates billable resources |
| Phase 8 (CI/CD) | **github** plugin for repository, Actions and OIDC setup. Do not push, create repositories or open PRs until I confirm |
| Phase 9 (testing) | **playwright** for end-to-end browser tests and print checks; **security-guidance** (or **claude-security**) for a security pass over auth, uploads and permissions |

If a listed skill is not installed, continue without it and mention it in the final report.

At the end of Phase 2, create:

- `CLAUDE.md` at the repo root with the conventions and non-negotiable rules from this prompt (RTL, server-authoritative fees and validation, never log national IDs, no secrets in code).
- `.claude/skills/medical-form-rules/SKILL.md` — a project skill containing the fee rules (section 17), national ID rules (section 13), kinship and document rules (sections 14–15) and status transitions (section 16), so future sessions apply them consistently.

---

# 4. Required Production Architecture

```text
                              USERS (doctors, admins)
                                       │ HTTPS
                                       ▼
                      ┌────────────────────────────────┐
                      │ Azure Static Web Apps (Std)    │
                      │ React + TypeScript + Vite      │
                      │ Tailwind CSS, Arabic RTL       │
                      │                                │
                      │ /api/*  ── linked backend ──┐  │
                      └─────────────────────────────┼──┘
                                                    │ same-origin proxy
                                                    ▼
   ┌──────────────────────┐        ┌───────────────────────────────┐
   │ Microsoft Entra      │◄──────►│ Azure Container Apps          │
   │ External ID tenant   │  OIDC  │ Django + DRF + Gunicorn       │
   │ (doctor & admin      │        │ (BFF: session cookies)        │
   │  sign-in, sign-up)   │        └───────┬────────┬────────┬─────┘
   └──────────────────────┘                │        │        │  managed identity
                                           ▼        ▼        ▼
                                    PostgreSQL   Blob     Key Vault
                                    Flexible     Storage  (secrets)
                                    Server       (private)
                                           │
                                           ▼                 ┌──────────────────┐
                                    relational data          │ Azure OpenAI     │
                                                             │ (OCR, optional)  │
                                                             └──────────────────┘
```

Also use:

```text
Azure Container Registry ──► Django Docker image ──► Azure Container Apps
```

Add:

- Azure Application Insights / Azure Monitor for backend observability, with Log Analytics.
- Managed identities wherever practical (PostgreSQL, Blob, Key Vault, Azure OpenAI, ACR pull).
- GitHub Actions for CI/CD.
- Azure Bicep for infrastructure-as-code.

## 4.1 Same-origin API (important for cookies)

The SPA and the API must be same-site so the HttpOnly session cookie works in all browsers (third-party cookies are blocked). Use ONE of these, in this order of preference, and document the choice:

1. Azure Static Web Apps **Standard** plan with the Container App registered as a **linked backend**, so the browser calls `/api/...` on the SWA origin.
2. Custom domains on the same registrable domain (for example `app.example.org` and `api.example.org`) with cookies scoped appropriately.

Local development uses the Vite dev-server proxy for `/api`.

## 4.2 Hard rules

- Do NOT put PostgreSQL inside a Docker container in production.
- Do NOT store uploaded documents inside the Django container filesystem.
- Do NOT store uploaded image/PDF binary files inside PostgreSQL.
- Do NOT call AI/OCR services from the browser.

---

# 5. Repository Architecture

Create a monorepo:

```text
medical-insurance-platform/
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── ...
│
├── backend/
│   ├── config/
│   │   └── settings/ (base.py, development.py, test.py, production.py)
│   ├── apps/
│   │   ├── accounts/       users, roles, Entra OIDC login (BFF)
│   │   ├── doctors/        member profile
│   │   ├── applications/   applications, statuses, reference numbers, validation
│   │   ├── beneficiaries/
│   │   ├── documents/      metadata, Blob storage, upload validation
│   │   ├── fees/           fee schedules and fee engine
│   │   ├── ocr/            OCR providers, prompts, normalizers
│   │   ├── reference/      governorates, kinships, document rules, syndicate types
│   │   └── audit/
│   ├── manage.py
│   ├── requirements/ (base.txt, dev.txt, prod.txt)
│   ├── Dockerfile
│   ├── entrypoint.sh
│   └── ...
│
├── infrastructure/
│   ├── main.bicep
│   ├── modules/
│   ├── parameters/
│   └── scripts/            Entra app registration helper scripts
│
├── .github/workflows/ (frontend.yml, backend.yml, infrastructure.yml)
├── .claude/skills/medical-form-rules/SKILL.md
├── CLAUDE.md
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
└── docs/
```

Keep frontend, backend, infrastructure and deployment responsibilities clearly separated.

---

# 6. Frontend Technology Stack

Use:

- React
- TypeScript (strict)
- Vite
- Tailwind CSS
- React Router
- TanStack Query
- React Hook Form
- Zod
- A clean Fetch API wrapper (or Axios) that sends the CSRF header and handles the error format in section 46
- Vitest + Testing Library for unit/component tests
- Playwright for end-to-end tests

Avoid `any` unless absolutely unavoidable. Create reusable components.

Suggested structure:

```text
frontend/src/
├── api/                 typed API client, query keys
├── auth/                session hook, route guards
├── components/
│   ├── form/            NidInput, BoxStringInput, DashedField, RadioBoxGroup,
│   │                    ProgressStepper, ValidationErrorPanel, StickyActionBar
│   └── ui/              buttons, badges, modal, cards, table
├── features/
│   ├── application-form/
│   ├── applications/
│   ├── beneficiaries/
│   ├── documents/
│   ├── fees/
│   └── admin/
├── hooks/
├── i18n/                ar.ts (all UI strings; structure ready for English later)
├── layouts/
├── pages/
├── types/
├── utils/               digits normalization, formatting (ar-EG)
├── App.tsx
└── main.tsx
```

---

# 7. Language, RTL and Design System

## 7.1 Arabic first

- The whole UI is Arabic, right-to-left. Set `<html lang="ar" dir="rtl">` in `index.html` so there is no left-to-right flash.
- Font: **Cairo** (Google Fonts), with a sensible fallback stack.
- Keep every UI string in `frontend/src/i18n/ar.ts`. No hard-coded strings in components.
- Use logical CSS properties / Tailwind logical utilities (`ms-*`, `me-*`, `ps-*`, `pe-*`, `start-*`, `end-*`, `text-start`). Do not use `ml-*`/`mr-*`/`left-*`/`right-*` for layout.
- Inputs whose content is left-to-right — national ID, phone, email, years, numbers — get `dir="ltr"`.
- Accept Eastern Arabic digits (٠١٢٣٤٥٦٧٨٩) in every numeric input; normalize to Western digits before validation and storage (frontend AND backend).
- Display money and dates with the `ar-EG` locale (for example `3٬025 ج.م`, `٣ أكتوبر ٢٠٢٦`). Store Western digits and ISO dates.
- Mirror directional icons (arrows, chevrons) in RTL; do not mirror logos, checkmarks or media icons.

## 7.2 Design tokens (from the prototype)

Define these as Tailwind theme colors and use them consistently:

```text
banana        #F5E642   primary call-to-action background
banana-deep   #C4B800   CTA hover
banana-light  #FDFBE8
teal          #0FA571   progress, success, money
teal-deep     #0A7A55
teal-light    #E3F8F0
charcoal      #1A1A2E   main text
slate         #4A5568
muted         #718096
smoke         #F7F8FA   page background
white         #FFFFFF
border        #E8EAED
border-hover  #CBD5E0
danger        #E53E3E   errors
danger-light  #FFF5F5
success       #38A169
warning       #D69E2E
```

Inside the paper-form area: black 1.5px borders, white background, entered values in blue (`blue-700`) like ink on paper, bold labels in near-black.

## 7.3 Status colors

| Status | Arabic label | Background | Text |
|---|---|---|---|
| DRAFT | مسودة | `#F7F8FA` | `#4A5568` |
| SUBMITTED | مقدم | `#FDFBE8` | `#744210` |
| UNDER_REVIEW | قيد المراجعة (pulsing dot) | `#EBF4FF` | `#2B6CB0` |
| NEEDS_CORRECTION | يحتاج تصحيح | `#FFFBEB` | `#92400E` |
| APPROVED | مقبول (check icon) | `#E3F8F0` | `#0A7A55` |
| REJECTED | مرفوض | `#FFF5F5` | `#742A2A` |

---

# 8. Frontend Pages and Routes

## Public

```text
/                      Landing page: union header, short explanation,
                       "تسجيل الدخول" and "إنشاء حساب" buttons (both go to Entra External ID)
/signed-out            Signed-out confirmation
```

Registration, email verification and password reset are handled by Entra External ID hosted pages (section 27). Do not build password forms in the SPA.

## Doctor

```text
/dashboard
/profile
/application/new                   creates a draft (or opens the existing one for the fiscal year)
/application/:id                   redirects to the right step
/application/:id/form              paper-form replica — wizard steps 1, 2, 3 (section 9)
/application/:id/payment           step 4 — fee summary + payment receipt upload
/application/:id/review            step 5 — read-only review, server validation, declaration, submit
/application/:id/status            confirmation + status timeline + review notes
/application/:id/print             A4 print view
```

## Administrator

```text
/admin/dashboard
/admin/applications
/admin/applications/:id
/admin/applications/:id/print
/admin/doctors
/admin/doctors/:id
/admin/fee-schedules
```

Every page must be responsive and usable on desktop, tablet and mobile. Printing always uses the A4 desktop layout.

---

# 9. The Paper-Form Replica (FormPage)

The main doctor screen is a faithful digital replica of the paper form, ported from the prototype's `FormPage.jsx`, `MemberSection.jsx`, `BeneficiaryTable.jsx` and `DeclarationSection.jsx`.

## 9.1 Page frame

- Sticky **ProgressStepper** at the top with five steps:

  ```text
  1 البيانات   →   2 المستفيدون   →   3 المستندات   →   4 الإيصال   →   5 المراجعة
  ```

  Completed steps show a teal check, the current step a pulsing banana circle, upcoming steps grey. Labels hide below 640px. Steps 1–3 are sections of the form page (scroll anchors `#member`, `#beneficiaries`, `#documents`); steps 4 and 5 are separate routes. Step completion comes from the server validation endpoint (section 24).
- Sticky top bar: sign-out icon button, title `استمارة اشتراك — {fiscal year}`, print icon button, and an autosave indicator (`جارٍ الحفظ…` / `تم الحفظ` / `تعذّر الحفظ — إعادة المحاولة`).
- Centered card (max width ~900px) holding the A4 form.
- **Validation error panel** above the card when the doctor tries to continue with errors: title `يرجى تصحيح الأخطاء التالية قبل المتابعة:`, a bullet list of ALL errors, red start border, scrolled into view. Also show each error inline under its field.
- **Fee summary card** below the form (section 17.6).
- Fixed bottom **action bar**: text button `تسجيل الخروج` (start side), outlined teal `طباعة`, primary banana `متابعة لرفع الإيصال`. Continuing runs server validation for steps 1–3 and navigates to `/application/:id/payment` only when they pass.

## 9.2 Form header (inside the card)

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ اتحاد نقابات المهن الطبية          استمارة اشتراك بمشروع العلاج      ┌───────┐ │
│ ─────────────────                   ( أول مرة - إضافة )             │ صورة  │ │
│ مشروع علاج الأعضاء وأسرهم                                            │ العضو │ │
│                                                                      │الأصلي │ │
│                                                                      └───────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

The photo box (about 112×144px, black border) is clickable to upload the member photo (`PERSONAL_PHOTO`, image only) and shows the uploaded photo.

Add an application-type selector styled like the paper boxes: `أول مرة` / `إضافة` (section 16.1).

## 9.3 Mandatory attachments panel (screen only, hidden in print)

Placed BEFORE the member fields so OCR can fill them:

- Title `مرفقات العضو الأصلي الإلزامية` and hint: `بعد رفع كل صورة، اضغط مسح تلقائي لاستخراج البيانات منها تلقائياً — يمكنك التعديل يدوياً بعد ذلك.`
- Three **SmartUpload** slots in a 3-column grid (1 column on mobile):
  - `صورة البطاقة (وجه)` → `NATIONAL_ID_FRONT`
  - `صورة البطاقة (ظهر)` → `NATIONAL_ID_BACK`
  - `كارنيه النقابة` → `SYNDICATE_ID`

## 9.4 Member field grid

12-column grid on desktop, same order and grouping as the paper (labels on the start side, dashed underline inputs, box-style radio groups):

| Row | Fields |
|---|---|
| 1 | `الـنـقـابـة :` radio boxes بشري / صيدلي / أسنان / بيطري (6 cols) · `النقابة الفرعية :` (3) · `رقم قيد النقابة :` (3) |
| 2 | `رقم بطاقة العلاج :` (5) · `سنة قيد النقابة :` (3) · `حالة العميل :` radio boxes يعمل / معاش / متوفى (4) |
| 3 | `أسم العضو :` (8) · `الديانة :` radio boxes مسلم / مسيحي (4) |
| 4 | `الرقم القومي :` 14-box NidInput (8) · `النوع :` radio boxes ذكر / أنثى (4) |
| 5 | `سنة الميلاد :` (5) · `محافظة السكن :` select of the 27 governorates (3) · `الحي :` (4) |
| 6 | `العنوان :` (8) · `المحمول :` (4, `dir="ltr"`) |
| 7 | `البريد الالكتروني :` 26-box BoxStringInput (12), prefilled from the Entra account |

Below 768px, stack fields one per row with the label above the input.

`سنة الميلاد` and `النوع` auto-fill from a valid national ID (section 13) when empty; if the doctor typed a different value, show a validation error.

## 9.5 Beneficiaries table — `بيانات المستفيدين مع العضو الأصلى`

- Paper-style bordered table with exactly `MAX_BENEFICIARIES` rows (default 10, configurable):

  ```text
  م | درجة القرابة | اسم المستفيد | سنة الميلاد | الرقم القومي (14 small boxes)
  ```

- `درجة القرابة` is a select with the kinship list from section 14.
- When a row has a kinship, a paperclip button appears beside the row number (screen only). Grey = documents missing, green = all required documents attached. It opens the **DocumentModal** for that beneficiary.
- Changing a row's kinship asks for confirmation if documents exist, then removes that row's documents (prototype behavior) because the required set changes.
- Clearing a row (empty name and kinship) deletes the beneficiary and its documents after confirmation.
- Below 768px, show each beneficiary as a card instead of a table row; print always uses the table.

## 9.6 Documents section (step 3, `#documents`)

A checklist generated from the rules in section 15 for the member and every active beneficiary: document label, status (✓ attached / missing / optional), and an upload or replace button. This is the single place to confirm everything is attached before continuing.

## 9.7 Declaration — `إقــــــــرار`

Render this text exactly (the underlined part in red-underlined bold), with an inline dashed input for the name:

```text
أقر أنا / [declaration_name] أن جميع البيانات بعاليه صحيحة وكذلك صور المستفيدين وأن الأولاد في الدراسة ولم يتخرجوا وأن بناتي المدونة أسماءهم لم يتزوجوا بعد واتعهد باخطار المشروع فور زواجهم
<u>مع العلم انه لا يجوز استفادة الابن بعد التخرج أو الابنة بعد الزواج واذا ثبت عكس ذلك أتحمل المسئولية المالية والقانونية فورا مع عدم رد قيمة الاشتراك وتحمل كافة التكاليف وللمشروع الحق في اتخاذ اي اجراء مناسب لذلك .</u>
وأقر بالموافقة علي النظام العلاجي الذي يسير عليه المشروع وأي تعديلات تتم اثناء العام الصادرة من لجنة العلاج العليا للمشروع وأتبرع تكافلا بمبلغ اشتراكي لعلاج زملائى المشتركين وأتعاون معهم في سداد قيمة العلاج.
```

Then a signature block on the end side: `المقر بما فيه` above a dotted line (for the printed copy).

`declaration_name` must match the member name (normalized: trimmed, collapsed spaces, unified Arabic letter variants such as أ/إ/آ→ا and ة/ه, ى/ي). On the review page the doctor must also tick an explicit acceptance checkbox; store `declaration_accepted_at`.

## 9.8 Print (A4)

- `@page { size: A4; margin: 0; }` with internal padding, `print-color-adjust: exact`.
- Hide app chrome, stepper, action bar, attachments panel, paperclips and modals.
- Show header, photo, all fields, the full beneficiaries table, the declaration and signature line, plus the reference number and submission date when they exist.
- Fit on one or two A4 pages. Verify with a Playwright PDF render in Phase 9.

---

# 10. Form State (port of FormContext)

Port `FormContext.jsx` into `ApplicationFormProvider` + `useApplicationDraft`, but the server is now the source of truth.

## 10.1 State shape (frontend type, camelCase; API uses snake_case)

```ts
type ApplicationFormState = {
  applicationType: 'FIRST_TIME' | 'ADDITION';
  syndicateType: SyndicateType | '';
  subSyndicate: string;
  registrationNumber: string;
  treatmentCardNumber: string;
  syndicateRegistrationYear: string;   // 4 digits
  workStatus: WorkStatus | '';
  memberName: string;
  religion: Religion | '';
  nationalId: string;                  // 14 Western digits
  gender: Gender | '';
  birthYear: string;
  governorate: string;                 // one of the 27 governorates
  neighborhood: string;
  address: string;
  mobile: string;
  email: string;
  beneficiaries: BeneficiaryRow[];     // always MAX_BENEFICIARIES rows in the UI
  declarationName: string;
};

type BeneficiaryRow = {
  id?: string;                         // server UUID once created
  kinship: Kinship | '';
  name: string;
  birthYear: string;
  nationalId: string;
  documents: Partial<Record<BeneficiaryDocumentType, DocumentSummary>>;
};
```

Main member documents (`NATIONAL_ID_FRONT`, `NATIONAL_ID_BACK`, `SYNDICATE_ID`, `PERSONAL_PHOTO`) and the receipt are `DocumentSummary` objects from the server, never raw `File` objects kept until the end.

## 10.2 Behaviors to keep from the prototype

- `updateField(field, value)` and `updateBeneficiary(index, field, value)`.
- OCR merge rule (`handleOcrResult`, `updateBeneficiaryBatch`): extracted values fill ONLY fields that are currently empty; never overwrite what the doctor typed.
- Changing a beneficiary's kinship clears that row's documents (with confirmation).
- Signing out clears all form state and the TanStack Query cache.

## 10.3 New behaviors

- **Draft autosave**: debounce (~800ms) and `PATCH` the application/profile/beneficiary that changed. Show the autosave indicator. Retry with backoff on network errors; never lose typed data (keep unsaved edits in memory and warn with `beforeunload` if unsaved).
- Drafts accept incomplete data but still enforce formats (digits only where needed, max lengths). Completeness is checked by the validation endpoint and at submit.
- **Upload on select**: when a file is chosen, upload it immediately (`POST /documents`) with progress; show the thumbnail from a short-lived URL returned by the server.
- **Fee quote**: after each successful autosave, refetch `GET /applications/{id}/fees/` and show it in the FeeSummaryPanel. The frontend never calculates fees.
- **Reference data** (governorates, kinships, document rules, syndicate types, statuses) comes from `GET /api/v1/reference-data/`, cached by TanStack Query. The frontend never duplicates these rules.
- Read-only mode when the application status is not editable (section 16).

---

# 11. Shared Form Components

Port and type these components; keep their look and keyboard behavior:

- **NidInput**: 14 single-character boxes, `dir="ltr"`, digits only (normalize Arabic-Indic), auto-advance on type, Backspace on an empty box moves back, paste fills all boxes, `size="large" | "small"`. Accessible: one `role="group"` with an `aria-label`, one visually-hidden full-value input or equivalent so screen readers read a single value. On narrow screens it may switch to a single masked input that displays digits in boxes.
- **BoxStringInput**: same pattern for free text (email, length 26), `dir="ltr"`, wraps on small screens.
- **DashedField**: label + dashed-underline input.
- **RadioBoxGroup**: label + bordered boxes acting as a radio group (selected = grey inset). Real radio inputs underneath for accessibility and keyboard arrows.
- **SmartUpload**: file picker (images + PDF), thumbnail, upload progress, `مسح تلقائي` button for OCR-capable document types, progress bar while scanning, messages `✓ تم الإرفاق: {name}`, `✓ تم استخراج البيانات — راجع الحقول أدناه وعدّل إن لزم`, `فشل المسح التلقائي. يمكنك إدخال البيانات يدوياً.`
- **DocumentModal**: title `مستندات المستفيد: {name}`, one slot per required/optional document for that beneficiary's kinship (rules from the server), SmartUpload for OCR-capable types (`BENEFICIARY_NATIONAL_ID`, `BIRTH_CERTIFICATE`), plain upload for others, `حفظ وإغلاق` button. Accessible modal (focus trap, Escape closes, labelled).
- **ProgressStepper**, **ValidationErrorPanel**, **StickyActionBar**, **StatusBadge**, **FeeSummaryPanel**.

---

# 12. Doctor (Member) Model

Create a `Doctor` profile model (1:1 with User):

```text
Doctor
------
id                            UUID (public identifier)
user_id                       1:1 → User
full_name
national_id                   14 digits, UNIQUE
date_of_birth                 derived from national ID
birth_year
gender                        MALE | FEMALE            (ذكر | أنثى)
religion                      MUSLIM | CHRISTIAN       (مسلم | مسيحي)
phone_number                  Egyptian mobile, normalized
email                         from Entra (verified)
syndicate_type                HUMAN_MEDICINE | PHARMACY | DENTISTRY | VETERINARY
                              (بشري | صيدلي | أسنان | بيطري)
sub_syndicate                 النقابة الفرعية
syndicate_registration_number رقم قيد النقابة
syndicate_registration_year   سنة قيد النقابة
treatment_card_number         رقم بطاقة العلاج (nullable; first-time members have none)
governorate                   محافظة السكن (one of 27)
neighborhood                  الحي
address                       العنوان
created_at, updated_at
```

- Do not use national ID as the primary key.
- Index `(syndicate_type, syndicate_registration_number)`; do not make it unique unless confirmed (open question).
- Religion is sensitive data collected because the paper form requires it; document this in `docs/security.md` as a legal/organizational decision.

---

# 13. Egyptian National ID Rules

Implement as a modular validator/parser (`backend/apps/reference/national_id.py`), mirrored for UX in the frontend:

```text
Position  1      century: 2 = 1900–1999, 3 = 2000–2099
Positions 2–7    YYMMDD date of birth (must be a real date, not in the future)
Positions 8–9    governorate-of-birth code (lookup table below)
Positions 10–13  sequence; position 13 odd = male, even = female
Position  14     check digit (do NOT validate it unless the algorithm is confirmed)
```

- Accept Arabic-Indic digits; normalize; strip spaces.
- Derive `date_of_birth`, `birth_year` and `gender`; validate consistency with entered values.
- Governorate codes (keep as a reference table; verify before relying on it for hard validation — unknown codes should be a warning, not a block):

  ```text
  01 القاهرة  02 الإسكندرية  03 بورسعيد  04 السويس  11 دمياط  12 الدقهلية  13 الشرقية
  14 القليوبية  15 كفر الشيخ  16 الغربية  17 المنوفية  18 البحيرة  19 الإسماعيلية
  21 الجيزة  22 بني سويف  23 الفيوم  24 المنيا  25 أسيوط  26 سوهاج  27 قنا  28 أسوان
  29 الأقصر  31 البحر الأحمر  32 الوادي الجديد  33 مطروح  34 شمال سيناء  35 جنوب سيناء
  88 خارج الجمهورية
  ```

- Residence governorates (the select in row 5) are the 27 governorates: القاهرة، الجيزة، الإسكندرية، الدقهلية، البحر الأحمر، البحيرة، الفيوم، الغربية، الإسماعيلية، المنوفية، المنيا، القليوبية، الوادي الجديد، السويس، أسوان، أسيوط، بني سويف، بورسعيد، دمياط، الشرقية، جنوب سيناء، كفر الشيخ، مطروح، الأقصر، قنا، شمال سيناء، سوهاج.
- Never log a full national ID. Mask in logs and admin lists as `29•••••••••123` style (first 2 + last 3).

---

# 14. Beneficiary Model

A beneficiary belongs to ONE application (a per-fiscal-year snapshot, because sons graduate and daughters marry). Do not create separate tables per relationship.

```text
Beneficiary
-----------
id               UUID
application_id   → InsuranceApplication
row_number       1..MAX_BENEFICIARIES (unique per application)
kinship          enum below
full_name        (OCR fills the first three names; see 21.4)
birth_year
national_id      nullable (young children may not have one)
created_at, updated_at
```

Kinship enum (Arabic labels exactly as on the prototype):

| Value | Arabic | Fee key |
|---|---|---|
| `MOTHER` | أم | parent |
| `FATHER` | أب | parent |
| `SON_MINOR` | ابن (18 سنة أو أقل) | child |
| `SON_UNIVERSITY` | ابن (طالب جامعي) | gradSon |
| `SON_GRADUATE` | ابن (خريج) | gradSon |
| `DAUGHTER` | ابنة | child |
| `HUSBAND` | زوج | spouse |
| `WIFE` | زوجة | spouse |

Brother, sister and "other" are intentionally NOT supported (they have no fee in the schedule). Keep the enum extensible.

Rules:

- Unique `(application_id, national_id)` when national ID is present; a beneficiary's national ID cannot equal the member's.
- `birth_year` between 1920 and the fiscal year.
- `HUSBAND` requires a female member; `WIFE` requires a male member (configurable check, flag as open question).
- `SON_MINOR` must be 18 or younger in the fiscal year (configurable check, flag as open question).
- Cross-application duplicates (the same child listed by two parents who are both members) are a WARNING shown to admins, not a block.

---

# 15. Required Documents (single rules table)

Implement ONE rules table in `backend/apps/reference/document_rules.py`, exposed through `/api/v1/reference-data/`, used by the validator, the DocumentModal and the documents checklist.

Member (always):

| Document | Required |
|---|---|
| `NATIONAL_ID_FRONT` | yes |
| `NATIONAL_ID_BACK` | yes |
| `SYNDICATE_ID` | yes |
| `PERSONAL_PHOTO` | configurable (`REQUIRE_MEMBER_PHOTO`, default false) |
| `PAYMENT_RECEIPT` | yes, before submission (step 4) |

Beneficiaries (age = fiscal year − birth year):

| Kinship | Required documents |
|---|---|
| HUSBAND / WIFE | `BENEFICIARY_NATIONAL_ID`, `MARRIAGE_CERTIFICATE`, `INSURANCE_PRINT` (برينت تأميني) |
| MOTHER / FATHER | `BENEFICIARY_NATIONAL_ID` |
| SON_MINOR / DAUGHTER | `BIRTH_CERTIFICATE` if age < 16 OR the member is female; `BENEFICIARY_NATIONAL_ID` if age ≥ 16 (optional below 16) |
| SON_UNIVERSITY | child rule above + `UNIVERSITY_ID` (كارنيه الجامعة) |
| SON_GRADUATE | child rule above + `INSURANCE_PRINT` |

The prototype's validator required both birth certificate and national ID for every child while its dialog labels described the age-16 rule above. Implement the age-aware rule, keep the threshold (16) configurable, and list it as an open business question.

Arabic document labels:

```text
NATIONAL_ID_FRONT        صورة البطاقة (وجه)
NATIONAL_ID_BACK         صورة البطاقة (ظهر)
SYNDICATE_ID             كارنيه النقابة
PERSONAL_PHOTO           صورة العضو الأصلي
PAYMENT_RECEIPT          إيصال الدفع
BENEFICIARY_NATIONAL_ID  بطاقة الرقم القومي
BIRTH_CERTIFICATE        شهادة الميلاد
MARRIAGE_CERTIFICATE     شهادة الزواج
INSURANCE_PRINT          برينت تأميني
UNIVERSITY_ID            كارنيه الجامعة
OTHER                    مستند آخر
```

---

# 16. Insurance Applications

## 16.1 Model

```text
InsuranceApplication
--------------------
id                       UUID
doctor_id                → Doctor
fiscal_year              e.g. 2026
application_type         FIRST_TIME | ADDITION   (أول مرة | إضافة)
work_status              WORKING | PENSIONER | DECEASED   (يعمل | معاش | متوفى)
status                   see 16.2
payment_status           NOT_UPLOADED | PENDING_REVIEW | CONFIRMED | REJECTED
reference_number         nullable until first submission, UNIQUE
declaration_name
declaration_accepted_at
fee_snapshot             JSON (tier, breakdown, admin fee, total, schedule id) — set at submission
fee_schedule_id          → FeeSchedule used for the snapshot
submitted_snapshot       JSON copy of member + beneficiaries at submission (for audit and print)
review_notes             doctor-visible reviewer message
reviewed_by, reviewed_at
submitted_at, created_at, updated_at
```

- Partial unique constraint: one application per doctor per fiscal year whose status is not `REJECTED` (concurrency-safe; return `ACTIVE_APPLICATION_EXISTS`).
- `work_status` lives on the application because it affects that year's fee.
- Fee rules for `ADDITION` are not defined in the prototype: calculate exactly like `FIRST_TIME` and list it as an open question.

## 16.2 Statuses and transitions

```text
DRAFT  NEEDS_CORRECTION  →  editable by the doctor
SUBMITTED  UNDER_REVIEW  APPROVED  REJECTED  →  read-only for the doctor
```

| From | To | Who | Conditions |
|---|---|---|---|
| DRAFT | SUBMITTED | doctor | full validation passes, receipt uploaded, declaration accepted |
| SUBMITTED | UNDER_REVIEW | admin | — |
| SUBMITTED / UNDER_REVIEW | NEEDS_CORRECTION | admin | `review_notes` required |
| UNDER_REVIEW | APPROVED | admin | `payment_status = CONFIRMED` |
| SUBMITTED / UNDER_REVIEW | REJECTED | admin | `review_notes` required |
| NEEDS_CORRECTION | SUBMITTED | doctor | full validation passes again; may replace documents and receipt |

- Implement transitions in one service (`applications/services.py::transition`) with `select_for_update`, permission checks, audit log entries and an explicit table. Reject every other transition with `INVALID_STATUS_TRANSITION`.
- `REJECTED` is final; the doctor may start a new application for the same fiscal year (open question).
- Doctors never write `status`, `payment_status`, `reference_number`, `fee_snapshot`, `review_notes` or reviewer fields. Serializers must make them read-only.

## 16.3 Reference numbers

- Format `MED-{fiscal_year}-{6-digit sequence}`, for example `MED-2026-000123`.
- Generate at FIRST submission inside the same transaction, using a per-year counter row locked with `select_for_update` (or a PostgreSQL sequence per year). Never reuse numbers. Resubmission keeps the same number.

---

# 17. Fee Calculation Service (port of CalculationService)

The server is authoritative. Port `CalculationService.js` into `backend/apps/fees/services.py` as pure, fully tested functions.

## 17.1 Fee schedule (stored in the database)

Create a `FeeSchedule` model per fiscal year (admin-editable, audited). Once an application has been submitted with a schedule, that schedule version becomes read-only (create a new version to change it). Seed FY 2026 with a data migration:

| Tier | member | spouse | child | gradSon | parent |
|---|---|---|---|---|---|
| 1 | 600 | 800 | 500 | 1200 | 1050 |
| 2 | 700 | 950 | 550 | 1400 | 1200 |
| 3 | 750 | 1000 | 550 | 1500 | 1300 |
| 4 | 850 | 1050 | 600 | 1750 | 1400 |

```text
admin_fee_member_only         150 EGP   (no active beneficiaries)
admin_fee_with_beneficiaries  175 EGP   (at least one active beneficiary)
age_cap_threshold             70 years
age_cap_amount                500 EGP
tier_boundaries               years since registration: ≤5 → 1, ≤10 → 2, ≤15 → 3, otherwise 4
registration_year_min         1950
```

Amounts are whole Egyptian pounds; use `Decimal`/integers, never floats.

## 17.2 Rules

1. `years = fiscal_year − syndicate_registration_year`. Tier from the boundaries above.
2. `work_status = PENSIONER` (معاش) → always tier 4.
3. Member fee = tier `member` fee, but `age_cap_amount` if member age ≥ 70 (age = fiscal_year − birth_year). Note: `تم تطبيق سقف 500 ج (عمر {age} سنة)`.
4. Each active beneficiary (has kinship AND a non-empty name) adds the fee for its fee key (section 14).
5. The age cap applies to the spouse (HUSBAND/WIFE) when the spouse is ≥ 70. It does NOT apply to parents or children.
6. Admin fee: 175 if any active beneficiary, else 150. Breakdown label `رسوم إدارية`.
7. Total = sum of the breakdown.
8. Invalid registration year (missing, not 4 digits, < 1950 or > fiscal year) → `is_valid = false` with message `يرجى إدخال سنة قيد النقابة بشكل صحيح لحساب الاشتراك.`
9. `DECEASED` (متوفى) is calculated like `WORKING` (as in the prototype) — open question.

## 17.3 Output

```json
{
  "fiscal_year": 2026,
  "tier": 3,
  "breakdown": [
    {"label": "العضو الأصلي", "fee": 750, "note": ""},
    {"label": "<beneficiary name>", "fee": 1000, "note": ""},
    {"label": "رسوم إدارية", "fee": 175, "note": ""}
  ],
  "admin_fee": 175,
  "total": 1925,
  "is_valid": true,
  "error_message": "",
  "schedule_id": "<uuid>"
}
```

## 17.4 Worked examples (use as table-driven tests; FY 2026)

| # | Registration year / work status | Member birth year | Beneficiaries | Expected |
|---|---|---|---|---|
| 1 | 2023 / WORKING | 1995 | none | tier 1: 600 + 150 = **750** |
| 2 | 2014 / WORKING | 1985 | WIFE 1988, SON_MINOR 2015, DAUGHTER 2018 | tier 3: 750 + 1000 + 550 + 550 + 175 = **3025** |
| 3 | 1990 / PENSIONER | 1950 (age 76) | WIFE 1955 (age 71), SON_GRADUATE 1995 | tier 4: 500 (cap) + 500 (cap) + 1750 + 175 = **2925** |
| 4 | 2018 / WORKING | 1990 | MOTHER 1960, SON_UNIVERSITY 2005 | tier 2: 700 + 1200 + 1400 + 175 = **3475** |
| 5 | boundaries | — | — | 2021 → tier 1, 2016 → tier 2, 2011 → tier 3, 2010 → tier 4 |
| 6 | age boundary | 1956 (age 70) / 1957 (age 69) | none | cap applies at 70; not at 69 |
| 7 | 1949 or 2027 | — | — | `is_valid = false` |
| 8 | 2023 / WORKING | 1995 | row with kinship but empty name | ignored; admin fee stays 150 |
| 9 | 2023 / WORKING | 1995 | FATHER 1950 (age 76) | tier 1: 600 + 1050 (no cap for parents) + 175 = **1825** |

## 17.5 API

- `GET /api/v1/applications/{id}/fees/` → quote computed from the saved draft.
- At submission, recompute and store `fee_snapshot` + `fee_schedule_id`. Admins always see the snapshot for submitted applications.

## 17.6 FeeSummaryPanel (UI)

Card with teal start border: title `ملخص الاشتراك — السنة المالية {FY}`, badge `الدرجة {tier}`, rows (label · amber note · amount `ar-EG` + `ج.م`), total row `الإجمالي`. While a quote is loading show a skeleton; if invalid, show the error message. The same summary appears on the payment and review pages.

---

# 18. Payment Receipt (step 4)

Port `ReceiptPage.jsx`:

- Back link `← رجوع للاستمارة`.
- Fee summary card (banana header `ملخص الرسوم`).
- Payment instructions text (configurable by admins; placeholder text until the organization provides it).
- Receipt drop zone: `اسحب صورة الإيصال هنا` / `أو اضغط للاختيار`, accepted `JPG, PNG, WEBP` (PDF optional by config), max 8 MB, minimum 400×300 pixels.
- Uploaded file bar with name, size and `إزالة`.
- Upload creates a `PAYMENT_RECEIPT` document and sets `payment_status = PENDING_REVIEW` (server-side).
- Continue button → review page.
- Validate type, size and pixel dimensions on the server with Pillow (frontend pre-check only for UX). Reject images that fail to decode.
- Only admins can set `CONFIRMED` / `REJECTED`; rejecting a receipt should normally come with `NEEDS_CORRECTION` and a note.

---

# 19. Documents

Document metadata in PostgreSQL; files in Azure Blob Storage.

```text
Document
--------
id                 UUID
application_id     → InsuranceApplication
beneficiary_id     nullable → Beneficiary
document_type      see section 15
blob_name          server-generated
original_filename  sanitized, for display only
content_type       detected server-side
file_size
sha256             for integrity and duplicate detection
scan_status        PENDING | CLEAN | INFECTED | SKIPPED   (ready for malware scanning)
uploaded_by        → User
created_at
deleted_at         soft delete (drafts only)
```

- One active document per `(application, beneficiary, document_type)`; uploading again replaces it (old one soft-deleted, blob deleted by a cleanup job or lifecycle policy).
- Documents can only be added, replaced or deleted while the application is editable.
- A periodic cleanup (management command, runnable as a Container Apps job) removes blobs whose metadata was soft-deleted or never committed.

---

# 20. Azure Blob Storage Organization

Use a PRIVATE container; never public.

```text
medical-documents/
└── applications/
    └── {application_uuid}/
        ├── doctor/
        │   ├── national-id-front-{uuid}.jpg
        │   ├── national-id-back-{uuid}.jpg
        │   ├── syndicate-id-{uuid}.pdf
        │   ├── personal-photo-{uuid}.jpg
        │   └── payment-receipt-{uuid}.jpg
        └── beneficiaries/
            └── {beneficiary_uuid}/
                ├── national-id-{uuid}.jpg
                ├── birth-certificate-{uuid}.pdf
                └── ...
```

- Generate blob names on the server. Never trust browser paths or filenames.
- Store only metadata and blob identifiers in PostgreSQL.
- Enable soft delete and versioning for blobs (section 48).

---

# 21. OCR (server-side automatic extraction)

Port `OcrService.js` to `backend/apps/ocr/`. OCR is a convenience: it SUGGESTS values; the doctor confirms them.

## 21.1 Flow

1. The document is uploaded first (section 19).
2. The frontend calls `POST /api/v1/documents/{id}/extract/`.
3. Django checks authorization, rate limits (per user, configurable, e.g. 30/hour), reads the blob with managed identity, sends it to the OCR provider, normalizes the result and returns suggested fields. Nothing is saved automatically.
4. The frontend merges suggestions into EMPTY fields only (section 10.2) and shows the success message.

## 21.2 Provider

- Define an `OcrProvider` interface with `AzureOpenAIProvider` (default) and `MockProvider` (local development and tests).
- `AzureOpenAIProvider`: Azure OpenAI resource with a vision-capable chat model deployment (deployment name and API version from settings; check regional availability), authenticated with managed identity (`Cognitive Services OpenAI User` role), using structured outputs (JSON schema) instead of parsing free text.
- Feature flag `OCR_ENABLED`; when off, hide the `مسح تلقائي` button.
- PDFs: convert the first page to an image server-side before sending, or skip OCR for PDFs with a clear message.
- Do not log images, prompts containing personal data, or extracted values.

## 21.3 Extraction schemas (port the Arabic prompts from the prototype)

| Document | Returned fields |
|---|---|
| `NATIONAL_ID_FRONT` | `member_name`, `national_id`, `birth_year` (derived from the ID), `governorate`, `neighborhood`, `address` |
| `NATIONAL_ID_BACK` | `gender` (ذكر/أنثى), `religion` (مسلم/مسيحي) |
| `SYNDICATE_ID` | `registration_number`, `sub_syndicate`, `syndicate_registration_year` (year only, from `تاريخ القيد`), `syndicate_type` (بشري/صيدلي/أسنان/بيطري from the header strip) |
| `BENEFICIARY_NATIONAL_ID` / `BIRTH_CERTIFICATE` | `name` (first three names), `national_id`, `birth_year` |

Map Arabic values to enums; map governorate text to the closest of the 27 governorates or leave it empty.

## 21.4 Normalizers (port and unit-test)

- Eastern Arabic digits → Western.
- National ID: first run of 14 digits after normalization.
- Birth year from the national ID (`2` → 19YY, `3` → 20YY); otherwise first `19xx`/`20xx` year in the date text; otherwise first four digits.
- Year extraction from dates like `٢٠٢١-٠٤-٢٨`, `2021/04/28`, `تاريخ القيد ٢٠٢١-٠٤-٢٨`, `٢٨-٠٤-٢٠٢١`.
- Triple name: split on whitespace; join `عبد`, `أبو`, `ابو` with the next word as one name; keep the first three names.

## 21.5 Privacy

Sending ID images to an AI service is a data-processing decision. Document in `docs/security.md` what is sent, where (Azure region), retention and abuse-monitoring behavior, and mark it as requiring legal approval before production use. OCR must be disable-able without code changes.

---

# 22. Validation Rules (port of validateForm)

Two levels:

- **Draft level** (every autosave): types, formats, lengths, enum values, digits normalization. Incomplete is OK.
- **Submission level** (`GET /validation/` and `POST /submit/`): everything below. Return ALL errors at once, grouped by step, with field paths and the Arabic messages.

| # | Rule | Arabic message |
|---|---|---|
| 1 | syndicate type required | يرجى اختيار نوع النقابة |
| 2 | member name ≥ 5 characters (and at least three names recommended) | اسم العضو يجب أن يكون 5 أحرف على الأقل |
| 3 | national ID valid (section 13) | الرقم القومي يجب أن يكون 14 رقماً صحيحاً |
| 4 | gender required and consistent with national ID | يرجى تحديد النوع (ذكر/أنثى) |
| 5 | work status required | يرجى تحديد حالة العمل |
| 6 | registration year 1950..fiscal year | سنة قيد النقابة غير صحيحة |
| 7 | mobile matches `^(\+20\|0020\|0)?1[0125]\d{8}$` | رقم الهاتف المحمول غير صحيح |
| 8 | national ID front attached | يرجى إرفاق صورة وجه البطاقة الشخصية |
| 9 | national ID back attached | يرجى إرفاق صورة ظهر البطاقة الشخصية |
| 10 | syndicate ID attached | يرجى إرفاق صورة كارنيه النقابة |
| 11 | beneficiary with a name needs a kinship | المستفيد رقم {n}: يرجى تحديد درجة القرابة |
| 12 | beneficiary birth year 1920..fiscal year | المستفيد {name}: سنة الميلاد غير صحيحة |
| 13 | beneficiary required documents (section 15) | المستفيد {name}: مستند {label} مطلوب |
| 14 | governorate, address, sub-syndicate, registration number, birth year required | يرجى إدخال {field} |
| 15 | declaration name matches the member name | اسم المقر يجب أن يطابق اسم العضو |
| 16 | receipt uploaded (submit only) | يرجى رفع إيصال الدفع |
| 17 | declaration accepted (submit only) | يرجى الموافقة على الإقرار |
| 18 | national ID not used by another doctor | الرقم القومي مسجل لعضو آخر |

Plus the beneficiary rules in section 14. The frontend Zod schemas mirror the field-level rules for instant feedback, but the server result is what gates navigation and submission.

---

# 23. Backend

Use:

- Python 3.12+
- Django (current LTS) + Django REST Framework
- PostgreSQL via psycopg 3
- Gunicorn
- django-cors-headers (development only; production is same-origin)
- django-filter
- Pillow (image validation, dimensions, PDF/HEIC handling if enabled)
- python-magic or equivalent for content-type sniffing
- azure-storage-blob, azure-identity, azure-keyvault-secrets
- openai SDK (Azure OpenAI) for OCR
- msal (or a maintained OIDC library) for Entra sign-in
- azure-monitor-opentelemetry
- structured JSON logging
- pytest, pytest-django, factory_boy, ruff

Use Django ORM. Do NOT construct raw SQL for normal CRUD. Keep business logic in service modules, not views.

---

# 24. REST API

Versioned under `/api/v1/`. Consistent snake_case JSON.

```text
Auth (BFF)
GET    /api/v1/auth/login/?next=/dashboard     redirect to Entra (doctor sign-in/sign-up)
GET    /api/v1/auth/callback/                  OIDC callback → session cookie → redirect
POST   /api/v1/auth/logout/                    end session (+ Entra sign-out URL)
GET    /api/v1/auth/me/                        user, role, csrf token bootstrap

Reference data
GET    /api/v1/reference-data/                 governorates, kinships, syndicate types, work statuses,
                                               religions, document types + rules, statuses, MAX_BENEFICIARIES

Profile
GET    /api/v1/profile/
PATCH  /api/v1/profile/

Applications (doctor; only own objects)
GET    /api/v1/applications/
POST   /api/v1/applications/                   create draft for current fiscal year (or return existing)
GET    /api/v1/applications/{id}/
PATCH  /api/v1/applications/{id}/              only while editable
GET    /api/v1/applications/{id}/fees/
GET    /api/v1/applications/{id}/validation/   errors grouped by step + step completion
POST   /api/v1/applications/{id}/submit/       DRAFT → SUBMITTED or NEEDS_CORRECTION → SUBMITTED

Beneficiaries
GET    /api/v1/applications/{id}/beneficiaries/
POST   /api/v1/applications/{id}/beneficiaries/
PATCH  /api/v1/applications/{id}/beneficiaries/{beneficiary_id}/
DELETE /api/v1/applications/{id}/beneficiaries/{beneficiary_id}/

Documents
POST   /api/v1/applications/{id}/documents/    multipart: file, document_type, beneficiary_id?
GET    /api/v1/documents/{id}/                 metadata
GET    /api/v1/documents/{id}/content/         authorized stream or redirect to ≤5-minute read-only SAS
DELETE /api/v1/documents/{id}/                 only while editable
POST   /api/v1/documents/{id}/extract/         OCR suggestions

Admin (role ADMIN)
GET    /api/v1/admin/stats/                    counts per status / payment status
GET    /api/v1/admin/applications/             filters: status, payment_status, fiscal_year, governorate,
                                               syndicate_type, sub_syndicate, submitted_from, submitted_to;
                                               search: name, masked/full national ID, reference, phone;
                                               ordering; pagination
GET    /api/v1/admin/applications/{id}/
POST   /api/v1/admin/applications/{id}/transition/     {to_status, review_notes}
POST   /api/v1/admin/applications/{id}/payment/        {payment_status, note}
GET    /api/v1/admin/applications/{id}/notes/
POST   /api/v1/admin/applications/{id}/notes/          internal notes (not visible to doctor)
GET    /api/v1/admin/applications/{id}/audit/
GET    /api/v1/admin/doctors/
GET    /api/v1/admin/doctors/{id}/
GET    /api/v1/admin/fee-schedules/
POST   /api/v1/admin/fee-schedules/                    new version
GET    /api/v1/admin/fee-schedules/{id}/

Health
GET    /api/health/                             liveness
GET    /api/ready/                              readiness (DB reachable)
```

Use serializers for validation, explicit read-only fields, and object-level permission checks on every endpoint. Generate an OpenAPI schema (drf-spectacular) and generate the frontend API types from it if practical.

---

# 25. Database Relationships

```text
User
 │ 1:1
 ▼
Doctor
 │ 1:*
 ▼
InsuranceApplication ──*:1── FeeSchedule
 │            │      \
 │ 1:*        │ 1:*   \ 1:*
 ▼            ▼        ▼
Beneficiary  Document  AdminNote
 │ 1:*        ▲
 └────────────┘ (documents may reference a beneficiary)

AuditLog (references user + object type/id)
ReferenceCounter (fiscal_year → last sequence)
```

Create foreign keys, unique constraints (including the partial unique constraint in 16.1), indexes and composite indexes for admin filters (`status, submitted_at`, `fiscal_year, status`, `payment_status`), appropriate `ON DELETE` behavior (PROTECT for anything audit-relevant), and migrations. Do not over-normalize; do not create duplicate tables for similar entities.

---

# 26. PostgreSQL Production Database

- Azure Database for PostgreSQL Flexible Server.
- Prefer Microsoft Entra authentication with the Container App's managed identity: implement a small custom Django database backend that obtains a fresh Entra access token as the password for each new connection (tokens expire; keep `CONN_MAX_AGE` below token lifetime or refresh on connect). Support password auth from Key Vault as a fallback via a setting.
- Require TLS (`sslmode=require` or stricter).
- Configuration only through environment variables/secrets. No credentials in code or Git.
- Development uses PostgreSQL via Docker Compose.

---

# 27. Authentication — Microsoft Entra External ID

- Use a Microsoft Entra **External ID (external tenant)** for doctors: self-service sign-up with email + password or email one-time passcode, email verification, password reset, and Arabic language on the hosted pages. Google federation is optional (configurable).
- Use the **BFF pattern**: Django is a confidential OIDC client. It runs the authorization code flow with PKCE, validates the ID token (signature, issuer, audience, nonce, expiry), maps the user by Entra `oid` + `tid` (never by email alone), and creates a Django session. The browser never stores tokens.
- Session cookie: `HttpOnly`, `Secure`, `SameSite=Lax`, reasonable idle and absolute timeouts. CSRF protection on all unsafe methods (SPA reads the token from `/auth/me/` or the CSRF cookie and sends `X-CSRFToken`).
- First sign-in creates the `User`; the doctor completes the profile in the form.
- Admins: the role lives in Django (`User.role`), granted with `python manage.py grant_admin <email-or-oid>`, never self-assigned. Require MFA for admin accounts in Entra and, where the token exposes it (`amr` contains `mfa`), refuse an admin session without it (configurable).
- Entra app registrations are not created by Bicep: provide `infrastructure/scripts/` (Azure CLI / Microsoft Graph) plus step-by-step docs, using the `entra-app-registration` skill. Store the client secret (or certificate) in Key Vault.
- Local development: a `DEV_AUTH_ENABLED` login (pick a seeded doctor or admin) available ONLY in development/test settings. Production settings must refuse to start if it is enabled.

---

# 28. Authorization

Roles: `DOCTOR`, `ADMIN`.

Doctors can access only their own profile, applications, beneficiaries and documents. Admins can review all applications, change statuses through the transition service, confirm payments and view documents.

- Never rely on frontend route protection; Django enforces everything.
- Every endpoint verifies the authenticated user may access the specific object (prevent IDOR). Querysets are always scoped to the requesting doctor.
- Writing protected fields through any endpoint must be impossible (tests required).

---

# 29. Azure Key Vault

Use Key Vault for production secrets: Django `SECRET_KEY`, Entra client secret/certificate, database password (only if Entra DB auth is not used), third-party credentials. Prefer managed identity over secrets everywhere (Blob, PostgreSQL, Azure OpenAI, ACR). Container Apps reference Key Vault secrets via managed identity. No secrets in source files; `.env.example` contains names only.

---

# 30. Django Production Configuration

`config/settings/base.py`, `development.py`, `test.py`, `production.py`.

Production: `DEBUG=False`, explicit `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, HTTPS, secure cookies, CSRF, HSTS, `SECURE_PROXY_SSL_HEADER`, security headers (CSP suitable for the API, `X-Content-Type-Options`, `Referrer-Policy`), no unrestricted CORS (same-origin, so CORS should be off), upload size limits, and a startup check that fails on missing required settings or `DEV_AUTH_ENABLED`.

Do not use `ALLOWED_HOSTS = ["*"]` in production.

---

# 31. Docker

- Production Dockerfile for Django: multi-stage, slim Python base, non-root user, Gunicorn (not `runserver`), `collectstatic` at build time, health check.
- The container must not run migrations on every replica start (section 37).
- No persistent state inside the container; it can be destroyed and recreated at any time.

```text
              Load balancing (Container Apps ingress)
                    │
         ┌──────────┼──────────┐
         ▼          ▼          ▼
      Django     Django     Django
      replica    replica    replica
         └──────────┼──────────┘
                    ▼
     PostgreSQL + Blob + Key Vault + Azure OpenAI
```

---

# 32. Local Development

`docker-compose.yml` with:

- PostgreSQL
- Azurite (Blob emulator) so document upload works locally
- Django backend (development settings, `DEV_AUTH_ENABLED=true`, `OCR_PROVIDER=mock`)

Frontend runs with Vite and proxies `/api` to Django.

```bash
docker compose up
cd frontend && npm install && npm run dev
```

Provide `make` or npm scripts for: migrations, seeding (fee schedule 2026, one admin, two doctors with sample applications in different statuses), tests, lint.

---

# 33. Infrastructure as Code (Bicep)

Modular templates:

```text
infrastructure/
├── main.bicep
├── modules/
│   ├── container-registry.bicep
│   ├── container-apps-env.bicep
│   ├── container-app.bicep          (+ migration job, cleanup job)
│   ├── postgres.bicep
│   ├── storage.bicep                (private container, soft delete, versioning)
│   ├── key-vault.bicep
│   ├── monitoring.bicep             (Log Analytics + Application Insights)
│   ├── static-web-app.bicep         (Standard plan + linked backend)
│   ├── openai.bicep                 (optional: enableOcr parameter, model deployment)
│   ├── identity.bicep               (user-assigned managed identity)
│   └── role-assignments.bicep       (Blob Data Contributor, Key Vault Secrets User,
│                                     AcrPull, Cognitive Services OpenAI User)
├── parameters/ (dev.bicepparam, staging.bicepparam, prod.bicepparam)
└── scripts/    (Entra app registration, PostgreSQL Entra admin + managed identity role)
```

No hard-coded globally unique names (use `uniqueString`), environment-specific naming, tags on everything, all sizes parameterized. Validate with `az bicep build` and `az deployment group what-if` (mark what-if NOT VERIFIED if no Azure access).

---

# 34. Network and Security Architecture

```text
Internet → Static Web App (/api proxied) → Django (Container Apps)
                                              ├── PostgreSQL
                                              ├── Blob Storage
                                              ├── Key Vault
                                              └── Azure OpenAI
```

HTTPS everywhere; minimize public exposure. Prepare for private endpoints, VNet-integrated Container Apps environment, PostgreSQL private access, storage and Key Vault firewalls, and managed identities. For an MVP, if private networking significantly increases cost/complexity, implement a secure MVP (firewall rules restricted to Azure services/Container Apps outbound IPs, no public blob access, Entra auth) and document the production upgrade path. Never expose PostgreSQL to ordinary internet users.

---

# 35. Autoscaling

Container Apps scales Django independently from the frontend: min replicas 1, max configurable, HTTP concurrency trigger, all parameterized. The frontend is static on Static Web Apps and does not scale with Django.

---

# 36. CI/CD (GitHub Actions)

Frontend:

```text
npm ci → lint → type check → unit tests → rtl_check.py → build → Azure Static Web Apps
```

Backend:

```text
ruff → pytest (PostgreSQL service container) → build Docker image → push to ACR
     → run migration job (once) → update Container App revision
```

Infrastructure:

```text
bicep build → what-if (on PR) → deploy (on main, with environment approval for prod)
```

End-to-end (optional job): start docker compose + Vite, run Playwright with dev auth and mock OCR.

Use GitHub OIDC federated credentials with Azure; no stored Azure passwords. Use GitHub environments (dev, staging, prod) with required reviewers for prod.

---

# 37. Database Migrations During Deployment

Run `python manage.py migrate` exactly once per deployment as a Container Apps **job** (or a single pipeline step) before shifting traffic to the new revision. Replicas never race to migrate. Migrations must be backward compatible with the previous revision (expand/contract), following the `django-safe-migration` skill. Document the procedure and rollback.

---

# 38. Monitoring

- `/api/health/` (liveness) and `/api/ready/` (DB connectivity).
- Structured JSON logs with request IDs, user ID (internal UUID), route, status, latency.
- OpenTelemetry → Application Insights (requests, dependencies, exceptions).
- Never log passwords, tokens, cookies, full national IDs, document contents, OCR payloads or secrets. Add a logging filter that masks 14-digit sequences.

---

# 39. Audit Logging

`AuditLog(id, user, action, object_type, object_id, timestamp, ip_hash, metadata)`, append-only.

Track at least:

```text
APPLICATION_CREATED        APPLICATION_SUBMITTED       APPLICATION_RESUBMITTED
APPLICATION_STATUS_CHANGED PAYMENT_STATUS_CHANGED      FEE_SNAPSHOT_CREATED
DOCUMENT_UPLOADED          DOCUMENT_REPLACED           DOCUMENT_DELETED
DOCUMENT_VIEWED            OCR_REQUESTED               ADMIN_APPLICATION_VIEWED
ADMIN_NOTE_ADDED           FEE_SCHEDULE_CHANGED        ADMIN_ROLE_GRANTED
```

No passwords, tokens or unnecessary personal data in metadata (store IDs and changed field names, not values, for sensitive fields).

---

# 40. Duplicate Handling

- National ID is a business identifier, never the primary key.
- Unique constraint on `Doctor.national_id`; on conflict return `DUPLICATE_NATIONAL_ID` with `الرقم القومي مسجل لعضو آخر`.
- Partial unique constraint for one active application per doctor per fiscal year.
- Unique beneficiary national ID per application.
- Concurrency-safe: rely on database constraints and handle `IntegrityError`, not only pre-checks.

---

# 41. Validation at Both Layers

React (Zod + React Hook Form) for instant feedback; Django is authoritative. Never trust frontend validation.

---

# 42. Testing

## Backend (pytest / pytest-django, against PostgreSQL)

- authentication (dev auth backend; OIDC callback with mocked token validation)
- permissions and object ownership (IDOR attempts on every resource)
- protected fields cannot be written by doctors (`status`, `payment_status`, `fee_snapshot`, `reference_number`, `review_notes`)
- national ID parser/validator (dates, century, gender digit, Arabic digits, governorate codes)
- doctor creation and duplicate national IDs (including concurrent inserts)
- beneficiary rules (kinship, birth year, spouse/gender, SON_MINOR age, duplicates)
- document rules table for every kinship and age boundary (15/16)
- fee engine: every worked example in 17.4 plus boundaries
- application creation, one-active-per-year constraint
- submission validation (all messages in section 22)
- every allowed and disallowed status transition, including `NEEDS_CORRECTION → SUBMITTED`
- reference number generation (unique, sequential, concurrent submissions, kept on resubmit)
- document upload validation (type sniffing, size, receipt dimensions, executable rejection, filename sanitization)
- unauthorized document access and SAS URL scope/expiry
- OCR: mock provider, normalizers (digits, ID, years, triple names), rate limiting, no auto-save
- audit entries for sensitive actions
- logging filter masks national IDs

## Frontend (Vitest + Testing Library)

- TypeScript compilation (`tsc --noEmit`)
- NidInput / BoxStringInput (typing, Arabic digits, paste, backspace, accessibility label)
- form validation and error panel
- OCR merge fills only empty fields
- kinship change clears documents after confirmation
- beneficiary management and DocumentModal required docs
- autosave states
- authentication flow (guards, sign-out clears state)
- application workflow and read-only mode
- `rtl_check.py frontend/src` passes

## End-to-end (Playwright)

- Doctor: sign in (dev auth) → upload ID front → mock OCR fills fields → complete form → add WIFE and SON_MINOR with documents → fee shows 3025 for example 2 data → upload receipt → review → submit → reference number shown.
- Admin: find the application → confirm payment → approve. Separate run: request correction → doctor resubmits.
- Print view renders to an A4 PDF within two pages.
- Mobile viewport (390×844) form is usable without horizontal scrolling.

---

# 43. Doctor UX

## Dashboard

```text
مرحباً د. {first name}

طلباتي
──────────────────────────────────────────
MED-2026-000123            [قيد المراجعة •]
٣ أكتوبر ٢٠٢٦                    3٬025 ج.م
▸ (expand: beneficiaries count, review notes)
                                     [عرض]

مسودة — السنة المالية 2026          [مسودة]
آخر حفظ: منذ 5 دقائق
                                    [متابعة]

[+ تقديم طلب جديد]   (disabled if an active application exists this fiscal year)
```

- Empty state: illustration + `لم تقدم أي طلبات بعد` + `تقديم طلب جديد`.
- `NEEDS_CORRECTION` cards show the review notes prominently and a `تصحيح وإعادة التقديم` button.
- Status timeline on `/application/:id/status`: `تم التقديم ✓ → قيد المراجعة → إشعار بالنتيجة`, polling every 30–60 seconds with TanStack Query.
- After submission show a confirmation screen with the reference number and a print button.

## Wizard

```text
1 البيانات → 2 المستفيدون → 3 المستندات → 4 الإيصال → 5 المراجعة والتقديم
```

Display completion progress; do not allow final submission when mandatory information is missing.

---

# 44. Administrator UI

Dashboard tiles: `إجمالي الطلبات`, `بانتظار المراجعة`, `قيد المراجعة`, `يحتاج تصحيح`, `مقبول`, `مرفوض`, `إيصالات بانتظار التأكيد`.

Applications table (server-side pagination, search, filters for status, payment status, fiscal year, governorate, syndicate type, sub-syndicate, date range; sortable columns):

```text
رقم الطلب          مقدم الطلب        النقابة   الحالة          الدفع            تاريخ التقديم    الإجمالي
MED-2026-000123    أحمد علي          بشري      قيد المراجعة    بانتظار التأكيد   ٣ أكتوبر ٢٠٢٦    3٬025
```

Application detail: member data, masked national ID with an audited "show full" action, beneficiaries with their documents, document viewer (images/PDF in a modal via short-lived URLs), fee snapshot, receipt with confirm/reject payment, duplicate warnings, transition buttons limited to allowed transitions, doctor-visible review notes, internal notes, audit history, print.

Fee schedules page: view the active schedule; create a new version for a fiscal year (with confirmation and audit).

---

# 45. Pagination

Never return thousands of rows. Server-side pagination, filtering, searching and ordering for all admin lists (page size default 25, max 100).

---

# 46. API Error Handling

Consistent format with Arabic user-facing messages and stable codes:

```json
{
  "error": {
    "code": "DUPLICATE_NATIONAL_ID",
    "message": "الرقم القومي مسجل لعضو آخر",
    "fields": {"national_id": ["الرقم القومي مسجل لعضو آخر"]}
  }
}
```

Codes include at least: `VALIDATION_ERROR`, `DUPLICATE_NATIONAL_ID`, `ACTIVE_APPLICATION_EXISTS`, `INVALID_STATUS_TRANSITION`, `APPLICATION_NOT_EDITABLE`, `FILE_TOO_LARGE`, `UNSUPPORTED_FILE_TYPE`, `IMAGE_TOO_SMALL`, `OCR_UNAVAILABLE`, `RATE_LIMITED`, `NOT_FOUND`, `PERMISSION_DENIED`, `NOT_AUTHENTICATED`. Validation responses list all field errors. The frontend shows understandable Arabic messages and never raw stack traces.

---

# 47. Privacy and Security

Treat national IDs, syndicate IDs, addresses, phone numbers, religion, identity documents, photos and family information as sensitive personal information.

Implement least privilege, object-level authorization, HTTPS, private Blob containers, short-lived document URLs, secure cookies, security headers, rate limiting (sign-in callback, OCR, uploads), audit logs, environment separation, backups and restricted production access.

Do not claim the system is automatically compliant with GDPR, Egypt's Personal Data Protection Law (Law 151 of 2020), HIPAA or any other regulation. Document the technical controls that exist and list items requiring legal/organizational decisions (data retention periods, religion field, OCR processing by an AI service, data residency/region, admin access policy, breach procedure).

---

# 48. Backups and Recovery

Document and configure: PostgreSQL automated backups with point-in-time restore (retention parameterized; geo-redundant backup for prod if affordable), Blob soft delete + versioning (+ optional lifecycle rules), Key Vault soft delete and purge protection. Document restore procedures, RPO/RTO assumptions and a restore drill.

---

# 49. Environments

`development`, `staging`, `production`, each with separate resources, identities, Entra app registrations (or redirect URIs), Key Vaults and credentials. Never share production credentials with other environments.

---

# 50. README

Root README with: architecture (ASCII diagram), local setup (exact commands), environment variables (each explained), database migrations, seeding, running tests (backend, frontend, e2e), Docker, Azure prerequisites, Entra External ID setup, Azure infrastructure deployment (exact commands), application deployment, enabling OCR, granting admin role, troubleshooting (common failures: cookies not sent cross-site, CSRF failures, Entra redirect URI mismatch, managed identity token errors with PostgreSQL — e.g. a wrong `AZURE_CLIENT_ID` — Blob 403, OCR quota).

---

# 51. Documentation

```text
docs/
├── architecture.md        (Azure architecture in Mermaid)
├── database.md            (ER diagram in Mermaid)
├── api.md                 (+ link to OpenAPI schema)
├── business-rules.md      (fees, national ID, kinships, documents, statuses, open questions)
├── azure-deployment.md
├── entra-setup.md
├── security.md
├── ocr.md
└── local-development.md
```

---

# 52. Cost Awareness

Do not choose unnecessarily expensive tiers. Sensible MVP defaults, all sizes configurable. Document: cheapest reasonable development configuration (Container Apps scale-to-zero for dev, Burstable PostgreSQL, SWA Standard only where the linked backend is needed), initial production configuration, and what to increase as traffic grows. Cost drivers to explain: PostgreSQL compute/storage/backups, Container Apps vCPU-seconds and min replicas, SWA Standard plan, Blob storage + transactions, Log Analytics ingestion, Azure OpenAI tokens per OCR call, private networking. Do not sacrifice critical security to reduce cost.

---

# 53. Implementation Rules

Important:

- DO NOT only describe how I could build the application. Actually create the files.
- DO NOT stop after an architecture diagram or frontend mockups.
- DO NOT create fake API implementations when the real backend can be implemented.
- DO NOT replace PostgreSQL with SQLite (tests also run on PostgreSQL).
- DO NOT put frontend and Django in one production container.
- DO NOT put PostgreSQL inside the Django container.
- DO NOT store files permanently inside containers.
- DO NOT hardcode secrets. DO NOT commit `.env`.
- DO NOT expose the Blob container publicly or create permanent document URLs.
- DO NOT trust client-side authorization, validation or fee calculation.
- DO NOT use national ID as the database primary key.
- DO NOT delete application data when a container restarts.
- DO NOT invent Azure credentials.
- DO NOT call OCR/AI from the browser.
- DO NOT copy Firebase code, configuration or the prototype defects listed in 2.3.
- DO NOT build password forms; authentication is Entra External ID.
- DO NOT hard-code UI strings outside `i18n/ar.ts`; DO NOT use physical left/right CSS for layout.

If Azure authentication or subscription access is unavailable, generate all infrastructure/deployment files and clearly state the exact commands I must run after authentication.

---

# 54. Development Process

Work incrementally and keep the repository runnable. Commit locally at the end of each phase with a clear message (do not push until I confirm).

## Phase 1 — Inspect

Inspect the target repository. Clone and read the Firebase prototype (section 2). Report the current structure and the prototype features you will port, briefly.

## Phase 2 — Architecture

Create the final architecture, directory structure, `CLAUDE.md`, the project skill `.claude/skills/medical-form-rules/SKILL.md`, and `docs/business-rules.md`. Write an implementation plan (superpowers `writing-plans`).

## Phase 3 — Backend

Django project, settings, models, constraints, migrations (including FY 2026 fee schedule seed), reference data, national ID module, fee engine, document rules, validation, transition service, reference numbers, dev auth + Entra OIDC BFF, API, permissions, OCR module with mock provider, audit, tests. Make backend tests pass.

## Phase 4 — Frontend

React app, Tailwind theme tokens, RTL setup, i18n, API client, routing and guards, landing page, dashboard, paper-form replica with all shared components, autosave, document uploads and DocumentModal, OCR merge, fee summary, payment page, review and submit, status page, print view, admin dashboard, applications list/detail, document viewer, fee schedules page. Make TypeScript compile and tests pass; run `rtl_check.py`.

## Phase 5 — Local Environment

Docker Compose (PostgreSQL, Azurite, Django), Vite proxy, seed data. Verify frontend and backend communicate and the full doctor flow works locally.

## Phase 6 — Azure Integration

Blob Storage via managed identity (Azurite locally), Key Vault configuration, Entra DB authentication backend, Azure OpenAI OCR provider, Application Insights.

## Phase 7 — Infrastructure

Generate and validate Bicep; Entra registration scripts and docs.

## Phase 8 — CI/CD

GitHub Actions workflows with OIDC, migration job, environments.

## Phase 9 — Testing

Run backend tests, frontend tests, lint, TypeScript check, production frontend build, Docker build, Playwright e2e, print check, RTL check, and a security review pass. Fix problems rather than only documenting them.

## Phase 10 — Deployment Readiness

Final deployment instructions and the final report (section 56).

---

# 55. Verification Requirement

Before considering the project complete, verify:

```text
✓ Frontend builds
✓ TypeScript passes
✓ Frontend unit tests pass
✓ RTL checker passes
✓ Backend starts
✓ Django system checks pass (including --deploy with production settings)
✓ Django migrations exist and apply on a clean PostgreSQL
✓ Backend tests pass (fee examples, national ID, document rules, transitions, permissions)
✓ Docker image builds
✓ PostgreSQL configuration works
✓ Document upload flow works end to end (Azurite locally)
✓ OCR flow works with the mock provider
✓ Authorization tests exist and pass
✓ Blob integration exists
✓ Entra OIDC BFF implemented (NOT VERIFIED against a real tenant if no credentials)
✓ Playwright e2e passes (doctor submit, admin approve, correction loop)
✓ Print view fits A4
✓ Bicep validates
✓ CI/CD files exist
✓ No secrets committed (scan the repo)
✓ README contains deployment commands
```

If an item cannot be verified because of missing external credentials or Azure access, mark it:

```text
NOT VERIFIED — requires Azure credentials
```

instead of pretending that it worked.

---

# 56. Final Output

When implementation is finished, give me:

1. Final architecture.
2. Repository tree.
3. Database schema.
4. Main API endpoints.
5. Azure services created.
6. Required environment variables.
7. Local development instructions.
8. Entra External ID setup steps.
9. Azure deployment instructions.
10. Approximate Azure cost drivers.
11. Security decisions.
12. Prototype features ported, and prototype defects fixed (section 2.3 checklist).
13. Remaining limitations.
14. Open business questions (section 57).
15. Tests executed and their results.

Give exact file paths and exact commands. No vague statements like "configure Azure as needed."

---

# 57. Open Business Questions (implement the default, report the question)

| # | Question | Default implemented |
|---|---|---|
| 1 | Are the FY 2026 fee amounts, tiers, admin fees and the 70+ cap final? | Values in 17.1, stored in an editable schedule |
| 2 | How are fees calculated for a deceased (متوفى) member's family? | Same as WORKING |
| 3 | What are the fees for an `ADDITION` (إضافة) application — only the new beneficiaries? | Same as FIRST_TIME |
| 4 | Children's documents: is the age-16 rule correct (birth certificate below 16, national ID from 16; birth certificate always if the member is female)? | Age-aware rule in section 15, threshold configurable |
| 5 | Maximum beneficiaries: 10 (prototype) or 11 (paper rows)? | 10, configurable |
| 6 | Must `SON_MINOR` be ≤ 18, and must spouse kinship match the member's gender? | Both enforced, configurable |
| 7 | Can a rejected applicant re-apply in the same fiscal year? | Yes, a new application |
| 8 | How do members pay (bank, Fawry, syndicate office)? What instructions should be shown? | Configurable placeholder text |
| 9 | Is the member photo mandatory? | Optional (`REQUIRE_MEMBER_PHOTO=false`) |
| 10 | Is `(syndicate_type, registration_number)` unique? | Indexed, not unique |
| 11 | Is sending ID images to Azure OpenAI for OCR legally approved, and in which region? | OCR behind a feature flag, off in prod until approved |
| 12 | Data retention period for applications and documents? | Not auto-deleted; documented as a decision |

---

# 58. Azure Target Architecture

```text
                        INTERNET
                           │
                           ▼
              ┌─────────────────────────────┐        ┌───────────────────────┐
              │ Azure Static Web App (Std)  │        │ Entra External ID     │
              │ React + TS + Vite + Tailwind│        │ (sign-up / sign-in)   │
              │ Arabic RTL                  │        └──────────▲────────────┘
              └──────────────┬──────────────┘                   │ OIDC
                             │ /api (linked backend, same origin)│
                             ▼                                   │
              ┌─────────────────────────────┐───────────────────┘
              │ Azure Container Apps        │
              │ Django + DRF + Gunicorn     │──── migration job / cleanup job
              └───┬────────┬────────┬───────┬───────────────┐
                  │        │        │       │               │  managed identity
                  ▼        ▼        ▼       ▼               ▼
          PostgreSQL   Blob      Key     Azure OpenAI   App Insights
          Flexible     Storage   Vault   (OCR, opt.)    + Log Analytics
          Server       (private)


GitHub
   ├── Frontend CI/CD ──→ Azure Static Web Apps
   ├── Backend CI/CD ───→ Azure Container Registry ──→ Container Apps (+ migration job)
   └── Bicep ───────────→ Azure infrastructure
```

Build toward this architecture.

Start by inspecting the existing repository and the Firebase prototype, then begin Phase 1.

Do not ask me to manually create project files that you can create yourself.
