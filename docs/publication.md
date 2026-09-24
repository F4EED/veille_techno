# E-mail, publication et archives

## E-mail

`config/email.yaml` indique l’expéditeur, les destinataires et le serveur SMTP (`smtp.free.fr`, port 465, SSL).

Le mot de passe n’est pas dans ce fichier. Il se place dans `config/email.secrets.yaml` (modèle : `config/email.secrets.yaml.example`) ou dans la variable d’environnement `VEILLE_SMTP_PASSWORD`. Ce fichier de secrets est ignoré par git.

`--sans-email` génère les rapports sans les envoyer. `actif: false` dans `email.yaml` désactive aussi l’envoi.

## Pages Perso

Quand l’envoi d’e-mail est actif, `publication.py` dépose le PDF et le HTML du jour par FTP (`ftpperso.free.fr`, dossier `veille`) puis réécrit :

- [la page du jour](https://f4eed.pages-perso.free.fr/veille/)
- [la page des anciennes veilles](https://f4eed.pages-perso.free.fr/veille/archives.html)

Ces deux pages tiennent sur un petit écran : une seule colonne, textes qui reviennent à la ligne, marges pour les encoches, et liens assez hauts pour le doigt.

L’archive regroupe les rapports dont le nom contient une date (`Veille_<Profil>_AAAA-MM-JJ.pdf` ou `Veille_<Profil>_AAAA-MM-JJ_HH-MM-SS.pdf`), du plus récent au plus ancien, avec le PDF et la lecture dans le navigateur. Les copies courtes `Veille_IOT.pdf` et les autres alias sans date n’y figurent pas.

Les noms des rapports du jour sont mémorisés dans `config/rapports_courants.yaml`, lui aussi ignoré par git. La page d’accueil s’en sert pour pointer vers le fichier horodaté.

## Ce que Pages Perso ne fait pas

L’hébergement Free sert les fichiers déjà déposés, et du PHP. Il n’exécute pas Python. La collecte des flux, la fabrication des PDF et l’envoi des courriels restent sur le poste qui lance `./lancer.sh`.

Un bouton « Actualiser » sur la page publique ne peut donc pas relancer une veille. Le fichier `serveur_actualiser.py` écoute seulement en local (`127.0.0.1:8765`) ; il n’est pas branché sur la page en ligne.
