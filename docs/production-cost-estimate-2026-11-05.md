# Production cost estimate, 5 November 2026

What production would cost per month at the sizes in `infrastructure/parameters/prod.bicepparam`.
Nothing here has been deployed, so this is an estimate, not a bill. USD retail prices before tax,
730 hours a month. Backend and data in UAE North; Static Web App in East Asia, as on dev.

## Result

| Scenario | What it assumes | Per month | If the environment meter applies |
|---|---|---:|---:|
| Low | Quiet service, replica mostly idle, very few logs | **$250** | $323 |
| Expected | Replica above the idle threshold half the time, 0.5 GB of logs a day | **$324** | $397 |
| Busy | Replica always active, a second replica 30% of the time, 2 GB of logs a day | **$571** | $644 |

**Plan on $324 a month and a $400 budget.** About $237 of this is fixed whatever the traffic. The
biggest open question is the Container Apps environment meter, $73 a month, which the evidence so far
suggests does not apply (see "Not verified").

Fixed sizing, no downsizing: 1 vCPU / 2 GiB app with 1 to 5 replicas, PostgreSQL `Standard_D2ds_v5`,
64 GB, 35-day backups with geo-redundancy, high availability off, ZRS storage, ACR Standard, Static
Web Apps Standard, 90-day log retention. OCR and private networking stay off (owner decision, D150).

## Breakdown

| Item | Low | Expected | Busy | Expected in West Europe |
|---|---:|---:|---:|---:|
| Container App, warm replica | 26.41 | 51.25 | 78.84 | 70.96 |
| Container App, extra replicas | 0.00 | 0.00 | 23.65 | 0.00 |
| Container App, requests | 0.08 | 0.40 | 4.00 | 0.56 |
| Job: notify (8,640 runs) | 7.78 | 11.66 | 15.55 | 16.33 |
| Jobs: cleanup and migrate | 0.05 | 0.13 | 0.31 | 0.18 |
| PostgreSQL compute | 158.41 | 158.41 | 158.41 | 154.76 |
| PostgreSQL storage, 64 GB | 8.83 | 8.83 | 8.83 | 8.76 |
| PostgreSQL backup above the free allowance | 0.00 | 7.56 | 28.56 | 7.42 |
| Blob storage (ZRS) with operations | 1.47 | 1.79 | 7.05 | 1.67 |
| Container Registry Standard | 20.28 | 20.28 | 20.28 | 20.28 |
| Static Web Apps Standard | 9.00 | 9.00 | 9.00 | 9.00 |
| Log Analytics ingestion | 0.00 | 33.59 | 183.69 | 30.52 |
| Log retention past 31 days | 0.78 | 3.89 | 15.58 | 3.83 |
| Key Vault operations | 0.04 | 0.08 | 0.40 | 0.06 |
| Availability test (8,640 runs) | 5.57 | 5.57 | 5.57 | 5.57 |
| Alert rules | 11.50 | 11.50 | 11.50 | 11.50 |
| **Total** | **250.19** | **323.93** | **571.22** | **341.40** |

UAE North is slightly cheaper overall than West Europe, because Container Apps and logs cost less
there. Region choice is not a meaningful cost lever.

**What drives the expected total:**

| Group | Per month | Share |
|---|---:|---:|
| PostgreSQL (compute, storage, backup) | $174.80 | 54% |
| Container App and jobs | $63.44 | 20% |
| Logs (ingestion, retention) | $37.48 | 12% |
| Everything else | $48.21 | 15% |

The figures that move the bill most are **log volume**, at about $1 to $199 a month across the scenarios,
and how often the replica counts as idle, at $24 to $79. PostgreSQL is large but fixed.

## Costs outside the table

| Item | Cost | Source |
|---|---|---|
| Static IP | None; none is used | Template |
| Data leaving Azure | $0 for the first 100 GB a month, then $0.12/GB; expected to stay under 100 GB | Retail API |
| Static Web Apps bandwidth | 100 GB included, then $0.20/GB | Retail API |
| Entra External ID | $0 for the first 50,000 monthly active users, then $0.03 each on the Basic meter ($0.01625 on Core) | Retail API; dev shows $0 |
| SMS sign-in codes | Not assumed: admin MFA uses email one-time codes. Phone authentication is billed at $0.03 to $0.35 per message if ever turned on | Retail API |
| Amazon SES email | About $0.10 per 1,000 emails, so under $1 a month at expected volume | **Not from the Azure API, verify** |
| PostgreSQL zone-redundant HA | **Not included**, off by owner decision. Would add about $167 a month ($158.41 compute, $8.83 storage) | Retail API; doubling is from Microsoft's documentation |

## Measured and assumed

**Measured (read-only, dev, 2026-11-05):**

| Fact | Value | How it was used |
|---|---|---|
| Notify job, last 12 runs | 26 to 40 s, all succeeded, on 0.5 vCPU | Basis for 30, 45 and 60 s at 1 vCPU; conservative because prod has twice the CPU |
| Cleanup job, recent runs | 30 to 37 s | Basis for 40, 120 and 300 s |
| Dev log ingestion | 0.36 GB in 16 days, about 0.02 GB a day | The low case of 0.1 GB a day is about 5 times this |
| Dev Key Vault operations | About 5,400 in 16 days | Basis for 10,000, 20,000 and 100,000 a month |
| Static Web App on the dev bill | $0.2959 a day, which is $9.00 a month | Confirms the flat price |
| Log alert rules on the dev bill | Charged on the 5-minute meter | Confirms the meter applies |

**Assumed; replace these once production has a month of real data:**

| Assumption | Low | Expected | Busy |
|---|---:|---:|---:|
| Time the warm replica is above the idle threshold | 5% | 50% | 100% |
| Extra replica hours (active) | 0 | 0 | 219 |
| Requests per month | 200,000 | 1 million | 10 million |
| Log ingestion per day | 0.1 GB | 0.5 GB | 2 GB |
| Backup storage used | 40 GB | 100 GB | 200 GB |
| Blob data (documents, versions, soft-deleted) | 50 GB | 50 GB | 200 GB |
| Blob writes / reads per month | 20,000 / 100,000 | 50,000 / 300,000 | 200,000 / 1 million |
| Releases per month (each about 180 s of job time) | 2 | 4 | 8 |

Other assumptions:

- **Log volume is probably overstated.** The expected 0.5 GB a day is 25 times dev's rate, chosen
  because real traffic is unknown. Real use could be well below the expected total.
- **Log retention:** the first 31 days are included. All data past that is priced at $0.132 per GB a
  month. Microsoft's public pricing includes 90 days for Application Insights tables, which would make
  this lower; that is not taken from the API.
- **Backups:** the first 64 GB (100% of provisioned storage) is treated as free. The API has only a
  locally redundant backup meter ($0.105/GB), so the geo-redundant copy is priced at twice that. This
  is an assumption, **not a published meter**.
- **Free monthly Container Apps grant:** not counted. Microsoft's public pricing gives 180,000
  vCPU-seconds, 360,000 GiB-seconds and 2 million requests per subscription. Dev's notify job alone
  uses about 142,560 vCPU-seconds and 285,120 GiB-seconds of it if production shares the subscription.
  At most it would save about $6 a month.
- **Dev's free PostgreSQL and storage meters** are 12-month offers for small SKUs and do not cover
  this sizing, so none are counted.
- **Alert rules:** 7 log rules at 5-minute frequency (3 service rules and 4 notify rules, $1.50 each),
  2 cleanup log rules ($0.50 each on the 15-minute meter), and up to 10 metric rules, which are free.
  A longer frequency or fewer rules changes this by a few dollars at most.
- **Availability test:** 3 locations, every 15 minutes, $0.000645 per run.
- **Rounding:** the API rounds prices to six decimals, so the smallest Container Apps rates (for example
  $0.000003) may differ slightly from the invoice.

## Not verified

| Item | Status | Effect |
|---|---|---|
| Container Apps **Environment Management Hour** meter, $0.10/hour | **NOT VERIFIED.** The meter is listed from 2026-11-01. Dev's environment is Consumption-only, and its bill shows no such charge for 1 to 4 November, which suggests it does not apply. Four days is thin evidence, and dev's bill shows no Container Apps lines at all. | $73 a month if it applies. Check the first production invoice. |
| Geo-redundant backup price | NOT VERIFIED, no meter found | Up to about $14 a month in the busy case |
| Amazon SES price | Not from the Azure API | Under $1 a month |
| Real traffic, log volume and idle time | Unknown until production runs | The Low-to-Busy range |

## Three ways to lower it, without weakening security

| Lever | Saves | Trade-off |
|---|---:|---|
| **Reserve PostgreSQL compute for one year**, after a load test confirms the size. The API lists $571 per vCore per year for this series (2 vCores = $95.17 a month against $158.41). Three years is $63.39 a month. | **About $63 a month** | A commitment; do it only once the size is settled |
| **Keep log volume down:** stay at `LOG_LEVEL=INFO`, add Application Insights sampling if traffic grows, and set a generous `logAnalyticsDailyQuotaGb` as a safety limit (production has none today) | $0 to about $150 a month | A daily cap drops logs once reached, which can hide evidence during an incident, so set it well above normal use |
| **Move ACR from Standard to Basic** through a reviewed commit | About $15 a month | Basic includes 10 GB, so retained release images must fit; check this first |

## Budget

Recommended monthly budget: **$400**. That is the expected total plus most of the unverified margin,
and just above the expected total if the environment meter applies. Alerts at 90% ($360) and 100%
($400) give a warning before the limit.

**Reviewable command only. It has not been run, and it needs the owner's approval.** The plain
`az consumption budget create` has no alert option, so this uses `create-with-rg`. The address is a
placeholder for the same value passed at deploy time. Set the start date to the first of the month
production is created.

```bash
az consumption budget create-with-rg \
  --resource-group "<prod-resource-group>" \
  --budget-name medsyn-prod-monthly \
  --amount 400 \
  --category Cost \
  --time-grain Monthly \
  --time-period start-date=2026-12-01 end-date=2027-11-30 \
  --notifications "{at90:{enabled:true,operator:GreaterThan,threshold:90,contact-emails:['<alert-email>']},at100:{enabled:true,operator:GreaterThan,threshold:100,contact-emails:['<alert-email>']}}"
```

A budget only warns. It does not stop any service or limit spending.

## Source

Azure Retail Prices API, `https://prices.azure.com/api/retail/prices`, read on 2026-11-05 with
`currencyCode=USD` and `priceType eq 'Consumption'`, no credentials. Filters by `armRegionName`
(`uaenorth`, `westeurope`) and `serviceName`: `Azure Container Apps`, `Azure Database for PostgreSQL`,
`Storage`, `Container Registry`, `Log Analytics`, `Azure Monitor`, `Key Vault`, `Bandwidth`. Static
Web Apps and Entra External ID were matched by product name. The PostgreSQL reservation prices used
`priceType eq 'Reservation'`.

Measured dev figures came from read-only `az containerapp job execution list` calls and Cost
Management `query` calls. No resource was created or changed.
