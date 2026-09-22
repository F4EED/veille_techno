"""Envoi du rapport de veille par e-mail, sans pièce jointe.

Free.fr classe spam les .html, .pdf et trop de liens d’un coup.
Le rapport part donc dans le corps du message (HTML), éventuellement
en plusieurs e-mails si le volume dépasse ce que le filtre accepte.
"""

from __future__ import annotations

import os
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import yaml

from veille import CONFIG, date_longue_fr

# IoT ~273 Ko / ~490 liens : accepté. Crise ~390 Ko / ~750 liens : refusé.
MAX_OCTETS = 300_000
MAX_LIENS = 550
MAX_OCTETS_BLOC = 240_000
MAX_LIENS_BLOC = 420
PAUSE_S = 6


def _charger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def charger_config_email() -> dict[str, Any]:
    cfg = _charger(CONFIG / "email.yaml")
    secrets = _charger(CONFIG / "email.secrets.yaml")
    mot = (
        os.environ.get("VEILLE_SMTP_PASSWORD")
        or secrets.get("mot_de_passe")
        or cfg.get("smtp", {}).get("mot_de_passe")
        or ""
    )
    cfg = dict(cfg)
    smtp = dict(cfg.get("smtp") or {})
    smtp["mot_de_passe"] = str(mot).strip()
    cfg["smtp"] = smtp
    return cfg


def extraire_titre(html_rapport: str, repli: str) -> str:
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html_rapport, re.IGNORECASE | re.DOTALL)
    if not match:
        return repli
    return re.sub(r"<[^>]+>", "", match.group(1)).strip() or repli


def extraire_stats(html_rapport: str) -> str:
    match = re.search(r'class="stats"[^>]*>(.*?)</p>', html_rapport, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"<[^>]+>", "", match.group(1)).strip()


def _nb_liens(html: str) -> int:
    return len(re.findall(r"\bhref\s*=", html, re.I))


def _octets(html: str) -> int:
    return len(html.encode("utf-8"))


def _tient(html: str) -> bool:
    return _octets(html) <= MAX_OCTETS and _nb_liens(html) <= MAX_LIENS


def _tient_bloc(html: str) -> bool:
    return _octets(html) <= MAX_OCTETS_BLOC and _nb_liens(html) <= MAX_LIENS_BLOC


def _texte_brut(html: str) -> str:
    texte = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    texte = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", texte)
    texte = re.sub(r"(?is)<br\s*/?>", "\n", texte)
    texte = re.sub(r"(?is)</(p|h1|h2|h3|tr|article|section)>", "\n", texte)
    texte = re.sub(r"<[^>]+>", " ", texte)
    texte = re.sub(r"[ \t]+\n", "\n", texte)
    texte = re.sub(r"\n{3,}", "\n\n", texte)
    texte = re.sub(r"[ \t]{2,}", " ", texte)
    return texte.strip()[:8000]


def _style(html: str) -> str:
    match = re.search(r"<style[^>]*>(.*?)</style>", html, re.I | re.S)
    return match.group(1).strip() if match else ""


def _header(html: str) -> str:
    match = re.search(r"<header\b.*?</header>", html, re.I | re.S)
    return match.group(0) if match else ""


def _assembler(html_source: str, contenu: str, partie: int, total: int) -> str:
    titre = extraire_titre(html_source, "Veille")
    note = ""
    if total > 1:
        note = (
            f'<p class="note">Partie {partie}/{total} — '
            "ouvrez aussi le(s) message(s) suivant(s) pour le reste de la veille.</p>"
        )
    return (
        "<!DOCTYPE html>\n<html lang=\"fr\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{titre}</title><style>{_style(html_source)}</style></head><body>\n"
        f"{_header(html_source)}\n<main>\n{note}\n{contenu}\n</main></body></html>\n"
    )


def _eclater_section(section: str) -> list[str]:
    if _tient_bloc(section):
        return [section]
    debut = re.match(r"(<section\b[^>]*>.*?</h2>)", section, re.I | re.S)
    tete = debut.group(1) if debut else "<section>"
    articles = re.findall(r'<article class="fiche">.*?</article>', section, re.S)
    if articles:
        lots: list[str] = []
        courant: list[str] = []
        for article in articles:
            essai = courant + [article]
            bloc = tete + "\n" + "\n".join(essai) + "\n</section>"
            if courant and not _tient_bloc(bloc):
                lots.append(tete + "\n" + "\n".join(courant) + "\n</section>")
                courant = [article]
            else:
                courant = essai
        if courant:
            lots.append(tete + "\n" + "\n".join(courant) + "\n</section>")
        return lots

    lignes = re.findall(r"<tr>.*?</tr>", section, re.S)
    if len(lignes) > 2:
        thead = "\n".join(lignes[:1])
        lots = []
        courant = []
        for ligne in lignes[1:]:
            essai = courant + [ligne]
            bloc = f"{tete}<table>{thead}{''.join(essai)}</table></section>"
            if courant and not _tient_bloc(bloc):
                lots.append(f"{tete}<table>{thead}{''.join(courant)}</table></section>")
                courant = [ligne]
            else:
                courant = essai
        if courant:
            lots.append(f"{tete}<table>{thead}{''.join(courant)}</table></section>")
        return lots
    return [section]


def decouper_rapport_html(html: str) -> list[str]:
    if _tient(html):
        return [html]

    main = re.search(r"<main\b[^>]*>(.*)</main>", html, re.I | re.S)
    if not main:
        milieu = max(1, len(html) // 2)
        return [html[:milieu], html[milieu:]]

    corps = main.group(1)
    idx = corps.find("<section")
    intro = corps[:idx] if idx >= 0 else ""
    sections = re.findall(r"<section\b.*?</section>", corps, re.S)
    unites: list[str] = []
    if intro.strip():
        unites.append(intro)
    for section in sections:
        unites.extend(_eclater_section(section))

    groupes: list[list[str]] = []
    courant: list[str] = []
    for unite in unites:
        essai = courant + [unite]
        page = _assembler(html, "\n".join(essai), 1, 1)
        if courant and not _tient(page):
            groupes.append(courant)
            courant = [unite]
        else:
            courant = essai
    if courant:
        groupes.append(courant)

    total = max(1, len(groupes))
    return [_assembler(html, "\n".join(groupe), i, total) for i, groupe in enumerate(groupes, 1)]


def chemin_html(rapport: Path) -> Path:
    if rapport.suffix.lower() == ".html":
        return rapport
    candidat = rapport.with_suffix(".html")
    if candidat.exists():
        return candidat
    alias = rapport.parent / f"{rapport.stem.split('_20')[0]}.html"
    if alias.exists():
        return alias
    raise FileNotFoundError(f"rapport HTML introuvable pour {rapport}")


def _message(
    html_partie: str,
    cfg: dict[str, Any],
    sujet: str,
) -> EmailMessage:
    destinataires = list(cfg.get("destinataires") or [])
    expediteur = cfg.get("expediteur", "f4eed@free.fr")
    nom = cfg.get("expediteur_nom", "Veille")
    titre = extraire_titre(html_partie, sujet)
    stats = extraire_stats(html_partie)
    apercu = f"{titre}\n"
    if stats:
        apercu += f"\n{stats}\n"
    apercu += "\nLe rapport est affiché ci-dessous (aucun fichier à ouvrir).\n\n"
    apercu += _texte_brut(html_partie)

    message = EmailMessage()
    message["Subject"] = sujet
    message["From"] = f"{nom} <{expediteur}>"
    message["To"] = ", ".join(destinataires)
    message.set_content(apercu)
    message.add_alternative(html_partie, subtype="html")
    return message


def _garder_liens(html: str, maximum: int) -> str:
    compte = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal compte
        compte += 1
        if compte <= maximum:
            return match.group(0)
        return match.group(1)

    return re.sub(r'<a\s+href="[^"]*"[^>]*>(.*?)</a>', repl, html, flags=re.I | re.S)


def _sans_liens(html: str) -> str:
    return _garder_liens(html, 0)


def _est_refus_spam(exc: BaseException) -> bool:
    texte = str(exc).lower()
    return "550" in texte and "spam" in texte


def _envoyer_partie(
    html_partie: str,
    cfg: dict[str, Any],
    sujet: str,
    smtp: dict[str, Any],
    utilisateur: str,
    mot_de_passe: str,
    eviter_liens_massifs: bool = False,
) -> str:
    variantes: list[tuple[str, str]] = []
    if not eviter_liens_massifs:
        variantes.append((html_partie, "liens complets"))
    variantes.extend(
        [
            (_garder_liens(html_partie, 40), "40 liens"),
            (_sans_liens(html_partie), "sans liens"),
        ]
    )
    vues: set[str] = set()
    derniere: Exception | None = None
    for html_var, libelle in variantes:
        if html_var in vues:
            continue
        vues.add(html_var)
        try:
            html_envoi = html_var
            if libelle != "liens complets":
                note = (
                    '<p class="note">Certains titres ne sont pas cliquables : '
                    "Free.fr refuse sinon le message. "
                    "Le PDF local conserve tous les liens.</p>"
                )
                html_envoi = html_var.replace("<main>", f"<main>\n{note}", 1)
            _envoyer(_message(html_envoi, cfg, sujet), smtp, utilisateur, mot_de_passe)
            return libelle
        except Exception as exc:  # noqa: BLE001
            derniere = exc
            if not _est_refus_spam(exc):
                raise
            time.sleep(PAUSE_S)
    if derniere is not None:
        texte = _texte_brut(html_partie)
        message = EmailMessage()
        destinataires = list(cfg.get("destinataires") or [])
        message["Subject"] = sujet
        message["From"] = f"{cfg.get('expediteur_nom', 'Veille')} <{cfg.get('expediteur', 'f4eed@free.fr')}>"
        message["To"] = ", ".join(destinataires)
        message.set_content(texte)
        try:
            _envoyer(message, smtp, utilisateur, mot_de_passe)
            return "texte brut"
        except Exception as exc:  # noqa: BLE001
            derniere = exc
    assert derniere is not None
    raise derniere


def _envoyer(message: EmailMessage, smtp: dict[str, Any], utilisateur: str, mot_de_passe: str) -> None:
    hote = str(smtp.get("hote") or "").strip()
    port = int(smtp.get("port") or 587)
    contexte = ssl.create_default_context()
    if smtp.get("ssl"):
        with smtplib.SMTP_SSL(hote, port, timeout=30, context=contexte) as serveur:
            serveur.login(utilisateur, mot_de_passe)
            serveur.send_message(message)
    else:
        with smtplib.SMTP(hote, port, timeout=30) as serveur:
            serveur.ehlo()
            if smtp.get("demarrer_tls", True):
                serveur.starttls(context=contexte)
                serveur.ehlo()
            serveur.login(utilisateur, mot_de_passe)
            serveur.send_message(message)


def chemin_pdf(rapport: Path) -> Path:
    if rapport.suffix.lower() == ".pdf":
        return rapport
    candidat = rapport.with_suffix(".pdf")
    if candidat.exists():
        return candidat
    alias = rapport.parent / f"{rapport.stem.split('_20')[0]}.pdf"
    if alias.exists():
        return alias
    raise FileNotFoundError(f"rapport PDF introuvable pour {rapport}")


def _via_gmail(smtp: dict[str, Any]) -> bool:
    return "gmail.com" in str(smtp.get("hote") or "").lower()


def _envoyer_pdf_gmail(
    pdf: Path,
    cfg: dict[str, Any],
    sujet: str,
    smtp: dict[str, Any],
    utilisateur: str,
    mot_de_passe: str,
) -> None:
    destinataires = list(cfg.get("destinataires") or [])
    expediteur = cfg.get("expediteur", utilisateur)
    nom = cfg.get("expediteur_nom", "Veille")
    titre = pdf.stem.replace("_", " ")
    message = EmailMessage()
    message["Subject"] = sujet
    message["From"] = f"{nom} <{expediteur}>"
    message["To"] = ", ".join(destinataires)
    message.set_content(
        f"{titre}\n\n"
        f"Le rapport PDF est en pièce jointe : {pdf.name}\n"
        "Ouvrez-le directement, sans le dézipper."
    )
    message.add_attachment(
        pdf.read_bytes(),
        maintype="application",
        subtype="pdf",
        filename=pdf.name,
    )
    _envoyer(message, smtp, utilisateur, mot_de_passe)


def _envoyer_lien(
    url_pdf: str,
    url_html: str,
    url_accueil: str,
    titre: str,
    cfg: dict[str, Any],
    sujet: str,
    smtp: dict[str, Any],
    utilisateur: str,
    mot_de_passe: str,
) -> None:
    destinataires = list(cfg.get("destinataires") or [])
    expediteur = cfg.get("expediteur", "f4eed@free.fr")
    nom = cfg.get("expediteur_nom", "Veille")
    texte = (
        f"{titre}\n\n"
        f"Le rapport est en ligne :\n{url_pdf}\n\n"
        "Cliquez le lien, le PDF s'ouvre. Rien à dézipper.\n"
    )
    if url_accueil:
        texte += f"\nToutes les veilles : {url_accueil}\n"
    html = f"""<!DOCTYPE html>
<html lang="fr"><body style="font-family:Georgia,serif;line-height:1.45;color:#1c1917;">
<p><strong>{titre}</strong></p>
<p>Le rapport est en ligne :</p>
<p><a href="{url_pdf}">Ouvrir le PDF</a></p>
"""
    if url_html:
        html += f'<p><a href="{url_html}">Lire dans le navigateur</a></p>\n'
    if url_accueil:
        html += f'<p>Toutes les veilles : <a href="{url_accueil}">{url_accueil}</a></p>\n'
    html += "</body></html>"
    message = EmailMessage()
    message["Subject"] = sujet
    message["From"] = f"{nom} <{expediteur}>"
    message["To"] = ", ".join(destinataires)
    message.set_content(texte)
    message.add_alternative(html, subtype="html")
    _envoyer(message, smtp, utilisateur, mot_de_passe)


def envoyer_rapport(rapport: Path, sujet: str | None = None) -> str:
    cfg = charger_config_email()
    if not cfg.get("actif", True):
        return "envoi e-mail désactivé"
    destinataires = list(cfg.get("destinataires") or [])
    if not destinataires:
        raise RuntimeError("aucun destinataire configuré")
    smtp = cfg.get("smtp") or {}
    utilisateur = str(smtp.get("utilisateur") or cfg.get("expediteur") or "").strip()
    mot_de_passe = str(smtp.get("mot_de_passe") or "")
    if not str(smtp.get("hote") or "").strip():
        raise RuntimeError("serveur SMTP non renseigné dans config/email.yaml")
    if not mot_de_passe:
        raise RuntimeError(
            "mot de passe SMTP manquant : définir VEILLE_SMTP_PASSWORD "
            "ou créer config/email.secrets.yaml"
        )

    sujet = sujet or f"Veille — {date_longue_fr()}"
    dest = ", ".join(destinataires)
    pub = cfg.get("publication") or {}
    if pub.get("actif", True) and not _via_gmail(smtp):
        from publication import publier, url_publique

        fichiers: list[Path] = []
        try:
            fichiers.append(chemin_pdf(rapport))
        except FileNotFoundError:
            pass
        try:
            html_local = chemin_html(rapport)
            if html_local not in fichiers:
                fichiers.append(html_local)
        except FileNotFoundError:
            pass
        if fichiers:
            try:
                publier(fichiers, cfg)
            except Exception as exc:  # noqa: BLE001
                print(f"publication pages perso impossible : {exc}", flush=True)
            else:
                pdf = fichiers[0] if fichiers[0].suffix.lower() == ".pdf" else next(
                    (f for f in fichiers if f.suffix.lower() == ".pdf"), fichiers[0]
                )
                url_pdf = url_publique(pdf.with_suffix(".pdf").name, cfg)
                url_html = url_publique(pdf.with_suffix(".html").name, cfg)
                url_accueil = url_publique("index.html", cfg).rsplit("/", 1)[0] + "/"
                _envoyer_lien(
                    url_pdf,
                    url_html,
                    url_accueil,
                    pdf.stem.replace("_", " "),
                    cfg,
                    sujet,
                    smtp,
                    utilisateur,
                    mot_de_passe,
                )
                return f"e-mail envoyé à {dest} (lien {url_pdf})"

    if _via_gmail(smtp):
        pdf = chemin_pdf(rapport)
        _envoyer_pdf_gmail(pdf, cfg, sujet, smtp, utilisateur, mot_de_passe)
        return f"e-mail envoyé à {dest} (PDF joint via Gmail)"

    html_path = chemin_html(rapport)
    html_rapport = html_path.read_text(encoding="utf-8")
    sujet = sujet or f"Veille — {date_longue_fr()}"
    parties = decouper_rapport_html(html_rapport)
    modes: list[str] = []
    for i, partie in enumerate(parties, 1):
        sujet_p = sujet if len(parties) == 1 else f"{sujet} — suite {i}/{len(parties)}"
        mode = _envoyer_partie(
            partie,
            cfg,
            sujet_p,
            smtp,
            utilisateur,
            mot_de_passe,
            eviter_liens_massifs=len(parties) > 1,
        )
        modes.append(mode)
        if i < len(parties):
            time.sleep(PAUSE_S)
    dest = ", ".join(destinataires)
    detail = ", ".join(modes)
    if len(parties) == 1:
        return f"e-mail envoyé à {dest} (HTML dans le message, {detail}, sans pièce jointe)"
    return (
        f"e-mail envoyé à {dest} "
        f"({len(parties)} messages HTML, {detail}, sans pièce jointe)"
    )
