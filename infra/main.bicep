// PriceTrack — Azure infrastructure
// Deploys: Log Analytics, Container Registry, Container Apps env + app, PostgreSQL Flexible Server.
// Usage: az deployment group create -g rg-pricetrack -f infra/main.bicep -p adminPassword='...'

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Prefix used in resource names (must be globally unique-friendly, lowercase, alphanumeric)')
@minLength(3)
@maxLength(20)
param namePrefix string = 'pricetrack'

@description('Password for the app UI (single-user mode). Leave empty to disable auth.')
@secure()
param adminPassword string = ''

@description('Secret used to sign session cookies')
@secure()
param secretKey string = ''

@description('Password for the PostgreSQL admin user (auto-generated when omitted)')
@secure()
param pgPassword string = newGuid()

@description('Container image. Empty = placeholder, updated by CI after the first push.')
param containerImage string = ''

@description('Interval used by the scheduler poll loop (seconds)')
param scrapePollSeconds int = 30

var acrName = '${namePrefix}acr'
var envName = '${namePrefix}-env'
var appName = '${namePrefix}-app'
var pgServerName = '${namePrefix}-pg'
var dbName = 'pricetrack'
var pgAdminUser = 'pricetrack'
var logName = '${namePrefix}-logs'

// ---------------------------------------------------------------- registry ---
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

// ------------------------------------------------------------- log analytics -
resource logs 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logName
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ------------------------------------------------------- container apps env --
resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      { name: 'Consumption', workloadProfileType: 'Consumption' }
    ]
  }
}

// ------------------------------------------------------------ postgres --------
resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: pgServerName
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: pgAdminUser
    administratorLoginPassword: pgPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    network: { publicNetworkAccess: 'Enabled' }
    highAvailability: { mode: 'Disabled' }
  }
}

resource pgDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  parent: pg
  name: dbName
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

// allow Azure-hosted Container Apps egress through the public endpoint
resource pgFirewallAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-12-01-preview' = {
  parent: pg
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ------------------------------------------------------------- container app --
resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
        traffic: [{ latestRevision: true, weight: 100 }]
      }
      registries: [
        {
          server: '${acrName}.azurecr.io'
          identity: 'system'
        }
      ]
      secrets: concat(
        [
          {
            name: 'database-url'
            value: 'postgresql+asyncpg://${pgAdminUser}:${pgPassword}@${pgServerName}.postgres.database.azure.com:5432/${dbName}'
          }
        ],
        adminPassword == '' ? [] : [{ name: 'admin-password', value: adminPassword }],
        secretKey == '' ? [] : [{ name: 'secret-key', value: secretKey }]
      )
    }
    template: {
      // exactly one replica: the in-process scheduler must not run twice
      scale: {
        minReplicas: 1
        maxReplicas: 1
        rules: []
      }
      containers: [
        {
          name: 'app'
          image: containerImage == '' ? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' : containerImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: concat(
            [
              { name: 'DATABASE_URL', secretRef: 'database-url' }
              { name: 'SCRAPE_POLL_SECONDS', value: string(scrapePollSeconds) }
            ],
            adminPassword == '' ? [] : [{ name: 'ADMIN_PASSWORD', secretRef: 'admin-password' }],
            secretKey == '' ? [] : [{ name: 'SECRET_KEY', secretRef: 'secret-key' }]
          )
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/api/health', port: 8000, scheme: 'HTTP' }
              initialDelaySeconds: 20
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/api/health', port: 8000, scheme: 'HTTP' }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
            }
          ]
        }
      ]
    }
  }
}

// let the app pull from ACR with its managed identity
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, app.id, 'AcrPull')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output appUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
output appName string = app.name
output containerRegistry string = '${acrName}.azurecr.io'
output postgresHost string = '${pgServerName}.postgres.database.azure.com'
