"""Découverte automatique de nouvelles sources RSS à chaque lancement."""

from __future__ import annotations

import html as html_stdlib
import json
import re
import sys
import time
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import feedparser
import yaml

from veille import (
    CONFIG,
    FICHIER_SOURCES,
    Domaine,
    Source,
    Tendance,
    analyser_flux,
    extraire_resume,
    matcher,
    nettoyer_html,
    normaliser,
    telecharger,
)

FICHIER_DECOUVERTES = FICHIER_SOURCES
FICHIER_CACHE = CONFIG / "decouverte_cache.yaml"
ENTETE_CATALOGUE = """# Catalogue unique des sources. Les sept veilles le lisent.
# Une source ajoutée ici, à la main ou par la découverte, est vue par toutes.
# filtre: mots_cles → l'article reste s'il contient un mot-clé de la veille.
# filtre: aucun et profils → tous les articles pour les veilles listées ;
# les autres veilles ne gardent que les articles qui matchent leurs mots-clés.

"""
MAX_CANDIDATS = 20
MAX_NOUVELLES = 15
RETRY_ECHECS_JOURS = 14

HOTES_IGNORES = {
    "amazon.com",
    "apple.com",
    "bing.com",
    "doubleclick.net",
    "facebook.com",
    "feedspot.com",
    "feedly.com",
    "google.com",
    "instagram.com",
    "linkedin.com",
    "mastodon.social",
    "piaille.fr",
    "mamot.fr",
    "fosstodon.org",
    "infosec.exchange",
    "bsky.app",
    "threads.net",
    "microsoft.com",
    "news.google.com",
    "pinterest.com",
    "reddit.com",
    "rss.com",
    "rsscatalog.com",
    "t.co",
    "tiktok.com",
    "twitter.com",
    "wikipedia.org",
    "x.com",
    "youtube.com",
}

CHEMINS_RSS = (
    "/feed",
    "/feed/",
    "/rss",
    "/rss.xml",
    "/feed.xml",
    "/atom.xml",
    "/index.xml",
    "/blog/feed",
    "/blog/rss.xml",
)

LINK_RSS = re.compile(
    r"""<link\b[^>]*?(?:type=["']application/(?:rss|atom)\+xml["'][^>]*href=["']([^"']+)["']|href=["']([^"']+)["'][^>]*type=["']application/(?:rss|atom)\+xml["'])[^>]*?>""",
    re.IGNORECASE,
)

REQUETES_WEB = (
    'IoT "RSS" feed blog',
    "LoRaWAN RSS feed blog",
    "Meshtastic RSS feed blog",
    "Meshcore LoRa mesh RSS",
    '"industrie 4.0" OR IIoT RSS feed',
    '"météo routière" OR RWIS RSS',
    '"gestion routière" OR "main courante" RSS',
    '"gestion de crise" OR "radio professionnelle" TETRA RSS',
    'site:linkedin.com IoT LoRaWAN Meshtastic RSS',
    'site:x.com OR site:mastodon.social IoT LoRaWAN RSS',
)


def hote_url(url: str) -> str:
    hote = urllib.parse.urlparse(url).netloc.lower()
    if hote.startswith("www."):
        hote = hote[4:]
    return hote


def normaliser_url(url: str) -> str:
    parse = urllib.parse.urlparse(url.strip())
    hote = hote_url(url)
    chemin = parse.path.rstrip("/") or "/"
    return f"{parse.scheme or 'https'}://{hote}{chemin}".lower()


def slug_hote(hote: str) -> str:
    return "dec-" + re.sub(r"[^a-z0-9]+", "-", hote).strip("-")


def hote_interdit(hote: str) -> bool:
    return any(hote == bloque or hote.endswith("." + bloque) for bloque in HOTES_IGNORES)


def charger_optionnel(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def charger_sources_decouvertes(fichier: Path | None = None) -> list[Source]:
    cfg = charger_optionnel(fichier or FICHIER_DECOUVERTES)
    sources: list[Source] = []
    for item in cfg.get("flux") or []:
        sources.append(
            Source(
                identifiant=item["id"],
                nom=item["nom"],
                url=item["url"],
                site=item.get("site", ""),
                filtre=item.get("filtre", "mots_cles"),
                domaine=item.get("domaine", ""),
                profils=tuple(str(p) for p in (item.get("profils") or []) if str(p).strip()),
            )
        )
    return sources


def urls_connues(sources: list[Source]) -> set[str]:
    connues: set[str] = set()
    for source in sources:
        connues.add(normaliser_url(source.url))
        if source.site:
            connues.add(normaliser_url(source.site))
    return connues


def hotes_connus(sources: list[Source]) -> set[str]:
    return {hote_url(source.url) for source in sources if source.url} | {
        hote_url(source.site) for source in sources if source.site
    }


def hotes_en_echec(cache: dict[str, Any]) -> set[str]:
    limite = datetime.now(timezone.utc) - timedelta(days=RETRY_ECHECS_JOURS)
    ignores: set[str] = set()
    for hote, info in (cache.get("echecs") or {}).items():
        try:
            date = datetime.fromisoformat(str(info.get("date", "")))
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            if date >= limite:
                ignores.add(hote)
        except ValueError:
            ignores.add(hote)
    return ignores


def enregistrer_cache(cache: dict[str, Any], echecs: dict[str, str], fichier: Path | None = None) -> None:
    actuel = dict(cache.get("echecs") or {})
    maintenant = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for hote, motif in echecs.items():
        actuel[hote] = {"date": maintenant, "motif": motif}
    cible = fichier or FICHIER_CACHE
    cible.write_text(
        yaml.safe_dump({"echecs": actuel}, allow_unicode=True, sort_keys=True),
        encoding="utf-8",
    )


@contextmanager
def _verrou_catalogue():
    """Les sept veilles écrivent le même fichier en parallèle."""
    verrou = CONFIG / "sources.lock"
    with verrou.open("a+b") as handle:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0, 2)
            if handle.tell() < 1:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield
            finally:
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _ecrire_catalogue(cfg: dict[str, Any]) -> None:
    FICHIER_SOURCES.write_text(
        ENTETE_CATALOGUE + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False, width=10**9),
        encoding="utf-8",
    )


def _identifiants_catalogue(cfg: dict[str, Any]) -> set[str]:
    pris: set[str] = set()
    for cle in ("google_news", "flux", "wms"):
        for item in cfg.get(cle) or []:
            identifiant = str(item.get("id") or "")
            if identifiant:
                pris.add(identifiant)
    return pris


def enregistrer_flux(nouvelles: list[Source], cible: Path | None = None) -> None:
    del cible
    if not nouvelles:
        return
    with _verrou_catalogue():
        cfg = charger_optionnel(FICHIER_SOURCES)
        if not isinstance(cfg, dict):
            cfg = {}
        flux = list(cfg.get("flux") or [])
        existants = {normaliser_url(str(item.get("url") or "")) for item in flux}
        identifiants = _identifiants_catalogue(cfg)
        aujourd_hui = datetime.now().strftime("%Y-%m-%d")
        for source in nouvelles:
            if normaliser_url(source.url) in existants:
                continue
            identifiant = source.identifiant
            if identifiant in identifiants:
                numero = 2
                while f"{identifiant}-{numero}" in identifiants:
                    numero += 1
                identifiant = f"{identifiant}-{numero}"
            flux.append(
                {
                    "id": identifiant,
                    "nom": source.nom,
                    "url": source.url,
                    "site": source.site,
                    "filtre": "mots_cles",
                    "decouverte": aujourd_hui,
                }
            )
            existants.add(normaliser_url(source.url))
            identifiants.add(identifiant)
        cfg["flux"] = flux
        _ecrire_catalogue(cfg)


def enregistrer_decouvertes(nouvelles: list[Source], fichier: Path | None = None) -> None:
    del fichier
    enregistrer_flux(nouvelles)


def extraire_editeur(entree: Any) -> tuple[str, str]:
    source = entree.get("source")
    if source:
        href = str(source.get("href") or "").strip()
        titre = nettoyer_html(str(source.get("title") or ""))
        if href:
            return href, titre
    titre = nettoyer_html(entree.get("title") or "")
    if " - " in titre:
        return "", titre.rsplit(" - ", 1)[-1].strip()
    return "", ""


def flux_depuis_html(html_page: str, base: str) -> list[str]:
    trouves: list[str] = []
    for match in LINK_RSS.finditer(html_page):
        href = match.group(1) or match.group(2)
        if href:
            trouves.append(urllib.parse.urljoin(base, html_stdlib.unescape(href)))
    return trouves


def extraire_liens_ddg(html_page: str) -> list[str]:
    liens: list[str] = []
    for brut in re.findall(r'uddg=([^&"]+)', html_page):
        liens.append(urllib.parse.unquote(brut))
    for brut in re.findall(r'class="result__a"[^>]*href="([^"]+)"', html_page):
        if brut.startswith("http"):
            liens.append(brut)
    uniques: list[str] = []
    vus: set[str] = set()
    for lien in liens:
        if not lien.startswith("http"):
            continue
        cle = normaliser_url(lien)
        if cle in vus:
            continue
        vus.add(cle)
        uniques.append(lien)
    return uniques


def rechercher_web(requetes: tuple[str, ...] | None = None) -> list[tuple[str, str, int]]:
    compteur: Counter[str] = Counter()
    noms: dict[str, str] = {}
    for requete in requetes or REQUETES_WEB:
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": requete})
        try:
            page = telecharger(url, timeout=10).decode("utf-8", errors="ignore")
        except Exception:
            continue
        for lien in extraire_liens_ddg(page)[:8]:
            hote = hote_url(lien)
            if not hote or hote_interdit(hote):
                continue
            site = f"https://{hote}/"
            compteur[site] += 1
            noms.setdefault(site, hote)
    return [(site, noms[site], n) for site, n in compteur.most_common()]


def editeurs_google_news(sources: list[Source]) -> list[tuple[str, str, int]]:
    compteur: Counter[str] = Counter()
    noms: dict[str, str] = {}
    for source in sources:
        if not source.identifiant.startswith("gn-"):
            continue
        _src, entrees, erreur = analyser_flux(source)
        if erreur:
            continue
        for entree in entrees:
            href, nom = extraire_editeur(entree)
            if not href:
                continue
            hote = hote_url(href)
            if not hote or hote_interdit(hote):
                continue
            site = f"https://{hote}/"
            compteur[site] += 1
            noms.setdefault(site, nom or hote)
    return [(site, noms[site], n) for site, n in compteur.most_common()]


def candidats_flux(site: str) -> list[str]:
    base = site.rstrip("/")
    urls: list[str] = []
    try:
        page = telecharger(base, timeout=8).decode("utf-8", errors="ignore")
        urls.extend(flux_depuis_html(page, base + "/"))
    except Exception:
        pass
    if urls:
        uniques: list[str] = []
        vus: set[str] = set()
        for url in urls:
            cle = normaliser_url(url)
            if cle in vus:
                continue
            vus.add(cle)
            uniques.append(url)
        return uniques[:4]
    for chemin in CHEMINS_RSS:
        urls.append(base + chemin)
    uniques: list[str] = []
    vus: set[str] = set()
    for url in urls:
        cle = normaliser_url(url)
        if cle in vus:
            continue
        vus.add(cle)
        uniques.append(url)
    return uniques[:8]


def flux_pertinent(url: str, domaines: list[Domaine], tendances: list[Tendance]) -> tuple[bool, str]:
    try:
        brut = telecharger(url, timeout=8)
    except Exception:
        return False, ""
    flux = feedparser.parse(brut)
    if not getattr(flux, "entries", None):
        return False, ""
    nom = nettoyer_html(getattr(flux.feed, "title", "") or hote_url(url))
    textes = [nom]
    for entree in list(flux.entries)[:8]:
        textes.append(nettoyer_html(entree.get("title") or ""))
        textes.append(extraire_resume(entree))
    domaines_ok, _mots, _tendances = matcher(normaliser(" ".join(textes)), domaines, tendances)
    return bool(domaines_ok), nom or hote_url(url)


def tester_site(
    site: str,
    nom: str,
    identifiants: set[str],
    connues_urls: set[str],
    domaines: list[Domaine],
    tendances: list[Tendance],
) -> Source | None:
    hote = hote_url(site)
    for url in candidats_flux(site):
        if normaliser_url(url) in connues_urls:
            continue
        ok, nom_flux = flux_pertinent(url, domaines, tendances)
        if not ok:
            continue
        identifiant = slug_hote(hote)
        if identifiant in identifiants:
            identifiant = slug_hote(hote + "-rss")
        return Source(
            identifiant=identifiant,
            nom=nom or nom_flux or hote,
            url=url,
            site=site,
            filtre="mots_cles",
            nouvelle=True,
        )
    return None


def decouvrir_sources(
    sources: list[Source],
    domaines: list[Domaine],
    tendances: list[Tendance],
    fichier_decouvertes: Path | None = None,
    fichier_cache: Path | None = None,
    requetes_web: tuple[str, ...] | None = None,
    prefixe: str = "",
) -> list[Source]:
    etiquette = f"{prefixe} " if prefixe else ""
    print(f"{etiquette}Recherche de nouvelles sources…", flush=True)
    cache_path = fichier_cache or FICHIER_CACHE
    cache = charger_optionnel(cache_path)
    connus_hotes = hotes_connus(sources)
    connues_urls = urls_connues(sources)
    ignores = hotes_en_echec(cache)
    scores: Counter[str] = Counter()
    noms: dict[str, str] = {}

    for site, nom, n in editeurs_google_news(sources) + rechercher_web(requetes_web):
        hote = hote_url(site)
        if hote in connus_hotes or hote in ignores or hote_interdit(hote):
            continue
        scores[site] += n
        noms.setdefault(site, nom)

    classés = scores.most_common(MAX_CANDIDATS)
    print(f"{etiquette}  {len(classés)} site(s) candidat(s) à tester.", flush=True)

    identifiants = {s.identifiant for s in sources}
    nouvelles: list[Source] = []
    echecs: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futurs = {
            pool.submit(
                tester_site,
                site,
                noms.get(site, ""),
                identifiants,
                connues_urls,
                domaines,
                tendances,
            ): site
            for site, _score in classés
        }
        for futur in as_completed(futurs):
            site = futurs[futur]
            hote = hote_url(site)
            try:
                resultat = futur.result()
            except Exception as exc:  # noqa: BLE001
                echecs[hote] = str(exc)
                continue
            if resultat is None:
                echecs[hote] = "aucun flux RSS pertinent"
                continue
            if len(nouvelles) >= MAX_NOUVELLES:
                continue
            if resultat.identifiant in identifiants:
                continue
            nouvelles.append(resultat)
            identifiants.add(resultat.identifiant)
            connues_urls.add(normaliser_url(resultat.url))
            print(f"{etiquette}  + {resultat.nom} — {resultat.url}", flush=True)

    if echecs:
        enregistrer_cache(cache, echecs, cache_path)
    if nouvelles:
        enregistrer_decouvertes(nouvelles, fichier_decouvertes or FICHIER_DECOUVERTES)
        print(f"{etiquette}  {len(nouvelles)} nouvelle(s) source(s) intégrée(s).", flush=True)
    else:
        print(f"{etiquette}  Aucune nouvelle source pertinente.", flush=True)
    return nouvelles


FICHIER_WMS = FICHIER_SOURCES
MAX_SONDES_WMS = 16
MAX_NOUVEAUX_WMS = 8

REQUETES_WMS_DATAGOUV = (
    "format=wms&page_size=40&page=1&sort=-created",
    "format=wms&page_size=40&page=2&sort=-created",
    "format=wms&q=SDIS&page_size=20",
    "format=wms&q=lidar&page_size=20",
    "format=wms&q=orthophoto&page_size=20",
    "format=wms&q=cadastre&page_size=15",
)


def cle_wms(url: str) -> str:
    parse = urllib.parse.urlparse(url.strip())
    chemin = parse.path.rstrip("/")
    if chemin.lower().endswith("/ows"):
        chemin = chemin[:-4] + "/wms"
    return f"{parse.scheme or 'https'}://{hote_url(url)}{chemin}".lower()


def wms_connu(cle: str, connus: set[str]) -> bool:
    if cle in connus:
        return True
    if f"{cle}/wms" in connus:
        return True
    if cle.endswith("/wms") and cle[: -len("/wms")] in connus:
        return True
    return False


def url_capabilities(url: str) -> str:
    if "request=getcapabilities" in url.lower():
        return url
    separateur = "&" if "?" in url else "?"
    return f"{url}{separateur}SERVICE=WMS&REQUEST=GetCapabilities"


def charger_wms_decouverts(fichier: Path | None = None) -> list[Source]:
    cfg = charger_optionnel(fichier or FICHIER_WMS)
    services: list[Source] = []
    for item in cfg.get("wms") or []:
        adresse = str(item.get("url") or "").strip()
        if not adresse:
            continue
        services.append(
            Source(
                identifiant=str(item.get("id") or "wms"),
                nom=str(item.get("nom") or "WMS"),
                url=adresse,
                site=adresse,
                filtre="aucun",
                domaine="donnees",
            )
        )
    return services


def enregistrer_wms(nouvelles: list[Source], fichier: Path | None = None) -> None:
    del fichier
    if not nouvelles:
        return
    with _verrou_catalogue():
        cfg = charger_optionnel(FICHIER_SOURCES)
        if not isinstance(cfg, dict):
            cfg = {}
        flux = list(cfg.get("wms") or [])
        existants = {cle_wms(str(item.get("url") or "")) for item in flux}
        identifiants = _identifiants_catalogue(cfg)
        aujourd_hui = datetime.now().strftime("%Y-%m-%d")
        for source in nouvelles:
            cle = cle_wms(source.url)
            if cle in existants:
                continue
            identifiant = source.identifiant
            if identifiant in identifiants:
                numero = 2
                while f"{identifiant}-{numero}" in identifiants:
                    numero += 1
                identifiant = f"{identifiant}-{numero}"
            flux.append(
                {
                    "id": identifiant,
                    "nom": source.nom,
                    "url": source.url,
                    "site": source.site or source.url,
                    "decouverte": aujourd_hui,
                }
            )
            existants.add(cle)
            identifiants.add(identifiant)
        cfg["wms"] = flux
        _ecrire_catalogue(cfg)


def _url_ressemble_wms(url: str) -> bool:
    bas = url.lower()
    if not bas.startswith("http"):
        return False
    hote = hote_url(url)
    if not hote.endswith((".fr", ".eu", ".org", ".com")):
        return False
    if "rie.gouv.fr" in hote or "wmts" in bas or "service=wfs" in bas or "getfeature" in bas:
        return False
    if "map=" in urllib.parse.urlparse(url).query.lower():
        return False
    return any(morceau in bas for morceau in ("/wms", "service=wms", "wmsserver", "/ows", "/wxs", "geoserver"))


def candidats_wms_datagouv() -> list[str]:
    """Services WMS cités dans les jeux data.gouv.fr, dédoublonnés par hôte et chemin."""
    candidats: list[str] = []
    vus: set[str] = set()
    for requete in REQUETES_WMS_DATAGOUV:
        url = "https://www.data.gouv.fr/api/1/datasets/?" + requete
        try:
            donnees = json.loads(telecharger(url, timeout=15))
        except Exception:
            continue
        for jeu in donnees.get("data") or []:
            for ressource in jeu.get("resources") or []:
                adresse = str(ressource.get("url") or "").strip()
                format_res = str(ressource.get("format") or "").lower()
                if "wms" not in format_res and not _url_ressemble_wms(adresse):
                    continue
                if not _url_ressemble_wms(adresse):
                    continue
                cle = cle_wms(adresse)
                if cle in vus:
                    continue
                vus.add(cle)
                candidats.append(adresse.split("#", 1)[0])
    return candidats


def sonder_wms(url: str) -> tuple[bool, str, str]:
    """Retourne (ok, nom, url GetCapabilities)."""
    cible = url_capabilities(url)
    try:
        brut = telecharger(cible, timeout=12)
    except Exception:
        return False, "", cible
    texte = brut[:6000].decode("utf-8", "replace")
    bas = texte.lower()
    if "wms_capabilities" not in bas and "wmt_ms_capabilities" not in bas:
        return False, "", cible
    titre = re.search(r"<Title>([^<]{2,90})</Title>", texte, re.IGNORECASE)
    nom = nettoyer_html(titre.group(1)) if titre else hote_url(cible)
    return True, nom or hote_url(cible), cible


def decouvrir_wms(
    connus: list[Source],
    prefixe: str = "",
    fichier: Path | None = None,
) -> list[Source]:
    """Cherche de nouveaux services WMS et les enregistre."""
    etiquette = f"{prefixe} " if prefixe else ""
    print(f"{etiquette}Recherche de nouveaux flux WMS…", flush=True)
    connus_cles = {cle_wms(service.url) for service in connus if service.url}
    identifiants = {service.identifiant for service in connus}
    candidats = [
        candidat
        for candidat in candidats_wms_datagouv()
        if not wms_connu(cle_wms(candidat), connus_cles)
    ][:MAX_SONDES_WMS]
    print(f"{etiquette}  {len(candidats)} adresse(s) WMS à vérifier.", flush=True)

    nouvelles: list[Source] = []
    for candidat in candidats:
        if len(nouvelles) >= MAX_NOUVEAUX_WMS:
            break
        ok, nom, cible = sonder_wms(candidat)
        if not ok:
            continue
        cle = cle_wms(cible)
        if wms_connu(cle, connus_cles):
            continue
        identifiant = "wms-dec-" + re.sub(r"[^a-z0-9]+", "-", cle.split("://", 1)[-1]).strip("-")[:48]
        if identifiant in identifiants:
            continue
        libelle = nom
        if any(service.nom == f"WMS — {libelle}" for service in (*connus, *nouvelles)):
            segment = urllib.parse.urlparse(cible).path.rstrip("/").rsplit("/", 2)
            precision = segment[-2] if len(segment) >= 2 else hote_url(cible)
            libelle = f"{nom} ({precision})"
        service = Source(
            identifiant=identifiant,
            nom=f"WMS — {libelle}",
            url=cible,
            site=cible,
            filtre="aucun",
            domaine="donnees",
            nouvelle=True,
        )
        nouvelles.append(service)
        identifiants.add(identifiant)
        connus_cles.add(cle)
        print(f"{etiquette}  + {service.nom} — {service.url}", flush=True)

    if nouvelles:
        enregistrer_wms(nouvelles, fichier or FICHIER_WMS)
        print(f"{etiquette}  {len(nouvelles)} nouveau(x) flux WMS intégré(s).", flush=True)
    else:
        print(f"{etiquette}  Aucun nouveau flux WMS.", flush=True)
    return nouvelles
