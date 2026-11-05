# Staging (retired)

Staging was retired from the active deployment path on 2026-11-05. The owner's decision: dev and
prod only. Nothing for staging was ever created except an empty GitHub environment.

Production now follows [`docs/production-runbook.md`](production-runbook.md), and its acceptance is
recorded in [`docs/production-acceptance.md`](production-acceptance.md). Dev validates the
application, CI checks each release, and restore drills use temporary copies.

What remains, all inactive:

- `infrastructure/parameters/staging.bicepparam` stays as a reference only. No workflow reads it, and
  `infrastructure.yml` still compiles it along with the others.
- The empty GitHub environment `staging` and the unused repository variable `DEPLOY_STAGING` (if it
  exists) can be removed by the owner. This file was kept so old links resolve:

```bash
gh api -X DELETE repos/<owner>/<repo>/environments/staging
gh variable delete DEPLOY_STAGING --repo <owner>/<repo>
```
