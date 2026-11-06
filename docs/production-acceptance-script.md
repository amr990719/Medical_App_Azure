# Production acceptance: the signed-in checks

A script for the owner, in order, on the production temporary host (the default `*.azurestaticapps.net`
address, which the owner has). It covers the rows of `docs/production-acceptance.md` that need a person.
About 60–90 minutes. Report each result by its ID; the record is updated from that.

**Use made-up people and documents only.** Production holds real data from the day it opens, and this
repository is public, so evidence never contains names, numbers or documents.

## What you need

| Item | Use |
|---|---|
| Account A: `a…@hotmail.com` (the administrator) | admin checks |
| Account B: your second account (`m…@hotmail.com`) | the doctor, and the "other doctor" for permission checks |
| A private browser window | each account in its own window, so sessions do not mix |
| 3–4 test images | any picture, clearly not a real document: for example a photo of a blank sheet with "TEST" written on it, JPG or PNG, at least 400×300 pixels, under 8 MB |
| One image just under 8 MB and one over 8 MB | for `DOC-4` |
| A phone, or the browser's phone view (390 px wide) | for `FORM-2` |

Made-up member details (they pass the format checks and belong to nobody):

| Field | Value |
|---|---|
| Name | `عضو تجريبي للاختبار` |
| National ID (male, born 1 Jan 1990) | `٢٩٠٠١٠١٠١٠٠٠١٣`, typed in **Eastern Arabic digits** on purpose |
| Mobile | `٠١٠٠٠٠٠٠٠٠١` |
| Registration year | `٢٠١٤` (tier 3) |
| Beneficiary: wife | name `زوجة تجريبية`, birth year `1988`, no national ID |
| Beneficiary: son | name `ابن تجريبي`, kinship "ابن/ابنة (18 سنة أو أقل)", birth year `2015`, no national ID |

## 1. Accounts (A first, then B)

| ID | Do | Expect |
|---|---|---|
| AUTH-5 | A: sign out, sign in again | the admin pages are offered |
| AUTH-2 | A: sign out | you land on the signed-out page; going back to `/doctor/form` asks you to sign in |
| — | A, private window: sign in | **you are asked for a code** (MFA) — say whether you were |
| AUTH-6 | — | done with the administrator later (it needs a second admin to revoke); skip for now |

## 2. The doctor's application (account B)

| ID | Do | Expect |
|---|---|---|
| FORM-1 | fill the member section with the made-up details, **typing Arabic digits** | each field accepts them; after saving and reloading, the numbers are still there |
| FEE-1 | add the wife and the son; open the fee summary | fiscal year 2026; tier 3; member 825, wife 1100, son 605, admin fee 725, service fee 800, total **4055** |
| FEE-2 | change the registration year to `1949`, look at the fees, then put `2014` back | an Arabic message asking for a valid registration year, no amount |
| DOC-1 | upload the ID front and back, the syndicate card, the photos and certificates the form asks for, using test images; then replace one | each upload shows; the replaced one shows the new image |
| DOC-4 | try the image over 8 MB, then the one just under | the large one is refused with a clear message; the other is accepted |
| FORM-2 | open the form at phone width | everything readable, right-to-left, no sideways scrolling |
| PRN-1 | look for a print button; open `/application/<id>/print` (the id is in the address bar) | no print button; the address shows "page not found" |
| APP-1 | upload a test payment receipt, accept the declaration, submit | a reference number `MED-2026-…` |

## 3. Permissions (account B, then a signed-out window)

| ID | Do | Expect |
|---|---|---|
| PERM-1 | as B, open `/admin` | refused or not found; no admin data |
| FORM-3 | as A in a private window, start an application with B's national ID | refused: `الرقم القومي مسجل لعضو آخر` |
| PERM-2 | as A (still a doctor's view), open B's application address | not found |
| DOC-2 | signed out, open a document address copied from B's application | refused |

`PERM-3` and `DOC-3` are API-level checks; they are done by script, not by hand.

## 4. The administrator's review (account A, admin pages)

| ID | Do | Expect |
|---|---|---|
| PAY-1 | open B's application; reject the receipt with a reason | B sees the rejection and can upload a new receipt |
| PAY-1 | as B, upload a new receipt; as A, confirm payment | payment shows as confirmed |
| DUES-1 | as A, request additional dues (for example 250) with a reason | B sees the amount and can upload a dues receipt |
| DUES-2 | as B, upload a dues receipt; as A, reject it with a reason; as B, upload again; as A, confirm | each step shows; the treatment fee and its receipt did not change |
| APR-1 | before confirming the dues, try to approve | refused with a message about dues |
| APP-2 | instead, request a correction with a note; as B, change something and resubmit | same reference number as before |
| APR-1 | as A, with payment and dues confirmed, approve | approved |
| AUD-1 | open the application's history | each action above, with who and when |
| CSRF-1 | — | covered by every save above; nothing to do by hand |

For `APR-2` (rejection), use a second, new application from B: submit it, then reject it with a note.
B can then start another.

## 5. Report back

For each ID: pass or fail, and for a fail what you saw. No screenshots with personal details. Afterwards
the test applications are removed as described in `docs/production-runbook.md`, "Test data".
