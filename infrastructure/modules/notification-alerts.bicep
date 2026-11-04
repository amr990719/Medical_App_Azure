// Alert rules for the notify job (docs/superpowers/specs/2026-11-02-notifications-design.md §6).
// All four read Application Insights `traces`; message names are exact and come from the
// notifications app (`notify_run`, `notify_run_failed`, `notification_failed`,
// `notification_expired`). One action group emails `alertEmail`.

param location string
param tags object
param namePrefix string
param appInsightsId string

@description('Recipient of every alert. Given at deploy time; never committed.')
param alertEmail string

var rules = [
  {
    key: 'failed-or-expired'
    description: 'A notification ended FAILED or EXPIRED.'
    query: 'traces | where message in ("notification_failed", "notification_expired")'
    operator: 'GreaterThan'
  }
  {
    key: 'oldest-due-too-old'
    description: 'The oldest due notification is older than 30 minutes.'
    query: 'traces | where message == "notify_run" | where toint(customDimensions.oldest_due_age_seconds) > 1800'
    operator: 'GreaterThan'
  }
  {
    key: 'missed-runs'
    description: 'No notify_run in 15 minutes: the job stopped running.'
    query: 'traces | where message == "notify_run"'
    operator: 'LessThan'
  }
  {
    key: 'job-failed'
    description: 'The notify job run failed.'
    query: 'traces | where message == "notify_run_failed"'
    operator: 'GreaterThan'
  }
]

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-${namePrefix}-notify'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'notify'
    enabled: true
    emailReceivers: [
      {
        name: 'owner'
        emailAddress: alertEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

resource alertRules 'Microsoft.Insights/scheduledQueryRules@2026-03-01' = [
  for rule in rules: {
    name: 'alert-${namePrefix}-notify-${rule.key}'
    location: location
    tags: tags
    kind: 'LogAlert'
    properties: {
      displayName: 'notify: ${rule.key}'
      description: rule.description
      severity: 2
      enabled: true
      scopes: [
        appInsightsId
      ]
      evaluationFrequency: 'PT5M'
      windowSize: 'PT15M'
      criteria: {
        allOf: [
          {
            query: rule.query
            timeAggregation: 'Count'
            operator: rule.operator
            threshold: rule.operator == 'LessThan' ? 1 : 0
            failingPeriods: {
              numberOfEvaluationPeriods: 1
              minFailingPeriodsToAlert: 1
            }
          }
        ]
      }
      autoMitigate: true
      actions: {
        actionGroups: [
          actionGroup.id
        ]
      }
    }
  }
]
