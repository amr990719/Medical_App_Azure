// Service alerts for production: availability, error rate, latency, database capacity, restarts,
// the cleanup job, and a controlled test that proves an alert reaches a person. The notify job has
// its own rules in notification-alerts.bicep. All of them email `alertEmail` through one action
// group. Thresholds are a starting point; tune them from real traffic.
//
// Availability results go to their own Application Insights component with local auth left on:
// the app's component is Entra-only, and Microsoft's documentation does not say that Standard
// availability tests can ingest into one. This component holds synthetic results only, no user
// data, so its ingestion key protects nothing sensitive.

param location string
param tags object
param namePrefix string
param appInsightsId string
param workspaceId string
param postgresServerId string
param containerAppName string

@description('Host the availability test calls. A custom domain or the Static Web App default hostname.')
param publicHost string

@description('Recipient of every alert. Given at deploy time; never committed.')
param alertEmail string

@description('Seconds between availability test runs from each location. Each run is billed.')
param frequencySeconds int = 900

// With three locations, two failing means the service and not one network path. Microsoft recommends
// five locations and "locations - 2"; three keeps the billed runs down, at a slower or less certain
// signal (docs/production-cost-estimate-2026-11-05.md).
var testLocations = [
  'emea-nl-ams-azr' // West Europe
  'emea-gb-db3-azr' // North Europe
  'emea-se-sto-edge' // UK West
]
var failedLocationCount = 2

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-${namePrefix}-ops'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'ops'
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

// --- Availability ------------------------------------------------------------------------------

resource uptimeInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${namePrefix}-uptime'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspaceId
    IngestionMode: 'LogAnalytics'
    DisableLocalAuth: false
  }
}

var webTestName = 'webtest-${namePrefix}-ready'

resource readyTest 'Microsoft.Insights/webtests@2022-06-15' = {
  name: webTestName
  location: location
  tags: union(tags, {
    'hidden-link:${uptimeInsights.id}': 'Resource'
  })
  kind: 'standard'
  properties: {
    SyntheticMonitorId: webTestName
    Name: 'GET /api/ready/ through the public host'
    Kind: 'standard'
    Enabled: true
    Frequency: frequencySeconds
    Timeout: 30
    RetryEnabled: true
    Locations: [for id in testLocations: { Id: id }]
    Request: {
      RequestUrl: 'https://${publicHost}/api/ready/'
      HttpVerb: 'GET'
      ParseDependentRequests: false
    }
    ValidationRules: {
      ExpectedHttpStatusCode: 200
      SSLCheck: true
      SSLCertRemainingLifetimeCheck: 14
    }
  }
}

#disable-next-line use-recent-api-versions // the long-stable version these criteria are documented for
resource availabilityAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-${namePrefix}-availability'
  location: 'global'
  tags: union(tags, {
    'hidden-link:${uptimeInsights.id}': 'Resource'
    'hidden-link:${readyTest.id}': 'Resource'
  })
  properties: {
    description: 'The public /api/ready/ check is failing from at least two locations.'
    severity: 0
    enabled: true
    scopes: [
      readyTest.id
      uptimeInsights.id
    ]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria'
      webTestId: readyTest.id
      componentId: uptimeInsights.id
      failedLocationCount: failedLocationCount
    }
    autoMitigate: true
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}

// --- Metrics: database capacity ----------------------------------------------------------------

var metricRules = [
  {
    key: 'db-cpu'
    description: 'PostgreSQL CPU above 85% for 15 minutes.'
    scope: postgresServerId
    namespace: 'Microsoft.DBforPostgreSQL/flexibleServers'
    metric: 'cpu_percent'
    aggregation: 'Average'
    threshold: 85
    severity: 2
  }
  {
    key: 'db-memory'
    description: 'PostgreSQL memory above 90% for 15 minutes.'
    scope: postgresServerId
    namespace: 'Microsoft.DBforPostgreSQL/flexibleServers'
    metric: 'memory_percent'
    aggregation: 'Average'
    threshold: 90
    severity: 2
  }
  {
    key: 'db-storage'
    description: 'PostgreSQL storage above 80%. It auto-grows and cannot shrink: find out why, and raise postgresStorageSizeGB to match in a reviewed commit, or the next deployment may fail.'
    scope: postgresServerId
    namespace: 'Microsoft.DBforPostgreSQL/flexibleServers'
    metric: 'storage_percent'
    aggregation: 'Average'
    threshold: 80
    severity: 2
  }
  {
    key: 'db-connections'
    description: 'More than 100 PostgreSQL connections: 5 replicas with 3 workers plus the jobs need about 20.'
    scope: postgresServerId
    namespace: 'Microsoft.DBforPostgreSQL/flexibleServers'
    metric: 'active_connections'
    aggregation: 'Average'
    threshold: 100
    severity: 2
  }
]

#disable-next-line use-recent-api-versions // the long-stable version these criteria are documented for
resource metricAlerts 'Microsoft.Insights/metricAlerts@2018-03-01' = [
  for rule in metricRules: {
    name: 'alert-${namePrefix}-${rule.key}'
    location: 'global'
    tags: tags
    properties: {
      description: rule.description
      severity: rule.severity
      enabled: true
      scopes: [
        rule.scope
      ]
      evaluationFrequency: 'PT5M'
      windowSize: 'PT15M'
      criteria: {
        'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
        allOf: [
          {
            criterionType: 'StaticThresholdCriterion'
            name: rule.key
            metricNamespace: rule.namespace
            metricName: rule.metric
            operator: 'GreaterThan'
            threshold: rule.threshold
            timeAggregation: rule.aggregation
          }
        ]
      }
      autoMitigate: true
      actions: [
        {
          actionGroupId: actionGroup.id
        }
      ]
    }
  }
]

// --- Logs: API errors and latency, restarts, the cleanup job, the controlled test --------------
// Each rule counts rows, so "alert" means the query returned something. The volume floors stop one
// failed request at night from paging anyone. Latency leaves out uploads, which are slow by nature.

var logRules = [
  {
    key: 'api-5xx-rate'
    description: 'More than 5% of API requests failed with 5xx (at least 20 requests in 15 minutes).'
    scope: appInsightsId
    query: 'requests | summarize total = count(), failed = countif(toint(resultCode) >= 500) | where total >= 20 and failed * 100.0 / total > 5'
    operator: 'GreaterThan'
    threshold: 0
    severity: 1
    frequency: 'PT5M'
    window: 'PT15M'
  }
  {
    key: 'api-latency-p95'
    description: 'API p95 above 3 seconds (at least 20 requests in 15 minutes, uploads left out).'
    scope: appInsightsId
    query: 'requests | where not(name has "documents") | summarize total = count(), p95 = percentile(duration, 95) | where total >= 20 and p95 > 3000'
    operator: 'GreaterThan'
    threshold: 0
    severity: 2
    frequency: 'PT5M'
    window: 'PT15M'
  }
  {
    // From events, not the RestartCount metric: that one is cumulative for the life of a replica,
    // so old restarts would keep it in alert.
    key: 'app-restarts'
    description: 'The app\'s containers terminated more than 3 times in 15 minutes.'
    scope: workspaceId
    query: 'ContainerAppSystemLogs_CL | where ContainerAppName_s == "${containerAppName}" and Reason_s == "ContainerTerminated"'
    operator: 'GreaterThan'
    threshold: 3
    severity: 2
    frequency: 'PT5M'
    window: 'PT15M'
  }
  {
    key: 'cleanup-failed'
    description: 'The cleanup job failed.'
    scope: appInsightsId
    query: 'traces | where message == "cleanup_run_failed"'
    operator: 'GreaterThan'
    threshold: 0
    severity: 2
    frequency: 'PT1H'
    window: 'PT1H'
  }
  {
    // Two days, not one, so a run a few minutes late cannot raise a false alarm. It fires once when
    // first created, because no run exists yet, and clears after the first night's run.
    key: 'cleanup-missed'
    description: 'No cleanup_run in 2 days: the cleanup job stopped running.'
    scope: appInsightsId
    query: 'traces | where message == "cleanup_run"'
    operator: 'LessThan'
    threshold: 1
    severity: 2
    frequency: 'PT1H'
    window: 'P2D'
  }
  {
    key: 'ops-alert-test'
    description: 'Controlled test, not a fault: `manage.py alert_test` proves that an alert reaches a person.'
    scope: appInsightsId
    query: 'traces | where message == "ops_alert_test"'
    operator: 'GreaterThan'
    threshold: 0
    severity: 4
    frequency: 'PT5M'
    window: 'PT5M'
  }
]

resource logAlerts 'Microsoft.Insights/scheduledQueryRules@2026-03-01' = [
  for rule in logRules: {
    name: 'alert-${namePrefix}-${rule.key}'
    location: location
    tags: tags
    kind: 'LogAlert'
    properties: {
      displayName: 'ops: ${rule.key}'
      description: rule.description
      severity: rule.severity
      enabled: true
      scopes: [
        rule.scope
      ]
      evaluationFrequency: rule.frequency
      windowSize: rule.window
      criteria: {
        allOf: [
          {
            query: rule.query
            timeAggregation: 'Count'
            operator: rule.operator
            threshold: rule.threshold
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
