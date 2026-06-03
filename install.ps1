param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$SetupArgs
)

$ErrorActionPreference = "Stop"

Write-Host "Installing repowire from RepowirePlus..."
Write-Host ""

$GitUrl = if ($env:REPOWIREPLUS_GIT_URL) { $env:REPOWIREPLUS_GIT_URL } else { "git+https://github.com/ROHITHGMURALI/repowireplus.git" }
$ScriptPath = $MyInvocation.MyCommand.Path
$SourcePath = if ($ScriptPath) { Split-Path -Parent $ScriptPath } else { $null }
$InstallTarget = if ($SourcePath -and (Test-Path (Join-Path $SourcePath "pyproject.toml"))) { $SourcePath } else { $GitUrl }

function Find-Python {
    $candidates = @("python", "py")
    foreach ($cmd in $candidates) {
        $resolved = Get-Command $cmd -ErrorAction SilentlyContinue
        if (-not $resolved) { continue }
        try {
            $version = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
            $parts = $version.Split(".")
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 10) {
                return $cmd
            }
        } catch {
            continue
        }
    }
    return $null
}

$python = Find-Python
if (-not $python) {
    Write-Error "Python 3.10+ is required. Install from https://python.org or winget install Python.Python.3.12"
}
Write-Host "Found Python via $python"

if (-not (Get-Command tmux -ErrorAction SilentlyContinue) -and -not (Get-Command psmux -ErrorAction SilentlyContinue)) {
    Write-Host "Warning: psmux/tmux alias not found. Spawn and pane injection require psmux on native Windows."
    Write-Host "  Install: winget install psmux"
}

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "Installing via uv from $InstallTarget..."
    uv tool install $InstallTarget --force
} elseif (Get-Command pipx -ErrorAction SilentlyContinue) {
    Write-Host "Installing via pipx from $InstallTarget..."
    pipx install $InstallTarget --force
} else {
    Write-Host "Installing via pip from $InstallTarget..."
    & $python -m pip install --user -U $InstallTarget
}

if (Get-Command repowire -ErrorAction SilentlyContinue) {
    Write-Host ""
    repowire --version
    Write-Host ""
    Write-Host "Running setup..."
    repowire setup @SetupArgs
} else {
    Write-Host "repowire installed but is not on PATH. Add the Python user scripts directory to PATH, then run: repowire setup"
}
