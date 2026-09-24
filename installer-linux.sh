#!/usr/bin/env bash
# Installe la veille sur un PC Linux et l'envoie chaque jour à 7 h 00.
# Usage, depuis ce dossier : ./installer-linux.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

if [[ "${EUID}" -eq 0 && -z "${SUDO_USER:-}" ]]; then
  echo "Lancez ./installer-linux.sh avec le compte du PC. Le script demandera sudo pour les paquets."
  exit 1
fi

RUN_USER="${SUDO_USER:-$(id -un)}"
RUN_GROUP="$(id -gn "${RUN_USER}")"
LIBERATION_URL="https://github.com/liberationfonts/liberation-fonts/files/7261482/liberation-fonts-ttf-2.1.5.tar.gz"
LIBERATION_SHA256="7191c669bf38899f73a2094ed00f7b800553364f90e2637010a69c0e268f25d0"
POLICES=(
  LiberationSans-Regular.ttf
  LiberationSans-Bold.ttf
  LiberationSans-Italic.ttf
)

as_user() {
  if [[ "$(id -un)" == "${RUN_USER}" ]]; then
    "$@"
  else
    sudo -u "${RUN_USER}" -H -- "$@"
  fi
}

need_sudo() {
  if [[ "$(id -un)" == "root" ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

python_ok() {
  command -v python3 >/dev/null 2>&1 || return 1
  python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)'
}

installer_paquets() {
  echo "Installation de Python, pip et des polices…"
  if command -v apt-get >/dev/null 2>&1; then
    need_sudo apt-get update
    need_sudo apt-get install -y python3 python3-pip ca-certificates curl tar fonts-liberation
  elif command -v dnf >/dev/null 2>&1; then
    need_sudo dnf install -y python3 python3-pip ca-certificates curl tar liberation-sans-fonts
  elif command -v pacman >/dev/null 2>&1; then
    need_sudo pacman -Sy --needed --noconfirm python python-pip ca-certificates curl tar ttf-liberation
  elif command -v zypper >/dev/null 2>&1; then
    need_sudo zypper --non-interactive install python3 python3-pip ca-certificates curl tar liberation-fonts
  else
    echo "Gestionnaire de paquets non reconnu."
    echo "Installez Python 3.8 ou plus récent, pip, curl et tar, puis relancez ce script."
    exit 1
  fi
}

polices_locales() {
  local nom
  for nom in "${POLICES[@]}"; do
    [[ -f "${ROOT}/fonts/${nom}" ]] || return 1
  done
}

copier_polices_systeme() {
  local dossier nom
  local dossiers=(
    /usr/share/fonts/truetype/liberation
    /usr/share/fonts/liberation
    /usr/share/fonts/liberation-sans
    /usr/share/fonts/TTF
  )
  for dossier in "${dossiers[@]}"; do
    [[ -d "${dossier}" ]] || continue
    local complet=1
    for nom in "${POLICES[@]}"; do
      [[ -f "${dossier}/${nom}" ]] || complet=0
    done
    if [[ "${complet}" -eq 1 ]]; then
      mkdir -p "${ROOT}/fonts"
      for nom in "${POLICES[@]}"; do
        cp -f "${dossier}/${nom}" "${ROOT}/fonts/${nom}"
      done
      return 0
    fi
  done
  return 1
}

telecharger_polices() {
  echo "Téléchargement de la police Liberation Sans…"
  local tmp archive
  tmp="$(mktemp -d)"
  archive="${tmp}/liberation.tgz"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "${archive}" "${LIBERATION_URL}"
  else
    wget -O "${archive}" "${LIBERATION_URL}"
  fi
  python3 - "${archive}" "${LIBERATION_SHA256}" <<'PY'
import hashlib
import sys

chemin, attendu = sys.argv[1], sys.argv[2]
empreinte = hashlib.sha256(open(chemin, "rb").read()).hexdigest()
if empreinte != attendu:
    raise SystemExit("Archive de polices inattendue.")
PY
  tar -xzf "${archive}" -C "${tmp}"
  mkdir -p "${ROOT}/fonts"
  local nom trouve
  for nom in "${POLICES[@]}"; do
    trouve="$(find "${tmp}" -name "${nom}" -type f -print -quit)"
    if [[ -z "${trouve}" ]]; then
      echo "Fichier ${nom} absent de l'archive." >&2
      rm -rf "${tmp}"
      return 1
    fi
    cp -f "${trouve}" "${ROOT}/fonts/${nom}"
  done
  rm -rf "${tmp}"
}

assurer_polices() {
  polices_locales && return 0
  copier_polices_systeme && return 0
  telecharger_polices
}

installer_python_libs() {
  echo "Installation des bibliothèques Python dans .vendor…"
  if ! as_user env PIP_BREAK_SYSTEM_PACKAGES=1 python3 -m pip install --disable-pip-version-check --upgrade --target "${ROOT}/.vendor" -r "${ROOT}/requirements.txt"; then
    as_user env PIP_BREAK_SYSTEM_PACKAGES=1 python3 -m pip install --disable-pip-version-check --upgrade --target "${ROOT}/.vendor" --break-system-packages -r "${ROOT}/requirements.txt"
  fi
}

demander_mot_de_passe() {
  as_user env PYTHONPATH="${ROOT}/.vendor" python3 - <<'PY'
import sys
from pathlib import Path

import yaml

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
    print("Mot de passe SMTP déjà renseigné.")
    raise SystemExit(0)

email = yaml.safe_load((root / "config" / "email.yaml").read_text(encoding="utf-8")) or {}
smtp = email.get("smtp") or {}
utilisateur = smtp.get("utilisateur") or email.get("expediteur") or "la boîte"
hote = smtp.get("hote") or "SMTP"
print(f"Mot de passe de {utilisateur} ({hote}).")
print("Il sert à envoyer les veilles. Entrée vide : les rapports seront créés, sans e-mail.")
if not sys.stdin.isatty():
    print(f"Éditez {secrets} avant 7 h.")
    raise SystemExit(0)

import getpass

mot = getpass.getpass("Mot de passe SMTP : ")
data["mot_de_passe"] = mot
secrets.write_text(
    yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
    encoding="utf-8",
)
secrets.chmod(0o600)
if mot.strip():
    print(f"Mot de passe enregistré dans {secrets.name}.")
else:
    print("Aucun mot de passe enregistré.")
PY
}

empecher_veille() {
  echo "Désactivation de la mise en veille (le PC reste allumé)."
  need_sudo mkdir -p /etc/systemd/sleep.conf.d
  need_sudo tee /etc/systemd/sleep.conf.d/veille-techno.conf >/dev/null <<'EOF'
[Sleep]
AllowSuspend=no
AllowHibernation=no
AllowSuspendThenHibernate=no
AllowHybridSleep=no
EOF
}

planifier_systemd() {
  local service="/etc/systemd/system/veille-techno.service"
  local timer="/etc/systemd/system/veille-techno.timer"
  echo "Programmation systemd : tous les jours à 7 h 00."
  need_sudo tee "${service}" >/dev/null <<EOF
[Unit]
Description=Veille techno (collecte, PDF, e-mail, publication)
After=network.target

[Service]
Type=oneshot
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory="${ROOT}"
ExecStart="${ROOT}/lancer-planifie.sh"
TimeoutStartSec=3h
Nice=10
EOF
  need_sudo tee "${timer}" >/dev/null <<'EOF'
[Unit]
Description=Veille techno chaque jour à 7 h 00

[Timer]
OnCalendar=*-*-* 07:00:00
AccuracySec=1min
Persistent=true
Unit=veille-techno.service

[Install]
WantedBy=timers.target
EOF
  need_sudo systemctl daemon-reload
  # Le tampon « déjà exécuté » évite un envoi pendant l'installation.
  # S'il manque, un minuteur persistant rattrape la veille dès qu'il est activé après 7 h.
  need_sudo python3 - <<'PY'
import struct
import time
from pathlib import Path

dossier = Path("/var/lib/systemd/timers")
dossier.mkdir(parents=True, exist_ok=True)
(dossier / "stamp-veille-techno.timer").write_bytes(
    struct.pack("<Q", int(time.time() * 1_000_000))
)
PY
  need_sudo systemctl enable --now veille-techno.timer
  need_sudo systemctl list-timers veille-techno.timer --no-pager || true
}

planifier_cron() {
  echo "systemd est absent. Programmation cron : tous les jours à 7 h 00."
  local tmp nouveau
  tmp="$(mktemp)"
  nouveau="$(mktemp)"
  as_user crontab -l >"${tmp}" 2>/dev/null || true
  grep -v "veille-techno-quotidien" "${tmp}" >"${nouveau}" || true
  echo "0 7 * * * \"${ROOT}/lancer-planifie.sh\" # veille-techno-quotidien" >>"${nouveau}"
  as_user crontab - <"${nouveau}"
  rm -f "${tmp}" "${nouveau}"
}

if ! python_ok || ! python3 -m pip --version >/dev/null 2>&1; then
  installer_paquets
fi
if ! python_ok; then
  echo "Python 3.8 ou plus récent est introuvable après l'installation des paquets."
  exit 1
fi

chmod +x "${ROOT}/lancer.sh" "${ROOT}/lancer-planifie.sh" "${ROOT}/installer-linux.sh"
mkdir -p "${ROOT}/.runlogs" "${ROOT}/fonts"
assurer_polices
installer_python_libs
demander_mot_de_passe

if [[ "$(id -un)" != "${RUN_USER}" ]]; then
  need_sudo chown -R "${RUN_USER}:${RUN_GROUP}" "${ROOT}/fonts" "${ROOT}/.vendor" "${ROOT}/.runlogs"
  if [[ -f "${ROOT}/config/email.secrets.yaml" ]]; then
    need_sudo chown "${RUN_USER}:${RUN_GROUP}" "${ROOT}/config/email.secrets.yaml"
  fi
fi

if command -v systemctl >/dev/null 2>&1 && [[ "$(ps -p 1 -o comm=)" == "systemd" ]]; then
  empecher_veille
  planifier_systemd
else
  echo "Sans systemd, la mise en veille du PC n'a pas été modifiée. Laissez-le allumé."
  planifier_cron
fi

echo
echo "La veille est installée sur ce PC."
echo "Envoi : tous les jours à 7 h 00 (heure affichée par le PC)."
if command -v timedatectl >/dev/null 2>&1; then
  timedatectl | awk '/Time zone|Local time/ { print }'
fi
echo "Si le PC était éteint à 7 h, l'envoi part au démarrage suivant."
echo "Journal : ${ROOT}/.runlogs/quotidien.log"
echo "Essai immédiat : ./lancer.sh"
echo "Pour autoriser à nouveau la mise en veille : supprimez /etc/systemd/sleep.conf.d/veille-techno.conf"
