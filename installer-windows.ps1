# Installe la veille sur un PC Windows et l'envoie chaque jour à 7 h 00.
# Usage : double-clic sur installer-windows.bat, ou :
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer-windows.ps1
$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root
$LiberationUrl = "https://github.com/liberationfonts/liberation-fonts/files/7261482/liberation-fonts-ttf-2.1.5.tar.gz"
$LiberationSha = "7191c669bf38899f73a2094ed00f7b800553364f90e2637010a69c0e268f25d0"

function Test-Python38([string]$Exe) {
    & $Exe -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)"
    return $LASTEXITCODE -eq 0
}

function Find-PythonExe {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
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
    $racines = @()
    $motifs = @(
        "C:\Program Files\Python*",
        "C:\Python*",
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python*")
    )
    foreach ($motif in $motifs) {
        foreach ($dossier in @(Get-ChildItem -Path $motif -Directory -ErrorAction SilentlyContinue)) {
            $racines += $dossier.FullName
        }
    }
    foreach ($racine in $racines) {
        $exe = Join-Path $racine "python.exe"
        if ((Test-Path -LiteralPath $exe) -and (Test-Python38 $exe)) { return $exe }
    }
    return $null
}

function Install-PythonWinget {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { return $false }
    Write-Host "Installation de Python avec winget…"
    & winget install --id Python.Python.3.12 -e --scope user --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -eq 0) { return $true }
    # Déjà présent.
    if ($LASTEXITCODE -eq -1978335189) { return $true }
    return $false
}

function Get-PythonInstallerUrl {
    $arch = "amd64"
    if (-not [Environment]::Is64BitOperatingSystem) { $arch = "win32" }
    Write-Host "Recherche de l'installateur Python ($arch)…"
    $html = (Invoke-WebRequest -Uri "https://www.python.org/ftp/python/" -UseBasicParsing).Content
    $versions = [regex]::Matches($html, 'href="(3\.\d+\.\d+)/"') | ForEach-Object { $_.Groups[1].Value }
    $candidats = @()
    foreach ($v in $versions) {
        try {
            $num = [version]$v
        } catch {
            continue
        }
        if ($num.Major -ne 3 -or $num.Minor -lt 8) { continue }
        if ($arch -eq "win32" -and $num.Minor -gt 11) { continue }
        if ($num.Minor -gt 13) { continue }
        $candidats += $num
    }
    $candidats = $candidats | Sort-Object -Descending | Select-Object -First 6
    foreach ($num in $candidats) {
        $url = "https://www.python.org/ftp/python/$num/python-$num-$arch.exe"
        try {
            Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing | Out-Null
            return $url
        } catch {
            continue
        }
    }
    throw "Installateur Python introuvable sur python.org."
}

function Install-PythonTelecharge {
    $url = Get-PythonInstallerUrl
    $dest = Join-Path $env:TEMP "veille-python-setup.exe"
    Write-Host "Téléchargement de $url"
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    Write-Host "Installation de Python pour ce compte…"
    $proc = Start-Process -FilePath $dest -Wait -PassThru -ArgumentList @(
        "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_pip=1",
        "Include_test=0", "Include_doc=0", "Include_launcher=1", "Shortcuts=0"
    )
    if ($proc.ExitCode -ne 0) {
        throw "L'installateur Python s'est arrêté avec le code $($proc.ExitCode)."
    }
}

function Install-Polices([string]$Python) {
    $dossier = Join-Path $Root "fonts"
    New-Item -ItemType Directory -Force -Path $dossier | Out-Null
    $env:VEILLE_FONT_URL = $LiberationUrl
    $env:VEILLE_FONT_SHA = $LiberationSha
    $env:VEILLE_FONT_DIR = $dossier
    & $Python -c @'
import hashlib, os, tarfile, urllib.request
from pathlib import Path
dest = Path(os.environ["VEILLE_FONT_DIR"])
noms = ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf", "LiberationSans-Italic.ttf")
if all((dest / nom).is_file() for nom in noms):
    raise SystemExit(0)
archive = dest / "_liberation.tgz"
print("Téléchargement de la police Liberation Sans…")
urllib.request.urlretrieve(os.environ["VEILLE_FONT_URL"], archive)
empreinte = hashlib.sha256(archive.read_bytes()).hexdigest()
if empreinte != os.environ["VEILLE_FONT_SHA"]:
    raise SystemExit("Archive de polices inattendue.")
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        if not member.isfile():
            continue
        nom = Path(member.name).name
        if nom not in noms:
            continue
        source = tar.extractfile(member)
        (dest / nom).write_bytes(source.read())
archive.unlink(missing_ok=True)
manquants = [nom for nom in noms if not (dest / nom).is_file()]
if manquants:
    raise SystemExit("Polices manquantes : " + ", ".join(manquants))
'@
    Remove-Item Env:VEILLE_FONT_URL -ErrorAction SilentlyContinue
    Remove-Item Env:VEILLE_FONT_SHA -ErrorAction SilentlyContinue
    Remove-Item Env:VEILLE_FONT_DIR -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -ne 0) {
        $arial = Join-Path $env:WINDIR "Fonts\arial.ttf"
        if (Test-Path -LiteralPath $arial) {
            Write-Host "Liberation Sans indisponible. Les PDF utiliseront Arial."
            return
        }
        throw "Police PDF introuvable."
    }
}

function Install-Bibliotheques([string]$Python) {
    Write-Host "Installation des bibliothèques Python dans .vendor…"
    $vendor = Join-Path $Root ".vendor"
    $req = Join-Path $Root "requirements.txt"
    & $Python -m pip install --disable-pip-version-check --upgrade --target $vendor -r $req
    if ($LASTEXITCODE -ne 0) {
        & $Python -m pip install --disable-pip-version-check --upgrade --target $vendor --break-system-packages -r $req
        if ($LASTEXITCODE -ne 0) { throw "pip a échoué." }
    }
}

function ConvertFrom-SecurePlain([Security.SecureString]$Secure) {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

function Set-MotDePasseSmtp([string]$Python) {
    $env:PYTHONPATH = Join-Path $Root ".vendor"
    $etat = & $Python -c @'
import yaml
from pathlib import Path
root = Path(".").resolve()
secrets = root / "config" / "email.secrets.yaml"
exemple = root / "config" / "email.secrets.yaml.example"
if not secrets.exists() and exemple.exists():
    secrets.write_text(exemple.read_text(encoding="utf-8"), encoding="utf-8")
data = {}
if secrets.exists():
    charge = yaml.safe_load(secrets.read_text(encoding="utf-8")) or {}
    if isinstance(charge, dict):
        data = charge
if str(data.get("mot_de_passe") or "").strip():
    print("DEJA=1")
    raise SystemExit(0)
email = yaml.safe_load((root / "config" / "email.yaml").read_text(encoding="utf-8")) or {}
smtp = email.get("smtp") or {}
utilisateur = smtp.get("utilisateur") or email.get("expediteur") or "boite"
hote = smtp.get("hote") or "SMTP"
print("DEST=%s (%s)" % (utilisateur, hote))
'@
    if ($LASTEXITCODE -ne 0) { throw "Lecture de la configuration e-mail impossible." }
    if (($etat | Out-String) -match "DEJA=1") {
        Write-Host "Mot de passe SMTP déjà renseigné."
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
        return
    }
    $ligne = @($etat) | Where-Object { "$_" -like "DEST=*" } | Select-Object -First 1
    if (-not $ligne) { $ligne = "DEST=la boite (SMTP)" }
    Write-Host "Mot de passe de $($ligne.Substring(5))."
    Write-Host "Il sert à envoyer les veilles. Entrée vide : les rapports seront créés, sans e-mail."
    $secret = Read-Host "Mot de passe SMTP" -AsSecureString
    $env:VEILLE_SMTP_PASSWORD = ConvertFrom-SecurePlain $secret
    & $Python -c @'
import os
from pathlib import Path
import yaml
root = Path(".").resolve()
secrets = root / "config" / "email.secrets.yaml"
data = {}
if secrets.exists():
    charge = yaml.safe_load(secrets.read_text(encoding="utf-8")) or {}
    if isinstance(charge, dict):
        data = charge
data["mot_de_passe"] = os.environ.get("VEILLE_SMTP_PASSWORD") or ""
secrets.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
print("ENREGISTRE=1" if data["mot_de_passe"].strip() else "ENREGISTRE=0")
'@ | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Enregistrement du mot de passe SMTP impossible." }
    if ($env:VEILLE_SMTP_PASSWORD) {
        Write-Host "Mot de passe enregistré dans email.secrets.yaml."
    } else {
        Write-Host "Aucun mot de passe enregistré. Les rapports seront créés, sans e-mail."
    }
    Remove-Item Env:VEILLE_SMTP_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
}

function Disable-MiseEnVeille {
    Write-Host "Désactivation de la mise en veille (le PC reste allumé, l'écran peut s'éteindre)."
    $commandes = @(
        "powercfg /change standby-timeout-ac 0",
        "powercfg /change standby-timeout-dc 0",
        "powercfg /change hibernate-timeout-ac 0",
        "powercfg /change hibernate-timeout-dc 0",
        "powercfg /change monitor-timeout-ac 20",
        "powercfg /change monitor-timeout-dc 20"
    )
    $echec = $false
    foreach ($commande in $commandes) {
        cmd /c $commande | Out-Null
        if ($LASTEXITCODE -ne 0) { $echec = $true }
    }
    if (-not $echec) { return }
    Write-Host "Une autorisation administrateur est demandée pour empêcher la mise en veille."
    $script = Join-Path $env:TEMP "veille-empecher-sommeil.ps1"
    $corps = ($commandes | ForEach-Object { "cmd /c $_" }) -join "`r`n"
    Set-Content -LiteralPath $script -Value $corps -Encoding ASCII
    $eleve = Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -PassThru -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $script
    )
    if (-not $eleve -or $eleve.ExitCode -ne 0) {
        Write-Host "Mise en veille inchangée. Relancez installer-windows.bat avec un compte administrateur, ou laissez le PC réglé pour ne jamais dormir."
    }
}

function Register-TacheQuotidienne {
    $planifie = Join-Path $Root "lancer-planifie.ps1"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$planifie`"" -WorkingDirectory $Root
    $trigger = New-ScheduledTaskTrigger -Daily -At 7:00am
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Hours 3) -MultipleInstances IgnoreNew
    Write-Host "Mot de passe Windows de $env:USERNAME."
    Write-Host "Il permet l'envoi à 7 h même si la session est fermée. Entrée vide : la veille part seulement quand ce compte est ouvert."
    $secret = Read-Host "Mot de passe Windows" -AsSecureString
    $mot = ConvertFrom-SecurePlain $secret
    $nom = "Veille techno"
    try {
        $existant = Get-ScheduledTask -TaskName $nom -ErrorAction Stop
    } catch {
        $existant = $null
    }
    if ($existant) {
        Unregister-ScheduledTask -TaskName $nom -Confirm:$false
    }
    function Register-VeilleTache([object]$Reglages) {
        if ($mot) {
            Register-ScheduledTask -TaskName $nom -Action $action -Trigger $trigger -Settings $Reglages -User $env:USERNAME -Password $mot | Out-Null
        } else {
            $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
            Register-ScheduledTask -TaskName $nom -Action $action -Trigger $trigger -Settings $Reglages -Principal $principal | Out-Null
        }
    }
    try {
        Register-VeilleTache $settings
    } catch {
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3)
        Register-VeilleTache $settings
    }
    if (-not $mot) {
        Write-Host "La tâche partira quand la session $env:USERNAME est ouverte. Laissez ce compte connecté."
    }
    $mot = $null
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root ".runlogs") | Out-Null
$python = Find-PythonExe
if (-not $python) {
    if (-not (Install-PythonWinget)) {
        Install-PythonTelecharge
    }
    $python = Find-PythonExe
}
if (-not $python) {
    throw "Python 3.8 ou plus récent est introuvable après l'installation."
}
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText((Join-Path $Root ".python-veille"), $python, $utf8)
Write-Host "Python : $python"

Install-Polices $python
Install-Bibliotheques $python
Set-MotDePasseSmtp $python
Disable-MiseEnVeille
Register-TacheQuotidienne

Write-Host ""
Write-Host "La veille est installée sur ce PC."
Write-Host "Envoi : tous les jours à 7 h 00 (heure affichée par le PC : $(Get-Date -Format 'yyyy-MM-dd HH:mm') )."
Write-Host "Si le PC était éteint à 7 h, l'envoi part au prochain démarrage, une fois la session disponible."
Write-Host "Journal : $(Join-Path $Root '.runlogs\quotidien.log')"
Write-Host "Essai immédiat : lancer.bat"
Write-Host "Pour autoriser à nouveau la mise en veille : powercfg /change standby-timeout-ac 30"
