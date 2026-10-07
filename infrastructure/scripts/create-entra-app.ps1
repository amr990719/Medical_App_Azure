<#
.SYNOPSIS
Creates or updates the Entra External ID app registration of one environment (PowerShell port of
create-entra-app.sh; PROMPT.md section 27, docs/entra-setup.md).

.DESCRIPTION
Idempotent. Web platform (Django BFF, authorization code flow + PKCE), implicit ID/access-token
issuance off, delegated openid/profile/email only, optional `email` ID-token claim. The client
secret is never printed: it is written straight into Key Vault as `entra-client-secret`
(only when missing, or with -RotateSecret).

Prerequisites (two sign-ins kept in the az CLI profile):
  az login --tenant <external-tenant-id> --allow-no-subscriptions
  az login --tenant <workforce-tenant-id>
  az account set --subscription <external-tenant-id>

Works in Windows PowerShell 5.1 and PowerShell 7.

.EXAMPLE
./infrastructure/scripts/create-entra-app.ps1 -Environment dev -TenantId <external-tenant-id> `
  -PublicUrl https://<static-web-app-host> -Local -KeyVault <vault> -Subscription <subscription-id>
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('dev', 'staging', 'prod')][string]$Environment,
    [Parameter(Mandatory = $true)][string]$TenantId,
    [Parameter(Mandatory = $true)][string[]]$PublicUrl,
    [switch]$Local,
    [string]$KeyVault = '',
    [string]$Subscription = '',
    [string]$UserFlowId = '',
    [switch]$RotateSecret,
    [ValidateRange(1, 2)][int]$SecretYears = 1
)

$ErrorActionPreference = 'Stop'

function Invoke-Az {
    $output = & az @args
    if ($LASTEXITCODE -ne 0) { throw "az $($args[0]) $($args[1]) failed with exit code $LASTEXITCODE" }
    if ($null -eq $output) { return '' }
    return (($output | Out-String).Trim())
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw 'Azure CLI (az) is required' }
if ($KeyVault -and -not $Subscription) { throw '-KeyVault needs -Subscription (the vault lives in the workforce tenant)' }
if ($Environment -eq 'prod' -and $Local) { throw '-Local is refused for prod (no localhost redirect URIs in production)' }

$currentTenant = Invoke-Az account show --query tenantId -o tsv
if ($currentTenant -ne $TenantId) {
    throw "The current az account is in tenant $currentTenant, not $TenantId. Run: az login --tenant $TenantId --allow-no-subscriptions; az account set --subscription $TenantId"
}

$displayName = "medical-syndicates-$Environment"

$redirectUris = New-Object System.Collections.Generic.List[string]
foreach ($url in $PublicUrl) {
    $trimmed = $url.TrimEnd('/')
    if (-not $trimmed.StartsWith('https://')) { throw "-PublicUrl must use https: $trimmed" }
    $redirectUris.Add("$trimmed/api/v1/auth/callback/")
    $redirectUris.Add("$trimmed/signed-out")
}
if ($Local) {
    $redirectUris.Add('http://localhost:5173/api/v1/auth/callback/')
    $redirectUris.Add('http://localhost:5173/signed-out')
}

$appId = Invoke-Az ad app list --display-name $displayName --query '[0].appId' -o tsv
if (-not $appId) {
    Write-Host "Creating app registration $displayName"
    $appId = Invoke-Az ad app create --display-name $displayName --sign-in-audience AzureADMyOrg `
        --enable-id-token-issuance false --enable-access-token-issuance false --query appId -o tsv
}
else {
    Write-Host "Updating existing app registration $displayName"
}

$existing = Invoke-Az ad app show --id $appId --query 'web.redirectUris' -o tsv
foreach ($uri in ($existing -split "`r?`n")) { if ($uri) { $redirectUris.Add($uri.Trim()) } }
$merged = @($redirectUris | Sort-Object -Unique)

$updateArgs = @('ad', 'app', 'update', '--id', $appId, '--web-redirect-uris') + $merged + @(
    '--enable-id-token-issuance', 'false', '--enable-access-token-issuance', 'false', '--sign-in-audience', 'AzureADMyOrg')
Invoke-Az @updateArgs | Out-Null

$claimsFile = [System.IO.Path]::GetTempFileName()
$secretFile = ''
try {
    Set-Content -Path $claimsFile -Value '{"idToken": [{"name": "email", "essential": false}]}' -Encoding ascii
    Invoke-Az ad app update --id $appId --optional-claims "@$claimsFile" | Out-Null

    # Delegated Graph openid, profile, email as the complete list (`permission add` appends
    # duplicates on every re-run).
    Set-Content -Path $claimsFile -Encoding ascii -Value ('[{"resourceAppId": "00000003-0000-0000-c000-000000000000", "resourceAccess": [' +
        '{"id": "37f7f235-527c-4136-accd-4a02d197296e", "type": "Scope"}, ' +
        '{"id": "14dad69e-099b-42c9-810b-d002981feec1", "type": "Scope"}, ' +
        '{"id": "64a6cdd6-aab1-4aaf-94b8-3cc8405e90d0", "type": "Scope"}]}]')
    Invoke-Az ad app update --id $appId --required-resource-accesses "@$claimsFile" | Out-Null

    $spId = Invoke-Az ad sp list --filter "appId eq '$appId'" --query '[0].id' -o tsv
    if (-not $spId) { Invoke-Az ad sp create --id $appId --only-show-errors | Out-Null }
    Invoke-Az ad app permission admin-consent --id $appId | Out-Null

    if ($UserFlowId) {
        $flowUrl = "https://graph.microsoft.com/v1.0/identity/authenticationEventsFlows/$UserFlowId/conditions/applications/includeApplications"
        $linked = Invoke-Az rest --method GET --url $flowUrl --query "value[?appId=='$appId'] | length(@)" -o tsv
        if ($linked -eq '0') {
            $bodyFile = [System.IO.Path]::GetTempFileName()
            try {
                Set-Content -Path $bodyFile -Encoding ascii -Value ('{"@odata.type": "#microsoft.graph.authenticationConditionApplication", "appId": "' + $appId + '"}')
                Invoke-Az rest --method POST --url $flowUrl --headers 'Content-Type=application/json' --body "@$bodyFile" --only-show-errors | Out-Null
                Write-Host "Linked the app to user flow $UserFlowId"
            }
            finally { Remove-Item -Force $bodyFile }
        }
    }

    if ($KeyVault) {
        $exists = Invoke-Az keyvault secret list --vault-name $KeyVault --subscription $Subscription --query "[?name=='entra-client-secret'] | length(@)" -o tsv
        if ($exists -eq '0' -or $RotateSecret) {
            $secretFile = [System.IO.Path]::GetTempFileName()
            $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd')
            $password = Invoke-Az ad app credential reset --id $appId --append --display-name "key-vault-$stamp" `
                --years $SecretYears --query password -o tsv
            [System.IO.File]::WriteAllText($secretFile, $password)
            $password = $null
            $expires = (Get-Date).ToUniversalTime().AddYears($SecretYears).ToString('yyyy-MM-ddTHH:mm:ssZ')
            Invoke-Az keyvault secret set --vault-name $KeyVault --subscription $Subscription --name entra-client-secret `
                --file $secretFile --encoding utf-8 --content-type 'text/plain' --expires $expires --output none | Out-Null
            Write-Host "Stored a new client secret in Key Vault $KeyVault (entra-client-secret, expires $expires)"
        }
        else {
            Write-Host "Key Vault $KeyVault already holds entra-client-secret (use -RotateSecret to replace it)"
        }
    }
    else {
        Write-Host 'No -KeyVault given: no client secret created. Re-run with -KeyVault/-Subscription.'
    }
}
finally {
    Remove-Item -Force $claimsFile
    if ($secretFile -and (Test-Path $secretFile)) { Remove-Item -Force $secretFile }
}

$initialDomain = Invoke-Az rest --method GET --url 'https://graph.microsoft.com/v1.0/domains' --query 'value[?isInitial].id | [0]' -o tsv
$subdomain = $initialDomain -replace '\.onmicrosoft\.com$', ''

Write-Host ''
Write-Host "Values for the $Environment environment (GitHub environment variables / parameter env vars):"
Write-Host "  ENTRA_TENANT_ID=$TenantId"
Write-Host "  ENTRA_CLIENT_ID=$appId"
Write-Host "  ENTRA_AUTHORITY=https://$subdomain.ciamlogin.com/$TenantId"
Write-Host 'Registered redirect URIs:'
foreach ($uri in $merged) { Write-Host "  $uri" }
