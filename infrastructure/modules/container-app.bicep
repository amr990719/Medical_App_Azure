// Django on Azure Container Apps (PROMPT.md §31, §35, §37) plus its two jobs, all running the
// same image with the same identity and settings:
//   app      `web` (image default): Gunicorn on port 8000, HTTP-concurrency scaling, probes.
//   migrate  manual job, `migrate`: run exactly once per deployment by backend.yml BEFORE the
//            app's image is updated (replicas never migrate).
//   cleanup  scheduled job, `cleanup`: removes soft-deleted / orphaned blobs after the grace period.
// Secrets are Key Vault references resolved with the user-assigned identity (versionless URLs,
// refreshed by the platform); nothing secret is a template parameter except the App Insights
// connection string, which is stored as a Container Apps secret rather than a plain variable.

param appName string
param migrateJobName string
param cleanupJobName string
param location string
param tags object

param environmentId string
param identityId string

@description('Full image reference, e.g. <registry>.azurecr.io/medical-backend:<git-sha>.')
param image string
param registryServer string

param keyVaultUri string

@secure()
param appInsightsConnectionString string

@description('Non-secret settings (name -> value) shared by the app and both jobs.')
param settings object

@description('vCPU per replica, as a string (e.g. "0.5").')
param cpu string = '0.5'
param memory string = '1Gi'

@minValue(0)
param minReplicas int = 1
@minValue(1)
param maxReplicas int = 3
@description('Concurrent HTTP requests per replica before scaling out.')
@minValue(1)
param httpConcurrency int = 20

@description('Cron (UTC) for the blob cleanup job.')
param cleanupCron string = '30 1 * * *'

@description('Optional inbound allow-list for the app\'s public ingress (Container Apps ipSecurityRestrictions).')
param ipSecurityRestrictions array = []

var port = 8000

var secrets = [
  {
    name: 'django-secret-key'
    keyVaultUrl: '${keyVaultUri}secrets/django-secret-key'
    identity: identityId
  }
  {
    name: 'entra-client-secret'
    keyVaultUrl: '${keyVaultUri}secrets/entra-client-secret'
    identity: identityId
  }
  {
    name: 'appinsights-connection-string'
    value: appInsightsConnectionString
  }
]

var secretEnv = [
  {
    name: 'DJANGO_SECRET_KEY'
    secretRef: 'django-secret-key'
  }
  {
    name: 'ENTRA_CLIENT_SECRET'
    secretRef: 'entra-client-secret'
  }
  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    secretRef: 'appinsights-connection-string'
  }
]

var plainEnv = [for item in items(settings): { name: item.key, value: string(item.value) }]

var registries = [
  {
    server: registryServer
    identity: identityId
  }
]

var resources = {
  cpu: json(cpu)
  memory: memory
}

resource app 'Microsoft.App/containerApps@2025-01-01' = {
  name: appName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      maxInactiveRevisions: 5
      ingress: {
        external: true
        targetPort: port
        transport: 'auto'
        allowInsecure: false
        ipSecurityRestrictions: ipSecurityRestrictions
      }
      registries: registries
      secrets: secrets
    }
    template: {
      containers: [
        {
          name: 'django'
          image: image
          resources: resources
          env: concat(plainEnv, secretEnv, [
            {
              name: 'OTEL_SERVICE_NAME'
              value: 'medical-backend'
            }
          ])
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/api/health/'
                port: port
              }
              periodSeconds: 5
              failureThreshold: 24
              timeoutSeconds: 3
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/api/health/'
                port: port
              }
              periodSeconds: 30
              failureThreshold: 3
              timeoutSeconds: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/api/ready/'
                port: port
              }
              periodSeconds: 10
              failureThreshold: 3
              timeoutSeconds: 5
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: string(httpConcurrency)
              }
            }
          }
        ]
      }
    }
  }
}

resource migrateJob 'Microsoft.App/jobs@2025-01-01' = {
  name: migrateJobName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      // A failed migration is investigated, never retried blindly.
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registries
      secrets: secrets
    }
    template: {
      containers: [
        {
          name: 'migrate'
          image: image
          args: [
            'migrate'
          ]
          resources: resources
          env: concat(plainEnv, secretEnv, [
            {
              name: 'OTEL_SERVICE_NAME'
              value: 'medical-migrate'
            }
          ])
        }
      ]
    }
  }
}

resource cleanupJob 'Microsoft.App/jobs@2025-01-01' = {
  name: cleanupJobName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 3600
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: cleanupCron
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registries
      secrets: secrets
    }
    template: {
      containers: [
        {
          name: 'cleanup'
          image: image
          args: [
            'cleanup'
          ]
          resources: resources
          env: concat(plainEnv, secretEnv, [
            {
              name: 'OTEL_SERVICE_NAME'
              value: 'medical-cleanup'
            }
          ])
        }
      ]
    }
  }
}

output appId string = app.id
output appName string = app.name
output appFqdn string = app.properties.configuration.ingress.fqdn
output migrateJobName string = migrateJob.name
output cleanupJobName string = cleanupJob.name
