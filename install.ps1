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

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Invoke-CheckedCommand "Installing backend Python dependencies" {
    pip install -r backend/requirements.txt
}

Invoke-CheckedCommand "Installing Playwright Chromium" {
    python -m playwright install chromium
}

Invoke-CheckedCommand "Installing frontend Node dependencies" {
    npm install --prefix frontend
}

Write-Host "Install complete."
