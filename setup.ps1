# One-time setup on Windows:  powershell -ExecutionPolicy Bypass -File setup.ps1
# Creates a standalone Python 3.12 env (uv-managed; NOT Anaconda, whose old msvcp140.dll crashes CTranslate2),
# installs the requirements, downloads the fonts and prints an environment report.
$ErrorActionPreference = 'Stop'
$Skill = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = if ($env:LECNOTES_VENV) { $env:LECNOTES_VENV } else { Join-Path $HOME '.lecnotes\venv' }
$Uv = if ($env:UV) { $env:UV } else { (Get-Command uv -ErrorAction SilentlyContinue).Source }
if (-not $Uv) {
    Write-Host 'uv is not installed. Install it (https://docs.astral.sh/uv/getting-started/installation/), then rerun:'
    Write-Host '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    exit 1
}
& $Uv python install 3.12
$Py = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path $Py)) { & $Uv venv --python 3.12 --python-preference only-managed --seed $Venv }
& $Uv pip install --python $Py -r (Join-Path $Skill 'requirements.txt')
& $Py (Join-Path $Skill 'scripts\fetch_fonts.py')
& $Py (Join-Path $Skill 'scripts\doctor.py')
Write-Host ''
Write-Host "Done. Python for this skill: $Py"
