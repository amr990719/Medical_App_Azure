// Registers the Django Container App as the Static Web App's linked backend: the browser calls
// `https://<swa-host>/api/...` (same origin, HttpOnly session cookie works, §4.1) and Static Web
// Apps forwards the request, path unchanged, to the Container App.

param staticWebAppName string
param backendResourceId string
param backendLocation string

resource site 'Microsoft.Web/staticSites@2024-11-01' existing = {
  name: staticWebAppName
}

resource linkedBackend 'Microsoft.Web/staticSites/linkedBackends@2024-11-01' = {
  parent: site
  name: 'django-api'
  properties: {
    backendResourceId: backendResourceId
    region: backendLocation
  }
}

output linkedBackendId string = linkedBackend.id
