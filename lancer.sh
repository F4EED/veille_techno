#!/usr/bin/env bash
# Installation et envoi chaque jour à 7 h : ./installer-linux.sh
set -euo pipefail
cd "$(dirname "$0")"

VENDOR="$(pwd)/.vendor"
export PYTHONPATH="${VENDOR}${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -d "${VENDOR}/feedparser" ]] || [[ ! -d "${VENDOR}/fpdf" ]]; then
  python3 -m pip install --target "${VENDOR}" -r requirements.txt
fi

# Un seul profil : ./lancer.sh --profil iot
if [[ "${1:-}" == "--profil" ]]; then
  exec python3 -u veille.py "$@"
fi

echo "Lancement de Veille_IOT, Veille_Crise, Veille_Radio, Veille_Outils_PC, Veille_Blackout, Veille_Geomatique et Veille_Mesh en parallèle…"
pids=()
profils=(iot crise radio outils blackout geomatique mesh)
for profil in "${profils[@]}"; do
  python3 -u veille.py --profil "${profil}" "$@" &
  pids+=("$!")
done

code=0
for i in "${!pids[@]}"; do
  if ! wait "${pids[$i]}"; then
    echo "La veille ${profils[$i]} a échoué." >&2
    code=1
  fi
done
exit "${code}"
