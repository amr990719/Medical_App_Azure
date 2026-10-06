# Microsoft Entra External ID setup

How doctors and administrators sign in (PROMPT.md §27). Django is a **confidential OIDC client**
(BFF): it runs the authorization code flow with PKCE, validates the ID token itself, maps users by
`oid` + `tid`, and gives the browser only an HttpOnly session cookie. The SPA never sees a token
and has no password form.

> **NOT VERIFIED — requires Azure credentials.** Every step below was written from the Microsoft
> documentation and the scripts were syntax-checked (`bash -n`, `shellcheck`, PowerShell parser);
> none was run against a real External ID tenant.

One app registration per environment (`medical-syndicates-dev`, `-staging`, `-prod`), each with
its own client secret in its own Key Vault (§49). Bicep does not create app registrations.

## 1. Create the external tenant (once)

1. Azure portal → **Microsoft Entra External ID** → **Overview** → **Create a tenant** →
   **External**. Choose a name (e.g. `medsyndicates`), the country/region (data location of the
   directory, see legal decision L3 in `docs/security.md`) and the subscription for billing.
2. Note the **tenant ID** (Overview page) and the **initial domain** (`<name>.onmicrosoft.com`).
   The authority used by Django is `https://<name>.ciamlogin.com/<tenant-id>`.
3. Add at least two administrators of the external tenant with MFA (break-glass account kept
   offline, decision L7).

## 2. Sign-up / sign-in user flow (Arabic)

1. External tenant → **External Identities** → **User flows** → **New user flow**.
   - Name: `signup-signin`
   - Identity providers: **Email with password** (or **Email one-time passcode**); add **Google**
     only if the organization wants it (§27, optional — configure it under *External Identities →
     All identity providers* first).
   - Attributes to collect: **Display Name** only. Everything else (national ID, syndicate data)
     is collected by the application form, never by Entra.
2. Open the flow → **Languages** → enable **Arabic (ar)** and make it the default; upload the
   Arabic strings if you customize them. Users with an Arabic browser get Arabic pages.
3. **Company branding** (tenant level): the union logo, sign-in page text in Arabic, and the
   privacy-policy link required by Law 151/2020 (decision L6/L4 owners provide the text).
4. Note the **user flow ID** (the flow's *Overview* or
   `az rest --url https://graph.microsoft.com/v1.0/identity/authenticationEventsFlows`) for
   `--user-flow-id` below.

## 3. App registration (script)

Prerequisites: Azure CLI ≥ 2.60, the environment's Key Vault already deployed (first Bicep phase,
`docs/azure-deployment.md`) and your account holding **Key Vault Secrets Officer** on it
(`keyVaultOperatorPrincipalId` parameter, or `az role assignment create`).

```bash
# Sign in to BOTH tenants; the external tenant must be the current account.
az login --tenant <workforce-tenant-id>                              # subscription with Key Vault
az login --tenant <external-tenant-id> --allow-no-subscriptions     # app registrations
az account set --subscription <external-tenant-id>

infrastructure/scripts/create-entra-app.sh \
  --environment dev \
  --tenant-id <external-tenant-id> \
  --public-url https://<static-web-app-default-hostname> \
  --local \
  --key-vault <key-vault-name> --subscription <subscription-id> \
  --user-flow-id <user-flow-id>
```

PowerShell (Windows PowerShell 5.1 or 7):

```powershell
./infrastructure/scripts/create-entra-app.ps1 -Environment dev -TenantId <external-tenant-id> `
  -PublicUrl https://<static-web-app-default-hostname> -Local `
  -KeyVault <key-vault-name> -Subscription <subscription-id> -UserFlowId <user-flow-id>
```

What the script does (idempotent; re-run it whenever a hostname is added):

| Setting | Value |
|---|---|
| Platform | **Web** (confidential client); no SPA platform, no public client |
| Redirect URIs | `https://<host>/api/v1/auth/callback/` and `https://<host>/signed-out` (post-logout) for each `--public-url`; `--local` adds `http://localhost:5173/...` (refused for prod) |
| Implicit grant | ID tokens **off**, access tokens **off** (code flow + PKCE only) |
| Supported accounts | this tenant only (`AzureADMyOrg`) |
| API permissions | Microsoft Graph delegated `openid`, `profile`, `email`; admin consent granted |
| Optional claim | `email` in the ID token (Q-T7) |
| Client secret | 1 year, created only if Key Vault has none (or `--rotate-secret`), written to Key Vault `entra-client-secret` with an expiry date; **never printed** |
| User flow | the app is added to the sign-up/sign-in flow (`--user-flow-id`) |

It prints `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID` and `ENTRA_AUTHORITY`. Store them as **GitHub
environment variables** of the same environment (`docs/github-setup.md`); they are not secrets.
The Bicep parameter files read them from the environment (`readEnvironmentVariable`), so they are
never committed.

Custom domain later: re-run with `--public-url https://<custom-domain>` (the existing URIs are
kept), set `PUBLIC_HOSTNAME` (GitHub variable) and redeploy the infrastructure so Django's redirect
URI and CSRF origin follow.

## 4. MFA for administrators (Conditional Access)

Admins are ordinary Entra users whose Django role is `ADMIN` (granted only with
`python manage.py grant_admin <email-or-oid>`, run as a one-off Container Apps job or exec).

1. External tenant → **Groups** → create `medical-admins-<env>`; add every administrator.
2. **Protection → Conditional Access → New policy** `Require MFA for administrators`:
   users = group `medical-admins-<env>`, target resources = the app `medical-syndicates-<env>`,
   grant = **Require multifactor authentication**, state **On**.
3. Optional for doctors: a second policy requiring MFA for everyone (organizational decision).
4. Django refuses an admin session whose ID token lacks `mfa` in `amr`
   (`ENTRA_ADMIN_REQUIRE_MFA=true`, the Bicep default). If the tenant does not emit `amr`
   (verify with a test admin: a refused admin lands on `/?auth_error=MFA_REQUIRED`), set the parameter
   `entraAdminRequireMfa=false` and rely on the Conditional Access policy alone (Q-T7).

## 5. Rotating the client secret

```bash
infrastructure/scripts/create-entra-app.sh --environment prod --tenant-id <id> \
  --public-url https://<host> --key-vault <vault> --subscription <sub> --rotate-secret
# Container Apps re-reads versionless Key Vault references within 30 minutes; force it now:
az containerapp revision restart -g <rg> -n <container-app> \
  --revision "$(az containerapp revision list -g <rg> -n <container-app> --query '[?properties.active].name | [0]' -o tsv)"
# After sign-in works with the new secret, delete the old one:
az ad app credential list --id <client-id> --query "[].{id:keyId, name:displayName, end:endDateTime}" -o table
az ad app credential delete --id <client-id> --key-id <old-key-id>
```

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `AADSTS50011` redirect URI mismatch | The browser host is not registered. Re-run the script with that `--public-url`; check `ENTRA_REDIRECT_URI` on the Container App ends with `/api/v1/auth/callback/`. |
| Sign-out leaves the user on an Entra page | `https://<host>/signed-out` not registered (Entra only redirects after logout to a registered reply URL). |
| `?auth_error=` on the landing page after sign-in | Django logs `ID token rejected` (with the reason: exception type, `nonce` or `tenant`) or `Token exchange failed` (with the OAuth error code); tokens are never logged. An issuer/audience error means a wrong `ENTRA_AUTHORITY` / `ENTRA_CLIENT_ID`. |
| Admin refused after sign-in (`auth_error=MFA_REQUIRED`) | No `mfa` in `amr` (section 4). |
| `invalid_client` | Client secret expired or Key Vault holds an old one — rotate (section 5). |
| Email missing on the user | `email` optional claim not configured, or the account signed up with a provider that does not return it. |
