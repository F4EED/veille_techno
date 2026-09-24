#!/usr/bin/env bash
# Lancé chaque jour à 7 h par systemd ou cron. Journal : .runlogs/quotidien.log
set -u
cd "$(dirname "$0")"
mkdir -p .runlogs
LOG=".runlogs/quotidien.log"

if [[ -f "${LOG}" ]]; then
  taille="$(stat -c%s "${LOG}" 2>/dev/null || stat -f%z "${LOG}" 2>/dev/null || echo 0)"
  if [[ "${taille}" -gt 2000000 ]]; then
    mv "${LOG}" "${LOG}.1"
  fi
fi

attendre_reseau() {
  local i
  for i in $(seq 1 30); do
    if python3 -c 'import socket, sys
s = socket.socket()
s.settimeout(5)
try:
    s.connect(("1.1.1.1", 443))
except OSError:
    sys.exit(1)
finally:
    s.close()'; then
      return 0
    fi
    sleep 10
  done
  return 1
}

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="
  if ! attendre_reseau; then
    echo "Réseau encore indisponible, la veille démarre quand même."
  fi
  ./lancer.sh
  code=$?
  echo "===== fin $(date '+%Y-%m-%d %H:%M:%S') code ${code} ====="
  exit "${code}"
} >>"${LOG}" 2>&1
