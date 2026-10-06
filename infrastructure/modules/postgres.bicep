// Azure Database for PostgreSQL Flexible Server (PROMPT.md §26, §48).
// Entra authentication on; password authentication off unless explicitly enabled (fallback,
// §26). TLS required (min 1.2). The application database and the managed identity's role are
// created by infrastructure/scripts/setup-postgres-entra.sh, connected as the Entra admin, so
// the database is owned by an Entra principal and the app role holds only what it needs.

param name string
param location string
param tags object

@description('Major version; >= 15 is required (NULLS NOT DISTINCT, D17).')
@allowed([
  '15'
  '16'
  '17'
])
param version string = '16'

param skuName string = 'Standard_B1ms'

@allowed([
  'Burstable'
  'GeneralPurpose'
  'MemoryOptimized'
])
param skuTier string = 'Burstable'

@minValue(32)
param storageSizeGB int = 32

@description('Point-in-time restore window in days.')
@minValue(7)
@maxValue(35)
param backupRetentionDays int = 7

param geoRedundantBackup bool = false

@allowed([
  'Disabled'
  'SameZone'
  'ZoneRedundant'
])
param highAvailabilityMode string = 'Disabled'

@description('Fallback only (PROMPT.md section 26). When true, administratorLogin/Password are required.')
param passwordAuth bool = false

param administratorLogin string = ''

@secure()
param administratorPassword string = ''

@description('Optional Entra administrator (object id of a group or user). Empty = set later with setup-postgres-entra.sh.')
param entraAdminObjectId string = ''
param entraAdminPrincipalName string = ''

@allowed([
  'Group'
  'User'
  'ServicePrincipal'
])
param entraAdminPrincipalType string = 'Group'

@description('Delegated subnet + private DNS zone (VNet integration). Empty = public access with firewall rules.')
param delegatedSubnetId string = ''
param privateDnsZoneId string = ''

param logAnalyticsWorkspaceId string = ''

var privateAccess = !empty(delegatedSubnetId)

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2025-08-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    version: version
    administratorLogin: passwordAuth ? administratorLogin : null
    administratorLoginPassword: passwordAuth ? administratorPassword : null
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: passwordAuth ? 'Enabled' : 'Disabled'
      tenantId: subscription().tenantId
    }
    storage: {
      storageSizeGB: storageSizeGB
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: backupRetentionDays
      geoRedundantBackup: geoRedundantBackup ? 'Enabled' : 'Disabled'
    }
    highAvailability: {
      mode: highAvailabilityMode
    }
    network: privateAccess
      ? {
          delegatedSubnetResourceId: delegatedSubnetId
          privateDnsZoneArmResourceId: privateDnsZoneId
          publicNetworkAccess: 'Disabled'
        }
      : {
          publicNetworkAccess: 'Enabled'
        }
  }
}

// Configuration changes on one server are applied one at a time.
resource requireTls 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2025-08-01' = {
  parent: server
  name: 'require_secure_transport'
  properties: {
    value: 'on'
    source: 'user-override'
  }
}

resource minTls 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2025-08-01' = {
  parent: server
  name: 'ssl_min_protocol_version'
  properties: {
    value: 'TLSv1.2'
    source: 'user-override'
  }
  dependsOn: [
    requireTls
  ]
}

// MVP (§34): Container Apps consumption egress IPs are not fixed, so the server accepts
// connections from Azure services only (0.0.0.0 rule), never from the internet at large.
// Every connection still needs an Entra token for a mapped role and TLS.
resource allowAzureServices 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2025-08-01' = if (!privateAccess) {
  parent: server
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
  dependsOn: [
    minTls
  ]
}

resource entraAdmin 'Microsoft.DBforPostgreSQL/flexibleServers/administrators@2025-08-01' = if (!empty(entraAdminObjectId)) {
  parent: server
  name: empty(entraAdminObjectId) ? 'unused' : entraAdminObjectId
  properties: {
    principalName: entraAdminPrincipalName
    principalType: entraAdminPrincipalType
    tenantId: subscription().tenantId
  }
  dependsOn: [
    minTls
    allowAzureServices
  ]
}

#disable-next-line use-recent-api-versions // categoryGroup needs 2021-05-01-preview; the linter only offers 2016-09-01
resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(logAnalyticsWorkspaceId)) {
  name: 'to-log-analytics'
  scope: server
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'PostgreSQLLogs'
        enabled: true
      }
    ]
  }
}

output id string = server.id
output name string = server.name
output fqdn string = server.properties.fullyQualifiedDomainName
