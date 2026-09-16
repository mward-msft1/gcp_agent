<#
.SYNOPSIS
    Creates (or reuses) a Microsoft Entra app registration, then creates/updates
    a Microsoft Purview DLP policy and rule scoped to that app.

.DESCRIPTION
    Beginner-friendly copy/paste script for this repository.

    What this script does:
      1) Optionally creates an Entra app registration for your agent.
      2) Optionally creates a client secret for that app.
      3) Automatically uses that App (client) ID in the DLP policy scope.
      4) Creates or updates DLP policy + rule for custom AI apps.
      5) Prints copy/paste .env lines for this repository.

    Use -NonInteractive for unattended runs (for example the weekly
    "Weekly Purview incident alerts" GitHub Actions workflow). In that mode the
    script never prompts, reads its configuration from environment variables,
    reuses an existing Entra app (PURVIEW_DLP_TARGET_APP_ID), connects to
    Security & Compliance PowerShell with app-only certificate authentication,
    and fails with a clear error when required configuration is missing.

    Source baseline:
      https://github.com/microsoft/purview-api-samples/tree/main/DLPforCustomAIApps
#>

[CmdletBinding()]
param(
    [bool]$CreateEntraApp = $true,

    # Unattended mode (GitHub Actions / scheduled automation).
    # All values are read from environment variables and the script never prompts.
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

if ($NonInteractive -and -not $PSBoundParameters.ContainsKey("CreateEntraApp")) {
    # Unattended runs never create Entra apps or secrets; they reuse an existing app id.
    $CreateEntraApp = $false
}

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$DefaultValue = ""
    )
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $DefaultValue }
    return $value.Trim()
}

function Get-EnvList {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$DefaultValue
    )
    $value = Get-EnvValue -Name $Name
    if ([string]::IsNullOrWhiteSpace($value)) { return $DefaultValue }
    return @($value -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

# -----------------------------------------------------------------------------
# Configuration - replace values if needed
# -----------------------------------------------------------------------------

# Every value below can be overridden with an environment variable, which is how
# the scheduled GitHub Actions workflow configures unattended runs.

# Entra app creation settings (used when -CreateEntraApp $true).
$EntraAppDisplayName      = Get-EnvValue -Name "PURVIEW_DLP_ENTRA_APP_DISPLAY_NAME" -DefaultValue "gcp-document-routing-agent"
$CreateClientSecret       = $true
$ClientSecretDisplayName  = "gcp-agent-secret"
$ClientSecretMonthsValid  = 12

# If you do NOT want this script to create an app, set -CreateEntraApp $false
# and set this AppId manually (or set PURVIEW_DLP_TARGET_APP_ID).
$ExistingAppClientId = Get-EnvValue -Name "PURVIEW_DLP_TARGET_APP_ID"

# Friendly names shown in Purview.
$DlpPolicyName = Get-EnvValue -Name "PURVIEW_DLP_POLICY_NAME" -DefaultValue "Contoso Custom AI Apps - Block Sensitive Data"
$DlpRuleName   = Get-EnvValue -Name "PURVIEW_DLP_RULE_NAME"   -DefaultValue "Block sensitive info in custom AI apps"

# Enforcement mode:
#   Enable | TestWithNotifications | TestWithoutNotifications | Disable
$PolicyMode = Get-EnvValue -Name "PURVIEW_DLP_POLICY_MODE" -DefaultValue "Enable"

# Rule action on sensitive match: Block | Audit
$RestrictAction = Get-EnvValue -Name "PURVIEW_DLP_RESTRICT_ACTION" -DefaultValue "Block"

# App name shown in Purview DLP locations.
$PurviewAppDisplayName = Get-EnvValue -Name "PURVIEW_DLP_APP_DISPLAY_NAME" -DefaultValue "GCP Document Routing Agent"

# Recipients for alerts and incidents ("SiteAdmin" or specific UPNs, comma separated).
$AlertRecipients     = Get-EnvList -Name "PURVIEW_DLP_ALERT_RECIPIENTS"    -DefaultValue @("SiteAdmin")
$IncidentRecipients  = Get-EnvList -Name "PURVIEW_DLP_INCIDENT_RECIPIENTS" -DefaultValue @("SiteAdmin")
$NotifyRecipients    = Get-EnvList -Name "PURVIEW_DLP_NOTIFY_RECIPIENTS"   -DefaultValue @("SiteAdmin")
$ReportSeverityLevel = Get-EnvValue -Name "PURVIEW_DLP_REPORT_SEVERITY"    -DefaultValue "High"

# Sensitive information types (Purview built-ins).
$SensitiveTypes = @(
    @{ Name = "Credit Card Number";                                    minCount = "1" },
    @{ Name = "U.S. Social Security Number (SSN)";                     minCount = "1" },
    @{ Name = "U.S. Bank Account Number";                              minCount = "1" },
    @{ Name = "U.S. Individual Taxpayer Identification Number (ITIN)"; minCount = "1" },
    @{ Name = "Passport Number";                                       minCount = "1" },
    @{ Name = "IBAN";                                                  minCount = "1" }
)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

function Ensure-Module {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not (Get-Module -ListAvailable -Name $Name)) {
        throw "PowerShell module '$Name' is not installed.`nInstall it with:`nInstall-Module $Name -Scope CurrentUser"
    }
    Import-Module $Name -ErrorAction Stop
}

function Prompt-RequiredValue {
    param(
        [Parameter(Mandatory = $true)][string]$PromptMessage,
        [string]$DefaultValue = "",
        [string]$EnvVarName = ""
    )
    if ($NonInteractive) {
        if (-not [string]::IsNullOrWhiteSpace($DefaultValue)) {
            return $DefaultValue.Trim()
        }
        $hint = if ([string]::IsNullOrWhiteSpace($EnvVarName)) { "" } else { " Set the '$EnvVarName' environment variable (GitHub Actions secret or variable)." }
        throw "Missing required configuration in -NonInteractive mode: $PromptMessage.$hint"
    }
    while ($true) {
        $raw = if ([string]::IsNullOrWhiteSpace($DefaultValue)) {
            Read-Host $PromptMessage
        } else {
            Read-Host "$PromptMessage [$DefaultValue]"
        }
        $value = if ([string]::IsNullOrWhiteSpace($raw)) { $DefaultValue } else { $raw }
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value.Trim()
        }
        Write-Host "A value is required. Please try again." -ForegroundColor Yellow
    }
}

function Get-OrCreate-EntraApp {
    param(
        [Parameter(Mandatory = $true)][string]$DisplayName,
        [Parameter(Mandatory = $true)][bool]$CreateSecret,
        [Parameter(Mandatory = $true)][string]$SecretDisplayName,
        [Parameter(Mandatory = $true)][int]$SecretMonthsValid
    )

    Ensure-Module -Name "Microsoft.Graph.Authentication"
    Ensure-Module -Name "Microsoft.Graph.Applications"

    Write-Host "Connecting to Microsoft Graph to create/read app registration..." -ForegroundColor Cyan
    Connect-MgGraph -Scopes "Application.ReadWrite.All","Directory.ReadWrite.All","Application.Read.All" -NoWelcome

    $app = Get-MgApplication -Filter "displayName eq '$DisplayName'" -Top 1
    if (-not $app) {
        Write-Host "Creating Entra app registration '$DisplayName'..." -ForegroundColor Yellow
        $app = New-MgApplication -DisplayName $DisplayName -SignInAudience "AzureADMyOrg"
        Write-Host "Entra app created." -ForegroundColor Green
    }
    else {
        Write-Host "Using existing Entra app '$DisplayName'." -ForegroundColor Green
    }

    $servicePrincipal = Get-MgServicePrincipal -Filter "appId eq '$($app.AppId)'" -Top 1
    if (-not $servicePrincipal) {
        Write-Host "Creating service principal for app..." -ForegroundColor Yellow
        New-MgServicePrincipal -AppId $app.AppId | Out-Null
        Write-Host "Service principal created." -ForegroundColor Green
    }

    $secretText = $null
    if ($CreateSecret) {
        Write-Host "Creating client secret (valid $SecretMonthsValid months)..." -ForegroundColor Yellow
        $secret = Add-MgApplicationPassword -ApplicationId $app.Id -PasswordCredential @{
            displayName = $SecretDisplayName
            endDateTime = (Get-Date).AddMonths($SecretMonthsValid)
        }
        $secretText = $secret.SecretText
        Write-Host "Client secret created." -ForegroundColor Green
    }

    $tenantId = (Get-MgContext).TenantId
    Disconnect-MgGraph | Out-Null

    return @{
        TenantId    = $tenantId
        AppId       = $app.AppId
        AppObjectId = $app.Id
        SecretText  = $secretText
    }
}

# -----------------------------------------------------------------------------
# Resolve the target app id for policy scope + .env output
# -----------------------------------------------------------------------------

$resolvedTenantId = ""
$resolvedAppId = ""
$resolvedSecretText = ""

if ([string]::IsNullOrWhiteSpace($DlpPolicyName)) {
    $DlpPolicyName = Prompt-RequiredValue -PromptMessage "Enter DLP policy name"
}
if ([string]::IsNullOrWhiteSpace($DlpRuleName)) {
    $DlpRuleName = Prompt-RequiredValue -PromptMessage "Enter DLP rule name"
}
if ([string]::IsNullOrWhiteSpace($PurviewAppDisplayName)) {
    $PurviewAppDisplayName = Prompt-RequiredValue -PromptMessage "Enter Purview app display name"
}

if ($CreateEntraApp) {
    if ($NonInteractive) {
        throw "-CreateEntraApp `$true is not supported with -NonInteractive. Create the Entra app once interactively, then set PURVIEW_DLP_TARGET_APP_ID."
    }
    $EntraAppDisplayName = Prompt-RequiredValue `
        -PromptMessage "Enter Entra app registration display name" `
        -DefaultValue $EntraAppDisplayName
    $appResult = Get-OrCreate-EntraApp `
        -DisplayName $EntraAppDisplayName `
        -CreateSecret $CreateClientSecret `
        -SecretDisplayName $ClientSecretDisplayName `
        -SecretMonthsValid $ClientSecretMonthsValid

    $resolvedTenantId = $appResult.TenantId
    $resolvedAppId = $appResult.AppId
    $resolvedSecretText = $appResult.SecretText
}
else {
    $ExistingAppClientId = Prompt-RequiredValue `
        -PromptMessage "CreateEntraApp is false. Enter existing Entra App (client) ID" `
        -DefaultValue $ExistingAppClientId `
        -EnvVarName "PURVIEW_DLP_TARGET_APP_ID"
    $resolvedAppId = $ExistingAppClientId
}

$Applications = @(
    @{
        AppId   = $resolvedAppId
        AppName = $PurviewAppDisplayName
    }
)

# -----------------------------------------------------------------------------
# Connect to Security & Compliance PowerShell
# -----------------------------------------------------------------------------

Write-Host "Connecting to Security & Compliance PowerShell..." -ForegroundColor Cyan
Ensure-Module -Name "ExchangeOnlineManagement"

if ($NonInteractive) {
    # App-only certificate authentication (no interactive sign-in available in CI).
    $organization = Prompt-RequiredValue `
        -PromptMessage "Purview organization (tenant domain, e.g. contoso.onmicrosoft.com)" `
        -DefaultValue (Get-EnvValue -Name "PURVIEW_DLP_ORGANIZATION") `
        -EnvVarName "PURVIEW_DLP_ORGANIZATION"
    $connectAppId = Prompt-RequiredValue `
        -PromptMessage "Entra app (client) ID used to connect to Security & Compliance PowerShell" `
        -DefaultValue (Get-EnvValue -Name "PURVIEW_DLP_CONNECT_APP_ID") `
        -EnvVarName "PURVIEW_DLP_CONNECT_APP_ID"
    $certBase64 = Prompt-RequiredValue `
        -PromptMessage "Base64-encoded PFX certificate for app-only authentication" `
        -DefaultValue (Get-EnvValue -Name "PURVIEW_DLP_CERT_BASE64") `
        -EnvVarName "PURVIEW_DLP_CERT_BASE64"
    $certPassword = Get-EnvValue -Name "PURVIEW_DLP_CERT_PASSWORD"

    try {
        $certBytes = [Convert]::FromBase64String($certBase64)
    }
    catch {
        throw "PURVIEW_DLP_CERT_BASE64 is not valid base64 content: $($_.Exception.Message)"
    }

    $certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
        $certBytes,
        $certPassword,
        [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::EphemeralKeySet)

    Connect-IPPSSession `
        -AppId $connectAppId `
        -Certificate $certificate `
        -Organization $organization `
        -ShowBanner:$false
}
else {
    Connect-IPPSSession
}

# -----------------------------------------------------------------------------
# Build policy location payload (scoped to app ids)
# -----------------------------------------------------------------------------

$LocationsObject = foreach ($app in $Applications) {
    @{
        Workload            = "Applications"
        Location            = $app.AppId
        LocationDisplayName = $app.AppName
        LocationSource      = "Entra"
        LocationType        = "Individual"
        Inclusions          = @(@{ Type = "Tenant"; Identity = "All" })
    }
}
$LocationsJson = $LocationsObject | ConvertTo-Json -Depth 6 -Compress

# -----------------------------------------------------------------------------
# Create/update DLP policy
# -----------------------------------------------------------------------------

Write-Host "Ensuring DLP policy '$DlpPolicyName' exists..." -ForegroundColor Yellow
$existingPolicy = Get-DlpCompliancePolicy -Identity $DlpPolicyName -ErrorAction SilentlyContinue
if (-not $existingPolicy) {
    New-DlpCompliancePolicy `
        -Name              $DlpPolicyName `
        -Comment           "Blocks common sensitive information types in custom AI apps and agents." `
        -Locations         $LocationsJson `
        -EnforcementPlanes @("Application") `
        -Mode              $PolicyMode | Out-Null
    Write-Host "DLP policy created." -ForegroundColor Green
}
else {
    Set-DlpCompliancePolicy `
        -Identity          $DlpPolicyName `
        -Locations         $LocationsJson `
        -EnforcementPlanes @("Application") `
        -Mode              $PolicyMode | Out-Null
    Write-Host "DLP policy updated." -ForegroundColor Green
}

# -----------------------------------------------------------------------------
# Create/update DLP rule
# -----------------------------------------------------------------------------

Write-Host "Ensuring DLP rule '$DlpRuleName' exists..." -ForegroundColor Yellow
$existingRule = Get-DlpComplianceRule -Identity $DlpRuleName -ErrorAction SilentlyContinue

$ruleParams = @{
    ContentContainsSensitiveInformation = $SensitiveTypes
    GenerateAlert                       = $AlertRecipients
    GenerateIncidentReport              = $IncidentRecipients
    IncidentReportContent               = @("Default","Detections","DetectionDetails","MatchedItem","RulesMatched","Service","Severity","Title")
    NotifyUser                          = $NotifyRecipients
    ReportSeverityLevel                 = $ReportSeverityLevel
    RestrictAccess                      = @(
        @{ Setting = "UploadText";   Value = $RestrictAction },
        @{ Setting = "DownloadText"; Value = $RestrictAction }
    )
    StopPolicyProcessing                = $true
    Comment                             = "Blocks prompts and responses containing listed sensitive information types."
}

if (-not $existingRule) {
    New-DlpComplianceRule -Name $DlpRuleName -Policy $DlpPolicyName @ruleParams | Out-Null
    Write-Host "DLP rule created." -ForegroundColor Green
}
else {
    Set-DlpComplianceRule -Identity $DlpRuleName @ruleParams | Out-Null
    Write-Host "DLP rule updated." -ForegroundColor Green
}

# -----------------------------------------------------------------------------
# Verification
# -----------------------------------------------------------------------------

Write-Host "`nVerification:" -ForegroundColor Cyan
Get-DlpCompliancePolicy -Identity $DlpPolicyName | Format-List Name, Mode, EnforcementPlanes, Locations
Get-DlpComplianceRule   -Identity $DlpRuleName   | Format-List Name, Policy, RestrictAccess, ReportSeverityLevel

# -----------------------------------------------------------------------------
# Copy/paste output for this repository
# -----------------------------------------------------------------------------

Write-Host "`nCopy/paste these lines into your .env file:" -ForegroundColor Cyan
if (-not [string]::IsNullOrWhiteSpace($resolvedTenantId)) {
    Write-Host "ENTRA_TENANT_ID=$resolvedTenantId"
}
Write-Host "ENTRA_CLIENT_ID=$resolvedAppId"
Write-Host "PURVIEW_CLIENT_APP_ID=$resolvedAppId"
if (-not [string]::IsNullOrWhiteSpace($resolvedSecretText)) {
    Write-Host "ENTRA_CLIENT_SECRET=$resolvedSecretText"
}
else {
    Write-Host "ENTRA_CLIENT_SECRET=<set-your-existing-secret-here>"
}

Write-Host "`nDone. Next:" -ForegroundColor Green
Write-Host "1) Paste the values above into .env"
Write-Host "2) Set ENABLE_PURVIEW_POLICY_ENFORCEMENT=true"
Write-Host "3) Run python main.py"
Write-Host "4) Run python purview_test.py to verify BLOCKED behavior"

# -----------------------------------------------------------------------------
# Cleanup (optional)
# -----------------------------------------------------------------------------
# Remove-DlpComplianceRule   -Identity $DlpRuleName   -Confirm:$false
# Remove-DlpCompliancePolicy -Identity $DlpPolicyName -Confirm:$false
