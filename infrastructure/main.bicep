// Medical Syndicates Treatment Project — one environment per resource group (PROMPT.md §33, §49).
//
//   az deployment group create -g <rg> -f infrastructure/main.bicep -p infrastructure/parameters/<env>.bicepparam
//
// First deployment of an environment: deployApplication=false (everything except the Container
// App, its jobs and the SWA link), then set the Key Vault secrets, run
// scripts/setup-postgres-entra.sh and push an image, then deploy with
// containerImage=<registry>/medical-backend@<digest> and deployWebApp=false (the migrate job only),
// run it, and deploy once more with deployWebApp=true, so the schema exists before anything serves
// (docs/production-runbook.md). Container Apps resolve Key Vault references at creation, so the
// secrets must exist first.

targetScope = 'resourceGroup'

// --- Environment ---------------------------------------------------------------------------------

@allowed([
  'dev'
  'staging'
  'prod'
])
param environmentName string

@description('Region for every resource except Static Web Apps (and Azure OpenAI when openAiLocation is set). Data residency: docs/security.md L3.')
param location string = resourceGroup().location

@description('Short lowercase alphanumeric prefix used in resource names.')
@minLength(3)
@maxLength(6)
param baseName string = 'medsyn'

@description('Static Web Apps region (limited availability; serves static files only).')
@allowed([
  'westeurope'
  'centralus'
  'eastus2'
  'westus2'
  'eastasia'
])
param staticWebAppLocation string = 'westeurope'

@description('Extra tags merged into the standard ones.')
param tags object = {}

@description('false on the first deployment of an environment (before Key Vault secrets and an image exist).')
param deployApplication bool = true

@description('Full image reference for the app and its jobs. Required when deployApplication=true.')
param containerImage string = ''

@description('false creates only the migrate job: the bootstrap step that applies the schema before any web app, schedule or SWA link exists. Ignored without deployApplication.')
param deployWebApp bool = true

@description('Public hostname users reach (custom domain bound to the Static Web App). Empty = the Static Web App default hostname.')
param publicHostname string = ''

@description('Fiscal year of new applications and fee quotes. No default and never inferred from the calendar: each environment sets it, and changing it is a reviewed commit (docs/production-runbook.md, fiscal-year rollover).')
@minValue(2000)
@maxValue(2100)
param currentFiscalYear int

@description('Recovery hold: closes the app ingress, sets notifications off and moves the cleanup and notify schedules out of the way, on every deployment until cleared (docs/production-runbook.md, recovery).')
param recoveryHold bool = false

// --- Feature switches ----------------------------------------------------------------------------

@description('Deploy Azure OpenAI and turn OCR on. Keep false until legal decision L2/L3 is approved (docs/security.md).')
param enableOcr bool = false

@description('Production upgrade path (PROMPT.md section 34): VNet-integrated Container Apps, VNet-integrated PostgreSQL, private endpoints for Blob/Key Vault/OpenAI. Must be chosen when the environment is created (PostgreSQL networking cannot change later).')
param enablePrivateNetworking bool = false

@description('Send Key Vault, Blob and PostgreSQL resource logs to Log Analytics.')
param enableDiagnostics bool = true

@description('Create the notify job, give the app and the job the notification settings, and (with alertEmail) deploy the alert rules. Email (Amazon SES) is the channel in use. With sesAccessKeyFromKeyVault the Key Vault secrets aws-access-key-id and aws-secret-access-key must exist first; notificationsMode allowlist also needs notifications-allowlist. The WhatsApp secrets are needed only with enableWhatsApp.')
param enableNotifications bool = false

@description('Turn the parked WhatsApp channel on (sets WHATSAPP_ENABLED and injects the WHATSAPP_* settings). When true the Key Vault secrets whatsapp-access-token, whatsapp-app-secret and whatsapp-verify-token must exist first. Off by default: email only.')
param enableWhatsApp bool = false

@description('Inject the Key Vault secrets aws-access-key-id and aws-secret-access-key as AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (app and notify job only). Long-lived keys are the fallback until OIDC federation (Task 14) exists; rotate them. The secrets must exist first.')
param sesAccessKeyFromKeyVault bool = false

@description('off = rows accumulate and expire, nothing is sent; allowlist = only NOTIFICATIONS_ALLOWLIST; live = everyone. The app and the notify job always share it.')
@allowed([
  'off'
  'allowlist'
  'live'
])
param notificationsMode string = 'off'

@description('Cron (UTC) for the notify job.')
param notifyCron string = '*/5 * * * *'

@description('Recipient of the notification alerts. Pass it at deploy time; never commit it.')
param alertEmail string = ''

param whatsappPhoneNumberId string = ''
param whatsappApiVersion string = ''
@description('AWS Region of the SES identity.')
param sesRegion string = ''
param sesFromAddress string = ''
@description('Base URL used in message links. Empty = the public URL.')
param notificationBaseUrl string = ''
@description('IAM role the identity assumes through OIDC federation to call SES.')
param awsRoleArn string = ''
param awsWebIdentityAudience string = ''
@description('Blank = the app default applies (the setting is left out).')
param notificationMaxAgeHours string = ''
@description('Blank = the app default applies (the setting is left out).')
param whatsappDeliveryTimeoutMinutes string = ''
@description('Blank = the app default applies (the setting is left out).')
param notificationResendRateLimit string = ''

// --- Container Apps sizes (§35) ------------------------------------------------------------------

param containerCpu string = '0.5'
param containerMemory string = '1Gi'

@minValue(0)
param minReplicas int = 1
@minValue(1)
param maxReplicas int = 3
@minValue(1)
param httpConcurrency int = 20
@minValue(1)
param gunicornWorkers int = 2

@description('Cron (UTC) for the blob cleanup job.')
param cleanupCron string = '30 1 * * *'

param containerRegistrySku string = 'Basic'

// --- PostgreSQL (§26, §48) -----------------------------------------------------------------------

param postgresVersion string = '16'
param postgresSkuName string = 'Standard_B1ms'
param postgresSkuTier string = 'Burstable'
param postgresStorageSizeGB int = 32
param postgresBackupRetentionDays int = 7
param postgresGeoRedundantBackup bool = false
param postgresHighAvailabilityMode string = 'Disabled'
param postgresDatabaseName string = 'medical'

@description('Name of a server restored from a backup, to adopt it as this environment\'s server. Kept in deployment configuration so the next deployment does not point the app back at the damaged one. Empty = the generated name.')
param postgresServerNameOverride string = ''

@description('Password authentication fallback (PROMPT.md section 26). Off by default: the app uses Entra tokens.')
param postgresPasswordAuth bool = false
param postgresAdministratorLogin string = ''
@secure()
param postgresAdministratorPassword string = ''

@description('Optional Entra admin group/user object id; otherwise set by scripts/setup-postgres-entra.sh.')
param postgresEntraAdminObjectId string = ''
param postgresEntraAdminPrincipalName string = ''
param postgresEntraAdminPrincipalType string = 'Group'

// --- Storage, Key Vault, monitoring (§20, §29, §38, §48) ---------------------------------------

param storageSkuName string = 'Standard_LRS'
param blobSoftDeleteRetentionDays int = 14
param blobPreviousVersionRetentionDays int = 90
param keyVaultSoftDeleteRetentionDays int = 90

@description('Operator who sets the Key Vault secrets (Key Vault Secrets Officer on this vault). Optional.')
param keyVaultOperatorPrincipalId string = ''
param keyVaultOperatorPrincipalType string = 'User'

@description('Availability, error rate, latency, database, restart and cleanup alerts. They need alertEmail and the deployed application.')
param enableServiceAlerts bool = false

@description('Seconds between availability test runs from each location. Each run is billed.')
@allowed([
  300
  600
  900
])
param availabilityTestFrequencySeconds int = 900

param logAnalyticsRetentionDays int = 30
param logAnalyticsDailyQuotaGb int = -1

@description('Q-T14: true = Application Insights accepts Entra-authenticated ingestion only.')
param appInsightsDisableLocalAuth bool = false

// --- Azure OpenAI (§21; only with enableOcr) -----------------------------------------------------

param openAiLocation string = location
param openAiModelName string = 'gpt-4o'
param openAiModelVersion string = '2024-11-20'
param openAiDeploymentSkuName string = 'Standard'
param openAiCapacity int = 10
param openAiApiVersion string = '2024-10-21'

// --- Microsoft Entra External ID (§27; values from scripts/create-entra-app.sh) ----------------

@description('e.g. https://<tenant-subdomain>.ciamlogin.com/<tenant-id>')
param entraAuthority string = ''
param entraTenantId string = ''
param entraClientId string = ''
param entraAdminRequireMfa bool = true

// --- Names (uniqueString per resource group + environment; no hard-coded global names) ------------

var envShort = {
  dev: 'dev'
  staging: 'stg'
  prod: 'prd'
}[environmentName]
var token = uniqueString(resourceGroup().id, environmentName, baseName)
var prefix = '${baseName}-${envShort}'
var names = {
  identity: 'id-${prefix}'
  logAnalytics: 'log-${prefix}-${token}'
  appInsights: 'appi-${prefix}-${token}'
  keyVault: take('kv${baseName}${envShort}${token}', 24)
  storage: take('st${baseName}${envShort}${token}', 24)
  registry: 'cr${baseName}${envShort}${token}'
  postgres: empty(postgresServerNameOverride) ? 'psql-${prefix}-${token}' : postgresServerNameOverride
  containerEnv: 'cae-${prefix}'
  app: 'ca-${prefix}-api'
  migrateJob: 'caj-${prefix}-migrate'
  cleanupJob: 'caj-${prefix}-cleanup'
  notifyJob: 'caj-${prefix}-notify'
  staticWebApp: 'swa-${prefix}-${token}'
  openAi: 'oai-${prefix}-${token}'
  vnet: 'vnet-${prefix}'
}

var allTags = union(tags, {
  application: 'medical-syndicates'
  environment: environmentName
  'managed-by': 'bicep'
})

// --- Foundation ----------------------------------------------------------------------------------

module identity 'modules/identity.bicep' = {
  name: 'identity'
  params: {
    name: names.identity
    location: location
    tags: allTags
  }
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    logAnalyticsName: names.logAnalytics
    appInsightsName: names.appInsights
    location: location
    tags: allTags
    retentionInDays: logAnalyticsRetentionDays
    dailyQuotaGb: logAnalyticsDailyQuotaGb
    disableLocalAuth: appInsightsDisableLocalAuth
  }
}

module network 'modules/network.bicep' = if (enablePrivateNetworking) {
  name: 'network'
  params: {
    name: names.vnet
    location: location
    tags: allTags
    postgresPrivateDnsZoneName: '${names.postgres}.private.postgres.database.azure.com'
  }
}

var diagnosticsWorkspaceId = enableDiagnostics ? monitoring.outputs.workspaceId : ''

module keyVault 'modules/key-vault.bicep' = {
  name: 'key-vault'
  params: {
    name: names.keyVault
    location: location
    tags: allTags
    softDeleteRetentionInDays: keyVaultSoftDeleteRetentionDays
    privateNetworking: enablePrivateNetworking
    logAnalyticsWorkspaceId: diagnosticsWorkspaceId
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    name: names.storage
    location: location
    tags: allTags
    skuName: storageSkuName
    softDeleteRetentionDays: blobSoftDeleteRetentionDays
    previousVersionRetentionDays: blobPreviousVersionRetentionDays
    privateNetworking: enablePrivateNetworking
    logAnalyticsWorkspaceId: diagnosticsWorkspaceId
  }
}

module postgres 'modules/postgres.bicep' = {
  name: 'postgres'
  params: {
    name: names.postgres
    location: location
    tags: allTags
    version: postgresVersion
    skuName: postgresSkuName
    skuTier: postgresSkuTier
    storageSizeGB: postgresStorageSizeGB
    backupRetentionDays: postgresBackupRetentionDays
    geoRedundantBackup: postgresGeoRedundantBackup
    highAvailabilityMode: postgresHighAvailabilityMode
    passwordAuth: postgresPasswordAuth
    administratorLogin: postgresAdministratorLogin
    administratorPassword: postgresAdministratorPassword
    entraAdminObjectId: postgresEntraAdminObjectId
    entraAdminPrincipalName: postgresEntraAdminPrincipalName
    entraAdminPrincipalType: postgresEntraAdminPrincipalType
    delegatedSubnetId: enablePrivateNetworking ? network!.outputs.postgresSubnetId : ''
    privateDnsZoneId: enablePrivateNetworking ? network!.outputs.postgresPrivateDnsZoneId : ''
    logAnalyticsWorkspaceId: diagnosticsWorkspaceId
  }
}

module registry 'modules/container-registry.bicep' = {
  name: 'container-registry'
  params: {
    name: names.registry
    location: location
    tags: allTags
    skuName: containerRegistrySku
  }
}

module openAi 'modules/openai.bicep' = if (enableOcr) {
  name: 'openai'
  params: {
    name: names.openAi
    location: openAiLocation
    tags: allTags
    modelName: openAiModelName
    modelVersion: openAiModelVersion
    deploymentSkuName: openAiDeploymentSkuName
    capacity: openAiCapacity
    privateNetworking: enablePrivateNetworking
  }
}

module privateEndpoints 'modules/private-endpoints.bicep' = if (enablePrivateNetworking) {
  name: 'private-endpoints'
  params: {
    location: location
    tags: allTags
    namePrefix: prefix
    vnetId: network!.outputs.vnetId
    subnetId: network!.outputs.privateEndpointSubnetId
    storageAccountId: storage.outputs.id
    keyVaultId: keyVault.outputs.id
    openAiAccountId: enableOcr ? openAi!.outputs.id : ''
  }
}

module roleAssignments 'modules/role-assignments.bicep' = {
  name: 'role-assignments'
  params: {
    principalId: identity.outputs.principalId
    storageAccountName: storage.outputs.name
    blobContainerName: storage.outputs.containerName
    keyVaultName: keyVault.outputs.name
    containerRegistryName: registry.outputs.name
    appInsightsName: monitoring.outputs.appInsightsName
    openAiAccountName: enableOcr ? openAi!.outputs.name : ''
    operatorPrincipalId: keyVaultOperatorPrincipalId
    operatorPrincipalType: keyVaultOperatorPrincipalType
  }
}

module containerEnv 'modules/container-apps-env.bicep' = {
  name: 'container-apps-env'
  params: {
    name: names.containerEnv
    location: location
    tags: allTags
    logAnalyticsWorkspaceName: monitoring.outputs.workspaceName
    infrastructureSubnetId: enablePrivateNetworking ? network!.outputs.containerAppsSubnetId : ''
  }
}

module staticWebApp 'modules/static-web-app.bicep' = {
  name: 'static-web-app'
  params: {
    name: names.staticWebApp
    location: staticWebAppLocation
    tags: allTags
  }
}

// --- Application (second phase) ------------------------------------------------------------------

var publicHost = empty(publicHostname) ? staticWebApp.outputs.defaultHostname : publicHostname
var appFqdn = '${names.app}.${containerEnv.outputs.defaultDomain}'
// Django sees the Container App host behind the linked backend (Q-T13, NOT VERIFIED): both
// the backend FQDN and the public host are allowed; never '*'.
var allowedHosts = join(union([appFqdn, publicHost], [staticWebApp.outputs.defaultHostname]), ',')
var trustedOrigins = join(
  union(['https://${publicHost}'], ['https://${staticWebApp.outputs.defaultHostname}']),
  ','
)

var baseSettings = {
  DJANGO_SETTINGS_MODULE: 'config.settings.production'
  DEBUG: 'false'
  DEV_AUTH_ENABLED: 'false'
  API_DOCS_ENABLED: 'false'
  LOG_LEVEL: 'INFO'
  ALLOWED_HOSTS: allowedHosts
  CSRF_TRUSTED_ORIGINS: trustedOrigins
  // X-Forwarded-For entries appended by the SWA linked backend and the Container Apps ingress
  // (client address for throttles and the audit hash; Q-T13, NOT VERIFIED on Azure).
  TRUSTED_PROXY_COUNT: '2'
  GUNICORN_WORKERS: string(gunicornWorkers)
  // Managed identity for every Azure SDK call (developer credentials excluded).
  AZURE_CLIENT_ID: identity.outputs.clientId
  AZURE_TOKEN_CREDENTIALS: 'prod'
  KEY_VAULT_URL: keyVault.outputs.uri
  // PostgreSQL: the user is the identity's role; the password is an Entra token per connection.
  DATABASE_URL: 'postgres://${names.identity}@${postgres.outputs.fqdn}:5432/${postgresDatabaseName}'
  DB_AUTH_MODE: 'entra'
  DB_SSLMODE: 'require'
  // Throttle counters shared by every replica (Q-T6); the table is created by the migrate job.
  CACHE_URL: 'dbcache://django_cache'
  BLOB_BACKEND: 'azure'
  BLOB_ACCOUNT_URL: storage.outputs.blobEndpoint
  BLOB_CONTAINER: storage.outputs.containerName
  BLOB_CREATE_CONTAINER: 'false'
  ENTRA_AUTHORITY: entraAuthority
  ENTRA_TENANT_ID: entraTenantId
  ENTRA_CLIENT_ID: entraClientId
  ENTRA_REDIRECT_URI: 'https://${publicHost}/api/v1/auth/callback/'
  ENTRA_POST_LOGOUT_REDIRECT_URI: 'https://${publicHost}/signed-out'
  ENTRA_ADMIN_REQUIRE_MFA: string(entraAdminRequireMfa)
  OCR_ENABLED: string(enableOcr)
  CURRENT_FISCAL_YEAR: string(currentFiscalYear)
}

var telemetrySettings = appInsightsDisableLocalAuth ? { APPLICATIONINSIGHTS_AUTHENTICATION: 'entra' } : {}

var ocrSettings = enableOcr
  ? {
      OCR_PROVIDER: 'azure_openai'
      AZURE_OPENAI_ENDPOINT: openAi!.outputs.endpoint
      AZURE_OPENAI_DEPLOYMENT: openAi!.outputs.deploymentName
      AZURE_OPENAI_API_VERSION: openAiApiVersion
    }
  : {}

// Plain settings for notifications. On whenever enableNotifications is true, in every mode
// including 'off'. The WHATSAPP_* ones exist only with enableWhatsApp (the channel is parked
// otherwise). Optional values are left out when blank rather than set to an empty string.
var whatsAppSettings = enableWhatsApp
  ? {
      WHATSAPP_ENABLED: 'true'
      WHATSAPP_PHONE_NUMBER_ID: whatsappPhoneNumberId
      WHATSAPP_API_VERSION: whatsappApiVersion
      WHATSAPP_DELIVERY_TIMEOUT_MINUTES: whatsappDeliveryTimeoutMinutes
    }
  : {}

var optionalNotificationSettings = union(whatsAppSettings, {
  SES_REGION: sesRegion
  SES_FROM_ADDRESS: sesFromAddress
  AWS_ROLE_ARN: awsRoleArn
  AWS_WEB_IDENTITY_AUDIENCE: awsWebIdentityAudience
  NOTIFICATION_MAX_AGE_HOURS: notificationMaxAgeHours
  NOTIFICATION_RESEND_RATE_LIMIT: notificationResendRateLimit
})

// A hold wins over the configured mode, the schedules and the open ingress. This cron still fires
// on 1 January: a hold across that date must clear or move it, or one cleanup run happens.
var effectiveNotificationsMode = recoveryHold ? 'off' : notificationsMode
var recoveryHoldCron = '0 0 1 1 *'
// TEST-NET-1 (RFC 5737): an allow rule nothing can match, so the ingress refuses every caller,
// including the Static Web App.
var recoveryHoldRestrictions = [
  {
    name: 'recovery-hold'
    ipAddressRange: '192.0.2.1/32'
    action: 'Allow'
    description: 'Recovery hold: every caller is refused until the hold is cleared.'
  }
]

var notificationSettings = enableNotifications
  ? union(
      {
        NOTIFICATIONS_MODE: effectiveNotificationsMode
        NOTIFICATION_PROVIDERS: 'real'
        NOTIFICATION_BASE_URL: empty(notificationBaseUrl) ? 'https://${publicHost}' : notificationBaseUrl
      },
      toObject(
        filter(items(optionalNotificationSettings), item => !empty(item.value)),
        item => item.key,
        item => item.value
      )
    )
  : {}

module app 'modules/container-app.bicep' = if (deployApplication) {
  name: 'container-app'
  params: {
    appName: names.app
    migrateJobName: names.migrateJob
    cleanupJobName: names.cleanupJob
    notifyJobName: names.notifyJob
    location: location
    tags: allTags
    environmentId: containerEnv.outputs.id
    identityId: identity.outputs.id
    image: containerImage
    registryServer: registry.outputs.loginServer
    keyVaultUri: keyVault.outputs.uri
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    deployWebApp: deployWebApp
    settings: union(baseSettings, telemetrySettings, ocrSettings)
    notificationEnv: notificationSettings
    cpu: containerCpu
    memory: containerMemory
    minReplicas: minReplicas
    maxReplicas: maxReplicas
    httpConcurrency: httpConcurrency
    cleanupCron: recoveryHold ? recoveryHoldCron : cleanupCron
    enableNotifications: enableNotifications
    enableWhatsApp: enableWhatsApp
    notificationsMode: effectiveNotificationsMode
    sesAccessKeyFromKeyVault: sesAccessKeyFromKeyVault
    notifyCron: recoveryHold ? recoveryHoldCron : notifyCron
    ipSecurityRestrictions: recoveryHold ? recoveryHoldRestrictions : []
  }
  dependsOn: [
    roleAssignments
  ]
}

module staticWebAppLink 'modules/static-web-app-link.bicep' = if (deployApplication && deployWebApp) {
  name: 'static-web-app-link'
  params: {
    staticWebAppName: staticWebApp.outputs.name
    backendResourceId: app!.outputs.appId
    backendLocation: location
  }
}

module notificationAlerts 'modules/notification-alerts.bicep' = if (enableNotifications && !empty(alertEmail)) {
  name: 'notification-alerts'
  params: {
    location: location
    tags: allTags
    namePrefix: prefix
    appInsightsId: monitoring.outputs.appInsightsId
    alertEmail: alertEmail
  }
}

module serviceAlerts 'modules/service-alerts.bicep' = if (enableServiceAlerts && !empty(alertEmail) && deployApplication && deployWebApp) {
  name: 'service-alerts'
  params: {
    location: location
    tags: allTags
    namePrefix: prefix
    alertEmail: alertEmail
    appInsightsId: monitoring.outputs.appInsightsId
    workspaceId: monitoring.outputs.workspaceId
    postgresServerId: postgres.outputs.id
    containerAppName: names.app
    publicHost: publicHost
    frequencySeconds: availabilityTestFrequencySeconds
  }
}

// --- Outputs (names only; no secrets, no deployment tokens) ------------------------------------

output identityName string = identity.outputs.name
output identityClientId string = identity.outputs.clientId
output identityPrincipalId string = identity.outputs.principalId
output keyVaultName string = keyVault.outputs.name
output storageAccountName string = storage.outputs.name
output postgresServerName string = postgres.outputs.name
output postgresFqdn string = postgres.outputs.fqdn
output postgresDatabaseName string = postgresDatabaseName
output containerRegistryName string = registry.outputs.name
output containerRegistryLoginServer string = registry.outputs.loginServer
output containerAppsEnvironmentName string = containerEnv.outputs.name
output containerAppName string = names.app
output migrateJobName string = names.migrateJob
output cleanupJobName string = names.cleanupJob
output notifyJobName string = enableNotifications ? names.notifyJob : ''
output currentFiscalYear int = currentFiscalYear
output containerAppFqdn string = appFqdn
output staticWebAppName string = staticWebApp.outputs.name
output staticWebAppHostname string = staticWebApp.outputs.defaultHostname
output publicUrl string = 'https://${publicHost}'
output entraRedirectUri string = 'https://${publicHost}/api/v1/auth/callback/'
output entraPostLogoutRedirectUri string = 'https://${publicHost}/signed-out'
output appInsightsName string = monitoring.outputs.appInsightsName
output openAiAccountName string = enableOcr ? openAi!.outputs.name : ''
