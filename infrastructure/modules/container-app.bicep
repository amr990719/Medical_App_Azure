// Django on Azure Container Apps (PROMPT.md §31, §35, §37) plus its two jobs, all running the
// same image with the same identity and settings:
//   app      `web` (image default): Gunicorn on port 8000, HTTP-concurrency scaling, probes.
//   migrate  manual job, `migrate`: run exactly once per deployment by backend.yml BEFORE the
//            app's image is updated (replicas never migrate).
//   cleanup  scheduled job, `cleanup`: removes soft-deleted / orphaned blobs after the grace period.
//   notify   scheduled job, `notify` (only with enableNotifications): sends doctor notifications.
//            The notification secrets (AWS keys, allowlist, WhatsApp when enabled) go to the app
//            and this job only, never to migrate or cleanup.
// Secrets are Key Vault references resolved with the user-assigned identity (versionless URLs,
// refreshed by the platform); nothing secret is a template parameter except the App Insights
// connection string, which is stored as a Container Apps secret rather than a plain variable.

param appName string
param migrateJobName string
param cleanupJobName string
@description('Name of the notify job. Used only when enableNotifications is true.')
param notifyJobName string = ''
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

@description('Non-secret settings (name -> value) shared by the app and every job.')
param settings object

@description('Notification settings (name -> value) for the app and the notify job ONLY. The migrate and cleanup jobs lack the notification secrets, so with these set production settings would refuse to import there.')
param notificationEnv object = {}

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

@description('Create the notify job and give it, and the app, the notification Key Vault references (the secrets must exist first).')
param enableNotifications bool = false

@description('WhatsApp is parked unless true: only then are the whatsapp-* Key Vault references injected.')
param enableWhatsApp bool = false

@description('The notifications mode. The notifications-allowlist reference exists only for allowlist.')
@allowed([
  'off'
  'allowlist'
  'live'
])
param notificationsMode string = 'off'

@description('Inject aws-access-key-id and aws-secret-access-key as AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (app and notify job only). Fallback until federation (Task 14).')
param sesAccessKeyFromKeyVault bool = false

@description('Cron (UTC) for the notify job.')
param notifyCron string = '*/5 * * * *'

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

// Key Vault references for notifications. Only the app (webhook replies) and the notify job get
// them; `secrets` and `secretEnv` stay as they are for migrate and cleanup. Each group exists
// only when its feature is on: the AWS keys with sesAccessKeyFromKeyVault, the allowlist only in
// allowlist mode, the WhatsApp ones only with enableWhatsApp. A missing Key Vault secret stops
// the app, so nothing is referenced that is not needed.
var awsKeySecrets = enableNotifications && sesAccessKeyFromKeyVault
  ? [
      {
        name: 'aws-access-key-id'
        keyVaultUrl: '${keyVaultUri}secrets/aws-access-key-id'
        identity: identityId
      }
      {
        name: 'aws-secret-access-key'
        keyVaultUrl: '${keyVaultUri}secrets/aws-secret-access-key'
        identity: identityId
      }
    ]
  : []

var allowlistSecrets = enableNotifications && notificationsMode == 'allowlist'
  ? [
      {
        name: 'notifications-allowlist'
        keyVaultUrl: '${keyVaultUri}secrets/notifications-allowlist'
        identity: identityId
      }
    ]
  : []

var whatsAppSecrets = enableNotifications && enableWhatsApp
  ? [
      {
        name: 'whatsapp-access-token'
        keyVaultUrl: '${keyVaultUri}secrets/whatsapp-access-token'
        identity: identityId
      }
      {
        name: 'whatsapp-app-secret'
        keyVaultUrl: '${keyVaultUri}secrets/whatsapp-app-secret'
        identity: identityId
      }
      {
        name: 'whatsapp-verify-token'
        keyVaultUrl: '${keyVaultUri}secrets/whatsapp-verify-token'
        identity: identityId
      }
    ]
  : []

var notificationSecrets = concat(awsKeySecrets, allowlistSecrets, whatsAppSecrets)

var awsKeyEnv = enableNotifications && sesAccessKeyFromKeyVault
  ? [
      {
        name: 'AWS_ACCESS_KEY_ID'
        secretRef: 'aws-access-key-id'
      }
      {
        name: 'AWS_SECRET_ACCESS_KEY'
        secretRef: 'aws-secret-access-key'
      }
    ]
  : []

var allowlistEnv = enableNotifications && notificationsMode == 'allowlist'
  ? [
      {
        name: 'NOTIFICATIONS_ALLOWLIST'
        secretRef: 'notifications-allowlist'
      }
    ]
  : []

var whatsAppEnv = enableNotifications && enableWhatsApp
  ? [
      {
        name: 'WHATSAPP_ACCESS_TOKEN'
        secretRef: 'whatsapp-access-token'
      }
      {
        name: 'WHATSAPP_APP_SECRET'
        secretRef: 'whatsapp-app-secret'
      }
      {
        name: 'WHATSAPP_VERIFY_TOKEN'
        secretRef: 'whatsapp-verify-token'
      }
    ]
  : []

var notificationSecretEnv = concat(awsKeyEnv, allowlistEnv, whatsAppEnv)

var plainEnv = [for item in items(settings): { name: item.key, value: string(item.value) }]
var notificationPlainEnv = [for item in items(notificationEnv): { name: item.key, value: string(item.value) }]

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
      secrets: concat(secrets, notificationSecrets)
    }
    template: {
      containers: [
        {
          name: 'django'
          image: image
          resources: resources
          env: concat(plainEnv, notificationPlainEnv, secretEnv, notificationSecretEnv, [
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

resource notifyJob 'Microsoft.App/jobs@2025-01-01' = if (enableNotifications) {
  name: notifyJobName
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
      // Under the 5-minute cron so runs rarely overlap; correctness relies on the database.
      replicaTimeout: 280
      // The next scheduled run is the retry.
      replicaRetryLimit: 0
      scheduleTriggerConfig: {
        cronExpression: notifyCron
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registries
      secrets: concat(secrets, notificationSecrets)
    }
    template: {
      containers: [
        {
          name: 'notify'
          image: image
          args: [
            'notify'
          ]
          resources: resources
          env: concat(plainEnv, notificationPlainEnv, secretEnv, notificationSecretEnv, [
            {
              name: 'OTEL_SERVICE_NAME'
              value: 'medical-notify'
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
output notifyJobName string = enableNotifications ? notifyJob.name : ''
