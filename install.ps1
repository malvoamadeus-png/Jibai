param(
    [string] $VenvDir = ".venv"
)

$ErrorActionPreference = "Stop"

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Label,
        [Parameter(Mandatory = $true)]
        [scriptblock] $Command
    )

    Write-Host "==> $Label"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

function Get-SupportedPython {
    $candidates = @(
        @{ Label = "py -3.13"; Command = "py"; Arguments = @("-3.13") },
        @{ Label = "py -3.12"; Command = "py"; Arguments = @("-3.12") },
        @{ Label = "py -3.11"; Command = "py"; Arguments = @("-3.11") },
        @{ Label = "python"; Command = "python"; Arguments = @() }
    )

    foreach ($candidate in $candidates) {
        $commandInfo = Get-Command $candidate.Command -ErrorAction SilentlyContinue
        if (-not $commandInfo) {
            continue
        }

        try {
            $versionText = & $candidate.Command @($candidate.Arguments) -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
            if ($LASTEXITCODE -ne 0) {
                continue
            }

            $parts = "$versionText".Trim().Split(".")
            if ($parts.Length -lt 2) {
                continue
            }

            $major = [int] $parts[0]
            $minor = [int] $parts[1]
            if ($major -ne 3) {
                continue
            }
            if ($minor -lt 11 -or $minor -ge 14) {
                continue
            }

            return $candidate
        } catch {
            continue
        }
    }

    throw "Could not find a supported Python interpreter. Install Python 3.11, 3.12, or 3.13 and ensure 'py' or 'python' is available."
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPath = Join-Path $Root $VenvDir
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$NpmCommand = Get-Command "npm.cmd" -ErrorAction SilentlyContinue

if (-not $NpmCommand) {
    throw "npm.cmd was not found. Install Node.js and ensure npm.cmd is on PATH."
}

Set-Location $Root

if (-not (Test-Path $VenvPython)) {
    $pythonLauncher = Get-SupportedPython
    Invoke-CheckedCommand "Creating project virtualenv with $($pythonLauncher.Label)" {
        & $pythonLauncher.Command @($pythonLauncher.Arguments) -m venv $VenvPath
    }
}

Invoke-CheckedCommand "Upgrading pip in $VenvDir" {
    & $VenvPython -m pip install --upgrade pip
}

Invoke-CheckedCommand "Installing backend Python dev dependencies into $VenvDir" {
    & $VenvPython -m pip install -r backend/requirements-dev.txt
}

Invoke-CheckedCommand "Installing Playwright Chromium into $VenvDir" {
    & $VenvPython -m playwright install chromium
}

Invoke-CheckedCommand "Installing public-web Node dependencies with npm.cmd" {
    & $NpmCommand.Source install --prefix public-web
}

if (Test-Path (Join-Path $Root "frontend\package.json")) {
    Invoke-CheckedCommand "Installing frontend Node dependencies with npm.cmd" {
        & $NpmCommand.Source install --prefix frontend
    }
}

Write-Host ""
Write-Host "Install complete."
Write-Host "Next steps:"
Write-Host "  .\dev.cmd check"
Write-Host "  .\dev.cmd public-web run dev"
Write-Host "  .\dev.cmd pytest tests\test_crypto_pipeline.py -q"
