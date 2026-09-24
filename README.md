# Veille techno

Outil local de veille. Il interroge des flux RSS, Google News et les réseaux sociaux, classe les articles par thème, écrit un rapport PDF et HTML, l’envoie par e-mail, puis le dépose sur les Pages Perso Free.

Sept veilles tournent en parallèle :

| Profil | Rapport | Thème |
| --- | --- | --- |
| `iot` | `Veille_IOT` | Objets connectés, LoRa, mesh, routes |
| `crise` | `Veille_Crise` | Risques, alertes, gestion de crise |
| `radio` | `Veille_Radio` | Radioamateur, modes digitaux, trafic |
| `outils` | `Veille_Outils_PC` | Outils de gestion de crise et poste de commandement |
| `blackout` | `Veille_Blackout` | Black-out, réseau électrique, déclarations de l’exécutif |
| `geomatique` | `Veille_Geomatique` | Géomatique, QGIS, cartographie, données géographiques |
| `mesh` | `Veille_Mesh` | Réseaux mesh, Meshtastic, MeshCore, mesh Wi-Fi |

Les sept lisent le même catalogue, `config/sources.yaml`. Une source ajoutée dans ce fichier est vue par toutes ; chaque veille ne garde que les articles qui correspondent à ses mots-clés. Le détail est dans [docs/profils.md](docs/profils.md).

## Lancer

Python 3, puis :

```bash
python3 -m pip install --target .vendor -r requirements.txt
cp config/email.secrets.yaml.example config/email.secrets.yaml
./lancer.sh
```

`lancer.sh` installe les dépendances dans `.vendor` s’il le faut, puis lance les sept profils.

Un seul profil :

```bash
./lancer.sh --profil iot
./lancer.sh --profil crise
./lancer.sh --profil radio
./lancer.sh --profil outils
./lancer.sh --profil blackout
./lancer.sh --profil geomatique
./lancer.sh --profil mesh
```

Options transmises à chaque veille :

```bash
./lancer.sh --jours 14
./lancer.sh --sans-decouverte
./lancer.sh --sans-email
./lancer.sh --sans-traduction
```

La fenêtre par défaut est de 7 jours (`periode_jours` dans le fichier de mots-clés). La veille black-out remonte 14 jours. Les titres et résumés anglais sont traduits en français quand le service de traduction répond.

## PC dédié, envoi à 7 h

Copier ce dossier sur le PC qui reste allumé, puis lancer l’installeur une fois.

Linux (Ubuntu ou Debian, dont Debian 13) :

```bash
chmod +x installer-linux.sh
./installer-linux.sh
```

Si le compte Debian n’a pas sudo :

```bash
su -c './installer-linux.sh'
```

Windows : double-clic sur `installer-windows.bat`.

L’installeur met Python 3, les bibliothèques, la police des PDF et le mot de passe de la boîte mail. Il empêche la mise en veille et programme les sept veilles tous les jours à 7 h 00, à l’heure affichée par le PC. Si le PC était éteint à cette heure, l’envoi part au démarrage suivant. Le journal est `.runlogs/quotidien.log`.

Essai immédiat : `./lancer.sh` ou `lancer.bat`.

## Où lire les résultats

Chaque lancement écrit, dans ce dossier :

- `Veille_<Profil>_AAAA-MM-JJ_HH-MM-SS.pdf`
- le même nom en `.html`
- une copie courte `Veille_<Profil>.pdf` et `.html`

Ces fichiers ne sont pas versionnés. Ils sont publiés sur [f4eed.pages-perso.free.fr/veille](https://f4eed.pages-perso.free.fr/veille/). La page [Anciennes veilles](https://f4eed.pages-perso.free.fr/veille/archives.html) liste les rapports datés déjà en ligne.

L’e-mail part de `f4eed@free.fr` vers les destinataires de `config/email.yaml`. Il contient les liens vers le PDF et le HTML, pas de pièce jointe.

Pages Perso ne fait qu’afficher les fichiers déposés par FTP. Le script Python ne peut pas y tourner : pas d’interpréteur Python, et une veille complète dure plusieurs minutes. On la relance sur ce poste avec `./lancer.sh`.

## Documentation

- [Les sept veilles](docs/profils.md)
- [Sources, mots-clés et découverte](docs/sources.md)
- [Paramétrer l’envoi et le site](docs/paramétrage.md)
- [E-mail, publication et archives](docs/publication.md)

## Fichiers du programme

| Fichier | Rôle |
| --- | --- |
| `lancer.sh` | Lance une ou les sept veilles |
| `installer-linux.sh` | Installe les prérequis et l’envoi quotidien à 7 h (Ubuntu et Debian) |
| `installer-windows.bat` | Idem sous Windows |
| `lancer.bat` | Lance les veilles sous Windows |
| `veille.py` | Collecte, filtre, rapport HTML |
| `traduction.py` | Traduction des titres et résumés anglais |
| `rapport_pdf.py` | PDF |
| `decouverte.py` | Recherche de nouveaux flux RSS |
| `email_envoi.py` | Envoi SMTP |
| `publication.py` | Dépôt FTP et pages `index.html` / `archives.html` |
| `config/sources.yaml` | Catalogue unique lu par les sept veilles |
| `config/` | Mots-clés, e-mail, réseaux sociaux |
