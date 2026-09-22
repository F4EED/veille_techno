# Veille techno

Outil local de veille. Il interroge des flux RSS, Google News et les réseaux sociaux, classe les articles par thème, écrit un rapport PDF et HTML, l’envoie par e-mail, puis le dépose sur les Pages Perso Free.

Cinq veilles tournent en parallèle :

| Profil | Rapport | Thème |
| --- | --- | --- |
| `iot` | `Veille_IOT` | Objets connectés, LoRa, mesh, routes |
| `crise` | `Veille_Crise` | Risques, alertes, gestion de crise |
| `radio` | `Veille_Radio` | Radioamateur, modes digitaux, trafic |
| `outils` | `Veille_Outils_PC` | Outils de gestion de crise et poste de commandement |
| `blackout` | `Veille_Blackout` | Black-out, réseau électrique, déclarations de l’exécutif |

Le détail de chaque veille est dans [docs/profils.md](docs/profils.md).

## Lancer

Python 3, puis :

```bash
python3 -m pip install --target .vendor -r requirements.txt
cp config/email.secrets.yaml.example config/email.secrets.yaml
./lancer.sh
```

`lancer.sh` installe les dépendances dans `.vendor` s’il le faut, puis lance les cinq profils.

Un seul profil :

```bash
./lancer.sh --profil iot
./lancer.sh --profil crise
./lancer.sh --profil radio
./lancer.sh --profil outils
./lancer.sh --profil blackout
```

Options transmises à chaque veille :

```bash
./lancer.sh --jours 14
./lancer.sh --sans-decouverte
./lancer.sh --sans-email
./lancer.sh --sans-traduction
```

La fenêtre par défaut est de 7 jours (`periode_jours` dans le fichier de mots-clés). La veille black-out remonte 14 jours. Les titres et résumés anglais sont traduits en français quand le service de traduction répond.

## Où lire les résultats

Chaque lancement écrit, dans ce dossier :

- `Veille_<Profil>_AAAA-MM-JJ_HH-MM-SS.pdf`
- le même nom en `.html`
- une copie courte `Veille_<Profil>.pdf` et `.html`

Ces fichiers ne sont pas versionnés. Ils sont publiés sur [f4eed.pages-perso.free.fr/veille](https://f4eed.pages-perso.free.fr/veille/). La page [Anciennes veilles](https://f4eed.pages-perso.free.fr/veille/archives.html) liste les rapports datés déjà en ligne.

L’e-mail part de `f4eed@free.fr` vers les destinataires de `config/email.yaml`. Il contient les liens vers le PDF et le HTML, pas de pièce jointe.

Pages Perso ne fait qu’afficher les fichiers déposés par FTP. Le script Python ne peut pas y tourner : pas d’interpréteur Python, et une veille complète dure plusieurs minutes. On la relance sur ce poste avec `./lancer.sh`.

## Documentation

- [Les cinq veilles](docs/profils.md)
- [Sources, mots-clés et découverte](docs/sources.md)
- [E-mail, publication et archives](docs/publication.md)

## Fichiers du programme

| Fichier | Rôle |
| --- | --- |
| `lancer.sh` | Lance une ou les cinq veilles |
| `veille.py` | Collecte, filtre, rapport HTML |
| `traduction.py` | Traduction des titres et résumés anglais |
| `rapport_pdf.py` | PDF |
| `decouverte.py` | Recherche de nouveaux flux RSS |
| `email_envoi.py` | Envoi SMTP |
| `publication.py` | Dépôt FTP et pages `index.html` / `archives.html` |
| `config/` | Mots-clés, sources, e-mail |
