# Lancé chaque jour à 7 h par le Planificateur de tâches. Journal : .runlogs\quotidien.log
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root
$logDir = Join-Path $Root ".runlogs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "quotidien.log"
if ((Test-Path -LiteralPath $log) -and ((Get-Item -LiteralPath $log).Length -gt 2000000)) {
    Move-Item -LiteralPath $log -Destination "$log.1" -Force
}

function Write-Log([string]$Message) {
    Add-Content -LiteralPath $log -Value $Message -Encoding UTF8
}

Write-Log "===== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ====="
$marker = Join-Path $Root ".python-veille"
$python = $null
if (Test-Path -LiteralPath $marker) {
    $python = (Get-Content -LiteralPath $marker -Raw).Trim().Trim([char]0xFEFF)
    if (-not (Test-Path -LiteralPath $python)) { $python = $null }
}
if ($python) {
    $reseau = $false
    for ($i = 0; $i -lt 30; $i++) {
        & $python -c "import socket,sys; s=socket.socket(); s.settimeout(5);`ntry:`n s.connect(('1.1.1.1',443))`nexcept OSError:`n sys.exit(1)`nfinally:`n s.close()"
        if ($LASTEXITCODE -eq 0) {
            $reseau = $true
            break
        }
        Start-Sleep -Seconds 10
    }
    if (-not $reseau) {
        Write-Log "Réseau encore indisponible, la veille démarre quand même."
    }
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "lancer.ps1") *>> $log
$code = $LASTEXITCODE
Write-Log "===== fin $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') code $code ====="
exit $code
