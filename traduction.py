"""Traduction automatique vers le français (titres et résumés anglais)."""

from __future__ import annotations

import json
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Any

CONFIG = Path(__file__).resolve().parent / "config"
FICHIER_CACHE = CONFIG / "traduction_cache.json"
MAX_TRADUCTIONS = 4
TIMEOUT_S = 14
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36"

MOTS_EN = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "for", "from",
    "had", "has", "have", "how", "in", "into", "is", "it", "its", "new", "not",
    "of", "on", "or", "over", "that", "the", "their", "this", "to", "was", "were",
    "what", "when", "which", "who", "will", "with", "after", "about", "more",
}

MOTS_FR = {
    "au", "aux", "avec", "ce", "ces", "cette", "dans", "de", "des", "du", "en",
    "est", "et", "la", "le", "les", "ou", "par", "pas", "plus", "pour", "que",
    "qui", "sont", "sur", "un", "une", "ses", "son",
}

_cache: dict[str, str] = {}
_cache_lock = threading.Lock()
_cache_charge = False
_erreur_affichee = False


@contextmanager
def _verrou_cache(exclusif: bool):
    """Empêche deux veilles d'écrire le cache en même temps (Linux et Windows)."""
    FICHIER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    verrou = FICHIER_CACHE.with_suffix(".lock")
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

            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_EX if exclusif else fcntl.LOCK_SH,
            )
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _charger_cache() -> None:
    global _cache_charge, _cache
    if _cache_charge:
        return
    if FICHIER_CACHE.exists():
        try:
            with _verrou_cache(False):
                brut = json.loads(FICHIER_CACHE.read_text(encoding="utf-8") or "{}")
            _cache = {
                k: v
                for k, v in brut.items()
                if isinstance(k, str) and isinstance(v, str) and v.strip() and v != k
            }
        except (OSError, json.JSONDecodeError):
            _cache = {}
    _cache_charge = True


def _sauver_cache() -> None:
    with _verrou_cache(True):
        try:
            existant = (
                json.loads(FICHIER_CACHE.read_text(encoding="utf-8") or "{}")
                if FICHIER_CACHE.exists()
                else {}
            )
        except json.JSONDecodeError:
            existant = {}
        if not isinstance(existant, dict):
            existant = {}
        with _cache_lock:
            existant.update(_cache)
            _cache.update({k: v for k, v in existant.items() if isinstance(v, str)})
        FICHIER_CACHE.write_text(
            json.dumps(existant, ensure_ascii=False, indent=0),
            encoding="utf-8",
        )


def _tokens(texte: str) -> list[str]:
    return re.findall(r"[a-zàâäéèêëïîôùûüçœ]+", texte.lower())


def semble_anglais(texte: str) -> bool:
    brut = (texte or "").strip()
    if len(brut) < 12:
        return False
    mots = _tokens(brut)
    if len(mots) < 3:
        return False
    n_en = sum(1 for mot in mots if mot in MOTS_EN)
    n_fr = sum(1 for mot in mots if mot in MOTS_FR)
    if n_fr >= n_en and n_fr >= 2:
        return False
    if re.search(r"[éèêëàâùûôîïçœ]", brut.lower()) and n_fr >= 1:
        return False
    return n_en >= 2 or (n_en > n_fr and n_en >= 1 and len(mots) >= 5)


def _get_json(url: str) -> Any:
    requete = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*"},
    )
    with urllib.request.urlopen(requete, timeout=TIMEOUT_S) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def _via_lingva(texte: str) -> str:
    q = urllib.parse.quote(texte, safe="")
    data = _get_json(f"https://lingva.ml/api/v1/en/fr/{q}")
    traduit = str((data or {}).get("translation") or "").strip()
    if not traduit:
        raise RuntimeError("traduction Lingva vide")
    return traduit


def _via_mymemory(texte: str) -> str:
    params = urllib.parse.urlencode({"q": texte[:500], "langpair": "en|fr"}, encoding="utf-8")
    data = _get_json(f"https://api.mymemory.translated.net/get?{params}")
    traduit = str((data or {}).get("responseData", {}).get("translatedText") or "").strip()
    if not traduit or traduit.lower() == texte.lower():
        raise RuntimeError("traduction MyMemory vide")
    if "QUOTA" in traduit.upper():
        raise RuntimeError("quota MyMemory")
    return traduit


def _via_google(texte: str) -> str:
    params = urllib.parse.urlencode(
        {"client": "gtx", "sl": "auto", "tl": "fr", "dt": "t", "q": texte},
        encoding="utf-8",
    )
    data = _get_json(f"https://translate.googleapis.com/translate_a/single?{params}")
    if not isinstance(data, list) or not data or not data[0]:
        raise RuntimeError("réponse Google vide")
    morceaux = []
    for segment in data[0]:
        if isinstance(segment, list) and segment and isinstance(segment[0], str):
            morceaux.append(segment[0])
    traduit = "".join(morceaux).strip()
    if not traduit:
        raise RuntimeError("traduction Google vide")
    return traduit


def _nettoyer(texte: str) -> str:
    return re.sub(r"\s+", " ", texte).strip()


def traduire_texte(texte: str) -> str:
    brut = (texte or "").strip()
    if not brut or not semble_anglais(brut):
        return brut
    _charger_cache()
    with _cache_lock:
        if brut in _cache:
            return _cache[brut]
    traduit = brut
    for moteur in (_via_lingva, _via_mymemory, _via_google):
        try:
            candidat = _nettoyer(moteur(brut))
            if candidat and candidat != brut:
                traduit = candidat
                break
        except Exception as exc:  # noqa: BLE001
            global _erreur_affichee
            if not _erreur_affichee:
                print(f"  traduction ({moteur.__name__}) : {exc}", flush=True)
                _erreur_affichee = True
            continue
    if traduit != brut:
        with _cache_lock:
            _cache[brut] = traduit
    return traduit


def traduire_articles(articles: list[Any], prefixe: str = "") -> None:
    _charger_cache()
    cibles = [a for a in articles if semble_anglais(a.titre) or semble_anglais(a.resume)]
    if not cibles:
        return
    print(f"{prefixe} Traduction de {len(cibles)} article(s) vers le français…", flush=True)

    def _un(article: Any) -> None:
        article.titre = traduire_texte(article.titre)
        article.resume = traduire_texte(article.resume)

    with ThreadPoolExecutor(max_workers=MAX_TRADUCTIONS) as pool:
        futurs = [pool.submit(_un, article) for article in cibles]
        for futur in as_completed(futurs):
            try:
                futur.result()
            except Exception:  # noqa: BLE001
                continue
    _sauver_cache()
