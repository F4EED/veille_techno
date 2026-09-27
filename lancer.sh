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

echo "Lancement de Veille_IOT, Veille_Crise, Veille_Radio, Veille_Outils_PC, Veille_Blackout, Veille_Geomatique et Veille_Mesh, une par une…"
profils=(iot crise radio outils blackout geomatique mesh)
code=0
for profil in "${profils[@]}"; do
  echo "===== profil ${profil} ====="
  if ! python3 -u veille.py --profil "${profil}" "$@"; then
    echo "La veille ${profil} a échoué." >&2
    code=1
  fi
done
exit "${code}"
