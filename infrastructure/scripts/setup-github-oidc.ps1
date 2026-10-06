<#
.SYNOPSIS
GitHub Actions -> Azure with OIDC federated credentials (PowerShell port of setup-github-oidc.sh).

.DESCRIPTION
Run once per environment; idempotent. Creates the user-assigned identity
id-github-<base>-<env> in the environment's resource group, a federated credential for
repo:<owner>/<repo>:environment:<env>, and resource-group-scoped roles: Contributor, AcrPush and
Role Based Access Control Administrator restricted (ABAC condition) to the data-plane roles
main.bicep assigns. Prints the GitHub environment variables to set; does not call GitHub.
Works in Windows PowerShell 5.1 and PowerShell 7.

.EXAMPLE
./infrastructure/scripts/setup-github-oidc.ps1 -ResourceGroup rg-medsyn-dev -Environment dev -Repo owner/repo
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ResourceGroup,
    [Parameter(Mandatory = $true)][ValidateSet('dev', 'staging', 'prod')][string]$Environment,
    [Parameter(Mandatory = $true)][ValidatePattern('^[^/]+/[^/]+$')][string]$Repo,
    [string]$BaseName = 'medsyn'
)

$ErrorActionPreference = 'Stop'

function Invoke-Az {
    # Runs az, throws on a non-zero exit code, returns trimmed stdout.
    $output = & az @args
    if ($LASTEXITCODE -ne 0) { throw "az $($args -join ' ') failed with exit code $LASTEXITCODE" }
    if ($null -eq $output) { return '' }
    return (($output | Out-String).Trim())
}

function Test-Az {
    # Runs az and returns $true when it succeeds (used for existence checks).
    & az @args 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw 'Azure CLI (az) is required' }

$identityName = "id-github-$BaseName-$Environment"
$subject = "repo:${Repo}:environment:$Environment"
$issuer = 'https://token.actions.githubusercontent.com'

$rgId = Invoke-Az group show -n $ResourceGroup --query id -o tsv
$subscriptionId = Invoke-Az account show --query id -o tsv
$tenantId = Invoke-Az account show --query tenantId -o tsv

if (-not (Test-Az identity show -g $ResourceGroup -n $identityName --output none)) {
    Write-Host "Creating identity $identityName"
    Invoke-Az identity create -g $ResourceGroup -n $identityName --tags purpose=github-actions "environment=$Environment" --output none | Out-Null
}
$clientId = Invoke-Az identity show -g $ResourceGroup -n $identityName --query clientId -o tsv
$principalId = Invoke-Az identity show -g $ResourceGroup -n $identityName --query principalId -o tsv

$credentialName = "github-$Environment"
$verb = 'create'
if (Test-Az identity federated-credential show -g $ResourceGroup --identity-name $identityName -n $credentialName --output none) {
    $verb = 'update'
}
Invoke-Az identity federated-credential $verb -g $ResourceGroup --identity-name $identityName -n $credentialName `
    --issuer $issuer --subject $subject --audiences api://AzureADTokenExchange --output none | Out-Null
Write-Host "Federated credential ${credentialName}: $subject"

function Grant-Role([string]$Role, [string]$Label, [string]$Condition = '') {
    $count = Invoke-Az role assignment list --assignee $principalId --scope $rgId --role $Role --query 'length(@)' -o tsv
    if ($count -ne '0') {
        Write-Host "Role already assigned: $Label"
        return
    }
    Write-Host "Assigning $Label"
    if ($Condition) {
        Invoke-Az role assignment create --assignee-object-id $principalId --assignee-principal-type ServicePrincipal `
            --role $Role --scope $rgId --condition $Condition --condition-version '2.0' --output none | Out-Null
    }
    else {
        Invoke-Az role assignment create --assignee-object-id $principalId --assignee-principal-type ServicePrincipal `
            --role $Role --scope $rgId --output none | Out-Null
    }
}

$contributor = 'b24988ac-6180-42a0-ab88-20f7382dd24c'
$acrPush = '8311e382-0749-4cb8-b61a-7f3ba6c4aaa5'
$rbacAdmin = 'f58310d9-a9f6-439a-9e8d-f62e7b41a168'
# The only roles main.bicep / role-assignments.bicep may grant.
$allowedRoles = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe, db58b8e5-c6ad-4a2a-8342-4190687cbf4a, 4633458b-17de-408a-b874-0445c86b69e6, b86a8fe4-44ce-4948-aee5-eccb2c155cd7, 7f951dda-4ed3-4680-a7ca-43fe172d538d, 5e0bd9bd-7b93-4f28-af87-19fc36ad61bd, 3913510d-42f4-4e42-8a64-420c390055eb'
$condition = "((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$allowedRoles})) AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$allowedRoles}))"

Grant-Role $contributor 'Contributor'
Grant-Role $acrPush 'AcrPush'
Grant-Role $rbacAdmin 'Role Based Access Control Administrator (condition-restricted)' $condition

Write-Host ''
Write-Host "GitHub environment '$Environment' variables (none is a secret):"
Write-Host "  gh variable set AZURE_CLIENT_ID       --env $Environment --repo $Repo --body $clientId"
Write-Host "  gh variable set AZURE_TENANT_ID       --env $Environment --repo $Repo --body $tenantId"
Write-Host "  gh variable set AZURE_SUBSCRIPTION_ID --env $Environment --repo $Repo --body $subscriptionId"
Write-Host "  gh variable set AZURE_RESOURCE_GROUP  --env $Environment --repo $Repo --body $ResourceGroup"
Write-Host 'After the first Bicep deployment, also set ACR_NAME, CONTAINER_APP_NAME, MIGRATE_JOB_NAME,'
Write-Host 'STATIC_WEB_APP_NAME, ENTRA_AUTHORITY, ENTRA_TENANT_ID, ENTRA_CLIENT_ID (docs/github-setup.md).'
