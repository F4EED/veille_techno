# Sources, mots-clés et découverte

## Mots-clés

Chaque veille a un fichier `config/keywords*.yaml` :

- `periode_jours` : nombre de jours remontés si `--jours` n’est pas passé. Aucune veille ne publie un article daté d’avant le 1er janvier 2025, y compris Google News et les réseaux sociaux.
- `domaines` : rubriques du rapport, avec une priorité et une liste de mots-clés
- `tendances` : étiquettes supplémentaires, qui ne font pas entrer un article à elles seules

Les alias français et anglais, avec ou sans accents, sont normalisés à l’exécution. Dans un domaine, les mots-clés se combinent par OU. L’article est rangé dans le domaine de plus haute priorité qui matche.

## Fichier de sources

Toutes les veilles lisent `config/sources.yaml` : flux RSS, Google News, réseaux sociaux et services WMS. `config/reseaux_sociaux.yaml` indique seulement les sites des réseaux (LinkedIn, Mastodon, etc.).

Une source ajoutée dans `config/sources.yaml` est lue par les sept veilles. Chacune garde les articles qui correspondent à ses mots-clés. Un flux marqué `filtre: aucun` avec `profils` est repris en entier par les veilles listées ; les autres n’en gardent que les articles qui matchent.

Un flux s’écrit ainsi :

```yaml
flux:
  - id: exemple
    nom: Nom lisible
    url: https://exemple.fr/rss
    site: https://exemple.fr
    filtre: mots_cles
```

`filtre` :

- `mots_cles` : l’article n’est gardé que si un mot-clé du profil matche
- `aucun` : tous les articles de la période sont gardés, pour les veilles citées dans `profils`

Un dépôt GitHub du périmètre s’ajoute dans `config/sources.yaml` avec l’adresse `https://github.com/orga/depot/releases.atom`, `filtre: aucun`, le `domaine` de la rubrique et `profils` pour la veille concernée. La liste des dépôts de chaque veille est dans [profils.md](profils.md).

Si la source porte aussi un `domaine` connu de la veille, ce domaine lui est attribué d’office. Le filtre par mots-clés ne l’écarte plus. On réserve ça à une requête déjà ciblée, par exemple une recherche Google News étroite.

Google News se déclare dans `google_news` (`id`, `label`, `query`, `hl`, `gl`, `ceid`, et au besoin `filtre` et `domaine`). Chaque requête est un flux distinct : l’adresse complète, paramètres compris, sert d’identité. Sans `filtre`, une requête Google News est prise en entier (`aucun`).

Un site sans RSS public s’ajoute en Google News avec `site:domaine.fr`.

Un service WMS (donnée cartographique, pas un fil d’articles) s’ajoute dans `wms` de `config/sources.yaml` (`id`, `nom`, `url` du GetCapabilities, `site`). À chaque lancement, la veille cherche aussi de nouveaux services WMS et les enregistre dans ce même fichier. Le rapport les regroupe dans la rubrique Flux WMS, anciens et nouveaux. Ils ne sont pas lus comme des flux RSS.

## Découverte

À chaque lancement, chaque veille cherche de nouveaux flux dans son périmètre, et de nouveaux services WMS. Les trouvailles sont ajoutées à `config/sources.yaml` avec `filtre: mots_cles`, donc les sept veilles les lisent ensuite. Une URL déjà connue est ignorée. `--sans-decouverte` saute ces deux recherches ; les services WMS déjà enregistrés restent listés dans le rapport.

Les caches `config/decouverte_cache*.yaml` et `config/traduction_cache.json` restent sur le poste. Ils ne sont pas versionnés.

## Ajouter une source à la main

1. Vérifier que l’adresse répond en XML (RSS ou Atom), pas en page HTML ni en 404.
2. L’ajouter dans `config/sources.yaml`, dans `flux`, `google_news` ou `wms`.
3. Ne pas réutiliser un `id` ni une URL déjà présents dans ce fichier.
4. Mettre `filtre: mots_cles`. Si le flux ne parle que d’une veille, mettre `filtre: aucun` et `profils` avec son identifiant (`iot`, `crise`, `radio`, `outils`, `blackout`, `geomatique` ou `mesh`) : les autres veilles ne gardent alors que les articles qui matchent leurs mots-clés.
