# Lance une ou les sept veilles. Installation et envoi à 7 h : installer-windows.bat
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root
if (-not $Arguments) { $Arguments = @() }

function Test-Python38([string]$Exe) {
    & $Exe -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)"
    return $LASTEXITCODE -eq 0
}

function Get-PythonVeille {
    $marker = Join-Path $Root ".python-veille"
    if (Test-Path -LiteralPath $marker) {
        $exe = (Get-Content -LiteralPath $marker -Raw).Trim().Trim([char]0xFEFF)
        if ($exe -and (Test-Path -LiteralPath $exe) -and (Test-Python38 $exe)) {
            return $exe
        }
    }
    foreach ($name in @("py", "python", "python3")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        if ($name -eq "py") {
            $exe = (& py -3 -c "import sys; print(sys.executable)" 2>$null)
            if ($LASTEXITCODE -eq 0 -and $exe -and (Test-Python38 $exe.Trim())) {
                return $exe.Trim()
            }
            continue
        }
        if (Test-Python38 $cmd.Source) { return $cmd.Source }
    }
    $motifs = @(
        "C:\Program Files\Python*",
        "C:\Python*",
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python*")
    )
    $racines = @()
    foreach ($motif in $motifs) {
        foreach ($dossier in @(Get-ChildItem -Path $motif -Directory -ErrorAction SilentlyContinue)) {
            $racines += $dossier.FullName
        }
    }
    foreach ($racine in $racines) {
        $exe = Join-Path $racine "python.exe"
        if ((Test-Path -LiteralPath $exe) -and (Test-Python38 $exe)) { return $exe }
    }
    throw "Python 3.8 ou plus récent est introuvable. Lancez installer-windows.bat."
}

$python = Get-PythonVeille
$vendor = Join-Path $Root ".vendor"
if (-not (Test-Path -LiteralPath (Join-Path $vendor "feedparser")) -or -not (Test-Path -LiteralPath (Join-Path $vendor "fpdf"))) {
    & $python -m pip install --disable-pip-version-check --target $vendor -r (Join-Path $Root "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        & $python -m pip install --disable-pip-version-check --target $vendor --break-system-packages -r (Join-Path $Root "requirements.txt")
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}

if ($Arguments.Count -ge 1 -and $Arguments[0] -eq "--profil") {
    & $python -u (Join-Path $Root "veille.py") @Arguments
    exit $LASTEXITCODE
}

$profils = @("iot", "crise", "radio", "outils", "blackout", "geomatique", "mesh")
Write-Host "Lancement de Veille_IOT, Veille_Crise, Veille_Radio, Veille_Outils_PC, Veille_Blackout, Veille_Geomatique et Veille_Mesh en parallèle…"
$procs = @()
foreach ($profil in $profils) {
    $argList = @("-u", (Join-Path $Root "veille.py"), "--profil", $profil) + $Arguments
    $procs += Start-Process -FilePath $python -ArgumentList $argList -WorkingDirectory $Root -PassThru -NoNewWindow
}
$code = 0
for ($i = 0; $i -lt $procs.Count; $i++) {
    $procs[$i].WaitForExit()
    if ($procs[$i].ExitCode -ne 0) {
        Write-Host "La veille $($profils[$i]) a échoué."
        $code = 1
    }
}
exit $code
