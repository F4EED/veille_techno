# Les sept veilles

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

Dépôts GitHub suivis par `releases.atom` : ChirpStack, The Things Stack, ESPHome, Tasmota, Zigbee2MQTT, Mosquitto, Node-RED, ThingsBoard, plus Meshtastic et MeshCore.

## Veille_Crise

Fichier : `config/keywords_crise.yaml`. Sources : `config/sources_crise.yaml`, plus `config/sources_crise_territoires.yaml`.

- Crise, crisis, crisi, gestion de crise
- Inondation
- Tremblement de terre
- Catastrophe
- Aléa climatique
- Aléa technologique

Sources dédiées : IRMA Grenoble, Vigilance Météo-France, Vigicrues, et la presse régionale de toute la France (France 3, ICI / France Bleu, BFM locales, presse quotidienne régionale).

Dépôts GitHub suivis par `releases.atom` : Ushahidi, OpenQuake, InaSAFE, CLIMADA.

## Veille_Radio

Fichier : `config/keywords_radio.yaml`. Sources : `config/sources_radio.yaml`.

- Radio, hamradio, radioamateur
- Modes digitaux (FT8, JS8, Winlink, DMR, D-STAR)
- Trafic
- Radio professionnelle (PMR, TETRA, DMR)
- SDR, APRS, relais
- HF, VHF, UHF

Dépôts GitHub suivis par `releases.atom` : GNU Radio, SDRangel, SDR++, OpenWebRX, Universal Radio Hacker, Dire Wolf, Hamlib, qdmr, Pat Winlink, dsd-fme.

## Veille_Outils_PC

Fichier : `config/keywords_outils.yaml`. Sources : `config/sources_outils.yaml`, plus `config/sources_crise_territoires.yaml`.

- Logiciels de gestion de crise
- Poste de commandement (PCO, PCA, PCC, salle de crise)
- Main courante numérique
- ORSEC, SYNERGI, NexSIS, COGIC, CODIS
- Éditeurs (Everbridge, WebEOC, Hexagon, Systel)

Dépôts GitHub suivis par `releases.atom` : Sahana Eden (poste de commandement) et KoboToolbox.

## Veille_Blackout

Fichier : `config/keywords_blackout.yaml`. Fenêtre de 14 jours. Sources : `config/sources_blackout.yaml`, plus `config/sources_crise_territoires.yaml`.

- Black-out, panne géante, coupure généralisée en France
- Exercice national de black-out, CIRN, SGDSN, guide « Tous résilients »
- Déclarations récentes de l’Élysée et d’Emmanuel Macron sur l’énergie, les carburants et la résilience, et les articles qui en découlent
- Réseau électrique, délestage, EcoWatt, RTE, Enedis
- Sabotage et cyberattaque du réseau

Le nom « Emmanuel Macron » n’est pas un mot-clé d’inclusion : il ferait entrer toute l’actualité présidentielle. Ses prises de parole sur ce thème arrivent par le flux de l’Élysée et par des requêtes Google News dédiées. La tendance `macron` ne sert qu’à étiqueter les articles déjà retenus.

Les sites d’État sans RSS public (SGDSN, gouvernement, Vie publique, RTE, Enedis, CRE, Cour des comptes) sont interrogés par Google News avec `site:`.

Dépôts GitHub suivis par `releases.atom` : Antares Simulator, Grid2Op (RTE), OpenEMS, PyPSA, Emoncms, oemof.

## Veille_Geomatique

Fichier : `config/keywords_geomatique.yaml`. Sources : `config/sources_geomatique.yaml`.

Le rapport reste une seule veille, Géomatique, avec ces sous-rubriques. L’article va dans la plus précise :

- Lidar
- Relevés (prises de vue aériennes, photogrammétrie, levés topographiques, drones)
- Cartographie d'urgence et de crise
- IA géomatique
- Outils (QGIS, PostGIS, GDAL, outils de géomatique et de cartographie)
- Données (Géoplateforme, BD TOPO, cadastre, adresses, open data)
- Général (géomatique, cartographie, IGN, OpenStreetMap, BRGM)

Les sites des SDIS qui publient un flux sont suivis pour la cartographie et l’open data (points d’eau incendie, SIG opérationnel). Leurs autres actualités ne sont pas retenues.

Sources dédiées : IGN, Géoportail, OpenStreetMap, hebdoOSM, QGIS, Geotribu, Afigéo, CNIG, OSGeo, OGC. Le BRGM, Géorisques, le SHOM, cartes.gouv.fr et le CRAIG (craig.fr, ids.craig.fr) n’ont pas de flux RSS utile : ils sont interrogés par Google News avec `site:`. Les services WMS du CRAIG (accès ouvert et PCRS) sont dans la rubrique Flux WMS.

Dépôts GitHub suivis par `releases.atom` : QGIS, GDAL, GeoServer, PostGIS, PROJ, GRASS GIS, OpenLayers, MapLibre, GeoPandas, PDAL, iD (OpenStreetMap), HOT Tasking Manager, cartes.gouv.fr (IGN).

À chaque lancement, les nouveaux flux trouvés sont ajoutés à `config/sources_decouvertes_geomatique.yaml` et à `config/sources_auto.yaml`. Les nouveaux services WMS sont cherchés en même temps et ajoutés à `config/sources_wms_decouvertes.yaml`. Le rapport les regroupe dans la rubrique Flux WMS, avec les services déjà connus.

## Veille_Mesh

Fichier : `config/keywords_mesh.yaml`. Sources : `config/sources_mesh.yaml`.

Le rapport reste une seule veille, Mesh, avec ces sous-rubriques. L’article va dans la plus précise :

- Meshtastic
- MeshCore
- Général (mesh Wi-Fi, réseaux maillés, 802.11s, Reticulum, Yggdrasil, cjdns)

Sources dédiées : blog Meshtastic, dépôts GitHub Meshtastic, blog MeshCore, dépôts MeshCore, Reticulum, RNode, Hackaday Meshtastic, Reddit r/meshtastic. reticulum.network et unsigned.io n’ont pas de flux RSS : ils sont interrogés par Google News avec `site:`. LinkedIn, X, Mastodon, Bluesky et Threads sont interrogés sur Meshtastic, MeshCore et le mesh Wi-Fi.

À chaque lancement, les nouveaux flux trouvés sont ajoutés à `config/sources_decouvertes_mesh.yaml` et à `config/sources_auto.yaml`.
