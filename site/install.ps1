$ErrorActionPreference = "Stop"

$DefaultVersion = "v0.5.0"
$Repository = "https://github.com/gabros20/project-context.git"
$Version = if ($env:PROJECT_CONTEXT_VERSION) { $env:PROJECT_CONTEXT_VERSION } else { $DefaultVersion }

$Git = Get-Command git -ErrorAction SilentlyContinue
$Python = Get-Command python3, python -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $Git) {
    throw "project-context requires Git."
}
if (-not $Python) {
    throw "project-context requires Python 3.10 or newer."
}

& $Python.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "project-context requires Python 3.10 or newer."
}

$InstallRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("project-context-" + [guid]::NewGuid().ToString("N"))
$Checkout = Join-Path $InstallRoot "project-context"

try {
    New-Item -ItemType Directory -Path $InstallRoot | Out-Null
    Write-Host "Installing project-context $Version..."
    & $Git.Source clone --quiet --depth 1 --branch $Version --single-branch $Repository $Checkout
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to download project-context $Version."
    }

    & $Python.Source (Join-Path $Checkout "scripts/install.py") install @args
    if ($LASTEXITCODE -ne 0) {
        throw "project-context installation failed."
    }

    Write-Host "project-context $Version installed. Run: ctx --help"
}
finally {
    if (Test-Path $InstallRoot) {
        Remove-Item -Recurse -Force $InstallRoot
    }
}
