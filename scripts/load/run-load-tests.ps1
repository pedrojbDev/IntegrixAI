param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [string]$WebhookSecret,

    [string]$WebhookSecretHeader,

    [string]$ToNumber,

    [string]$SearchCpf,

    [string]$SearchEspecialidade,

    [string]$SearchCidade,

    # Legacy parameter accepted during migration but intentionally not sent to k6.
    [string]$SearchBairro,

    [switch]$RandomizeSearchArgs,

    [int]$ToolsTargetVus = 100,

    [ValidateSet("health", "tools", "idempotency", "all")]
    [string]$Mode = "tools",

    [switch]$AggressiveMode
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-K6Executable {
    $command = Get-Command k6 -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $fallbackPaths = @(
        "C:\Program Files\k6\k6.exe",
        "C:\Program Files (x86)\k6\k6.exe"
    )

    foreach ($path in $fallbackPaths) {
        if (Test-Path $path) {
            return $path
        }
    }

    return $null
}

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Key
    )

    $envFile = Join-Path (Resolve-Path (Join-Path $scriptRoot "..\\..")).Path ".env"
    if (-not (Test-Path $envFile)) {
        return $null
    }

    foreach ($line in Get-Content $envFile) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith("#")) {
            continue
        }

        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) {
            continue
        }

        if ($parts[0].Trim() -eq $Key) {
            return $parts[1].Trim().Trim("'`"")
        }
    }

    return $null
}

function Invoke-K6Script {
    param(
        [Parameter(Mandatory = $true)]
        [string]$K6Executable,

        [Parameter(Mandatory = $true)]
        [string]$ScriptPath
    )

    $k6Args = @(
        "run",
        "-e", "BASE_URL=$BaseUrl",
        "-e", "WEBHOOK_SECRET=$WebhookSecret",
        "-e", "WEBHOOK_SECRET_HEADER=$WebhookSecretHeader",
        "-e", "TO_NUMBER=$ToNumber",
        "-e", "TOOLS_TARGET_VUS=$ToolsTargetVus",
        "-e", "AGGRESSIVE_MODE=$(if ($AggressiveMode.IsPresent) { 'true' } else { 'false' })",
        "-e", "RANDOMIZE_SEARCH_ARGS=$(if ($RandomizeSearchArgs.IsPresent) { 'true' } else { 'false' })"
    )

    if ($SearchCpf) {
        $k6Args += @("-e", "SEARCH_CPF=$SearchCpf")
    }
    if ($SearchEspecialidade) {
        $k6Args += @("-e", "SEARCH_ESPECIALIDADE=$SearchEspecialidade")
    }
    if ($SearchCidade) {
        $k6Args += @("-e", "SEARCH_CIDADE=$SearchCidade")
    }
    $k6Args += $ScriptPath

    & $K6Executable @k6Args
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$k6Executable = Resolve-K6Executable
if (-not $k6Executable) {
    Write-Host "k6 nao encontrado."
    Write-Host "Instale com:"
    Write-Host "  winget install k6"
    exit 1
}

$webhookSecretSource = "parameter"
if (-not $PSBoundParameters.ContainsKey("WebhookSecret") -or -not $WebhookSecret) {
    $dotenvWebhookSecret = Get-DotEnvValue -Key "WEBHOOK_SECRET"
    if ($dotenvWebhookSecret) {
        $WebhookSecret = $dotenvWebhookSecret
        $webhookSecretSource = ".env"
    } elseif ($env:WEBHOOK_SECRET) {
        $WebhookSecret = $env:WEBHOOK_SECRET
        $webhookSecretSource = "environment"
    }
}

$webhookSecretHeaderSource = "parameter"
if (-not $PSBoundParameters.ContainsKey("WebhookSecretHeader") -or -not $WebhookSecretHeader) {
    $dotenvWebhookSecretHeader = Get-DotEnvValue -Key "WEBHOOK_SECRET_HEADER"
    if ($dotenvWebhookSecretHeader) {
        $WebhookSecretHeader = $dotenvWebhookSecretHeader
        $webhookSecretHeaderSource = ".env"
    } elseif ($env:WEBHOOK_SECRET_HEADER) {
        $WebhookSecretHeader = $env:WEBHOOK_SECRET_HEADER
        $webhookSecretHeaderSource = "environment"
    }
}

if (-not $WebhookSecretHeader) {
    $WebhookSecretHeader = "x-webhook-secret"
    $webhookSecretHeaderSource = "default"
}

if (-not $ToNumber) {
    $ToNumber = if ($env:TO_NUMBER) { $env:TO_NUMBER } else { Get-DotEnvValue -Key "TO_NUMBER" }
}

if (-not $ToNumber) {
    $ToNumber = "+5511999999999"
}

if (-not $WebhookSecret -and $Mode -ne "health") {
    Write-Host "WEBHOOK_SECRET nao informado e nao encontrado no ambiente ou no .env."
    Write-Host "Informe -WebhookSecret ou configure WEBHOOK_SECRET."
    exit 1
}

$secretLength = if ($WebhookSecret) { $WebhookSecret.Length } else { 0 }
Write-Host "k6 config: base_url=$BaseUrl mode=$Mode webhook_header=$WebhookSecretHeader webhook_header_source=$webhookSecretHeaderSource webhook_secret_length=$secretLength webhook_secret_source=$webhookSecretSource to_number=$ToNumber tools_target_vus=$ToolsTargetVus"

switch ($Mode) {
    "health" {
        Invoke-K6Script -K6Executable $k6Executable -ScriptPath (Join-Path $scriptRoot "load-health.js")
    }
    "tools" {
        Invoke-K6Script -K6Executable $k6Executable -ScriptPath (Join-Path $scriptRoot "load-tools.js")
    }
    "idempotency" {
        Invoke-K6Script -K6Executable $k6Executable -ScriptPath (Join-Path $scriptRoot "load-idempotency.js")
    }
    "all" {
        Invoke-K6Script -K6Executable $k6Executable -ScriptPath (Join-Path $scriptRoot "load-health.js")
        Invoke-K6Script -K6Executable $k6Executable -ScriptPath (Join-Path $scriptRoot "load-tools.js")
        Invoke-K6Script -K6Executable $k6Executable -ScriptPath (Join-Path $scriptRoot "load-idempotency.js")
    }
}
