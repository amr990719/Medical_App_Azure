<#
.SYNOPSIS
GitHub Actions -> Azure with OIDC federated credentials (PowerShell port of setup-github-oidc.sh).

.DESCRIPTION
Run once per environment; idempotent. Creates two GitHub identities in the environment's
resource group:
  deploy  id-github-<base>-<env>, federated to environment <env> (restrict that GitHub
          environment to the protected main branch; required reviewers for prod).
          Roles: Contributor, AcrPush, and Role Based Access Control Administrator with an ABAC
          condition: only the six data-plane roles main.bicep declares, only for the app
          identity id-<base>-<env> (created here so its principal id is known).
  plan    id-github-<base>-<env>-plan, federated to environment <env>-plan (pull requests and
          what-if-only runs). Roles: Reader + a custom role allowing only deployment
          validate/what-if.
Prints the GitHub environment variables to set; does not call GitHub.
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
    if ($LASTEXITCODE -ne 0) { throw "az $($args[0]) $($args[1]) failed with exit code $LASTEXITCODE" }
    if ($null -eq $output) { return '' }
    return (($output | Out-String).Trim())
}

function Test-Az {
    # Runs az and returns $true when it succeeds (existence checks).
    & az @args 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw 'Azure CLI (az) is required' }

$envShort = @{ dev = 'dev'; staging = 'stg'; prod = 'prd' }[$Environment]
$issuer = 'https://token.actions.githubusercontent.com'
$rgId = Invoke-Az group show -n $ResourceGroup --query id -o tsv
$subscriptionId = Invoke-Az account show --query id -o tsv
$tenantId = Invoke-Az account show --query tenantId -o tsv

function Get-Identity([string]$Name, [string]$Purpose) {
    if (-not (Test-Az identity show -g $ResourceGroup -n $Name --output none)) {
        Write-Host "Creating identity $Name"
        Invoke-Az identity create -g $ResourceGroup -n $Name --tags "purpose=$Purpose" "environment=$Environment" --output none | Out-Null
    }
    return @{
        PrincipalId = (Invoke-Az identity show -g $ResourceGroup -n $Name --query principalId -o tsv)
        ClientId    = (Invoke-Az identity show -g $ResourceGroup -n $Name --query clientId -o tsv)
    }
}

function Set-Federation([string]$Identity, [string]$GitHubEnvironment) {
    $name = "github-$GitHubEnvironment"
    $subject = "repo:${Repo}:environment:$GitHubEnvironment"
    $verb = 'create'
    if (Test-Az identity federated-credential show -g $ResourceGroup --identity-name $Identity -n $name --output none) { $verb = 'update' }
    Invoke-Az identity federated-credential $verb -g $ResourceGroup --identity-name $Identity -n $name `
        --issuer $issuer --subject $subject --audiences api://AzureADTokenExchange --output none | Out-Null
    Write-Host "Federated credential on ${Identity}: $subject"
}

function Grant-Role([string]$Principal, [string]$Role, [string]$Label, [string]$Condition = '') {
    $existing = Invoke-Az role assignment list --assignee $Principal --scope $rgId --role $Role --query '[0].id' -o tsv
    if ($existing) {
        $current = Invoke-Az role assignment list --assignee $Principal --scope $rgId --role $Role --query '[0].condition' -o tsv
        if ($current -eq $Condition) {
            Write-Host "Role already assigned: $Label"
            return
        }
        Write-Host "Replacing $Label (condition changed)"
        Invoke-Az role assignment delete --ids $existing --output none | Out-Null
    }
    Write-Host "Assigning $Label"
    if ($Condition) {
        Invoke-Az role assignment create --assignee-object-id $Principal --assignee-principal-type ServicePrincipal `
            --role $Role --scope $rgId --condition $Condition --condition-version '2.0' --output none | Out-Null
    }
    else {
        Invoke-Az role assignment create --assignee-object-id $Principal --assignee-principal-type ServicePrincipal `
            --role $Role --scope $rgId --output none | Out-Null
    }
}

# --- App identity (same name as main.bicep: id-<base>-<env-short>) ---------------------------
$app = Get-Identity "id-$BaseName-$envShort" 'app'

# --- Deploy identity -------------------------------------------------------------------------
$deployName = "id-github-$BaseName-$Environment"
$deploy = Get-Identity $deployName 'github-actions-deploy'
Set-Federation $deployName $Environment

$contributor = 'b24988ac-6180-42a0-ab88-20f7382dd24c'
$acrPush = '8311e382-0749-4cb8-b61a-7f3ba6c4aaa5'
$rbacAdmin = 'f58310d9-a9f6-439a-9e8d-f62e7b41a168'
# The six role definitions role-assignments.bicep grants to the app identity.
$appRoles = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe, db58b8e5-c6ad-4a2a-8342-4190687cbf4a, 4633458b-17de-408a-b874-0445c86b69e6, 7f951dda-4ed3-4680-a7ca-43fe172d538d, 5e0bd9bd-7b93-4f28-af87-19fc36ad61bd, 3913510d-42f4-4e42-8a64-420c390055eb'
$appPrincipal = $app.PrincipalId
$condition = "((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$appRoles} AND @Request[Microsoft.Authorization/roleAssignments:PrincipalId] ForAnyOfAnyValues:GuidEquals {$appPrincipal})) AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$appRoles} AND @Resource[Microsoft.Authorization/roleAssignments:PrincipalId] ForAnyOfAnyValues:GuidEquals {$appPrincipal}))"

Grant-Role $deploy.PrincipalId $contributor 'Contributor'
Grant-Role $deploy.PrincipalId $acrPush 'AcrPush'
Grant-Role $deploy.PrincipalId $rbacAdmin 'Role Based Access Control Administrator (app roles, app identity only)' $condition

# --- Plan identity (pull requests, what-if only) ----------------------------------------------
$planName = "id-github-$BaseName-$Environment-plan"
$plan = Get-Identity $planName 'github-actions-plan'
Set-Federation $planName "$Environment-plan"

$whatIfRole = "Deployment What-If Operator ($ResourceGroup)"
$existingRole = Invoke-Az role definition list --custom-role-only true --name $whatIfRole --query '[0].name' -o tsv
if (-not $existingRole) {
    Write-Host "Creating custom role $whatIfRole"
    $roleFile = [System.IO.Path]::GetTempFileName()
    try {
        $definition = [ordered]@{
            Name             = $whatIfRole
            Description      = 'Validate and preview (what-if) resource group deployments; no write access.'
            Actions          = @(
                'Microsoft.Resources/deployments/read',
                'Microsoft.Resources/deployments/validate/action',
                'Microsoft.Resources/deployments/whatIf/action',
                'Microsoft.Resources/deployments/operationstatuses/read')
            NotActions       = @()
            AssignableScopes = @($rgId)
        }
        Set-Content -Path $roleFile -Encoding ascii -Value ($definition | ConvertTo-Json -Depth 3)
        Invoke-Az role definition create --role-definition "@$roleFile" --output none | Out-Null
    }
    finally { Remove-Item -Force $roleFile }
    # New role definitions take a moment to replicate before they can be assigned.
    for ($i = 0; $i -lt 6; $i++) {
        if (Invoke-Az role definition list --custom-role-only true --name $whatIfRole --query '[0].name' -o tsv) { break }
        Start-Sleep -Seconds 10
    }
}
Grant-Role $plan.PrincipalId 'Reader' 'Reader'
Grant-Role $plan.PrincipalId $whatIfRole $whatIfRole

$protection = 'deployment branches: protected branches only (main)'
if ($Environment -eq 'prod') { $protection += '; required reviewers' }

Write-Host ''
Write-Host 'GitHub environments (none of these values is a secret):'
Write-Host "  $Environment        $protection"
Write-Host "    gh variable set AZURE_CLIENT_ID --env $Environment --repo $Repo --body $($deploy.ClientId)"
Write-Host "  $Environment-plan   no branch restriction (pull requests); read + what-if only"
Write-Host "    gh variable set AZURE_CLIENT_ID --env $Environment-plan --repo $Repo --body $($plan.ClientId)"
Write-Host '  Both environments:'
Write-Host "    gh variable set AZURE_TENANT_ID       --env <environment> --repo $Repo --body $tenantId"
Write-Host "    gh variable set AZURE_SUBSCRIPTION_ID --env <environment> --repo $Repo --body $subscriptionId"
Write-Host "    gh variable set AZURE_RESOURCE_GROUP  --env <environment> --repo $Repo --body $ResourceGroup"
Write-Host 'After the first Bicep deployment, also set ACR_NAME, CONTAINER_APP_NAME, MIGRATE_JOB_NAME,'
Write-Host 'CLEANUP_JOB_NAME, STATIC_WEB_APP_NAME, ENTRA_AUTHORITY, ENTRA_TENANT_ID, ENTRA_CLIENT_ID.'
