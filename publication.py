"""Publication des rapports sur les pages perso Free (f4eed.free.fr)."""

from __future__ import annotations

import ftplib
import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import yaml

from veille import CONFIG, MOIS_FR, date_longue_fr

_ARCHIVE_NOM = re.compile(
    r"^(Veille_(?:Outils_PC|Blackout|Geomatique|Mesh|IOT|Crise|Radio))"
    r"_(\d{4})-(\d{2})-(\d{2})(?:_(\d{2})-(\d{2})-(\d{2}))?\.(pdf|html)$"
)
_ORDRE_VEILLES = (
    ("Veille_IOT", "iot"),
    ("Veille_Crise", "crise"),
    ("Veille_Radio", "radio"),
    ("Veille_Outils_PC", "outils"),
    ("Veille_Blackout", "blackout"),
    ("Veille_Geomatique", "geomatique"),
    ("Veille_Mesh", "mesh"),
)

THEMES_WEB = {
    "iot": ("#0f4c5c", "Objets connectés, LoRa, mesh et routes"),
    "crise": ("#7a1f1f", "Risques, alertes et gestion de crise"),
    "radio": ("#1e3a5f", "Radioamateur, modes digitaux et trafic"),
    "outils": ("#4a5c2a", "Outils de gestion de crise et poste de commandement"),
    "blackout": ("#5c3d12", "Black-out, réseau électrique et déclarations de l'exécutif"),
    "geomatique": ("#0d6e4f", "Géomatique, QGIS, cartographie et données géographiques"),
    "mesh": ("#1d4e89", "Réseaux mesh, Meshtastic, MeshCore et mesh Wi-Fi"),
}


def _charger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _pub_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    if cfg is None:
        cfg = _charger(CONFIG / "email.yaml")
        secrets = _charger(CONFIG / "email.secrets.yaml")
        mot = str(secrets.get("mot_de_passe") or "")
        smtp = dict(cfg.get("smtp") or {})
        smtp["mot_de_passe"] = mot
        cfg = dict(cfg)
        cfg["smtp"] = smtp
    pub = dict(cfg.get("publication") or {})
    smtp = cfg.get("smtp") or {}
    if not pub.get("utilisateur"):
        user = str(smtp.get("utilisateur") or cfg.get("expediteur") or "")
        pub["utilisateur"] = user.split("@", 1)[0]
    pub.setdefault("hote", "ftpperso.free.fr")
    pub.setdefault("dossier", "veille")
    pub.setdefault("url_base", "https://f4eed.pages-perso.free.fr")
    pub["mot_de_passe"] = str(smtp.get("mot_de_passe") or "")
    return pub


def url_publique(nom: str, cfg: dict[str, Any] | None = None) -> str:
    pub = _pub_cfg(cfg)
    base = str(pub.get("url_base") or "https://f4eed.free.fr").rstrip("/")
    dossier = str(pub.get("dossier") or "veille").strip("/")
    return f"{base}/{dossier}/{nom}" if dossier else f"{base}/{nom}"


def _connecter(pub: dict[str, Any]) -> ftplib.FTP:
    hote = str(pub.get("hote") or "ftpperso.free.fr")
    user = str(pub.get("utilisateur") or "").strip()
    mot = str(pub.get("mot_de_passe") or "").strip()
    if not user or not mot:
        raise RuntimeError("identifiants FTP pages perso manquants")
    ftp = ftplib.FTP()
    ftp.connect(hote, 21, timeout=30)
    ftp.login(user, mot)
    ftp.set_pasv(True)
    return ftp


def _envoyer_fichier(ftp: ftplib.FTP, local: Path, distant: str) -> None:
    with local.open("rb") as handle:
        ftp.storbinary(f"STOR {distant}", handle)


def _noms_rapports() -> dict[str, dict[str, str]]:
    chemin = CONFIG / "rapports_courants.yaml"
    if not chemin.exists():
        return {}
    data = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def memoriser_rapport(identifiant: str, pdf: Path, html: Path) -> None:
    """Retient le nom daté du dernier rapport, pour la page des résultats."""
    chemin = CONFIG / "rapports_courants.yaml"
    data = _noms_rapports()
    data[identifiant] = {"pdf": pdf.name, "html": html.name}
    chemin.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=True),
        encoding="utf-8",
    )


def _index_html() -> str:
    date_lue = date_longue_fr()
    genere = datetime.now().strftime("%d/%m/%Y à %H:%M")
    courants = _noms_rapports()
    cartes = [
        ("Veille_IOT", "iot", "Veille_IOT.pdf", "Veille_IOT.html"),
        ("Veille_Crise", "crise", "Veille_Crise.pdf", "Veille_Crise.html"),
        ("Veille_Radio", "radio", "Veille_Radio.pdf", "Veille_Radio.html"),
        ("Veille_Outils_PC", "outils", "Veille_Outils_PC.pdf", "Veille_Outils_PC.html"),
        ("Veille_Blackout", "blackout", "Veille_Blackout.pdf", "Veille_Blackout.html"),
        ("Veille_Geomatique", "geomatique", "Veille_Geomatique.pdf", "Veille_Geomatique.html"),
        ("Veille_Mesh", "mesh", "Veille_Mesh.pdf", "Veille_Mesh.html"),
    ]
    cartes = [
        (
            titre,
            cle,
            str((courants.get(cle) or {}).get("pdf") or pdf),
            str((courants.get(cle) or {}).get("html") or html),
        )
        for titre, cle, pdf, html in cartes
    ]
    blocs = []
    for titre, cle, pdf, html in cartes:
        couleur, accroche = THEMES_WEB[cle]
        blocs.append(
            f"""
<a class="carte" href="{escape(pdf)}" style="--accent:{couleur}">
<span class="pastille">PDF</span>
<strong>{escape(titre)}</strong>
<em>{escape(accroche)}</em>
<span class="lien">Ouvrir le rapport</span>
</a>
<p class="alt"><a href="{escape(html)}">lire dans le navigateur</a></p>
"""
        )
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache">
<title>Veilles — {escape(date_lue)}</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; }}
html {{ -webkit-text-size-adjust: 100%; }}
body {{
  margin: 0;
  font: 1rem/1.45 "Segoe UI", sans-serif;
  background: #f4f1ea;
  color: #1c1917;
  overflow-wrap: anywhere;
}}
header {{
  background: #1c1917;
  color: #fff;
  padding: max(1.25rem, env(safe-area-inset-top)) max(1rem, env(safe-area-inset-right)) 1.15rem max(1rem, env(safe-area-inset-left));
}}
h1 {{ margin: 0; font-size: clamp(1.45rem, 6vw, 2rem); line-height: 1.15; }}
header p {{ margin: .45rem 0 0; opacity: .85; font-size: clamp(.9rem, 3.4vw, 1rem); }}
.aide {{ margin: .7rem 0 0; font-size: 1rem; opacity: .9; }}
.aide a {{ color: #fff; display: inline-block; padding: .45rem 0; min-height: 44px; }}
main {{
  max-width: 40rem;
  margin: 0 auto;
  padding: 1rem max(1rem, env(safe-area-inset-right)) max(2rem, env(safe-area-inset-bottom)) max(1rem, env(safe-area-inset-left));
}}
.carte {{
  display: block;
  background: #fff;
  border-radius: 14px;
  padding: 1rem 1rem .85rem;
  text-decoration: none;
  color: inherit;
  border-left: 6px solid var(--accent);
  box-shadow: 0 6px 18px rgba(0,0,0,.06);
}}
.carte + .alt {{ margin: .1rem 0 1rem; }}
.pastille {{
  display: inline-block;
  background: var(--accent);
  color: #fff;
  border-radius: 999px;
  font-size: .72rem;
  letter-spacing: .06em;
  padding: .2rem .55rem;
  margin-bottom: .5rem;
}}
.carte strong {{ display: block; font-size: clamp(1.15rem, 4.8vw, 1.35rem); line-height: 1.2; }}
.carte em {{
  display: block;
  margin: .35rem 0 .65rem;
  color: #57534e;
  font-style: normal;
  font-size: .95rem;
}}
.lien {{ color: var(--accent); font-weight: 600; display: inline-block; padding: .2rem 0; }}
.alt a {{
  color: #57534e;
  font-size: .95rem;
  display: inline-block;
  padding: .65rem 0;
  min-height: 44px;
}}
@media (max-width: 420px) {{
  .carte {{ border-radius: 12px; border-left-width: 5px; padding: .9rem .85rem .75rem; }}
}}
</style>
</head>
<body>
<header>
<h1>Veilles du jour</h1>
<p>{escape(date_lue)} · mis à jour le {escape(genere)}</p>
<p class="aide"><a href="archives.html">Anciennes veilles</a></p>
</header>
<main>
{"".join(blocs)}
</main>
</body>
</html>
"""


def _libelle_archive(annee: str, mois: str, jour: str, heure: str, minute: str) -> str:
    moment = f"{int(jour)} {MOIS_FR[int(mois) - 1]} {annee}"
    if heure and minute:
        return f"{moment} à {heure}h{minute}"
    return moment


def _rapports_archives(noms: set[str] | None = None) -> dict[str, list[dict[str, str]]]:
    """Regroupe les rapports datés, du plus récent au plus ancien."""
    trouves: set[str] = set(noms or ())
    for chemin in CONFIG.parent.glob("Veille_*.*"):
        if chemin.suffix.lower() in {".pdf", ".html"}:
            trouves.add(chemin.name)
    groupes: dict[tuple[str, str], dict[str, str]] = {}
    for nom in trouves:
        match = _ARCHIVE_NOM.match(nom)
        if not match:
            continue
        titre, annee, mois, jour, heure, minute, seconde, ext = match.groups()
        fiche = groupes.setdefault(
            (titre, f"{annee}-{mois}-{jour}-{heure or '00'}-{minute or '00'}-{seconde or '00'}"),
            {
                "titre": titre,
                "quand": _libelle_archive(annee, mois, jour, heure or "", minute or ""),
                "tri": f"{annee}{mois}{jour}{heure or '00'}{minute or '00'}{seconde or '00'}",
            },
        )
        fiche[ext] = nom
    par_titre: dict[str, list[dict[str, str]]] = {}
    for fiche in groupes.values():
        par_titre.setdefault(fiche["titre"], []).append(fiche)
    for items in par_titre.values():
        items.sort(key=lambda item: item["tri"], reverse=True)
    return par_titre


def _archives_html(noms: set[str] | None = None) -> str:
    date_lue = date_longue_fr()
    par_titre = _rapports_archives(noms)
    blocs: list[str] = []
    for titre, cle in _ORDRE_VEILLES:
        couleur, accroche = THEMES_WEB[cle]
        items = par_titre.get(titre) or []
        if not items:
            continue
        lignes = []
        for item in items:
            liens = []
            if item.get("pdf"):
                liens.append(f'<a href="{escape(item["pdf"])}">PDF</a>')
            if item.get("html"):
                liens.append(f'<a href="{escape(item["html"])}">lire dans le navigateur</a>')
            lignes.append(
                f'<li><span>{escape(item["quand"])}</span> {" · ".join(liens)}</li>'
            )
        blocs.append(
            f"""
<section style="--accent:{couleur}">
<h2>{escape(titre)}</h2>
<p class="accroche">{escape(accroche)}</p>
<ul>
{"".join(lignes)}
</ul>
</section>
"""
        )
    contenu = "".join(blocs) or "<p>Aucune veille archivée pour le moment.</p>"
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache">
<title>Anciennes veilles — {escape(date_lue)}</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; }}
html {{ -webkit-text-size-adjust: 100%; }}
body {{
  margin: 0;
  font: 1rem/1.45 "Segoe UI", sans-serif;
  background: #f4f1ea;
  color: #1c1917;
  overflow-wrap: anywhere;
}}
header {{
  background: #1c1917;
  color: #fff;
  padding: max(1.25rem, env(safe-area-inset-top)) max(1rem, env(safe-area-inset-right)) 1.15rem max(1rem, env(safe-area-inset-left));
}}
header a {{ color: #fff; display: inline-block; padding: .45rem 0; min-height: 44px; }}
h1 {{ margin: 0; font-size: clamp(1.45rem, 6vw, 2rem); line-height: 1.15; }}
header p {{ margin: .45rem 0 0; opacity: .85; }}
main {{
  max-width: 40rem;
  margin: 0 auto;
  padding: 1rem max(1rem, env(safe-area-inset-right)) max(2rem, env(safe-area-inset-bottom)) max(1rem, env(safe-area-inset-left));
}}
section {{
  background: #fff;
  border-radius: 14px;
  border-left: 6px solid var(--accent);
  box-shadow: 0 6px 18px rgba(0,0,0,.06);
  padding: 1rem .95rem 1.05rem;
  margin: 0 0 1rem;
}}
h2 {{ margin: 0; font-size: clamp(1.1rem, 4.5vw, 1.25rem); }}
.accroche {{ margin: .25rem 0 .7rem; color: #57534e; font-size: .95rem; }}
ul {{ margin: 0; padding: 0; list-style: none; }}
li {{
  display: flex;
  flex-wrap: wrap;
  gap: .35rem .75rem;
  align-items: baseline;
  padding: .7rem 0;
  border-top: 1px solid #e7e5e4;
}}
li span {{ flex: 1 1 12rem; }}
li a {{ padding: .35rem 0; min-height: 44px; display: inline-flex; align-items: center; }}
a {{ color: var(--accent, #5c3d12); }}
</style>
</head>
<body>
<header>
<h1>Anciennes veilles</h1>
<p><a href="index.html">Retour aux veilles du jour</a></p>
</header>
<main>
{contenu}
</main>
</body>
</html>
"""


def _noms_distants(ftp: ftplib.FTP) -> set[str]:
    try:
        return {Path(nom).name for nom in ftp.nlst()}
    except ftplib.error_perm:
        return set()


def publier(fichiers: list[Path], cfg: dict[str, Any] | None = None) -> list[str]:
    """Envoie les fichiers dans /veille/ et met à jour la page d'accueil du dossier."""
    pub = _pub_cfg(cfg)
    dossier = str(pub.get("dossier") or "veille").strip("/")
    urls: list[str] = []
    ftp = _connecter(pub)
    try:
        if dossier:
            try:
                ftp.cwd(dossier)
            except ftplib.error_perm:
                ftp.mkd(dossier)
                ftp.cwd(dossier)
        for chemin in fichiers:
            if not chemin.exists():
                continue
            _envoyer_fichier(ftp, chemin, chemin.name)
            urls.append(url_publique(chemin.name, cfg))
        distants = _noms_distants(ftp)
        for chemin in sorted(CONFIG.parent.glob("Veille_*.*")):
            if chemin.suffix.lower() not in {".pdf", ".html"}:
                continue
            if not _ARCHIVE_NOM.match(chemin.name) or chemin.name in distants:
                continue
            _envoyer_fichier(ftp, chemin, chemin.name)
            distants.add(chemin.name)
            urls.append(url_publique(chemin.name, cfg))
        index = CONFIG.parent / ".index_veille.html"
        index.write_text(_index_html(), encoding="utf-8")
        _envoyer_fichier(ftp, index, "index.html")
        archives = CONFIG.parent / ".archives_veille.html"
        archives.write_text(_archives_html(distants), encoding="utf-8")
        _envoyer_fichier(ftp, archives, "archives.html")
        urls.append(url_publique("index.html", cfg).rsplit("/", 1)[0] + "/")
        urls.append(url_publique("archives.html", cfg))
    finally:
        try:
            ftp.quit()
        except Exception:  # noqa: BLE001
            ftp.close()
    return urls
