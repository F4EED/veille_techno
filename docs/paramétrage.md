# Paramétrage de l’envoi et du site

Tout se règle dans `config/email.yaml`. Le mot de passe n’y figure pas : il est dans `config/email.secrets.yaml`, ignoré par git. Le modèle est `config/email.secrets.yaml.example`.

L’installeur demande ce mot de passe une fois. On peut le changer ensuite en éditant le fichier de secrets, puis relancer `./lancer.sh`.

## Ajouter des destinataires

La liste `destinataires` reçoit un courriel par adresse, avec les liens vers le PDF et le HTML du rapport. Une ligne par adresse :

```yaml
destinataires:
  - frederic.f4eed@gmail.com
  - autre.personne@example.com
```

Enregistrer le fichier. Le prochain envoi, à 7 h ou avec `./lancer.sh`, utilise la liste telle quelle. Aucune autre étape.

`actif: false` en tête du fichier coupe l’envoi. Les rapports sont quand même créés sur le PC.

## Boîte qui envoie

`expediteur` est l’adresse visible dans le champ De. `expediteur_nom` est le nom affiché à côté.

```yaml
actif: true
expediteur: f4eed@free.fr
expediteur_nom: Veille
```

Le serveur SMTP est le bloc `smtp` :

```yaml
smtp:
  hote: smtp.free.fr
  port: 465
  utilisateur: f4eed@free.fr
  demarrer_tls: false
  ssl: true
```

`utilisateur` est le compte qui s’authentifie. Avec Free, c’est l’adresse complète de la boîte.

Le mot de passe se pose dans `config/email.secrets.yaml` :

```yaml
mot_de_passe: "le mot de passe de la boîte"
```

On peut à la place définir la variable d’environnement `VEILLE_SMTP_PASSWORD`. Elle prime sur le fichier.

Pour une boîte Gmail, `hote` devient `smtp.gmail.com`. Le mot de passe est un mot de passe d’application (16 lettres), pas le mot de passe habituel du compte. Dans ce cas le PDF part en pièce jointe, et le dépôt sur le site décrit plus bas n’est pas fait.

## Site où est déposé index.html

Le bloc `publication` indique le serveur FTP et l’adresse publique de la page d’accueil. Après chaque envoi, le PDF, le HTML et `index.html` sont déposés dans le dossier distant. `archives.html` est réécrit à côté.

```yaml
publication:
  actif: true
  hote: ftpperso.free.fr
  utilisateur: f4eed
  dossier: veille
  url_base: https://f4eed.pages-perso.free.fr
```

| Champ | Rôle |
| --- | --- |
| `actif` | `false` laisse les rapports sur le PC, sans dépôt FTP |
| `hote` | Serveur FTP. Free : `ftpperso.free.fr` |
| `utilisateur` | Identifiant FTP. Free : le login Pages Perso, sans `@` |
| `dossier` | Dossier distant. `index.html` y est écrit |
| `url_base` | Début de l’adresse publique, sans le dossier et sans slash final |

L’adresse de la page d’accueil est `url_base` + `/` + `dossier` + `/`. Avec les valeurs ci-dessus : `https://f4eed.pages-perso.free.fr/veille/`. Les liens des courriels sont construits de la même façon.

Le mot de passe FTP est le même que celui du SMTP, dans `config/email.secrets.yaml`.

`publication.actif: false` n’empêche pas les courriels. `actif: false` tout en haut du fichier coupe les deux.
