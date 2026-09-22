# Les cinq veilles

Chaque profil a ses mots-clés, ses flux dédiés et son fichier de sources découvertes. Toutes partagent la presse nationale, la presse d’Auvergne-Rhône-Alpes, la presse informatique et les réseaux sociaux. Voir [sources.md](sources.md).

## Veille_IOT

Fichier : `config/keywords.yaml`. Sources : `config/sources.yaml`.

- IoT et objets connectés
- LoRa et LoRaWAN
- Mesh, Meshtastic, Meshcore
- Industrie et IIoT
- Routes et gestion routière
- Main courante
- Radio (PMR, TETRA, DMR)

## Veille_Crise

Fichier : `config/keywords_crise.yaml`. Sources : `config/sources_crise.yaml`, plus `config/sources_crise_territoires.yaml`.

- Crise, crisis, crisi, gestion de crise
- Inondation
- Tremblement de terre
- Catastrophe
- Aléa climatique
- Aléa technologique

Sources dédiées : IRMA Grenoble, Vigilance Météo-France, Vigicrues, et la presse régionale de toute la France (France 3, ICI / France Bleu, BFM locales, presse quotidienne régionale).

## Veille_Radio

Fichier : `config/keywords_radio.yaml`. Sources : `config/sources_radio.yaml`.

- Radio, hamradio, radioamateur
- Modes digitaux (FT8, JS8, Winlink, DMR, D-STAR)
- Trafic
- Radio professionnelle (PMR, TETRA, DMR)
- SDR, APRS, relais
- HF, VHF, UHF

## Veille_Outils_PC

Fichier : `config/keywords_outils.yaml`. Sources : `config/sources_outils.yaml`, plus `config/sources_crise_territoires.yaml`.

- Logiciels de gestion de crise
- Poste de commandement (PCO, PCA, PCC, salle de crise)
- Main courante numérique
- ORSEC, SYNERGI, NexSIS, COGIC, CODIS
- Éditeurs (Everbridge, WebEOC, Hexagon, Systel)

## Veille_Blackout

Fichier : `config/keywords_blackout.yaml`. Fenêtre de 14 jours. Sources : `config/sources_blackout.yaml`, plus `config/sources_crise_territoires.yaml`.

- Black-out, panne géante, coupure généralisée en France
- Exercice national de black-out, CIRN, SGDSN, guide « Tous résilients »
- Déclarations récentes de l’Élysée et d’Emmanuel Macron sur l’énergie, les carburants et la résilience, et les articles qui en découlent
- Réseau électrique, délestage, EcoWatt, RTE, Enedis
- Sabotage et cyberattaque du réseau

Le nom « Emmanuel Macron » n’est pas un mot-clé d’inclusion : il ferait entrer toute l’actualité présidentielle. Ses prises de parole sur ce thème arrivent par le flux de l’Élysée et par des requêtes Google News dédiées. La tendance `macron` ne sert qu’à étiqueter les articles déjà retenus.

Les sites d’État sans RSS public (SGDSN, gouvernement, Vie publique, RTE, Enedis, CRE, Cour des comptes) sont interrogés par Google News avec `site:`.
