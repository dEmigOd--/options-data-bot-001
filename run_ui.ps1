# Run the SPX options UI (no pip install -e required).
# From project root: .\run_ui.ps1
# Prerequisite: pip install -r requirements.txt (in the same venv).
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$env:PYTHONPATH = Join-Path $root "src"
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Virtual environment not found. Run: python -m venv .venv"
    exit 1
}
& $py -c "import dotenv" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Dependencies missing. Run: .\.venv\Scripts\pip.exe install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}
& $py -m spx_options.ui.main @args
