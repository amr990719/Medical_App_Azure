# Production acceptance record

Production is **not ready** until every row below is `PASS` with evidence. Passing tests, a green
release or a healthy `/api/ready/` do not change this. Production was bootstrapped on 2026-11-06 and
runs on its temporary host; the rows below record what has been proven on it since.

Check what is still open at any time:

```bash
python infrastructure/scripts/acceptance_record.py docs/production-acceptance.md --stage before-cutover
python infrastructure/scripts/acceptance_record.py docs/production-acceptance.md --stage all
```

`cutover-domain.sh preflight` runs the first one and refuses to go on if anything is open.

## How to fill it in

- **Status** is `PASS`, `FAIL` or `PENDING`. **Evidence** is a run link, a date and who checked, or a
  screenshot path. This repository is public, so evidence never holds an address, a phone number,
  a national ID or a document. Use synthetic test people only, and remove them afterwards
  (`docs/production-runbook.md`, "Test data").
- **Stages** happen in this order, and a stage also needs the ones before it:
  `before-admin` → `before-cutover` → `after-cutover` → `before-live`.
- A `FAIL` is a finding: fix it through a normal release, then check it again.

## Automated part

The `Smoke test` step of each release, or by hand at any time. It reads only and needs no
credentials:

```bash
python infrastructure/scripts/acceptance_smoke.py --base-url https://<host> \
  --expect-client-id <production ENTRA_CLIENT_ID> \
  --direct-backend-url https://<container-app-fqdn>
```

A pass covers the page and its language, deep links, security headers, liveness, readiness including
the schema, anonymous refusals, API docs off, and the sign-in redirect (External ID host, production
client ID, exact redirect URI, PKCE S256, cookie flags). The rest needs a person.

## Before the first administrator

MFA has to be proven before `grant_admin`: the app's `amr` check is off by owner decision (D144,
D150), so nothing in the app would notice a missing Conditional Access policy.

| ID | Stage | Check | Status | Evidence |
|---|---|---|---|---|
| ENV-1 | before-admin | Production is a separate resource group, with its own Key Vault, database, storage and Entra app. No dev data or secret was copied, and `seed_dev_data` was not run | PASS | `rg-medsyn-prod`, own Key Vault, database, storage and Entra app; bootstrap https://github.com/amr990719/Medical_App_Azure/actions/runs/42128227759; no seed or copy (2026-11-06) |
| ENV-2 | before-admin | The release manifest shows the same backend digest and frontend digest as dev for that commit | PASS | release `5d31934`: backend `sha256:22ebf7…` on app and both jobs, the same digest dev runs (2026-11-06) |
| SMK-1 | before-admin | `acceptance_smoke.py` passes on the temporary host, with the direct backend check | PASS | `acceptance_smoke.py` on the temporary host: 12/12 passed, direct backend check included (2026-11-06) |
| AUTH-1 | before-admin | A new test doctor signs up and signs in on the temporary host through the production Entra app; `/auth/me/` returns them | PASS | two different accounts signed in on production; both reached `/auth/callback/` (302), Entra log 08:21 UTC (2026-11-06) |
| AUTH-2 | before-admin | Sign-out ends the session and lands on `/signed-out`; `/auth/me/` is 401 afterwards | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| AUTH-3 | before-admin | Conditional Access policy exists, is **On**, and targets group `medical-admins-prod` and app `medical-syndicates-prod` (screenshot of the policy) | PASS | "Require MFA for medical prod admins": enabled, grant MFA, only `medical-admins-prod` and `medical-syndicates-prod` (Graph read-back, 2026-11-06) |
| AUTH-4 | before-admin | A real member of that group is **asked for MFA** at sign-in, and a non-member is not refused. Done before any `grant_admin` | PASS | Entra log: the group member's sign-in had requirement `multiFactorAuthentication`, satisfied; a non-member's was single factor, as intended (2026-11-06) |
| AUTH-5 | before-admin | `grant_admin` for that person, run as a job execution; the audit history shows `ADMIN_ROLE_GRANTED`; they reach `/admin` | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| AUTH-6 | before-admin | `revoke_admin` on a second test admin removes access at once and is audited; it refuses the last admin | PENDING | |

## Before the domain moves

All on the temporary host. Application printing was retired on 2026-10-28 (D171), so the print check
confirms it stays retired. If printing should come back, that is a new feature, not an acceptance
item.

| ID | Stage | Check | Status | Evidence |
|---|---|---|---|---|
| FORM-1 | before-cutover | A new doctor completes the form using Eastern Arabic digits (٠-٩) in the national ID, phone and years; they are stored as Western digits and none is dropped | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| FORM-2 | before-cutover | The whole form works at phone width (390 px) in RTL, with no sideways scroll | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| FORM-3 | before-cutover | A national ID already used by another doctor is refused with `الرقم القومي مسجل لعضو آخر` | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| PERM-1 | before-cutover | A doctor cannot open admin pages or admin API endpoints | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| PERM-2 | before-cutover | Doctor B cannot read or change doctor A's application, beneficiaries or documents (404, using A's real IDs) | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| PERM-3 | before-cutover | A doctor's API request cannot set `status`, `payment_status`, `reference_number`, `fee_snapshot` or `review_notes` | PENDING | |
| DOC-1 | before-cutover | A doctor uploads, replaces and opens a document; the bytes are in Blob Storage and only metadata is in PostgreSQL | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| DOC-2 | before-cutover | Doctor B opening A's document is refused; a signed-out request is refused | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| DOC-3 | before-cutover | The blob's direct URL without a SAS is refused; a SAS link stops working within 5 minutes | PASS | anonymous GET of a blob URL in the private `medical-documents` container is refused with 409 PublicAccessNotPermitted (account public access and shared keys off). Production streams documents through the authorized endpoint (`DOCUMENT_CONTENT_DELIVERY` unset = stream; 38 content GETs on 2026-11-06 all 200, no SAS redirect), so no SAS link is ever issued; the SAS lifetime is capped at 300 s in code if that mode is enabled later. Owner accepted this as PASS (2026-11-07) |
| DOC-4 | before-cutover | A file just under 8 MB uploads **through the Static Web App**; one over 8 MB gets `FILE_TOO_LARGE`, not a platform error (Q-T13) | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| FEE-1 | before-cutover | Reference data and the quote use fiscal year 2026, and the quote for a known case matches `apps/fees/tests/test_engine.py` | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| FEE-2 | before-cutover | A registration year of 1949 gives the invalid-quote message, not a number | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| APP-1 | before-cutover | Submit gives a `MED-2026-` reference number; the fee snapshot is shown to the admin | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| APP-2 | before-cutover | Admin requests a correction with a note; the doctor edits and resubmits; the reference number stays the same | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| PAY-1 | before-cutover | Admin rejects a receipt with a reason (an empty reason is refused); the application returns to the doctor as NEEDS_CORRECTION with the reason visible and the internal note hidden (D220); the doctor replaces the receipt and resubmits with the same reference number; admin confirms; `payment_status` follows each step | PASS | re-tested by the owner on production after release `84306ee` (D220, run 42308932352, smoke 12/12), 2026-11-07. The access log shows the admin's rejection (23:21 UTC), the doctor's new receipt and resubmission (23:22), then the admin's confirmation (23:22). The first run on 2026-11-06 had failed: the doctor could not replace a rejected receipt or see the reason, which led to the fix |
| PAY-2 | before-cutover | The payment page shows `برجاء مسح رمز QR ثم رفع إيصال الدفع.` and the fixed InstaPay QR (implemented 2026-11-06); a phone scan of the QR opens the owner's InstaPay address, the address under it matches, and its copy button copies it on a phone | PASS | Released `11b744e` (run 42263258715, smoke 12/12); production serves the wording, the QR image and the address. The owner checked it on production with a phone: the QR scan opens the confirmed InstaPay address, the address matches, and the copy button copies it (2026-11-06) |
| DUES-1 | before-cutover | Admin requests additional dues; the doctor sees the amount and uploads a receipt | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| DUES-2 | before-cutover | Admin rejects that receipt with a reason; the doctor re-uploads; admin confirms; the treatment fee, its receipt and `payment_status` did not change | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| APR-1 | before-cutover | Approval is refused without confirmed payment, and refused with unconfirmed dues; it succeeds once both are done | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| APR-2 | before-cutover | Rejection needs a note, is final, and the doctor can then start a new application | PENDING | |
| PRN-1 | before-cutover | No print action is offered; `/application/<id>/print` and `/admin/applications/<id>/print` show the not-found page (D171) | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| AUD-1 | before-cutover | The audit history shows these actions with actor and time, and an audit row cannot be edited | PASS | the owner ran it on production (release `11b744e`, temporary host) following `docs/production-acceptance-script.md` and reported it passed (2026-11-06) |
| CSRF-1 | before-cutover | A signed-in POST works; the same POST without the CSRF token is refused | PENDING | |
| PROXY-1 | before-cutover | One request in Application Insights shows the browser's address as the client, so `TRUSTED_PROXY_COUNT=2` holds and throttles count per user; a burst to a throttled endpoint gets `RATE_LIMITED` (Q-T13) | PASS | first failed: 25 anonymous `/auth/callback/` requests with distinct spoofed X-Forwarded-For got no 429 (2026-11-06 23:37 UTC). Probes then showed a shared cache (`dbcache`), one replica, a stable key on one keep-alive connection (429 from request 21) and a new key per connection: the forwarded entry carries the client's port. Fixed by D221 (PR #33: the key is the bare client IP; production refuses a per-process cache). After release `9e7ef1f` (run 42356601748, smoke 12/12): 25 requests, each on a new connection with a distinct spoofed X-Forwarded-For, gave 302 x20 then 429 x5 (2026-11-07 09:02 UTC), so neither a new connection nor a spoofed entry escapes the limit and `TRUSTED_PROXY_COUNT=2` holds. App Insights masks client addresses (0.0.x.x), so the address itself cannot be read there; the burst is the evidence |
| OBS-1 | before-cutover | Requests, traces and dependencies arrive in Application Insights with **Entra-only** ingestion on; the 14-digit scan in `docs/azure-deployment.md` returns `hits = 0` | PASS | requests, traces, dependencies arriving with Entra-only ingestion; 14-digit scan over 30 days: 0 hits (2026-11-06) |
| OBS-2 | before-cutover | Console logs of a migrate and a cleanup execution can be read in Log Analytics | PASS | migrate job console logs readable in Log Analytics (2026-11-06 23:13 UTC: 'No migrations to apply', `release_check result=ok`); the scheduled cleanup execution of 2026-11-07 01:30 UTC (Succeeded) logged `cleanup_blobs: purged=0 orphans=0` in `ContainerAppConsoleLogs_CL` |
| OBS-3 | before-cutover | `manage.py alert_test` as a job execution: **a person receives the `ops-alert-test` email**. This is the controlled test; the test-email API is not used (Q-N17) | PASS | `manage.py alert_test` on production 08:26 UTC; the owner received the email, after verifying the action group address by one-time code (2026-11-06) |
| OBS-7 | before-cutover | `modules/service-alerts.bicep` deployed once on dev (`ENABLE_SERVICE_ALERTS=true`) before production, then turned off; the `cleanup-missed` email at creation was expected and cleared after the first run | PASS | deployed on dev 2026-11-05 (14 resources, ARM accepted them all); the alert trace arrived; removed on 2026-11-06 |
| OBS-4 | before-cutover | The availability test shows results for its 3 locations in `appi-medsyn-prd-uptime`, and a certificate check passes | PASS | 3 locations report; the only failures were 404s at 06:33 UTC, before the frontend upload; every later run passed (2026-11-06) |
| OBS-5 | before-cutover | A scheduled cleanup run leaves a `cleanup_run` trace | PASS | scheduled cleanup (cron `30 1 * * *`) ran 2026-11-07 01:30 UTC, execution Succeeded, and left a `cleanup_run` trace in App Insights (`AppTraces`: purged 0, orphans 0, dry_run False) |
| OBS-6 | before-cutover | A named person owns incident response, and the alert address is monitored (`docs/production-runbook.md`, "Who owns what") | PENDING | |
| REL-1 | before-cutover | A second release proceeds in order, and a release of an older commit is refused by the order check | PASS | releases `11b744e` (run 42263258715) then `84306ee` (run 42308932352); the order step logged 'allowed' each time and the prod record holds `medical-release:current`=84306ee, `:previous`=11b744e. Refusal of an older commit shown by running the same `release_gate.py order` against the real record (11b744e over 84306ee: refused, exit 1) and by its tests; no live refused dispatch. Owner accepted this as PASS (2026-11-07) |
| REL-2 | before-cutover | `mode=rollback` puts back the previous digests and the service works; roll forward again afterwards | PASS | rollback drill (owner approved, 2026-11-07): `mode=rollback` to `84306ee` (run 42358082917) put back the previous backend digest (`sha256:42b5ce...`, revision `r84306ee2e1-7-1`) and frontend, smoke 12/12, `/api/ready/` ok, record `current`=84306ee with `previous_sha`=9e7ef1f. Rolled forward with a normal release of `9e7ef1f` (run 42358611871): backend `sha256:d28d65...`, revision `r9e7ef1f8af-8-1`, smoke 12/12, recorded as `medical-release:current` (09:22 UTC) |
| REL-3 | before-cutover | A manual `infrastructure.yml` run on prod deploys the current release's template while main is ahead, and keeps the running image | PASS | manual `infrastructure.yml` run on prod (run 42314611046, 2026-11-07 01:23 UTC) while main was ahead: it logged 'Deploying the template of the current release 84306ee' and 'Keeping image ...@sha256:42b5ce...'; the same revision `r84306ee2e1-4-1` kept serving and `/api/ready/` stayed ok |
| REC-1 | before-cutover | Database drill on a temporary copy with synthetic data and sending off: measured RPO and RTO recorded in the runbook | PASS | dev drill with `recovery.sh`: hold 09:01:43 UTC, point-in-time restore to a temporary server, prepare, select, check, reconcile; ready to reopen 09:37:41 (36 min), about 40 min with hold-off. Restore point 2 min before the hold. Temporary server deleted (2026-11-06) |
| REC-2 | before-cutover | Document drill on the temporary copy: a deleted blob and an overwritten blob are restored; `reconcile_documents` reports as expected | PENDING | |
| REC-3 | before-cutover | Secret drill: a deleted test secret is recovered, and a recovered secret reaches the app after a restart | PENDING | half shown: a throwaway dev secret was deleted and recovered intact in 14 s (2026-11-06). Not yet shown: a recovered secret reaching the app after a restart |
| REC-4 | before-cutover | With `RECOVERY_HOLD=true` the public API refuses callers, both schedules are moved, a release is refused and a rollback is allowed; hold-off restores all of it | PENDING | mostly shown on dev: the API answered 403 to every caller, both crons moved to 1 January, notifications forced off, hold-off restored all of it (2026-11-06). Not yet shown: a release refused and a rollback allowed during a hold |
| REC-5 | before-cutover | A restored server is accepted by the deployment (geo-redundancy and storage match), and `POSTGRES_SERVER_NAME_OVERRIDE` survives a later deployment: `DATABASE_URL` stays on the selected server | PENDING | half shown on dev: the deployment accepted the restored server, recreated its firewall rule and pointed the jobs at it; removing the override pointed dev back (2026-11-06). Not yet shown: the override surviving a second deployment |
| REC-6 | before-cutover | `reconcile_notifications` on a restored copy leaves nothing to resend, and an admin can still resend one row on purpose | PENDING | ran on the restored dev copy: guards refused before selection, then dry run and apply with 0 rows in flight (2026-11-06). Not yet shown with real in-flight rows, nor a deliberate admin resend |
| LOAD-1 | before-cutover | Small load test through the public host at the agreed concurrency: errors, p95, replicas and database connections recorded, and the alert thresholds still make sense | PASS | 20 connections for 60 s on `/api/ready/` (database read each time): 7,538 requests, 0 errors, p50 134 ms, p99 632 ms; at most 13 database connections, CPU under 4%, 1 replica (2026-11-06) |
| COST-1 | before-cutover | The monthly budget exists and its alert address is monitored (`docs/production-cost-estimate-2026-11-05.md`) | PASS | budget `medsyn-prod-monthly`, $400, from 2026-11-01, emails at 90% and 100% actual and 100% forecast (2026-11-06) |

## After the domain moves

| ID | Stage | Check | Status | Evidence |
|---|---|---|---|---|
| CUT-1 | after-cutover | `cutover-domain.sh verify` passes on `neqabacare.com`, including the old host's redirect | PENDING | |
| CUT-2 | after-cutover | A real sign-in and sign-out on `neqabacare.com` | PENDING | |
| CUT-3 | after-cutover | A signed-in, CSRF-protected change on `neqabacare.com` | PENDING | |
| CUT-4 | after-cutover | A session started on the old host cannot sign in by accident: it is redirected first (Q-T24), and `www` lands on the apex with its path | PENDING | |
| CUT-5 | after-cutover | Dev works at `dev.neqabacare.com`, including its own sign-in | PENDING | |
| CUT-6 | after-cutover | The SES records were untouched: a test email still shows SPF, DKIM and DMARC PASS, and mail to `notifications@` still arrives | PENDING | |
| CUT-7 | after-cutover | The availability test and alert follow the final host (`/api/ready/` on `neqabacare.com`) | PENDING | |

## Before notifications go live

Production first runs with notifications off, then a real allowlist trial. `live` is a separate
owner decision. Formal legal sign-off and the AWS reputation alarms were declined by the owner, so
they are **not** gates here; the risk was explained and recorded (`docs/security.md`).

| ID | Stage | Check | Status | Evidence |
|---|---|---|---|---|
| NOTE-1 | before-live | With notifications off, a status change creates rows and nothing is sent | PENDING | |
| NOTE-2 | before-live | A dedicated, narrow production SES sender exists in the selected AWS Region, separate from dev's; its rotation date is recorded | PASS | IAM user `neqabacare-ses-sender-prod` (path `/service/`, no groups or attached policies), separate from dev's `neqabacare-ses-sender`. One inline policy, `ses-send-notifications-only`: `ses:SendEmail` only, on the `neqabacare.com` domain identity in `eu-north-1`, with `StringEquals ses:FromAddress = notifications@neqabacare.com`. `SimulatePrincipalPolicy` (with `aws:RequestedRegion=eu-north-1`): allowed for that address; implicit deny for another From address, for `ses:SendRawEmail` and for another SES action. One key, stored only in the production Key Vault as `aws-access-key-id` and `aws-secret-access-key`; both read back equal and STS returned the new user. No email sent. Rotate by about 2027-02-04 (90 days) (2026-11-06) |
| NOTE-3 | before-live | In `allowlist`, a real email reaches an approved test address, for at least a submitted and a dues event, with links on `neqabacare.com` | PENDING | |
| NOTE-4 | before-live | A recipient not on the allowlist gets nothing and the row ends `SUPPRESSED` | PENDING | |
| NOTE-5 | before-live | A send to the SES bounce simulator ends in a recorded failure, and what happens to bounces afterwards is written down (Q-N16: the app has no bounce feedback today) | PENDING | |
| NOTE-6 | before-live | Pausing the notify job fires `notify-missed-runs`, **a person receives it**, and the schedule is restored | PENDING | |
| NOTE-7 | before-live | The rows waiting from the `off` period are counted, and it is decided what happens to them (`docs/production-runbook.md`, "Switching to live") | PENDING | |
| NOTE-8 | before-live | The owner has decided on `live`; the decision and the date are recorded in `docs/progress.md` | PENDING | |
