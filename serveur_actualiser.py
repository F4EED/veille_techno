#!/usr/bin/env python3
"""Le bouton Actualiser relance les cinq veilles sur ce poste."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import yaml

HOTE = "127.0.0.1"
PORT = 8765
URL_ACTUALISER = f"http://{HOTE}:{PORT}/actualiser"

_verrou = threading.Lock()
_etat: dict[str, object] = {
    "running": False,
    "code": None,
    "lignes": [],
}


def url_accueil() -> str:
    chemin = ROOT / "config" / "email.yaml"
    cfg = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    pub = cfg.get("publication") or {}
    base = str(pub.get("url_base") or "https://f4eed.pages-perso.free.fr").rstrip("/")
    dossier = str(pub.get("dossier") or "veille").strip("/")
    return f"{base}/{dossier}/" if dossier else f"{base}/"


def _ajouter(ligne: str) -> None:
    with _verrou:
        lignes = _etat["lignes"]
        assert isinstance(lignes, list)
        lignes.append(ligne.rstrip())
        if len(lignes) > 30:
            del lignes[:-30]


def _lancer() -> None:
    code = 1
    try:
        proc = subprocess.Popen(
            [str(ROOT / "lancer.sh")],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for ligne in proc.stdout:
            if ligne.strip():
                _ajouter(ligne)
        code = proc.wait()
    except Exception as exc:  # noqa: BLE001
        _ajouter(f"Erreur : {exc}")
        code = 1
    with _verrou:
        _etat["running"] = False
        _etat["code"] = code
        if code == 0:
            _ajouter("Veilles terminées. Retour à la page des résultats…")
        else:
            _ajouter(f"Une veille a échoué (code {code}).")


def demarrer_si_besoin() -> None:
    with _verrou:
        if _etat["running"]:
            return
        _etat["running"] = True
        _etat["code"] = None
        _etat["lignes"] = ["Relance des cinq veilles (IoT, crise, radio, outils de PC, black-out)…"]
    threading.Thread(target=_lancer, name="veille-actualiser", daemon=True).start()


PAGE_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relance des veilles</title>
<style>
body { margin:0; font:18px/1.45 "Segoe UI", sans-serif; background:#f4f1ea; color:#1c1917; }
header { background:#1c1917; color:#fff; padding:2rem 1.25rem 1.5rem; }
header p { margin:.4rem 0 0; opacity:.85; }
main { max-width:720px; margin:0 auto; padding:1.5rem 1rem 3rem; }
pre { white-space:pre-wrap; background:#fff; border-radius:12px; padding:1rem 1.1rem; font-size:.82rem; line-height:1.4; }
a { color:#5c3d12; }
</style>
</head>
<body>
<header>
<h1>Relance des veilles</h1>
<p id="msg">Collecte en cours. Cette page se met à jour toute seule.</p>
</header>
<main>
<pre id="log"></pre>
</main>
<script>
const accueil = __ACCUEIL_JSON__;
async function tick() {
  let j;
  try {
    j = await (await fetch("/statut", {cache: "no-store"})).json();
  } catch (e) {
    document.getElementById("msg").textContent = "Le suivi de la relance est interrompu.";
    return;
  }
  document.getElementById("log").textContent = j.log || "";
  if (j.running) {
    setTimeout(tick, 2000);
    return;
  }
  if (j.code === 0) {
    document.getElementById("msg").textContent = "Veilles terminées. Retour aux résultats…";
    const u = new URL(j.url || accueil);
    u.searchParams.set("r", Date.now());
    setTimeout(() => location.replace(u), 1200);
    return;
  }
  document.getElementById("msg").textContent = "La relance ne s'est pas terminée correctement.";
}
tick();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        chemin = urlparse(self.path).path
        if chemin == "/sante":
            self._send(200, b"ok", "text/plain; charset=utf-8")
            return
        if chemin == "/statut":
            with _verrou:
                payload = {
                    "running": bool(_etat["running"]),
                    "code": _etat["code"],
                    "log": "\n".join(_etat["lignes"]) if isinstance(_etat["lignes"], list) else "",
                    "url": url_accueil(),
                }
            self._send(200, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        if chemin == "/actualiser":
            demarrer_si_besoin()
            page = PAGE_HTML.replace("__ACCUEIL_JSON__", json.dumps(url_accueil()))
            self._send(200, page.encode(), "text/html; charset=utf-8")
            return
        self._send(404, "Introuvable.".encode(), "text/plain; charset=utf-8")


def main() -> None:
    serveur = ThreadingHTTPServer((HOTE, PORT), Handler)
    print(f"Bouton Actualiser : {URL_ACTUALISER}", flush=True)
    serveur.serve_forever()


if __name__ == "__main__":
    main()
