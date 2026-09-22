"""Rapport de veille au format PDF, pensé pour la lecture à l’écran et l’impression."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from veille import (
    Article,
    Domaine,
    Profil,
    Source,
    Tendance,
    charger_profils,
    date_longue_fr,
    formater_date_court,
    resume_propre,
    titre_propre,
    tronquer,
)

POLICE = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
POLICE_GRAS = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
POLICE_ITAL = "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf"

THEMES = {
    "iot": {
        "accent": (15, 76, 92),
        "clair": (232, 242, 244),
        "or": (196, 163, 90),
        "fond": (248, 245, 238),
        "accroche": "Objets connectés, LoRa, mesh et routes",
    },
    "crise": {
        "accent": (122, 31, 31),
        "clair": (247, 232, 226),
        "or": (214, 122, 58),
        "fond": (250, 244, 238),
        "accroche": "Risques, alertes et gestion de crise",
    },
    "radio": {
        "accent": (30, 58, 95),
        "clair": (230, 238, 248),
        "or": (70, 140, 214),
        "fond": (244, 247, 251),
        "accroche": "Radioamateur, modes digitaux et trafic",
    },
    "outils": {
        "accent": (74, 92, 42),
        "clair": (238, 242, 226),
        "or": (168, 140, 62),
        "fond": (247, 248, 240),
        "accroche": "Outils de gestion de crise et poste de commandement",
    },
    "blackout": {
        "accent": (92, 61, 18),
        "clair": (247, 240, 226),
        "or": (196, 140, 40),
        "fond": (250, 246, 238),
        "accroche": "Black-out, réseau électrique et déclarations de l'exécutif",
    },
}


_HORS_POLICE = re.compile(r"[^\x09\x0a\x0d\x20-\u024f\u1e00-\u1eff]")


def texte_pdf(valeur: str) -> str:
    brut = (
        (valeur or "")
        .replace("\u00a0", " ")
        .replace("\u202f", " ")
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2026", "...")
        .replace("«", '"')
        .replace("»", '"')
    )
    return _HORS_POLICE.sub("", brut).strip()


def _arrondi(pdf: FPDF, x: float, y: float, w: float, h: float, r: float, style: str = "F") -> None:
    rayon = min(r, max(0.4, min(w, h) / 2 - 0.1))
    pdf.rect(x, y, w, h, style=style, round_corners=True, corner_radius=rayon)


class RapportPDF(FPDF):
    def __init__(self, profil: Profil, theme: dict, date_lue: str):
        super().__init__(format="A4", unit="mm")
        self.profil = profil
        self.theme = theme
        self.date_lue = date_lue
        self.couverture = True
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(16, 16, 16)
        self.add_font("Lib", "", POLICE)
        self.add_font("Lib", "B", POLICE_GRAS)
        self.add_font("Lib", "I", POLICE_ITAL)
        self.set_title(f"{profil.titre} — {date_lue}")
        self.set_author("Veille")
        self.set_creator("Veille locale")

    @property
    def accent(self) -> tuple[int, int, int]:
        return self.theme["accent"]

    def header(self) -> None:
        if self.couverture or self.page_no() == 1:
            return
        self.set_fill_color(*self.theme["fond"])
        self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*self.accent)
        self.rect(0, 0, 210, 9, "F")
        self.set_xy(16, 2.2)
        self.set_font("Lib", "", 8)
        self.set_text_color(255, 255, 255)
        self.cell(0, 5, f"{self.profil.titre}  ·  {self.date_lue}", align="L")
        self.set_y(14)
        self.set_text_color(28, 25, 23)

    def footer(self) -> None:
        if self.couverture or self.page_no() == 1:
            return
        self.set_y(-12)
        self.set_draw_color(220, 215, 208)
        self.line(16, self.get_y(), 194, self.get_y())
        self.set_y(-10)
        self.set_font("Lib", "", 8)
        self.set_text_color(120, 113, 108)
        self.cell(90, 6, "Rapport de veille", align="L")
        self.cell(0, 6, str(self.page_no()), align="R")

    def reste(self) -> float:
        return self.h - 18 - self.get_y()


def _cartes_stats(pdf: RapportPDF, items: list[tuple[str, str]], y: float) -> None:
    largeur = 42
    espace = 3
    x0 = 16
    for i, (valeur, libelle) in enumerate(items):
        x = x0 + i * (largeur + espace)
        pdf.set_fill_color(255, 255, 255)
        pdf.set_draw_color(*pdf.theme["or"])
        _arrondi(pdf, x, y, largeur, 28, 3, "DF")
        pdf.set_xy(x + 2, y + 4)
        pdf.set_font("Lib", "B", 16)
        pdf.set_text_color(*pdf.accent)
        pdf.cell(largeur - 4, 10, valeur, align="C")
        pdf.set_xy(x + 2, y + 16)
        pdf.set_font("Lib", "", 8)
        pdf.set_text_color(87, 83, 78)
        pdf.cell(largeur - 4, 8, libelle, align="C")


def _barre(pdf: RapportPDF, x: float, y: float, largeur: float, ratio: float) -> None:
    pdf.set_fill_color(228, 224, 216)
    _arrondi(pdf, x, y, largeur, 4.2, 2, "F")
    plein = max(1.5, largeur * max(0.0, min(1.0, ratio))) if ratio > 0 else 0
    if plein:
        pdf.set_fill_color(*pdf.accent)
        _arrondi(pdf, x, y, plein, 4.2, 2, "F")


def _titre_section(pdf: RapportPDF, titre: str) -> None:
    if pdf.reste() < 28:
        pdf.add_page()
    pdf.ln(3)
    pdf.set_font("Lib", "B", 14)
    pdf.set_text_color(*pdf.accent)
    pdf.cell(0, 8, titre, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*pdf.theme["or"])
    pdf.set_line_width(0.7)
    y = pdf.get_y()
    pdf.line(16, y, 70, y)
    pdf.set_line_width(0.2)
    pdf.ln(4)
    pdf.set_text_color(28, 25, 23)


def _ligne_volume(pdf: RapportPDF, label: str, n: int, maximum: int) -> None:
    if pdf.reste() < 10:
        pdf.add_page()
    y = pdf.get_y()
    pdf.set_font("Lib", "", 9)
    pdf.set_text_color(45, 42, 40)
    pdf.set_xy(16, y)
    pdf.cell(78, 7, texte_pdf(label)[:48], align="L")
    _barre(pdf, 96, y + 1.5, 72, n / maximum if maximum else 0)
    pdf.set_xy(170, y)
    pdf.set_font("Lib", "B", 9)
    pdf.set_text_color(*pdf.accent)
    pdf.cell(24, 7, str(n), align="R")
    pdf.set_y(y + 8)


def _fiche(
    pdf: RapportPDF,
    article: Article,
    par_id: dict,
    par_tendance: dict,
    numero: int | None = None,
) -> None:
    titre = texte_pdf(titre_propre(article.titre))
    resume = texte_pdf(resume_propre(article.resume, titre))
    if resume:
        resume = tronquer(resume, 220)
    meta = f"{texte_pdf(article.source)}  ·  {formater_date_court(article.date)}"
    badges = [texte_pdf(m) for m in article.mots_trouves[:4]]
    extra = [par_id[d].label for d in article.domaines[1:] if d in par_id]
    tags = [par_tendance[t].label for t in article.tendances if t in par_tendance]
    details = ""
    if extra:
        details = "aussi : " + ", ".join(extra[:3])
    elif tags:
        details = "tendances : " + ", ".join(tags[:3])

    pdf.set_font("Lib", "", 8.5)
    h_resume = 0.0
    if resume:
        h_resume = float(pdf.multi_cell(166, 4, resume, dry_run=True, output="HEIGHT"))
    hauteur = 16.5
    if badges:
        hauteur += 6.4
    if details:
        hauteur += 5.2
    if resume:
        hauteur += h_resume + 2.2
    if pdf.reste() < hauteur + 4:
        pdf.add_page()

    x, y, w = 16, pdf.get_y(), 178
    pdf.set_auto_page_break(auto=False)
    pdf.set_fill_color(255, 255, 255)
    pdf.set_draw_color(228, 224, 216)
    _arrondi(pdf, x, y, w, hauteur, 2.2, "DF")
    pdf.set_fill_color(*pdf.accent)
    pdf.rect(x, y, 1.6, hauteur, "F")
    if numero is not None:
        pdf.set_fill_color(*pdf.theme["or"])
        pdf.ellipse(x + 4.5, y + 2.4, 6.2, 6.2, "F")
        pdf.set_xy(x + 4.5, y + 3.2)
        pdf.set_font("Lib", "B", 8)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(6.2, 4.6, str(numero), align="C")
        pdf.set_xy(x + 13, y + 2.5)
        w_titre = w - 17
    else:
        pdf.set_xy(x + 6, y + 2.5)
        w_titre = w - 10
    pdf.set_font("Lib", "B", 10)
    pdf.set_text_color(28, 25, 23)
    if article.lien:
        pdf.cell(w_titre, 6, titre[:110], link=article.lien)
    else:
        pdf.cell(w_titre, 6, titre[:110])
    pdf.set_xy(x + 6, y + 8.5)
    pdf.set_font("Lib", "I", 8)
    pdf.set_text_color(110, 104, 98)
    pdf.cell(w - 10, 4.5, meta[:110])
    curseur = y + 14
    if badges:
        bx = x + 6
        pdf.set_font("Lib", "", 7.5)
        for badge in badges:
            tw = pdf.get_string_width(badge) + 4
            if bx + tw > x + w - 8:
                break
            pdf.set_fill_color(*pdf.theme["clair"])
            pdf.set_text_color(*pdf.accent)
            _arrondi(pdf, bx, curseur, tw, 4.6, 1.5, "F")
            pdf.set_xy(bx, curseur + 0.4)
            pdf.cell(tw, 3.8, badge, align="C")
            bx += tw + 1.8
        curseur += 6.2
    if details:
        pdf.set_xy(x + 6, curseur)
        pdf.set_font("Lib", "I", 8)
        pdf.set_text_color(120, 113, 108)
        pdf.cell(w - 10, 4, texte_pdf(details)[:120])
        curseur += 5
    if resume:
        pdf.set_xy(x + 6, curseur)
        pdf.set_font("Lib", "", 8.5)
        pdf.set_text_color(68, 64, 60)
        pdf.multi_cell(w - 12, 4, resume)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_y(y + hauteur + 3.2)


def ecrire_rapport_pdf(
    chemin: Path,
    articles: list[Article],
    domaines: list[Domaine],
    tendances: list[Tendance],
    sources: list[Source],
    erreurs: list[tuple[str, str]],
    depuis: datetime,
    nouvelles: list[Source] | None = None,
    profil: Profil | None = None,
) -> None:
    profil = profil or charger_profils()["iot"]
    theme = THEMES.get(profil.identifiant, THEMES["iot"])
    par_id = {d.identifiant: d for d in domaines}
    par_tendance = {t.identifiant: t for t in tendances}
    comptes: dict[str, int] = {d.identifiant: 0 for d in domaines}
    for article in articles:
        if article.domaines:
            comptes[article.domaines[0]] = comptes.get(article.domaines[0], 0) + 1
    orphelins = [a for a in articles if not a.domaines]
    max_compte = max([*comptes.values(), len(orphelins), 1])
    hits_tendances: dict[str, int] = {t.identifiant: 0 for t in tendances}
    for article in articles:
        for identifiant in set(article.tendances):
            hits_tendances[identifiant] = hits_tendances.get(identifiant, 0) + 1
    max_tendance = max([*hits_tendances.values(), 1])
    date_lue = date_longue_fr()
    genere = datetime.now().strftime("%d/%m/%Y à %H:%M")
    nouvelles = nouvelles or []

    pdf = RapportPDF(profil, theme, date_lue)
    pdf.add_page()

    pdf.set_fill_color(*theme["fond"])
    pdf.rect(0, 0, 210, 297, "F")
    pdf.set_fill_color(*theme["accent"])
    pdf.rect(0, 0, 210, 92, "F")
    r, g, b = theme["or"]
    pdf.set_fill_color(min(255, r + 55), min(255, g + 55), min(255, b + 55))
    with pdf.rect_clip(0, 0, 210, 92):
        pdf.ellipse(148, -22, 86, 86, "F")
        pdf.ellipse(-28, 48, 78, 78, "F")
    pdf.couverture = False

    pdf.set_fill_color(*theme["or"])
    _arrondi(pdf, 16, 16, 46, 8, 4, "F")
    pdf.set_xy(16, 17.2)
    pdf.set_font("Lib", "B", 8)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(46, 6, "ÉDITION DU JOUR", align="C")

    pdf.set_xy(16, 30)
    pdf.set_font("Lib", "B", 28)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, profil.titre)
    pdf.set_xy(16, 46)
    pdf.set_font("Lib", "", 13)
    pdf.cell(0, 7, texte_pdf(theme["accroche"]))
    pdf.set_xy(16, 58)
    pdf.set_font("Lib", "I", 11)
    pdf.cell(0, 6, date_lue)
    pdf.set_xy(16, 72)
    pdf.set_font("Lib", "", 9)
    pdf.cell(
        0,
        5,
        f"Depuis le {depuis.astimezone().strftime('%d/%m/%Y')}  ·  généré le {genere}",
    )

    _cartes_stats(
        pdf,
        [
            (str(len(articles)), "articles"),
            (str(len(sources)), "sources"),
            (str(len(nouvelles)), "nouvelles sources"),
            (f"{sum(1 for a in articles if a.domaines)}", "classés"),
        ],
        102,
    )

    pdf.set_y(138)
    pdf.set_font("Lib", "B", 13)
    pdf.set_text_color(*theme["accent"])
    pdf.cell(0, 8, "Cette semaine, en un coup d'oeil", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    for domaine in domaines:
        n = comptes.get(domaine.identifiant, 0)
        if n:
            _ligne_volume(pdf, domaine.label, n, max_compte)
    if orphelins:
        _ligne_volume(pdf, profil.orphelins, len(orphelins), max_compte)

    if pdf.reste() < 32:
        pdf.add_page()
    pdf.ln(4)
    pdf.set_fill_color(*theme["clair"])
    y = pdf.get_y()
    perimetre = texte_pdf(profil.perimetre)
    pdf.set_font("Lib", "", 8.5)
    h_text = pdf.multi_cell(166, 4.2, perimetre, dry_run=True, output="HEIGHT")
    h_box = max(22.0, 14.0 + float(h_text))
    if pdf.reste() < h_box + 6:
        pdf.add_page()
        y = pdf.get_y()
    _arrondi(pdf, 16, y, 178, h_box, 3, "F")
    pdf.set_xy(22, y + 4)
    pdf.set_font("Lib", "B", 9)
    pdf.set_text_color(*theme["accent"])
    pdf.cell(0, 5, "Périmètre")
    pdf.set_xy(22, y + 11)
    pdf.set_font("Lib", "", 8.5)
    pdf.set_text_color(55, 50, 48)
    pdf.multi_cell(166, 4.2, perimetre)

    pdf.add_page()
    _titre_section(pdf, "Tendances détectées")
    tendance_vue = False
    for tendance in tendances:
        n = hits_tendances.get(tendance.identifiant, 0)
        if not n:
            continue
        tendance_vue = True
        _ligne_volume(pdf, tendance.label, n, max_tendance)
    if not tendance_vue:
        pdf.set_font("Lib", "I", 10)
        pdf.set_text_color(110, 104, 98)
        pdf.cell(0, 8, "Aucune tendance forte détectée sur la période.", new_x="LMARGIN", new_y="NEXT")

    if nouvelles:
        _titre_section(pdf, "Nouvelles sources")
        for source in nouvelles:
            if pdf.reste() < 8:
                pdf.add_page()
            pdf.set_font("Lib", "B", 9)
            pdf.set_text_color(*theme["accent"])
            pdf.cell(70, 6, texte_pdf(source.nom)[:40])
            pdf.set_font("Lib", "", 8)
            pdf.set_text_color(90, 86, 82)
            pdf.cell(0, 6, texte_pdf(source.url or source.site)[:70], new_x="LMARGIN", new_y="NEXT", link=source.url or source.site)

    une = articles[:5]
    if une:
        _titre_section(pdf, "À la une")
        for i, article in enumerate(une, start=1):
            _fiche(pdf, article, par_id, par_tendance, numero=i)

    for domaine in domaines:
        selection = [a for a in articles if a.domaines and a.domaines[0] == domaine.identifiant]
        if not selection:
            continue
        _titre_section(pdf, f"{domaine.label}  ({len(selection)})")
        for article in selection:
            _fiche(pdf, article, par_id, par_tendance)

    if orphelins:
        _titre_section(pdf, f"{profil.orphelins}  ({len(orphelins)})")
        for article in orphelins:
            _fiche(pdf, article, par_id, par_tendance)

    _titre_section(pdf, "Sources interrogées")
    erreurs_par_nom = {nom: motif for nom, motif in erreurs}
    for source in sources:
        if pdf.reste() < 7:
            pdf.add_page()
        nom = texte_pdf(source.nom)
        if source.nouvelle:
            nom = f"{nom}  (nouvelle)"
        pdf.set_font("Lib", "", 8)
        pdf.set_text_color(40, 37, 35)
        pdf.cell(88, 5, nom[:52])
        if source.nom in erreurs_par_nom:
            pdf.set_text_color(159, 18, 57)
            pdf.cell(0, 5, f"inaccessible — {texte_pdf(erreurs_par_nom[source.nom])[:40]}", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_text_color(110, 104, 98)
            pdf.cell(0, 5, texte_pdf(source.site or "ok")[:55], new_x="LMARGIN", new_y="NEXT", link=source.site or "")

    pdf.output(str(chemin))
