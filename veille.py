#!/usr/bin/env python3
"""Génère un rapport de veille au format HTML et PDF."""

from __future__ import annotations

import argparse
import html
import re
import shutil
import socket
import sys
import threading
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import time
from typing import Any

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import feedparser
import yaml

CONFIG = ROOT / "config"
USER_AGENT = "Mozilla/5.0 (compatible; VeilleIOT/1.0; outil local de veille technique)"
TIMEOUT_S = 18
MAX_WORKERS = 10
MOIS_FR = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
BRUIT_TITRE = (
    r"nyse:iot",
    r"shares gap",
    r"stock a bargain",
    r"gf score",
    r"cpi report",
    r"valuations could swing",
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def normaliser(text: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(text).lower()).strip()


def nettoyer_html(raw: str) -> str:
    if not raw:
        return ""
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def charger_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def extraire_date(entry: Any) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    for attr in ("published", "updated"):
        value = getattr(entry, attr, None) or entry.get(attr)
        if not value:
            continue
        try:
            dt = parsedate_to_datetime(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            pass
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(value[:19] + ("+0000" if fmt.endswith("%z") and "Z" not in value else ""), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except ValueError:
                continue
    return None


def extraire_lien(entry: Any) -> str:
    link = entry.get("link") or ""
    if link:
        return str(link).strip()
    for candidate in entry.get("links", []):
        href = candidate.get("href")
        if href:
            return str(href).strip()
    return ""


def extraire_resume(entry: Any) -> str:
    if entry.get("summary"):
        return nettoyer_html(entry.get("summary"))
    if entry.get("description"):
        return nettoyer_html(entry.get("description"))
    for content in entry.get("content", []) or []:
        value = content.get("value")
        if value:
            return nettoyer_html(value)
    return ""


@dataclass
class MotCle:
    brut: str
    normalise: str
    est_phrase: bool


@dataclass
class Domaine:
    identifiant: str
    label: str
    priorite: int
    mots_cles: list[MotCle]


@dataclass
class Tendance:
    identifiant: str
    label: str
    mots_cles: list[MotCle]


@dataclass
class Source:
    identifiant: str
    nom: str
    url: str
    site: str = ""
    filtre: str = "mots_cles"
    domaine: str = ""
    ignorer_date: bool = False
    nouvelle: bool = False


@dataclass
class Profil:
    identifiant: str
    titre: str
    perimetre: str
    prefixe_sortie: str
    alias_sortie: str | None
    keywords: Path
    sources: Path
    decouvertes: Path
    cache: Path
    requetes_web: tuple[str, ...]
    sujet_email: str
    orphelins: str
    sources_extra: tuple[Path, ...] = field(default_factory=tuple)


def charger_profils() -> dict[str, Profil]:
    return {
        "iot": Profil(
            identifiant="iot",
            titre="Veille_IOT",
            perimetre=(
                "Domaines suivis : IoT, LoRa / LoRaWAN, mesh, Meshtastic, Meshcore, "
                "industrie / IIoT, routes, gestion routière, main courante, radio. "
                "Sources : flux RSS, Google News, presse nationale, Auvergne-Rhône-Alpes, "
                "informatique / technique / IA, LinkedIn, X, Mastodon, Bluesky et Threads."
            ),
            prefixe_sortie="Veille_IOT",
            alias_sortie="Veille_IOT.pdf",
            keywords=CONFIG / "keywords.yaml",
            sources=CONFIG / "sources.yaml",
            decouvertes=CONFIG / "sources_decouvertes.yaml",
            cache=CONFIG / "decouverte_cache.yaml",
            requetes_web=(
                'IoT "RSS" feed blog',
                "LoRaWAN RSS feed blog",
                "Meshtastic RSS feed blog",
                "Meshcore LoRa mesh RSS",
                '"industrie 4.0" OR IIoT RSS feed',
                '"météo routière" OR RWIS RSS',
                '"gestion routière" OR "main courante" RSS',
                'site:linkedin.com IoT LoRaWAN Meshtastic RSS',
                'site:x.com OR site:mastodon.social IoT LoRaWAN RSS',
                '"presse informatique" OR "usine digitale" RSS',
                '"intelligence artificielle" RSS France',
                '"Auvergne-Rhône-Alpes" IoT OR LoRa RSS',
            ),
            sujet_email="Veille_IOT",
            orphelins="Autres articles des sources IoT",
        ),
        "crise": Profil(
            identifiant="crise",
            titre="Veille_Crise",
            perimetre=(
                "Rubrique Gestion de crise : crise, crisis, crisi, gestion de crise, "
                "inondation, tremblement de terre, catastrophe, aléa climatique, "
                "aléa technologique. Sources : flux RSS, Google News, presse nationale, "
                "presse régionale de toute la France, informatique / technique / IA, "
                "LinkedIn, X, Mastodon, Bluesky et Threads."
            ),
            prefixe_sortie="Veille_Crise",
            alias_sortie="Veille_Crise.pdf",
            keywords=CONFIG / "keywords_crise.yaml",
            sources=CONFIG / "sources_crise.yaml",
            decouvertes=CONFIG / "sources_decouvertes_crise.yaml",
            cache=CONFIG / "decouverte_cache_crise.yaml",
            requetes_web=(
                '"gestion de crise" RSS',
                "inondation flood RSS",
                '"tremblement de terre" earthquake RSS',
                "catastrophe disaster RSS",
                '"aléa climatique" OR "aléa technologique" RSS',
                "IRMA Grenoble risques majeurs RSS",
                "vigilance Météo-France RSS",
                'site:afp.com catastrophe inondation RSS',
                'site:linkedin.com "gestion de crise" ORSEC "cellule de crise"',
                'site:linkedin.com inondation OR "plan communal de sauvegarde"',
                'site:linkedin.com "crisis management" OR "emergency management" disaster',
                'site:x.com OR site:mastodon.social "crisis management" flood RSS',
                '"Auvergne-Rhône-Alpes" inondation OR tempête RSS',
                '"presse nationale" vigilance OR alerte RSS',
                '"presse régionale" inondation OR tempête OR séisme RSS France',
            ),
            sujet_email="Veille_Crise",
            orphelins="Autres articles des sources crise",
            sources_extra=(CONFIG / "sources_crise_territoires.yaml",),
        ),
        "radio": Profil(
            identifiant="radio",
            titre="Veille_Radio",
            perimetre=(
                "Rubrique Radio : radio, hamradio, radioamateur, modes digitaux, trafic, "
                "SDR, APRS, PMR / TETRA / DMR. Sources : flux RSS, Google News, presse nationale, "
                "Auvergne-Rhône-Alpes, informatique / technique / IA, LinkedIn, X, Mastodon, Bluesky et Threads."
            ),
            prefixe_sortie="Veille_Radio",
            alias_sortie="Veille_Radio.pdf",
            keywords=CONFIG / "keywords_radio.yaml",
            sources=CONFIG / "sources_radio.yaml",
            decouvertes=CONFIG / "sources_decouvertes_radio.yaml",
            cache=CONFIG / "decouverte_cache_radio.yaml",
            requetes_web=(
                "ham radio RSS feed",
                "radioamateur RSS",
                '"digital modes" FT8 Winlink RSS',
                '"trafic radio" OR TETRA PMR RSS',
                "SDR APRS RTL-SDR RSS",
                'site:linkedin.com "amateur radio" DMR RSS',
                'site:x.com OR site:mastodon.social "ham radio" FT8 RSS',
                '"radioamateur" OR hamradio RSS France',
                '"Auvergne-Rhône-Alpes" radioamateur OR relais RSS',
            ),
            sujet_email="Veille_Radio",
            orphelins="Autres articles des sources radio",
        ),
        "outils": Profil(
            identifiant="outils",
            titre="Veille_Outils_PC",
            perimetre=(
                "Rubrique Outils de gestion de crise et de poste de commandement (PC) : "
                "logiciels et systèmes d'information de crise, SYNERGI, NexSIS, ORSEC, "
                "main courante, salle de crise, PCO / PCA / PCC, éditeurs (Everbridge, "
                "WebEOC, Hexagon, Systel…). Sources : flux RSS, Google News, presse "
                "nationale, presse régionale de toute la France, informatique / technique / IA, "
                "LinkedIn, X, Mastodon, Bluesky et Threads."
            ),
            prefixe_sortie="Veille_Outils_PC",
            alias_sortie="Veille_Outils_PC.pdf",
            keywords=CONFIG / "keywords_outils.yaml",
            sources=CONFIG / "sources_outils.yaml",
            decouvertes=CONFIG / "sources_decouvertes_outils.yaml",
            cache=CONFIG / "decouverte_cache_outils.yaml",
            requetes_web=(
                '"logiciel de gestion de crise" RSS',
                '"poste de commandement" OR "salle de crise" RSS',
                '"main courante numérique" RSS',
                "NexSIS OR SYNERGI OR ORSEC RSS",
                '"crisis management software" OR WebEOC Everbridge RSS',
                'site:linkedin.com "crisis management software" WebEOC Everbridge',
                'site:linkedin.com NexSIS OR SYNERGI OR "poste de commandement"',
                'site:linkedin.com "main courante numérique" OR "salle de crise"',
                'site:x.com OR site:mastodon.social "emergency management software" RSS',
            ),
            sujet_email="Veille_Outils_PC",
            orphelins="Autres articles des sources outils PC",
            sources_extra=(CONFIG / "sources_crise_territoires.yaml",),
        ),
        "blackout": Profil(
            identifiant="blackout",
            titre="Veille_Blackout",
            perimetre=(
                "Rubrique Black-out en France : panne géante, délestage, EcoWatt, "
                "réseau électrique (RTE, Enedis), exercice national de résilience, "
                "SGDSN, CIRN, documents des services de l'État. Les prises de parole "
                "récentes de l'Élysée et d'Emmanuel Macron sur l'électricité, l'énergie "
                "et la résilience sont remontées en priorité, avec les articles et "
                "dossiers de presse qui en découlent. Sources : flux RSS, Google News, "
                "presse nationale, presse régionale de toute la France, sites d'État, "
                "informatique / technique, LinkedIn, X, Mastodon, Bluesky et Threads."
            ),
            prefixe_sortie="Veille_Blackout",
            alias_sortie="Veille_Blackout.pdf",
            keywords=CONFIG / "keywords_blackout.yaml",
            sources=CONFIG / "sources_blackout.yaml",
            decouvertes=CONFIG / "sources_decouvertes_blackout.yaml",
            cache=CONFIG / "decouverte_cache_blackout.yaml",
            requetes_web=(
                '"black-out" OR blackout France RSS',
                '"exercice black-out" OR CIRN OR SGDSN RSS',
                'délestage OR EcoWatt RTE Enedis RSS',
                'site:elysee.fr électricité OR énergie OR résilience RSS',
                'site:sgdsn.gouv.fr OR site:gouvernement.fr black-out OR résilience RSS',
                'site:rte-france.com OR site:enedis.fr délestage OR EcoWatt RSS',
                '"Emmanuel Macron" (black-out OR délestage OR électricité) RSS',
                'site:vie-publique.fr "système électrique" OR résilience RSS',
            ),
            sujet_email="Veille_Blackout",
            orphelins="Autres articles des sources black-out",
            sources_extra=(CONFIG / "sources_crise_territoires.yaml",),
        ),
    }


@dataclass
class Article:
    titre: str
    lien: str
    source: str
    date: datetime | None
    resume: str
    domaines: list[str] = field(default_factory=list)
    mots_trouves: list[str] = field(default_factory=list)
    tendances: list[str] = field(default_factory=list)

    @property
    def cle_dedup(self) -> str:
        titre_n = re.sub(r"[^a-z0-9]+", " ", normaliser(self.titre))
        return f"{titre_n}|{normaliser(self.lien.split('?')[0])}"


def compiler_mots(valeurs: list[str]) -> list[MotCle]:
    mots: list[MotCle] = []
    for brut in valeurs:
        normalise = normaliser(brut)
        if not normalise:
            continue
        mots.append(MotCle(brut=brut, normalise=normalise, est_phrase=(" " in normalise or "-" in normalise)))
    return mots


def charger_domaines(cfg: dict[str, Any]) -> list[Domaine]:
    domaines: list[Domaine] = []
    for identifiant, data in (cfg.get("domaines") or {}).items():
        domaines.append(
            Domaine(
                identifiant=identifiant,
                label=data["label"],
                priorite=int(data.get("priorite", 0)),
                mots_cles=compiler_mots(data.get("mots_cles") or []),
            )
        )
    domaines.sort(key=lambda d: d.priorite, reverse=True)
    return domaines


def charger_tendances(cfg: dict[str, Any]) -> list[Tendance]:
    tendances: list[Tendance] = []
    for data in cfg.get("tendances") or []:
        tendances.append(
            Tendance(
                identifiant=data["id"],
                label=data["label"],
                mots_cles=compiler_mots(data.get("mots_cles") or []),
            )
        )
    return tendances


def mot_dans_texte(mot: MotCle, texte: str) -> bool:
    if mot.est_phrase:
        return mot.normalise in texte
    return re.search(rf"(?<![a-z0-9]){re.escape(mot.normalise)}(?![a-z0-9])", texte) is not None


def matcher(texte: str, domaines: list[Domaine], tendances: list[Tendance]) -> tuple[list[str], list[str], list[str]]:
    domaines_ok: list[tuple[int, str]] = []
    mots_trouves: list[str] = []
    for domaine in domaines:
        hits = [mot.brut for mot in domaine.mots_cles if mot_dans_texte(mot, texte)]
        if hits:
            domaines_ok.append((domaine.priorite, domaine.identifiant))
            mots_trouves.extend(hits)
    tendances_ok = [
        tendance.identifiant
        for tendance in tendances
        if any(mot_dans_texte(mot, texte) for mot in tendance.mots_cles)
    ]
    domaines_ok.sort(reverse=True)
    vus: set[str] = set()
    mots_uniques: list[str] = []
    for mot in mots_trouves:
        cle = normaliser(mot)
        if cle not in vus:
            vus.add(cle)
            mots_uniques.append(mot)
    return [identifiant for _, identifiant in domaines_ok], mots_uniques, tendances_ok


def url_google_news(query: str, hl: str, gl: str, ceid: str) -> str:
    params = urllib.parse.urlencode({"q": query, "hl": hl, "gl": gl, "ceid": ceid})
    return f"https://news.google.com/rss/search?{params}"


def requete_site(sites: list[str], query: str) -> str:
    if not sites:
        return query
    if len(sites) == 1:
        return f"site:{sites[0]} ({query})"
    clause = " OR ".join(f"site:{site}" for site in sites)
    return f"({clause}) ({query})"


def sources_reseaux_sociaux(cfg: dict[str, Any]) -> list[Source]:
    """LinkedIn, X, Mastodon, Bluesky, Threads via Google News + hashtags Mastodon."""
    chemin = CONFIG / "reseaux_sociaux.yaml"
    reseaux_cfg = charger_yaml(chemin) if chemin.exists() else {}
    sources: list[Source] = []
    for req in cfg.get("requetes_rs") or []:
        autorises = {str(x).lower() for x in (req.get("reseaux") or [])}
        for reseau in reseaux_cfg.get("reseaux") or []:
            if autorises and str(reseau.get("id") or "").lower() not in autorises:
                continue
            sites = list(reseau.get("sites") or [])
            if not sites or not req.get("query"):
                continue
            identifiant_req = req.get("id") or re.sub(r"[^a-z0-9]+", "-", str(req.get("label", "rs")).lower()).strip("-")
            sources.append(
                Source(
                    identifiant=f"rs-{reseau['id']}-{identifiant_req}",
                    nom=f"{reseau['label']} — {req['label']}",
                    url=url_google_news(
                        requete_site(sites, req["query"]),
                        req.get("hl", "fr"),
                        req.get("gl", "FR"),
                        req.get("ceid", "FR:fr"),
                    ),
                    site=reseau.get("url") or f"https://{sites[0]}/",
                    filtre=req.get("filtre", "mots_cles"),
                    domaine=req.get("domaine", ""),
                    ignorer_date=True,
                )
            )
    for tag in cfg.get("mastodon_tags") or []:
        slug_tag = re.sub(r"[^a-z0-9]+", "-", str(tag).lower()).strip("-")
        for instance in reseaux_cfg.get("mastodon_instances") or []:
            parse = urllib.parse.urlparse(instance if "://" in str(instance) else f"https://{instance}")
            base = f"{parse.scheme}://{parse.netloc}".rstrip("/")
            hote = parse.netloc
            tag_enc = urllib.parse.quote(str(tag))
            sources.append(
                Source(
                    identifiant=f"masto-{re.sub(r'[^a-z0-9]+', '-', hote)}-{slug_tag}",
                    nom=f"Mastodon #{tag} ({hote})",
                    url=f"{base}/tags/{tag_enc}.rss",
                    site=f"{base}/tags/{tag}",
                    filtre="mots_cles",
                )
            )
    return sources


def charger_bloc_sources(cfg: dict[str, Any], *, reseaux: bool = False) -> list[Source]:
    sources: list[Source] = []
    for item in cfg.get("google_news") or []:
        sources.append(
            Source(
                identifiant=item["id"],
                nom=item["label"],
                url=url_google_news(item["query"], item.get("hl", "fr"), item.get("gl", "FR"), item.get("ceid", "FR:fr")),
                site=item.get("site") or "https://news.google.com/",
                filtre=item.get("filtre", "aucun"),
                domaine=item.get("domaine", ""),
                ignorer_date=True,
            )
        )
    if reseaux:
        sources.extend(sources_reseaux_sociaux(cfg))
    for item in cfg.get("flux") or []:
        sources.append(
            Source(
                identifiant=item["id"],
                nom=item["nom"],
                url=item["url"],
                    site=item.get("site", ""),
                filtre=item.get("filtre", "mots_cles"),
                domaine=item.get("domaine", ""),
                ignorer_date=bool(item.get("ignorer_date", False)),
            )
        )
    return sources


def cle_url_source(url: str) -> str:
    """Identité d'un flux. La requête Google News fait partie de l'adresse."""
    brut = (url or "").strip()
    if not brut:
        return ""
    parse = urllib.parse.urlparse(brut)
    if parse.netloc.endswith("news.google.com"):
        return brut.lower()
    return brut.split("?")[0].rstrip("/").lower()


def fusionner_sources(*listes: list[Source]) -> list[Source]:
    vus_id: set[str] = set()
    vus_url: set[str] = set()
    resultat: list[Source] = []
    for sources in listes:
        for source in sources:
            url = cle_url_source(source.url)
            if source.identifiant in vus_id or (url and url in vus_url):
                continue
            vus_id.add(source.identifiant)
            if url:
                vus_url.add(url)
            resultat.append(source)
    return resultat


def charger_sources_presse() -> list[Source]:
    sources: list[Source] = []
    for nom in ("sources_presse.yaml", "sources_tech.yaml", "sources_auto.yaml"):
        chemin = CONFIG / nom
        if chemin.exists():
            sources.extend(charger_bloc_sources(charger_yaml(chemin), reseaux=False))
    return sources


def charger_sources_extra(profil: Profil) -> list[Source]:
    sources: list[Source] = []
    for chemin in profil.sources_extra:
        if chemin.exists():
            sources.extend(charger_bloc_sources(charger_yaml(chemin), reseaux=False))
    return sources


def charger_sources(cfg: dict[str, Any]) -> list[Source]:
    return fusionner_sources(
        charger_bloc_sources(cfg, reseaux=True),
        charger_sources_presse(),
    )


def telecharger(url: str, timeout: int | None = None) -> bytes:
    delai = timeout or TIMEOUT_S
    requete = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html, */*",
        },
    )
    resultat: list[bytes | BaseException] = []

    def _run() -> None:
        try:
            with urllib.request.urlopen(requete, timeout=delai) as reponse:
                resultat.append(reponse.read())
        except BaseException as exc:  # noqa: BLE001
            resultat.append(exc)

    fil = threading.Thread(target=_run, daemon=True)
    fil.start()
    fil.join(delai + 4)
    if fil.is_alive() or not resultat:
        raise TimeoutError("délai dépassé")
    valeur = resultat[0]
    if isinstance(valeur, BaseException):
        raise valeur
    return valeur


def analyser_flux(source: Source) -> tuple[Source, list[Any], str | None]:
    try:
        brut = telecharger(source.url)
        flux = feedparser.parse(brut)
        if getattr(flux, "bozo", False) and not flux.entries:
            motif = getattr(getattr(flux, "bozo_exception", None), "args", [""])[0]
            return source, [], f"flux illisible ({motif})"
        return source, list(flux.entries), None
    except urllib.error.HTTPError as exc:
        return source, [], f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return source, [], f"réseau ({exc.reason})"
    except TimeoutError:
        return source, [], "délai dépassé"
    except Exception as exc:  # noqa: BLE001
        return source, [], str(exc)


def date_longue_fr(dt: datetime | None = None) -> str:
    moment = dt or datetime.now()
    return f"{moment.day} {MOIS_FR[moment.month - 1]} {moment.year}"


def formater_date(dt: datetime | None) -> str:
    if not dt:
        return "date inconnue"
    local = dt.astimezone()
    return f"{local.day:02d}/{local.month:02d}/{local.year} {local.hour:02d}:{local.minute:02d}"


def formater_date_court(dt: datetime | None) -> str:
    abrev = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")
    if not dt:
        return "date inconnue"
    local = dt.astimezone()
    return f"{local.day} {abrev[local.month - 1]} {local.year}"


def est_bruit(titre: str) -> bool:
    texte = normaliser(titre)
    return any(re.search(motif, texte) for motif in BRUIT_TITRE)


def tronquer(texte: str, taille: int = 420) -> str:
    if len(texte) <= taille:
        return texte
    return texte[: taille - 1].rsplit(" ", 1)[0] + "…"


def echap_html(texte: str) -> str:
    return html.escape(texte or "", quote=True)


def ancre(titre: str) -> str:
    texte = normaliser(titre)
    texte = re.sub(r"[^a-z0-9]+", "-", texte).strip("-")
    return texte or "section"


def titre_propre(titre: str) -> str:
    texte = unicodedata.normalize("NFKC", titre or "")
    texte = re.sub(r"\s+", " ", texte).strip()
    if " - " in texte:
        gauche, droite = texte.rsplit(" - ", 1)
        if 2 <= len(droite) <= 42:
            texte = gauche.strip()
    if len(texte) > 110:
        texte = tronquer(texte, 110)
    return texte or "(sans titre)"


def resume_propre(resume: str, titre: str) -> str:
    texte = unicodedata.normalize("NFKC", resume or "")
    texte = re.sub(r"(?is)the post .+? appeared first on .+$", "", texte)
    texte = re.sub(r"\s+", " ", texte).strip(" -–—")
    titre_n = normaliser(titre)
    resume_n = normaliser(texte)
    if not resume_n or resume_n == titre_n:
        return ""
    if titre_n and resume_n.startswith(titre_n):
        texte = texte[len(titre) :].lstrip(" -–—:.")
    return tronquer(texte.strip(), 280)


def barre_html(valeur: int, maximum: int) -> str:
    largeur = 0 if maximum <= 0 or valeur <= 0 else min(100, max(4, round(valeur / maximum * 100)))
    return f'<span class="barre" title="{valeur}"><i style="width:{largeur}%"></i></span>'


COULEURS_PROFIL = {
    "iot": "#0f4c5c",
    "crise": "#7a1f1f",
    "radio": "#1e3a5f",
    "outils": "#4a5c2a",
    "blackout": "#5c3d12",
}

CSS_RAPPORT = """
:root { --accent: #0f4c5c; --fond: #f4f1ea; --carte: #fff; --texte: #1c1917; --muted: #57534e; --ligne: #e7e5e4; }
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: var(--fond); color: var(--texte); font: 16px/1.5 "Source Sans 3", "Segoe UI", sans-serif; }
a { color: var(--accent); }
header { background: var(--accent); color: #fff; padding: 2rem 1.25rem 1.5rem; }
header h1 { margin: 0 0 .35rem; font-size: 1.9rem; letter-spacing: .02em; }
header .date { margin: 0; opacity: .9; }
header .stats { margin: .75rem 0 0; font-size: .95rem; opacity: .92; }
main { max-width: 920px; margin: 0 auto; padding: 1.25rem 1rem 3rem; }
h2 { margin: 2rem 0 .75rem; padding-bottom: .35rem; border-bottom: 2px solid var(--accent); font-size: 1.25rem; }
h3 { margin: 0 0 .35rem; font-size: 1.05rem; }
.perimetre, .note { background: var(--carte); border: 1px solid var(--ligne); border-radius: 10px; padding: 1rem 1.1rem; }
.sommaire { display: flex; flex-wrap: wrap; gap: .5rem; margin: 0; padding: 0; list-style: none; }
.sommaire a { display: inline-flex; gap: .4rem; align-items: center; background: var(--carte); border: 1px solid var(--ligne); border-radius: 999px; padding: .35rem .75rem; text-decoration: none; color: var(--texte); }
.sommaire a:hover { border-color: var(--accent); }
.sommaire strong { color: var(--accent); }
table { width: 100%; border-collapse: collapse; background: var(--carte); border-radius: 10px; overflow: hidden; }
th, td { text-align: left; padding: .55rem .7rem; border-bottom: 1px solid var(--ligne); vertical-align: top; }
th { background: #ece7dc; font-size: .85rem; text-transform: uppercase; letter-spacing: .04em; }
td.nb { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.barre { display: inline-block; width: 7rem; height: .55rem; background: #e7e5e4; border-radius: 99px; overflow: hidden; vertical-align: middle; }
.barre i { display: block; height: 100%; background: var(--accent); }
.fiche { background: var(--carte); border: 1px solid var(--ligne); border-left: 4px solid var(--accent); border-radius: 10px; padding: .9rem 1rem 1rem; margin: 0 0 .75rem; }
.meta { margin: 0; color: var(--muted); font-size: .88rem; }
.badges { display: flex; flex-wrap: wrap; gap: .3rem; margin: .5rem 0 0; }
.badge { background: #ece7dc; color: var(--accent); border-radius: 999px; padding: .1rem .5rem; font-size: .78rem; }
.details { margin: .4rem 0 0; color: var(--muted); font-size: .85rem; }
.resume { margin: .55rem 0 0; color: #44403c; }
.erreur { color: #9f1239; }
.compte { color: var(--muted); margin: 0 0 1rem; }
footer, .footer { color: var(--muted); font-size: .85rem; margin-top: 2rem; }
@media print { body { background: #fff; } header { print-color-adjust: exact; -webkit-print-color-adjust: exact; } .fiche { break-inside: avoid; } }
""".strip()


def ecrire_rapport(
    chemin: Path,
    articles: list[Article],
    domaines: list[Domaine],
    tendances: list[Tendance],
    sources: list[Source],
    erreurs: list[tuple[str, str]],
    depuis: datetime,
    duree_s: float,
    nouvelles: list[Source] | None = None,
    profil: Profil | None = None,
) -> None:
    profil = profil or charger_profils()["iot"]
    par_id = {d.identifiant: d for d in domaines}
    par_tendance = {t.identifiant: t for t in tendances}
    comptes: dict[str, int] = {d.identifiant: 0 for d in domaines}
    for article in articles:
        if article.domaines:
            comptes[article.domaines[0]] = comptes.get(article.domaines[0], 0) + 1
    orphelins = [a for a in articles if not a.domaines]
    max_compte = max([*comptes.values(), len(orphelins), 1])
    accent = COULEURS_PROFIL.get(profil.identifiant, "#0f4c5c")
    date_lue = date_longue_fr()
    genere = datetime.now().strftime("%d/%m/%Y à %H:%M")
    stats = (
        f"{len(articles)} article(s) · {len(sources)} source(s) · "
        f"depuis le {depuis.astimezone().strftime('%d/%m/%Y')} · généré le {genere}"
    )

    hits_tendances: dict[str, int] = {t.identifiant: 0 for t in tendances}
    for article in articles:
        for identifiant in set(article.tendances):
            hits_tendances[identifiant] = hits_tendances.get(identifiant, 0) + 1
    max_tendance = max([*hits_tendances.values(), 1])

    def lien_titre(titre: str, url: str) -> str:
        texte = echap_html(titre)
        return f'<a href="{echap_html(url)}">{texte}</a>' if url else texte

    def fiche(article: Article) -> str:
        titre = titre_propre(article.titre)
        resume = resume_propre(article.resume, titre)
        extra = [par_id[d].label for d in article.domaines[1:] if d in par_id]
        tags = [par_tendance[t].label for t in article.tendances if t in par_tendance]
        badges = "".join(f'<span class="badge">{echap_html(mot)}</span>' for mot in article.mots_trouves[:6])
        details: list[str] = []
        if extra:
            details.append("aussi : " + ", ".join(extra))
        if tags:
            details.append("tendances : " + ", ".join(tags))
        blocs = [
            '<article class="fiche">',
            f"<h3>{lien_titre(titre, article.lien)}</h3>",
            f'<p class="meta">{echap_html(article.source)} · {echap_html(formater_date_court(article.date))}</p>',
        ]
        if badges:
            blocs.append(f'<p class="badges">{badges}</p>')
        if details:
            blocs.append(f'<p class="details">{echap_html(" · ".join(details))}</p>')
        if resume:
            blocs.append(f'<p class="resume">{echap_html(resume)}</p>')
        blocs.append("</article>")
        return "\n".join(blocs)

    def tableau_compact(items: list[Article]) -> str:
        lignes = [
            "<table><thead><tr><th>Date</th><th>Source</th><th>Titre</th></tr></thead><tbody>"
        ]
        for article in items:
            titre = lien_titre(titre_propre(article.titre), article.lien)
            lignes.append(
                "<tr>"
                f"<td>{echap_html(formater_date_court(article.date))}</td>"
                f"<td>{echap_html(article.source)}</td>"
                f"<td>{titre}</td>"
                "</tr>"
            )
        lignes.append("</tbody></table>")
        return "\n".join(lignes)

    sommaire: list[str] = ['<ul class="sommaire">']
    for domaine in domaines:
        n = comptes.get(domaine.identifiant, 0)
        if n:
            sommaire.append(
                f'<li><a href="#{ancre(domaine.label)}">{echap_html(domaine.label)} <strong>{n}</strong></a></li>'
            )
    if orphelins:
        sommaire.append(
            f'<li><a href="#{ancre(profil.orphelins)}">{echap_html(profil.orphelins)} <strong>{len(orphelins)}</strong></a></li>'
        )
    sommaire.append('<li><a href="#sources">Sources</a></li></ul>')

    if nouvelles:
        lignes_nouvelles = ["<table><thead><tr><th>Source</th><th>Flux</th></tr></thead><tbody>"]
        for source in nouvelles:
            url = source.url or source.site
            lignes_nouvelles.append(
                f"<tr><td><strong>{echap_html(source.nom)}</strong></td>"
                f"<td><a href=\"{echap_html(url)}\">{echap_html(url)}</a></td></tr>"
            )
        lignes_nouvelles.append("</tbody></table>")
        bloc_nouvelles = "\n".join(lignes_nouvelles)
    else:
        bloc_nouvelles = '<p class="note">Aucune nouvelle source cette fois. Les sources déjà connues restent interrogées.</p>'

    lignes_synth: list[str] = [
        "<table><thead><tr><th>Rubrique</th><th>Volume</th><th>Articles</th></tr></thead><tbody>"
    ]
    for domaine in domaines:
        n = comptes.get(domaine.identifiant, 0)
        lignes_synth.append(
            f"<tr><td>{echap_html(domaine.label)}</td><td>{barre_html(n, max_compte)}</td>"
            f'<td class="nb">{n}</td></tr>'
        )
    if orphelins:
        n = len(orphelins)
        lignes_synth.append(
            f"<tr><td>{echap_html(profil.orphelins)}</td><td>{barre_html(n, max_compte)}</td>"
            f'<td class="nb">{n}</td></tr>'
        )
    lignes_synth.append("</tbody></table>")

    lignes_tend: list[str] = [
        "<table><thead><tr><th>Tendance</th><th>Volume</th><th>Signaux</th></tr></thead><tbody>"
    ]
    tendance_vue = False
    for tendance in tendances:
        n = hits_tendances.get(tendance.identifiant, 0)
        if not n:
            continue
        tendance_vue = True
        lignes_tend.append(
            f"<tr><td>{echap_html(tendance.label)}</td><td>{barre_html(n, max_tendance)}</td>"
            f'<td class="nb">{n}</td></tr>'
        )
    lignes_tend.append("</tbody></table>")
    bloc_tendances = "\n".join(lignes_tend) if tendance_vue else '<p class="note">Aucune tendance forte détectée sur la période.</p>'

    sections: list[str] = []

    def ajouter_section(titre: str, items: list[Article], compact: bool = False) -> None:
        if not items:
            return
        sections.append(f'<section id="{ancre(titre)}">')
        sections.append(f"<h2>{echap_html(titre)}</h2>")
        sections.append(f'<p class="compte">{len(items)} article(s)</p>')
        if compact:
            sections.append(tableau_compact(items))
        else:
            sections.extend(fiche(article) for article in items)
        sections.append("</section>")

    for domaine in domaines:
        selection = [a for a in articles if a.domaines and a.domaines[0] == domaine.identifiant]
        ajouter_section(domaine.label, selection)
    if orphelins:
        ajouter_section(profil.orphelins, orphelins, compact=len(orphelins) > 8)

    erreurs_par_nom = {nom: motif for nom, motif in erreurs}
    lignes_src = ["<table><thead><tr><th>Source</th><th>Statut</th></tr></thead><tbody>"]
    for source in sources:
        nom = echap_html(source.nom)
        if source.nouvelle:
            nom = f"<strong>{nom}</strong> (nouvelle)"
        if source.nom in erreurs_par_nom:
            statut = f'<span class="erreur">inaccessible — {echap_html(erreurs_par_nom[source.nom])}</span>'
        elif source.site:
            statut = f'<a href="{echap_html(source.site)}">{echap_html(source.site)}</a>'
        else:
            statut = "ok"
        lignes_src.append(f"<tr><td>{nom}</td><td>{statut}</td></tr>")
    lignes_src.append("</tbody></table>")

    page = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{echap_html(profil.titre)} — {echap_html(date_lue)}</title>
<style>
{CSS_RAPPORT}
:root {{ --accent: {accent}; }}
</style>
</head>
<body>
<header>
<h1>{echap_html(profil.titre)}</h1>
<p class="date">{echap_html(date_lue)}</p>
<p class="stats">{echap_html(stats)}</p>
</header>
<main>
<h2>Périmètre</h2>
<p class="perimetre">{echap_html(profil.perimetre)}</p>
<h2>Sommaire</h2>
{"".join(sommaire)}
<h2>Nouvelles sources</h2>
{bloc_nouvelles}
<h2>Synthèse par domaine</h2>
{" ".join(lignes_synth)}
<h2>Tendances détectées</h2>
{bloc_tendances}
{" ".join(sections)}
<section id="sources">
<h2>Sources</h2>
{" ".join(lignes_src)}
</section>
<p class="footer">Rapport généré localement · {echap_html(genere)}</p>
</main>
</body>
</html>
"""
    del duree_s
    chemin.write_text(page, encoding="utf-8")


def collecter(
    jours: int,
    decouvrir: bool = True,
    profil: Profil | None = None,
) -> tuple[list[Article], list[Source], list[tuple[str, str]], list[Domaine], list[Tendance], datetime, list[Source]]:
    from decouverte import charger_sources_decouvertes, decouvrir_sources

    profil = profil or charger_profils()["iot"]
    prefixe = f"[{profil.identifiant}]"
    kw_cfg = charger_yaml(profil.keywords)
    src_cfg = charger_yaml(profil.sources)
    domaines = charger_domaines(kw_cfg)
    tendances = charger_tendances(kw_cfg)
    sources = fusionner_sources(
        charger_sources(src_cfg),
        charger_sources_extra(profil),
        charger_sources_decouvertes(profil.decouvertes),
    )
    nouvelles: list[Source] = []
    if decouvrir:
        nouvelles = decouvrir_sources(
            sources,
            domaines,
            tendances,
            fichier_decouvertes=profil.decouvertes,
            fichier_cache=profil.cache,
            requetes_web=profil.requetes_web,
            prefixe=prefixe,
        )
        sources.extend(nouvelles)
    depuis = now_utc() - timedelta(days=jours)

    articles: list[Article] = []
    erreurs: list[tuple[str, str]] = []

    print(f"{prefixe} Collecte de {len(sources)} sources sur {jours} jour(s)…", flush=True)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futurs = {pool.submit(analyser_flux, source): source for source in sources}
        for futur in as_completed(futurs):
            source, entrees, erreur = futur.result()
            if erreur:
                print(f"{prefixe}   ✗ {source.nom} — {erreur}", flush=True)
                erreurs.append((source.nom, erreur))
                continue
            print(f"{prefixe}   ✓ {source.nom} — {len(entrees)} entrée(s)", flush=True)
            if source.ignorer_date:
                entrees = entrees[:18]
            for entree in entrees:
                date = extraire_date(entree)
                if date and date < depuis and not source.ignorer_date:
                    continue
                titre = nettoyer_html(entree.get("title") or "")
                if not normaliser(titre) or normaliser(titre) in {"sans titre", "(sans titre)"}:
                    continue
                if est_bruit(titre):
                    continue
                resume = extraire_resume(entree)
                lien = extraire_lien(entree)
                texte = normaliser(f"{titre} {resume}")
                domaines_ok, mots, tendances_ok = matcher(texte, domaines, tendances)
                if source.domaine and source.domaine not in domaines_ok:
                    domaines_ok = [source.domaine] + domaines_ok
                if source.filtre == "mots_cles" and not domaines_ok:
                    continue
                articles.append(
                    Article(
                        titre=titre,
                        lien=lien,
                        source=source.nom,
                        date=date,
                        resume=resume,
                        domaines=domaines_ok,
                        mots_trouves=mots,
                        tendances=tendances_ok,
                    )
                )

    vus: set[str] = set()
    uniques: list[Article] = []
    for article in sorted(articles, key=lambda a: a.date or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
        if article.cle_dedup in vus:
            continue
        vus.add(article.cle_dedup)
        uniques.append(article)
    return uniques, sources, erreurs, domaines, tendances, depuis, nouvelles


def main() -> int:
    socket.setdefaulttimeout(TIMEOUT_S)
    parser = argparse.ArgumentParser(description="Génère un rapport de veille HTML et PDF.")
    parser.add_argument("--profil", choices=sorted(charger_profils()), default="iot", help="Profil de veille à lancer")
    parser.add_argument("--jours", type=int, default=None, help="Nombre de jours à remonter (défaut : config)")
    parser.add_argument("--sortie", type=Path, default=None, help="Chemin du fichier PDF généré")
    parser.add_argument(
        "--sans-decouverte",
        action="store_true",
        help="Ne pas chercher de nouvelles sources à ce lancement",
    )
    parser.add_argument(
        "--sans-email",
        action="store_true",
        help="Ne pas envoyer le rapport par e-mail",
    )
    parser.add_argument(
        "--sans-traduction",
        action="store_true",
        help="Ne pas traduire les titres et résumés anglais",
    )
    args = parser.parse_args()

    profil = charger_profils()[args.profil]
    kw_cfg = charger_yaml(profil.keywords)
    jours = args.jours if args.jours is not None else int(kw_cfg.get("periode_jours", 7))
    date_nom = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if args.sortie:
        sortie_pdf = args.sortie
        sortie_html = args.sortie.with_suffix(".html")
    else:
        sortie_pdf = ROOT / f"{profil.prefixe_sortie}_{date_nom}.pdf"
        sortie_html = ROOT / f"{profil.prefixe_sortie}_{date_nom}.html"

    debut = time()
    articles, sources, erreurs, domaines, tendances, depuis, nouvelles = collecter(
        jours,
        decouvrir=not args.sans_decouverte,
        profil=profil,
    )
    if not args.sans_traduction:
        from traduction import traduire_articles

        traduire_articles(articles, prefixe=f"[{profil.identifiant}]")
    duree = time() - debut
    ecrire_rapport(sortie_html, articles, domaines, tendances, sources, erreurs, depuis, duree, nouvelles, profil)
    from rapport_pdf import ecrire_rapport_pdf

    ecrire_rapport_pdf(sortie_pdf, articles, domaines, tendances, sources, erreurs, depuis, nouvelles, profil)
    from publication import memoriser_rapport

    memoriser_rapport(profil.identifiant, sortie_pdf, sortie_html)
    alias_html = ROOT / f"{profil.prefixe_sortie}.html"
    alias_html.write_text(sortie_html.read_text(encoding="utf-8"), encoding="utf-8")
    if profil.alias_sortie:
        alias_pdf = ROOT / profil.alias_sortie
        shutil.copyfile(sortie_pdf, alias_pdf)
        print(f"[{profil.identifiant}] Alias écrits : {alias_html.name}, {alias_pdf.name}", flush=True)
    print(f"\n[{profil.identifiant}] Rapport HTML : {sortie_html}", flush=True)
    print(f"[{profil.identifiant}] Rapport PDF  : {sortie_pdf}", flush=True)
    print(
        f"[{profil.identifiant}] {len(articles)} article(s) retenu(s), "
        f"{len(nouvelles)} nouvelle(s) source(s), {len(erreurs)} source(s) en erreur.",
        flush=True,
    )

    if not args.sans_email:
        from email_envoi import envoyer_rapport

        piece = sortie_pdf
        try:
            print(envoyer_rapport(piece, sujet=f"{profil.sujet_email} — {date_longue_fr()}"), flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[{profil.identifiant}] Envoi e-mail impossible : {exc}", flush=True)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
