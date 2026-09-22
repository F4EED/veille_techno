"""Découverte automatique de nouvelles sources RSS à chaque lancement."""

from __future__ import annotations

import html as html_stdlib
import re
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import feedparser
import yaml

from veille import (
    CONFIG,
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

FICHIER_DECOUVERTES = CONFIG / "sources_decouvertes.yaml"
FICHIER_CACHE = CONFIG / "decouverte_cache.yaml"
FICHIER_AUTO = CONFIG / "sources_auto.yaml"
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


def enregistrer_flux(nouvelles: list[Source], cible: Path) -> None:
    cfg = charger_optionnel(cible)
    flux = list(cfg.get("flux") or [])
    existants = {normaliser_url(item.get("url", "")) for item in flux}
    aujourd_hui = datetime.now().strftime("%Y-%m-%d")
    for source in nouvelles:
        if normaliser_url(source.url) in existants:
            continue
        flux.append(
            {
                "id": source.identifiant,
                "nom": source.nom,
                "url": source.url,
                "site": source.site,
                "filtre": source.filtre,
                "decouverte": aujourd_hui,
            }
        )
        existants.add(normaliser_url(source.url))
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(
        yaml.safe_dump(
            {
                "comment": "Sources ajoutées automatiquement à chaque lancement.",
                "flux": flux,
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def enregistrer_decouvertes(nouvelles: list[Source], fichier: Path | None = None) -> None:
    enregistrer_flux(nouvelles, fichier or FICHIER_DECOUVERTES)
    enregistrer_flux(nouvelles, FICHIER_AUTO)


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
