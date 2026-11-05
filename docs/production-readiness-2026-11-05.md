# Production readiness review and implementation prompt

Reviewed 5 November 2026. Requested direction: keep dev, skip staging, prepare a separate production environment.

## Assessment

The application has substantial implementation already: Arabic/RTL doctor and admin interfaces, Entra External ID sign-in, server-side fee calculation and validation, document storage, application/payment/dues workflows, audit history, and an email notification outbox. The next work is production deployment and operational verification, not a rewrite.

Skipping a permanent staging environment is workable. Use dev for application validation, automated CI for each release, isolated temporary recovery copies for restore drills, and production acceptance tests before opening registration. Do not turn the existing dev resource group into production or copy its test accounts, applications, or documents.

### Evidence checked

- Local checkout: `fix/notification-alert-secret`, HEAD `14a0012`. `origin/main` and the GitHub main commit endpoint both report `737a66a`, the merge of PR #17. `git diff HEAD origin/main` contains documentation changes only; the application and workflow findings below therefore also apply to that main revision. Start implementation from current main in a clean branch without disturbing this checkout's untracked audit and `outputs/` files.
- Azure resource-group inventory in the current subscription returns only `Medical_App`, in UAE North. Its resource inventory contains dev services and the four notification alert rules; no separate staging/prod resource groups were returned.
- Dev notify job: real providers, `allowlist`, SES `eu-north-1`, schedule every five minutes, image `c5958d0...`. No secrets were read.
- PR #17/main's rollout notes and the IDE memory record real inbox delivery, SPF/DKIM/DMARC PASS, and a working forwarding mailbox. These are owner-reported checks. Alert firing, bounce handling and allowlist suppression on Azure remain unproven. Do not redo the failed alert-test API attempts; investigate using a controlled test agreed with the owner.
- The GitHub prod environment endpoint shows a required reviewer and protected-branch deployment policy. Branch-protection inspection returned 401, so current required status checks were not independently verified.
- Executed now: `npm run typecheck` passed; production-settings, Bicep job-environment and management-command tests: **102 passed**, with one pytest cache-write warning.
- Full PostgreSQL/Azurite tests, browser E2E, restore drills, production startup and cloud writes were not run. Docker is not running locally. Historical suite counts are not fresh execution evidence.

## Priorities before launch

| Priority | Finding and evidence | Required result |
|---|---|---|
| P1 | All three deploy workflows use `deploy-prod.needs: deploy-staging`; staging is conditional on `DEPLOY_STAGING`. See `.github/workflows/{backend,frontend,infrastructure}.yml`. | Remove staging from the active release path. A disabled staging job must never suppress prod. Avoid `always()` as a shortcut that also permits deployment after failed validation. |
| P1 | Backend/frontend/infrastructure deploy independently. E2E is a separate PR/manual workflow and is not a deploy prerequisite. | Release one selected main commit after all relevant checks and dev validation pass. Keep normal merges deploying dev; make production release explicit and reviewed. Coordinate infrastructure, migration, backend and frontend compatibility. |
| P1 | `prod.bicepparam` has no notification parameters. `main.bicep` defaults notifications to disabled/off. | Add the prod equivalents of dev's environment-variable wiring, including the alert receiver secret. Bootstrap with notifications off, then a controlled real-provider allowlist trial, then an explicit decision to switch to live. |
| P1 | No production Azure environment exists in the inspected subscription. The existing pipeline cannot bootstrap all prerequisites by itself: without a running app image it deploys only phase 1. | Complete resource group, prod OIDC deploy identity/RBAC, runtime identity, prod Key Vault secrets, Entra client, PostgreSQL administrator/database/principal, image upload, app/jobs and SWA link. Use deployment outputs, not invented resource names. |
| P1 | First deployment creates the web app before migrations. `backend/config/health.py` readiness executes only `SELECT 1`. The deployment guide explicitly records the resulting initial failure window. | Keep public access unavailable until migrations and acceptance checks finish, or split job/application bootstrap so migrations precede serving. A connectivity probe alone does not prove schema, Blob access, authentication, or business readiness. |
| P1 | `neqabacare.com` currently belongs to dev. The app has a single configured Entra redirect origin. | Prepare a dev-host change and a production domain/certificate/DNS/default-domain cutover together with Entra callbacks, logout URL, allowed hosts, CSRF origins and notification links. Verify login and a real authenticated POST on the final hostname. |
| P1 | `entraAdminRequireMfa=false` intentionally relies on tenant Conditional Access. Application role checks do not prove the CA policy exists or covers the production app/admins. | Verify the production registration/user-flow association, admin group membership, enforced CA policy, and real admin MFA before granting the initial production admin role. Do not flip the app flag based on an assumed `amr` claim. |
| P1 | Payment text remains marked `PLACEHOLDER` in `frontend/src/i18n/ar.ts:622`. Several newer signed-in workflows remain on the owner smoke-test list. | Supply final payment instructions and validate the complete member/admin journey, including correction, receipt rejection/replacement, dues and print. |
| P1 | Restore procedures predate notifications: they update migrate/cleanup only and call the direct Container App hostname, which is protected by SWA authentication. | Restore instructions must pause writers, notify and destructive cleanup; update app plus every enabled job; validate through SWA; preserve restored server selection on future Bicep deploys; reconcile notification replay before resuming sending. Run a drill on isolated copies and record actual recovery time/data loss. |
| P2 | Monitoring module creates workspace/App Insights, and a separate module creates notification alerts. There are no explicit general availability, API error-rate, latency, database capacity or cleanup-failure alert resources. | Add a small set of actionable production alerts with a tested human receiver. Verify Entra-only App Insights ingestion and command-job console log visibility. |
| P2 | Python requirements use version ranges for most packages; container image tags use commit SHAs but are not digest-pinned. | Produce reproducible dependency resolution and a release manifest with source SHA, backend digest and frontend artifact identity. Preserve previous release artifacts beyond the existing seven-day GitHub artifact retention when needed for rollback. Scan dependencies/images and define updates. |
| P2 | Production is sized for one warm 1 vCPU/2 GiB replica, up to five; GP PostgreSQL D2ds_v5/64 GB, HA disabled; logs are uncapped. | Verify regional availability/quotas and expected concurrency/DB connections with a small load test. Agree an uptime/recovery target and budget. Do not describe disabled PostgreSQL HA as automatic failover. |
| P2 | `CURRENT_FISCAL_YEAR` defaults to 2026 in settings and is not wired by Bicep. | Make the active fiscal year explicit in deployment configuration and prepare/test the next year's fee schedule and activation process before rollover. Do not infer business fiscal-year rules from the calendar. |

### Recovery limitations to account for

Production currently configures PostgreSQL 35-day PITR and geo-redundant backups, Blob ZRS, 14-day Blob soft delete, 90-day previous-version cleanup and 90-day Key Vault soft delete/purge protection. These settings are useful, but they are not a completed disaster-recovery exercise.

Blob ZRS is within-region redundancy; it does not provide the document copy in another region that a regional rebuild would need. Decide whether whole-region recovery is required before promising it. Recovery must cover database rows, document bytes, secret availability and configuration together. Database restore can bring back old outbox rows and cause repeat notifications; leave sending paused until reconciliation is complete. Cleanup against an older database can delete newer blobs, so it must also stay paused during reconciliation.

### Existing decisions to preserve

- OCR off; no Azure OpenAI resource for production.
- Public service endpoints with Entra/RBAC controls; private networking off.
- Malware scanning off, as already chosen. Do not imply it exists by setting the flag: there is no completed scanning pipeline in this review.
- Admin MFA through Conditional Access.
- Email through SES; WhatsApp remains parked.
- The current handoff records that the owner declined formal legal sign-off and AWS bounce/complaint CloudWatch alarms. Preserve those decisions in status documentation; do not add those items back as hidden launch gates. Email feedback and suppression verification remain separate operational work.
- AWS federation is deferred. Production currently needs SES keys; `AWS_ROLE_ARN` alone does not implement a working token bridge. Use a separate narrowly scoped prod sending identity/credentials and a prod vault, with a documented rotation process. The handoff records dev key rotation due around 2 February 2027; do not assume that is the expiry of a future production key.

### Work after initial deployment

- Record the remaining functional business decisions in one current list; old progress entries include superseded statements and are not all current blockers.
- Set ownership for incident response, admin onboarding/revocation, secrets rotation and recovery drills.
- Define operational retention for applications, documents, notifications, audit and backups. Cleanup currently removes expired sessions and orphan/soft-deleted blobs; it does not implement a general retention policy. Do not invent destructive retention periods or delete records without an agreed policy.
- Consider self-hosting Cairo and frontend code splitting after launch if privacy/performance goals justify them; these are not prerequisites for a production resource group.

## Copyable implementation prompt

```text
Prepare and implement production deployment for this Medical_App_Azure repository using DEV and PROD only. Skip staging entirely in the active deployment path. Keep dev as the validation environment; production must be a separate environment with separate data and credentials.

First read CLAUDE.md, PROMPT.md, the latest docs/progress.md, docs/production-readiness-2026-11-05.md, docs/azure-deployment.md, docs/deployment-path.md, docs/github-setup.md, docs/entra-setup.md and the current notification implementation. Reconcile old docs with current main and observed state. Preserve existing local/untracked files; work from current main in an isolated branch/checkout. Do not treat the old notifications design audit as proof of current implementation defects: substantial implementation followed that audit.

Preserve the owner's choices: production OCR off, private networking off, malware scanning off, admin MFA through Conditional Access, SES email only, WhatsApp parked. Formal legal sign-off and AWS reputation alarms were declined; record that decision without reopening it. Do not enable any optional provider or service silently.

Do the authorized local implementation and verification before requesting cloud-write approval. Deliver working code/configuration/scripts and exact commands, not only an architecture plan. This request does not authorize billable resources, DNS/certificate changes, real sends, dev mutations, git push/merge, or production cutover. Present a concrete reviewed change and targeted approval step before such external actions; after approval, execute the covered work without repeatedly asking.

1. Fix releases
- Remove deploy-prod's dependency on deploy-staging in backend, frontend and infrastructure workflows. Remove staging from active dispatch choices and promotion instructions; legacy parameter files can remain inactive for reference.
- Normal merges keep deploying dev. Add an explicit production release workflow for a selected tested commit from protected main, using GitHub environment prod with its reviewer and main-branch restriction. Reject untrusted refs and ensure an input SHA actually belongs to protected main.
- Run or verify successful backend, frontend, Bicep/security and E2E checks for that exact release. Handle path-filtered checks without deadlocking unrelated PRs or allowing unchecked application releases. Require dev deploy/acceptance evidence for the same application artifacts.
- Build once and promote those artifacts. Record source SHA, backend digest and frontend artifact identity; retain the previous production release. Coordinate infrastructure, migration, backend and frontend order, with backward-compatible schemas/APIs. Keep backend/Bicep deployment locking and migration-failure behavior. Prevent an older queued release from replacing a newer accepted release.
- If the what-if must be reviewed before applying, expose it before the apply approval; the existing prod environment gate alone occurs before its what-if step. Avoid duplicate automatic prod jobs left in old workflows.

2. Complete production configuration and bootstrap
- Extend infrastructure/parameters/prod.bicepparam to read ENABLE_NOTIFICATIONS, NOTIFICATIONS_MODE, SES_ACCESS_KEY_FROM_KEY_VAULT, SES_REGION, SES_FROM_ADDRESS and ALERT_EMAIL, following dev's existing pattern. Keep ALERT_EMAIL an environment secret and keep secrets out of logs. Keep app and notify settings aligned; migrate and cleanup must not receive sending credentials/settings.
- Use current prod sizing as the baseline. Verify the chosen Azure data region, SWA region, SKU/quota support, backup/storage capabilities, expected load and current costs before resource creation. Make the active fiscal year explicit. Do not silently downsize services or enable PostgreSQL HA.
- Provide an idempotent first-deploy sequence: resource group and phase 1; prod GitHub OIDC deploy identity with scoped RBAC; runtime identity; Key Vault secrets; separate prod Entra application and its user flow; PostgreSQL Entra administrator/database/principal; trusted release image push; migrate and cache table; app, jobs and SWA backend link; frontend deployment; acceptance checks. Discover real identifiers from outputs. Never use seed_dev_data or copy dev data/secrets blindly.
- Address the bootstrap cycle explicitly: existing infrastructure CI cannot deploy phase 2 until a running app already exists. Keep first-deploy public traffic and scheduled sending unavailable until schema and required data are ready. Do not treat SELECT 1 readiness as proof of schema/functional readiness.
- List required prod GitHub variables, vault secret names and secure input steps without reading or printing secret values. Use a dedicated least-privilege SES production sender credential; federation is a separate deferred task.

3. Prepare domain and identity cutover
- neqabacare.com currently points at dev. Prepare the dev replacement hostname and prod binding/DNS/TLS/default-domain plan, including any binding transfer window and rollback. Do not assume DNS changes alone transfer an SWA custom domain.
- Keep Entra callback/logout URLs, PUBLIC_HOSTNAME, allowed hosts, CSRF origins and notification URLs consistent at every phase. Test prod first on a temporary hostname with matching callbacks, then test again on the final hostname. Check old/default-host redirects and session behavior.
- Verify the prod Conditional Access policy targets the prod app and admin group and prove MFA with a real admin sign-in before grant_admin. The app's disabled amr check does not prove MFA is enforced.

4. Complete launch checks and operations
- Replace payment.instructions only with supplied final payment wording. If it is missing, continue all independent work and list it as a remaining launch input.
- Test a new doctor, Arabic digit normalization, document access boundaries/uploads, fee quotes, submit, correction/resubmit, receipt rejection/replacement/confirmation, dues request/rejection/re-upload/confirmation, approval/rejection and print. Include a phone-width RTL check. Verify real Entra login, logout and a CSRF-protected mutation on the final origin. Check direct backend protection, proxy/throttle assumptions and upload size limits.
- Deploy notifications initially off, then real-provider allowlist with only approved test recipients. Verify production SES regional access/identity, received email links, suppression and bounce-feedback handling. Existing dev delivery/SPF/DKIM/DMARC/forwarding evidence is already recorded. Prove the Azure alerts reach a person using a controlled test; do not keep retrying the rejected test-email API. Switch live only in the separately approved cutover and define handling of accumulated outbox rows.
- Add actionable availability, 5xx/latency, database capacity and scheduled-job failure monitoring; confirm Entra-authenticated App Insights ingestion and access to migrate/cleanup logs. Name the alert receiver/incident owner. Do not add the declined AWS reputation alarms.
- Update restore/rollback instructions for the app plus migrate, cleanup and notify jobs. Pause traffic/writers/sending/cleanup during restore; avoid notification replay and deleting post-restore-point blobs; make restored DB selection survive the next Bicep deployment. Validate via the SWA hostname, not the protected direct app URL. Run database, document and secret recovery checks on isolated temporary copies with synthetic data and sending disabled. Record measured RPO/RTO and the Blob cross-region limitation. No permanent staging environment is needed.
- Preserve append-only audit behavior. Document an operational retention policy without inventing durations or enabling destructive deletion. Add dependency/image scanning and reproducible dependency resolution, secret rotation ownership, a current regional cost estimate and budget tracking.

5. Verify and deliver
- Run meaningful regression checks for changed behavior, full backend tests against PostgreSQL, Azurite integration, frontend CI, browser E2E, Django deploy checks, fresh-database migrations, Bicep build/lint/parameter compilation, template security checks, script/workflow validation and dependency/secret scans. Clearly distinguish executed tests, historical evidence and checks needing credentials or user interaction.
- Produce a production runbook with separate bootstrap, normal release, final domain/live cutover and rollback procedures; an environment variable/secret inventory; a release manifest; an acceptance checklist with pass/fail/evidence; and remaining inputs limited to genuine missing information.
- Update current docs so none require staging. Do not call production ready until the actual production checks pass. If cloud actions are not yet approved, finish the local changes and return the exact deploy/what-if commands and approval scope with outstanding acceptance steps marked pending.
```

## Primary references

- [GitHub job dependency behavior](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs): skipped dependencies propagate to dependent jobs.
- [SWA default-domain management](https://learn.microsoft.com/en-us/azure/static-web-apps/custom-domain-default): a designated custom default domain redirects other configured domains.
- [PostgreSQL backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore): PITR retention and geo-backup configuration/recovery behavior. Verify regional support before provisioning.
