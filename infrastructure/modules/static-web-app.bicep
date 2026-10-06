// Azure Static Web Apps, Standard plan (PROMPT.md §4.1 option 1): the SPA and `/api/*` share
// one origin through the linked backend (static-web-app-link.bicep, deployed after the
// Container App because the app's CSRF origin and redirect URI need this site's hostname).
// Content is deployed by .github/workflows/frontend.yml with a deployment token fetched over
// OIDC at run time (never stored, never a template output).

param name string

@description('Static Web Apps is offered in a few regions only (westeurope, centralus, eastus2, westus2, eastasia). It serves static files; the data stays with the backend region.')
param location string

param tags object

resource site 'Microsoft.Web/staticSites@2024-11-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
  properties: {
    // Pull-request preview environments would call the same linked backend: disabled.
    stagingEnvironmentPolicy: 'Disabled'
    allowConfigFileUpdates: true
    enterpriseGradeCdnStatus: 'Disabled'
  }
}

output id string = site.id
output name string = site.name
output defaultHostname string = site.properties.defaultHostname
