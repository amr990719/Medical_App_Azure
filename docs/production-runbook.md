# Production runbook

How production is created, released, moved to `neqabacare.com`, recovered and run. There are two
environments: **dev**, where every merge deploys, and **prod**, which only changes through the steps
below. There is no staging: dev validates the application, CI checks each release, temporary copies
carry restore drills, and acceptance checks run on production before it opens.

**Status (2026-11-05): production does not exist. Nothing here has run against production.**
Commands and scripts passed the local checks listed in `docs/progress.md`. Anything that needs Azure,
Entra, GitHub or AWS is **NOT VERIFIED — requires Azure credentials** until
`docs/production-acceptance.md` records it. Production is ready only when that record is complete.

Every step that creates billable resources, changes DNS, changes trust or sends a real message needs
the owner's approval first. Each script only shows what it would do until given `--execute`.

| When | Go to |
|---|---|
| First time | [Bootstrap](#bootstrap) |
| Shipping a change | [Normal release](#normal-release) |
| Moving the domain | [Domain cutover](#domain-cutover) |
| A release went wrong | [Rolling back a release](#rolling-back-a-release) |
| Data or documents went wrong | [Recovery](#recovery) |
| Turning on email | [Notifications](#notifications) |

## How a release works

```text
merge to main
  backend, frontend, infrastructure, e2e  (path filtered; each runs on what changed)
  dev deploys; the backend image and frontend build stay in the dev registry, by commit

person: gh workflow run release-production.yml -f sha=<commit> -f mode=release -f dev_acceptance=<link>
  verify    the commit is on main; each component's checks and dev deployment succeeded
  export    copy both artifacts out of the dev registry, digests unchanged
  preview   APPROVAL 1, then shows what-if, new migrations and the dependency audit
  deploy    APPROVAL 2, then in one job:
              refuse an older release, or a recovery hold
              copy the artifacts to the production registry (the digest must match)
              infrastructure (keeping the running image)
              migrate job, once       <- the previous revision keeps serving
              release_check           <- schema, cache, fee schedule, documents, sign-in
              cleanup and notify jobs -> new image
              new revision            <- traffic moves only when it is ready
              frontend
              smoke test through the public host
              release record in the registry
```

Why it is shaped like this:

- **Same artifacts.** Images are copied by digest with `skopeo`, which keeps the manifest bytes. Dev
  and production run identical bytes, and images run by digest, never by a tag.
- **Path filters.** A commit that only changes docs has no build of its own. Each component's evidence
  comes from the last commit at or before the selected one that changed that component, which is
  exactly what the selected commit contains (`infrastructure/scripts/release_gate.py`). E2E now also
  runs on pushes to `main`, because a pull request's run tests a different commit.
- **Two approvals.** A what-if needs the write-capable identity (D145), so the first approval only
  releases the preview. The second, after reading it, is the one that changes production.
- **Older releases.** The order check runs with the deployment lock held, so a queued older release
  cannot replace a newer one. GitHub keeps only one *pending* run per concurrency group, so a third
  queued run replaces a pending one; start it again if that happens.
- **Compatibility.** While migrations run, the previous image serves the new schema; while the
  frontend deploys, the new backend serves the old frontend. Migrations and APIs must therefore stay
  expand/contract. The preview flags new migrations with contract operations (`RemoveField`,
  `RenameField` and so on) for a person to check.
- **Readiness.** `/api/ready/` now also fails while a migration this image knows about is unapplied,
  and `release_check` covers what a web request cannot. An older image on a newer schema stays ready,
  which is what makes a rollback possible.

A green release means the deployment worked. It does not mean production is accepted.

## Bootstrap

The problem it solves: the normal pipeline cannot create what it needs. Key Vault references resolve
when an app is created, so secrets come first; a release needs identities and variables; and without
care the web app would start before its schema exists. So a person does the foundation with a script,
and then the same reviewed workflow does the rest, in `bootstrap` mode, applying the schema before
anything serves.

```bash
cp infrastructure/production-bootstrap.env.example .env.production-bootstrap   # ignored by Git
# Fill it in. Confirm the data region: moving it later is a rebuild.
B="infrastructure/scripts/bootstrap-production.sh --env-file .env.production-bootstrap"
$B status
$B preflight                  # read only: tools, sign-in, GitHub protection, region, SKU, policy
$B resource-group  [--execute]
$B github-oidc     [--execute]   # runtime and deploy identities, federated to the environment prod
$B foundation      [--execute]   # always shows what-if first
$B django-secret   [--execute]   # generated in place; never replaced; never printed
$B entra           [--execute]   # medical-syndicates-prod, on the default host, with user flow
$B postgres        [--execute]   # Entra admin group, database, runtime identity role
$B github          [--execute]   # prod variables from deployment outputs; the ALERT_EMAIL secret
$B next
```

Bash only (Git Bash on Windows). Each stage looks before acting, and is safe to run again. Then set
the variables the `github-oidc` and `entra` stages printed. Then, in the external tenant, the
Conditional Access steps in `docs/entra-setup.md` section 4.

Merge the commit, let dev deploy it, accept it on dev, and start the bootstrap:

```bash
gh workflow run release-production.yml --repo <owner>/<repo> --ref main \
  -f sha=<commit on main> -f mode=bootstrap -f dev_acceptance=<link to the dev acceptance record>
```

Approve the preview, read it, then approve the deployment. It runs, in order: copy the artifacts →
**migrate job only** (`DEPLOY_WEB_APP=false`) → migrations → `release_check` → **app, schedules and
SWA link** → `release_check` → frontend → smoke test → release record. Notifications stay off: their
variables are not set yet, so no notify job exists.

`release_check` can be repeated at any time:

```bash
infrastructure/scripts/run-job-command.sh --job <migrate-job> --resource-group <rg> \
  -- python manage.py release_check
```

Production now answers on its default `*.azurestaticapps.net` host. **Anyone who has that address
can reach it, and sign up.** Logs mask it, but treat it as findable: that is not access control. What
protects this stage is that it holds no real data and sends nothing. Do not put real people or real
documents on it until acceptance is done.

Expect one `cleanup-missed` email when the alerts are first created, because no cleanup has run yet.
It clears after the first night's run.

**Before this bootstrap, once:** set `ENABLE_SERVICE_ALERTS=true` on dev and deploy, to prove
`modules/service-alerts.bicep` deploys somewhere it cannot hurt, and that `OBS-3` reaches a person.
Then remove it, because each alert and availability run is billed.

Then: `docs/production-acceptance.md`, stage `before-admin`, including proving MFA **before** the
first grant. Grant the first administrator:

```bash
infrastructure/scripts/run-job-command.sh --job <migrate-job> --resource-group <rg> \
  -- python manage.py grant_admin <email-or-oid>
```

## Normal release

```bash
# 1. The commit is merged; dev deployed it; it is accepted on dev. Record where.
# 2. Start it, from main:
gh workflow run release-production.yml --repo <owner>/<repo> --ref main \
  -f sha=<full commit sha> -f mode=release -f dev_acceptance=<link>
# 3. Approve the preview. Read the what-if, migrations and audit in the run's summary.
# 4. Approve the deployment.
# 5. Read the release record in the summary; check production.
```

If it stops, nothing is half-promoted on the app:

| Stops at | State | Do |
|---|---|---|
| verify or export | nothing changed | fix the cause (usually a missing run), or pick another commit |
| preview | nothing changed | do not approve the deployment |
| infrastructure | possibly part-applied, app unchanged | read the error, re-run the job |
| migrate | old revision still serving, on whatever applied | fix forward with a new migration; never edit an applied one |
| `release_check` | schema applied, old revision serving | read the job's log (below), fix, re-run |
| new revision | previous revision keeps serving | read the revision's logs, fix, re-run |
| frontend or smoke test | **new backend is live**, with the old or new frontend | re-run, or roll back to the release on record (below) |

```bash
az containerapp logs show -n <app> -g <rg> --type system --format json --tail 30
az containerapp logs show -n <app> -g <rg> --type console --tail 40
```

Job logs go to Log Analytics (`docs/azure-deployment.md`, "Telemetry verification"):
`ContainerAppConsoleLogs_CL | where ContainerGroupName_s startswith "<execution>"`.

**Configuration between releases** (notifications mode, hold, hostname): change the GitHub variable,
then run `infrastructure.yml` manually for `prod`. It waits for the reviewer, keeps the running image,
and deploys the template **of the current release**, so unreleased Bicep cannot reach production this
way. Run it with `what_if_only=true` first to read the preview.

**If a merge had its run replaced:** GitHub keeps one pending run per concurrency group, so a third
quick merge can replace the second's `backend` or `frontend` run, and that commit cannot release.
Release the newest commit instead; it contains the older one. Do not re-run the replaced run: it would
deploy the older image to dev.

**After this branch merges:** `production.py` refuses to start without `CURRENT_FISCAL_YEAR`, which
Bicep now sets. On that first merge, `infrastructure` normally reaches dev well before `backend`. If
the backend deploy gets there first, its migrate job fails and the running revision is untouched:
re-run it once `infrastructure` succeeds.

## Domain cutover

`neqabacare.com` serves dev today (D185). Azure refuses to bind one domain to two Static Web Apps in
the same slice, so DNS alone cannot move it. The slice is the number in
`<random>.<slice>.azurestaticapps.net`. With the same slice, the window between detaching from dev and
attaching to production is a real outage, of minutes. Microsoft's TXT route suggests a different slice
might avoid it; that is not verified, so plan for the outage either way and announce it.

```bash
C="infrastructure/scripts/cutover-domain.sh --repo <owner>/<repo> --dev-group Medical_App --prod-group <prod-rg> \
   --entra-tenant <external-tenant-id> --subscription <subscription-id>"
```

| # | When | Step | What it does, and why here |
|---|---|---|---|
| 1 | days before | `$C preflight` | refuses while the payment text is a placeholder, or an acceptance row before cutover is open |
| 2 | days before | `$C prepare-dev --execute` | `dev.neqabacare.com` on dev (add the CNAME it prints first), and dev's Entra URIs. Nothing visible changes |
| 3 | days before | `$C prepare-prod --execute` | adds `https://neqabacare.com/...` to the production Entra app. Existing URIs stay, so the temporary host keeps working |
| 4 | start of window | `$C move-dev --execute` | dev's `PUBLIC_HOSTNAME`, so its sign-in, CSRF, links and hosts follow together. Wait for the run |
| 5 | window | `$C detach-dev --execute` | **outage starts** |
| 6 | window | `$C attach-prod --execute` | binds production, prints the exact Cloudflare changes. Make them, then wait for `Ready` |
| 7 | window | `$C switch-prod --execute` | production's `PUBLIC_HOSTNAME`: allowed hosts, CSRF origins, Entra URLs and notification links all change in one deployment. Refused until the binding is `Ready`. Wait for the run. **Outage ends** |
| 8 | window | portal: Static Web App → Custom domains → `neqabacare.com` → **Set default** | no CLI exists. Makes the default host redirect, so a sign-in cannot start on the wrong origin (Q-T24) |
| 9 | window | `$C verify`, then by hand | smoke check with the redirect, then a real sign-in, a real change and a sign-out. Record `CUT-1` to `CUT-7` |

**DNS safety:** change only the apex and `www` CNAMEs and the SWA validation TXT. SES depends on
the DKIM CNAMEs, custom MAIL FROM, SPF and DMARC; mail depends on the routing of `notifications@`.
An apex TXT record can hold SPF, so read it before editing. The apex stays **DNS only** (D185): a
proxy would add a third `X-Forwarded-For` hop and sit in front of SWA's certificate.

**HSTS:** `includeSubDomains` already applies, so `dev.neqabacare.com` must be HTTPS from its first
visit; SWA provides the certificate.

### Rolling back the cutover

Decide before the window: if a real sign-in on the final host does not work within the agreed time,
roll back rather than debug live.

```bash
$C rollback --execute
```

It removes the binding from production, removes production's `PUBLIC_HOSTNAME` (back to its default
host) and redeploys, prints the Cloudflare changes, rebinds dev and sets dev's `PUBLIC_HOSTNAME` back.
It can be repeated, and skips what is already undone. The Entra URIs stay; they are harmless. Sessions
do not survive either way: cookies are per host.
If production was already set as the default domain, Azure may refuse to remove the binding until
it is unset in the portal (NOT VERIFIED); check that first when the time matters.

## Rolling back a release

Migrations are expand/contract, so the previous image works on the newer schema. A rollback never
reverses a migration and never changes infrastructure.

```bash
gh workflow run release-production.yml --repo <owner>/<repo> --ref main \
  -f sha=<an earlier released commit> -f mode=rollback -f dev_acceptance="<why>"
```

There is no preview, so it needs one approval. It reads that release's digests from the production
registry, points the jobs at the old image, creates a revision, and redeploys that frontend. Retained
indefinitely: `medical-release:<sha>`, `:current`, `:previous`, and every promoted image. **Do not add
a registry purge** without keeping those. Fix forward through a normal release afterwards; the order
check accepts any commit newer than the rollback's.

**After a release that failed part way**, name the commit in `medical-release:current`. The record is
the release's last step, so it still names what last worked, while the new image may already be live.
Read it in the summary of the last successful release run.

A rollback is allowed during a recovery hold, and skips the smoke test, which a closed ingress could
only fail. Nothing in it needs a preview: it deploys no template.

If the schema itself is the problem, a rollback will not help: see Recovery.

## Recovery

### What protects what

| Store | Protection in production | Limit |
|---|---|---|
| PostgreSQL | 35-day point-in-time restore, geo-redundant backup | HA is **off**, so there is no automatic failover. A restore makes a **new server** |
| Blob documents | ZRS, 14-day soft delete, 90-day previous versions | **ZRS stays in one region.** A regional loss leaves the database restorable and the documents not, unless the owner chooses GZRS (a cost decision) |
| Key Vault | 90-day soft delete, purge protection | nobody can purge early, including an owner |
| Configuration and code | Git, the production registry, GitHub variables | Entra users live in the tenant; Microsoft operates it |

Measured on dev on 2026-11-06 for the database and secrets; documents and a regional loss are not drilled (acceptance `REC-1` to `REC-6`).

| Scenario | Target RPO | Target RTO | Measured |
|---|---|---|---|
| Bad release, schema intact | 0 | ~10 min | PENDING |
| Data damaged | ≤ 5 min before the damage | 1-2 h | about 40 min on dev (2026-11-06): 36 min from hold to ready, plus hold-off. The data lost is whatever came after the chosen restore point |
| Deleted or overwritten document | 0 within the window | minutes | PENDING |
| Deleted secret | 0 within the window | minutes | 14 s to recover a deleted secret, on dev (2026-11-06) |
| Region lost | database ≤ 1 h; **documents not recoverable with ZRS** | several hours, not promised | not drilled |

These are assumptions to confirm with the owner. Do not promise whole-region recovery without choosing
it, paying for it and drilling it.

### Restoring the database

The dangers of restoring are not the restore itself. An old database brings back old outbox rows,
which would send again. Newer blobs look like orphans, which cleanup would delete. And the next
deployment would point the app back at the damaged server. The hold and the selected server are
**GitHub variables that the parameter files read**, so each survives every later deployment.

```bash
R="infrastructure/scripts/recovery.sh --environment prod --repo <owner>/<repo> --resource-group <rg>"
T=2026-11-05T08:00:00Z           # UTC, just before the damage. Note who chose it and why.

$R status
$R hold-on --execute             # closes the app, moves both schedules, notifications off. Wait for the run.
$R restore-db --restored-name <new-server> --restore-time "$T" --execute     # the original stays untouched
$R prepare-db --restored-name <new-server> --execute                         # Entra admin, role, grants
$R select-db  --restored-name <new-server> --execute                         # read the what-if. Wait for the run.
$R check --execute                                                           # does its schema match the image?
#  Only if `check` reports pending migrations, which means T predates one. Choose:
#    the damage came with that release: mode=rollback to the release matching T's schema, or
#    it did not: $R migrate --restored-name <new-server> --execute
$R reconcile --restored-name <new-server> --restore-time "$T" --execute          # documents, then a dry run
$R reconcile --restored-name <new-server> --restore-time "$T" --apply --execute  # in-flight rows end SUPERSEDED
$R check --execute                                                           # release_check, again
gh variable set NOTIFICATIONS_MODE --env prod --repo <owner>/<repo> --body off   # a staged return
$R hold-off --execute
```

- **The hold** is `RECOVERY_HOLD`. Every deployment while it is set closes the app's ingress with an
  allow rule nothing can match (TEST-NET-1), forces notifications off, and moves the cleanup and notify
  crons to 1 January. A release refuses to run during a hold. If it could reach 1 January, one cleanup
  would run: move it or clear the hold first.
- **The selected server** is `POSTGRES_SERVER_NAME_OVERRIDE`. Bicep then manages the restored server as
  this environment's server, so `DATABASE_URL` and the firewall rule follow it. A restore does **not**
  copy firewall rules or server parameters, and Microsoft does not state whether it copies the Entra
  admin, which is why `prepare-db` and the deployment set them again. Whether that deployment accepts a
  restored server unchanged is **NOT VERIFIED** until `REC-5`: read its what-if, and if PostgreSQL storage
  auto-grew past `postgresStorageSizeGB`, raise the parameter first, because storage cannot shrink.
- **Notifications.** A row in flight at the restore point may already have been sent afterwards, and
  the restored database cannot tell. `reconcile_notifications --apply` ends those rows `SUPERSEDED`
  with `RESTORE_RECONCILED`, without a fallback. Some doctors may then miss a notification; that is
  chosen over telling everyone twice. An admin can resend a row on purpose. **It cannot see the
  sending mode through the migrate job**, so `recovery.sh` refuses unless the notify job shows the hold,
  neither job has a run in progress, and the migrate job really uses the restored server.
- **Documents.** `reconcile_documents` only reads. `missing_blobs` are rows without bytes: restore them
  (below); it exits non-zero, which stops `reconcile`. `orphans_newer_than_restore_point` are real
  uploads whose database rows were lost. **Cleanup would delete them.** Keep the hold until a person
  has decided about each, and export anything to keep. Soft delete gives 14 more days as a backstop.
- **Validating.** Through the public host only, after hold-off. The app's own address answers 401 by
  design, and during a hold the public API refuses everyone. `release_check` is the check during a hold.

After the restored data is accepted, delete the damaged server by hand, leaving the override in place.
The override stays for the life of that server. Keep the override's value in the incident record.

**Every job after a restore:** `migrate` runs only with a release or `recovery.sh migrate`; `cleanup` and
`notify` return on their schedules at hold-off, on the selected server. `reconcile` and `check` run as
executions of the migrate job, which has no notification settings, so they cannot send.

### Restoring a document

`docs/azure-deployment.md` section B has the commands. Grant yourself *Storage Blob Data Contributor*
for the duration, then remove it. A downloaded document is personal data.

### Recovering a secret

`docs/azure-deployment.md` section C. After recovering, restart the active revision so Container Apps
reads it again; the same for the notify job's next run.

### Restore drills

Quarterly, on **temporary copies with synthetic data and sending off**; no permanent environment is
needed. The drill for dev costs little; run it there first.

```bash
R="infrastructure/scripts/recovery.sh --environment dev --repo <owner>/<repo> --resource-group <dev-rg>"
```

1. Note the time `T`. Create a test application with documents. Delete one document and overwrite one.
2. On a production drill: use a **temporary server and a temporary storage container**, never the live
   ones. Restore to `T` as a new server with `az postgres flexible-server restore`, and point nothing
   at it except a job execution.
3. Run `release_check`, `reconcile_documents` and `reconcile_notifications` (dry run).
4. Record measured RPO, measured RTO and every surprise in the table above and in `docs/progress.md`.
5. Delete the temporary server. Check the bill.

`REC-4` and `REC-5` need the real hold and override, so do those on dev.

## Notifications

Each stage is a variable change, then a manual `infrastructure.yml` run for `prod`, which waits for the
reviewer. Before enabling, also set `NOTIFY_JOB_NAME` after the first deployment that creates the job,
so releases keep it on the new image (`recovery.sh` and alerts read the deployment's output instead).

| Stage | Variables | Needs |
|---|---|---|
| Off (bootstrap) | none | nothing; rows accumulate and expire after 72 h |
| Job created, sending off | `ENABLE_NOTIFICATIONS=true`, `NOTIFICATIONS_MODE=off` | nothing secret |
| Allowlist trial | `NOTIFICATIONS_MODE=allowlist`, `SES_ACCESS_KEY_FROM_KEY_VAULT=true`, `SES_REGION`, `SES_FROM_ADDRESS` | the Key Vault secrets `aws-access-key-id`, `aws-secret-access-key`, `notifications-allowlist` (`bootstrap-production.sh ses-secrets`) |
| Live | `NOTIFICATIONS_MODE=live` | the owner's decision (`NOTE-8`) |

- **Credentials.** Federation is deferred, and `AWS_ROLE_ARN` alone does not implement it. Production
  uses its own narrow sender (`ses:SendEmail` on the one identity), never dev's. The dev key's rotation
  date (around 2027-02-02) is not this key's: record production's when it is created.
- **Settings stay apart.** Only the app and the notify job get notification settings. Migrate and
  cleanup never do (`backend/config/tests/test_bicep_job_environment.py`).
- **WhatsApp stays parked**: nothing in `prod.bicepparam` turns it on.
- **Proving the alerts.** `manage.py alert_test` proves the path to a person (`OBS-3`). For the notify
  rules, pause the schedule in a controlled test and restore it (`NOTE-6`). Do not retry the rejected
  test-email API (Q-N17).

### Switching to live

Rows created while sending was off or in `allowlist` wait until they expire (72 h by default). When
the mode changes:

- Rows younger than 72 h that still pass the relevance check **will send**, as soon as the next job
  runs, so a long pause can mean a burst. Count them first (`NOTE-7`), with a dry run that changes
  nothing: `run-job-command.sh ... -- python manage.py reconcile_notifications --restored-to <now>`.
  Decide whether that is wanted; if not, leave the mode off until they expire, then switch.
- Older rows end `EXPIRED`, which raises the `notify-failed-or-expired` alert on the first run, so
  expect that email.
- Rows that ended `SUPPRESSED` during the trial do not return. An admin can resend one on purpose.
- SES reputation is watched by hand: the owner declined the CloudWatch alarms, understanding there is
  no early warning before AWS reviews or pauses sending.

## Monitoring

`modules/service-alerts.bicep` emails `ALERT_EMAIL` through `ag-medsyn-prd-ops`. Thresholds are a
starting point; tune them after `LOAD-1` and real traffic.

| Alert | Signal | Severity | First response |
|---|---|---|---|
| `availability` | `/api/ready/` fails from 2 of 3 locations | 0 | Is the app, the database or Static Web Apps down? Check its revision, then Azure status |
| `api-5xx-rate` | over 5% of at least 20 requests in 15 min | 1 | `AppExceptions`; was there a recent release? Roll back |
| `api-latency-p95` | p95 over 3 s, uploads excluded | 2 | database CPU, replica count |
| `db-cpu`, `db-memory` | over 85% / 90% for 15 min | 2 | slow queries; consider a larger SKU |
| `db-storage` | over 80% | 2 | it auto-grows and never shrinks: find out why |
| `db-connections` | over 100 | 2 | a normal peak is about 20: look for a leak |
| `app-restarts` | over 3 container terminations in 15 min | 2 | console and system logs |
| `cleanup-failed` | `cleanup_run_failed` | 2 | job logs; **do not retry while a restore is being reconciled** |
| `cleanup-missed` | no `cleanup_run` in 2 days | 2 | job execution history (a hold also causes this) |
| `notify-*` | `modules/notification-alerts.bicep` | 2 | `docs/azure-deployment.md` section 11 |
| `ops-alert-test` | `manage.py alert_test` | 4 | none: it is the test |

Availability results go to `appi-medsyn-prd-uptime`, kept apart on purpose: the app's component is
Entra-only, and Microsoft's documentation does not say Standard tests can write to one. The separate
component holds synthetic results only. Three locations every 15 minutes is a cost choice; Microsoft
recommends five. To detect faster, raise `availabilityTestFrequencySeconds`, which costs more.

Declined by the owner and deliberately absent: AWS bounce and complaint alarms. Log volume has no cap
in production, so watch it in the first bill.

## Fiscal-year rollover

The active year is a reviewed commit, `currentFiscalYear` in `dev.bicepparam` and `prod.bicepparam`,
and production refuses to start without it. It is never inferred from the calendar. **No FY 2027
schedule exists yet**: the amounts are a business input.

1. Well before the change, an admin creates the next year's schedule on dev (tiers 0-4, admin fee,
   service fee), and then on production. Nothing uses it until the year changes.
2. Check it on both, without changing anything:
   `run-job-command.sh ... -- python manage.py release_check --fiscal-year 2027`
3. Open a pull request changing `currentFiscalYear` in `dev.bicepparam` only. Accept it on dev: new
   application, quote, submit (reference `MED-2027-…`), with a doctor who has a 2026 application.
4. On the agreed date, a pull request for `prod.bicepparam`; release it, or run `infrastructure.yml`.
5. Earlier applications keep their fiscal year and fee snapshot.

## Dependency updates

| What | How it is pinned | How it updates |
|---|---|---|
| Python | `backend/requirements/*.txt`, hashes, from `*.in` | `backend/requirements/lock.sh --upgrade`, monthly and for advisories, in a pull request; CI refuses a stale lock |
| npm | `frontend/package-lock.json` | Dependabot, monthly |
| Base image | digest in `backend/Dockerfile` | Dependabot, monthly |
| Actions | full commit SHA | Dependabot, monthly |

`security-scan.yml` audits dependencies and the image weekly and on relevant pull requests; the release
preview shows the audit to the reviewer. A finding does not block a release by itself, because a fix may
be the very thing being released. A weekly red run is the signal to act. Secret scanning and push
protection come with the public repository; confirm they stay on. The repository's dependency graph
was off on 2026-11-05, so GitHub's dependency review and Dependabot alerts do not run; the scans above
cover the same ground. To turn them on: Settings → Advanced Security → Dependency graph.

## Who owns what

Until the owner names someone else, each of these is the owner. Update this table when that changes.

| Duty | Owner | Rhythm |
|---|---|---|
| Incident response; the alert address is read | the owner | always |
| Release approval (the `prod` reviewer) | the owner | each release |
| Admin onboarding and revocation (`grant_admin`, `revoke_admin`, the group) | the owner | as needed |
| Secret rotation: Entra client secret (1 year), SES key (about 90 days), `django-secret-key` | the owner | calendar reminder at creation |
| Restore drill | the owner | quarterly |
| Cost review against the budget | the owner | monthly |

Rotating `django-secret-key` ends every session; do it deliberately. SES and Entra: create the new
credential first, then update, then remove the old (`docs/azure-deployment.md` section 11,
`docs/entra-setup.md` section 5).

## Retention

**Nothing here deletes anything new.** Periods are for the owner to decide, and until then nothing is
removed automatically apart from what is listed as automatic. Audit rows stay append-only.

| Data | Today | Period |
|---|---|---|
| Applications, beneficiaries | kept | not decided |
| Documents | kept while active; soft-deleted and orphan blobs removed after the grace period | not decided |
| Notification rows | kept (12 months was proposed) | not decided |
| Audit history | kept, append-only | not decided |
| Sessions | expired ones removed nightly | automatic |
| Logs and telemetry | 90 days (Log Analytics) | set in `prod.bicepparam` |
| Backups | 35 days (PITR), 14 days (blob soft delete), 90 days (blob versions, Key Vault) | set in `prod.bicepparam` |

## Test data

Production acceptance uses synthetic people, made up national IDs and clearly fake documents. Delete
them before opening: applications through the admin interface where it allows, then, for what it does
not allow, a one-off reviewed command, recorded in `docs/progress.md`. The audit history keeps a record
that they existed, which is intended; `MED-2026-` numbers used by test applications are not reused, so
real numbering starts above them.

## Inventory

**GitHub variables, `prod` environment.** None is secret.

| Variable | From | Used by |
|---|---|---|
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | `github-oidc` stage | release, infrastructure |
| `AZURE_RESOURCE_GROUP` | your choice | release, infrastructure |
| `ACR_NAME`, `CONTAINER_APP_NAME`, `MIGRATE_JOB_NAME`, `CLEANUP_JOB_NAME`, `STATIC_WEB_APP_NAME` | deployment outputs (`github` stage) | release |
| `NOTIFY_JOB_NAME` | output `notifyJobName`, after the job exists | release |
| `ENTRA_AUTHORITY`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID` | `entra` stage | release, infrastructure |
| `STATIC_WEB_APP_LOCATION` | your choice (dev uses `eastasia`) | release, infrastructure |
| `POSTGRES_ENTRA_ADMIN_OBJECT_ID`, `_NAME`, `_TYPE` | the admin group | release, infrastructure |
| `PUBLIC_HOSTNAME` | set at cutover; unset means the default host | release, infrastructure |
| `ENABLE_NOTIFICATIONS`, `NOTIFICATIONS_MODE`, `SES_ACCESS_KEY_FROM_KEY_VAULT`, `SES_REGION`, `SES_FROM_ADDRESS` | see Notifications | release, infrastructure |
| `RECOVERY_HOLD`, `POSTGRES_SERVER_NAME_OVERRIDE` | set only during recovery | release, infrastructure, `recovery.sh` |

**GitHub secret, `prod` environment:** `ALERT_EMAIL`. A secret so logs mask it; a release refuses to run
without it.

**GitHub `dev` environment** also needs `ACR_NAME` (already set): dev now stores both artifacts there.

**Key Vault secrets (names only; values never in Git, logs or shell history):**

| Secret | Needed from | Set by |
|---|---|---|
| `django-secret-key` | first app or job | `bootstrap-production.sh django-secret` |
| `entra-client-secret` | first app or job | `create-entra-app.sh`, through the `entra` stage |
| `aws-access-key-id`, `aws-secret-access-key` | `SES_ACCESS_KEY_FROM_KEY_VAULT=true` | `ses-secrets` stage, from files |
| `notifications-allowlist` | `NOTIFICATIONS_MODE=allowlist` | `ses-secrets` stage, from a file |

**Fixed in a reviewed commit, not variables:** OCR off, private networking off (D150), malware scanning
off and no pipeline for it, admin MFA through Conditional Access (`entraAdminRequireMfa=false`), SES only
and WhatsApp parked, the sizing, `currentFiscalYear`.

## Before the first production deployment: what only the owner can give

Tracked with their state in `docs/progress.md`, "Next session starts with":

1. Final payment instructions, for `payment.instructions`. **Supplied 2026-11-06:** the owner's
   wording, a fixed InstaPay QR and its copyable address, implemented on the payment page (PR #28);
   not yet released to production, and `PAY-2` is checked there.
2. A production SES sender. **Created 2026-11-06:** IAM user `neqabacare-ses-sender-prod` (path
   `/service/`), separate from dev's sender, with one inline policy `ses-send-notifications-only` that
   allows only `ses:SendEmail` on the `neqabacare.com` identity in `eu-north-1`, for the From address
   `notifications@neqabacare.com` (`ses:FromAddress` condition). Its key is in the production Key Vault
   as `aws-access-key-id` and `aws-secret-access-key`. Rotate it by about 2027-02-04. Notifications
   stay off: nothing reads these secrets until `sesAccessKeyFromKeyVault` and notifications are enabled.
3. The cutover date, and how long an outage is acceptable.

Answered on 2026-11-05: approval for the cloud steps; the data region is `uaenorth`, which supports the
SKU and geo backup; the first administrator and the alert address (kept out of Git). PostgreSQL's Entra
administrator is the same person as on dev, set by the `postgres` stage, because no group was named.
