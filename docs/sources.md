# Sources, mots-clés et découverte

## Mots-clés

Chaque veille a un fichier `config/keywords*.yaml` :

- `periode_jours` : nombre de jours remontés si `--jours` n’est pas passé
- `domaines` : rubriques du rapport, avec une priorité et une liste de mots-clés
- `tendances` : étiquettes supplémentaires, qui ne font pas entrer un article à elles seules

Les alias français et anglais, avec ou sans accents, sont normalisés à l’exécution. Dans un domaine, les mots-clés se combinent par OU. L’article est rangé dans le domaine de plus haute priorité qui matche.

## Fichiers de sources

| Fichier | Qui l’utilise |
| --- | --- |
| `config/sources.yaml` | IoT |
| `config/sources_crise.yaml` | Crise |
| `config/sources_radio.yaml` | Radio |
| `config/sources_outils.yaml` | Outils de PC |
| `config/sources_blackout.yaml` | Black-out |
| `config/sources_presse.yaml` | Les cinq veilles (presse nationale et Auvergne-Rhône-Alpes) |
| `config/sources_tech.yaml` | Les cinq veilles (informatique, technique, IA, développement) |
| `config/sources_auto.yaml` | Les cinq veilles (sources ajoutées au fil de l’eau) |
| `config/sources_crise_territoires.yaml` | Crise, outils de PC et black-out (presse régionale de France) |
| `config/reseaux_sociaux.yaml` | Les cinq veilles |

Les articles de la presse partagée ne sont gardés que s’ils correspondent aux mots-clés du profil.

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
- `aucun` : tous les articles de la période sont gardés (source déjà dédiée au sujet)

Si la source porte aussi un `domaine`, ce domaine lui est attribué d’office. Le filtre par mots-clés ne l’écarte plus. On réserve ça à une requête déjà ciblée, par exemple une recherche Google News étroite.

Google News se déclare dans `google_news` (`id`, `label`, `query`, `hl`, `gl`, `ceid`, et au besoin `filtre` et `domaine`). Chaque requête est un flux distinct : l’adresse complète, paramètres compris, sert d’identité. Sans `filtre`, une requête Google News est prise en entier (`aucun`).

Un site sans RSS public s’ajoute en Google News avec `site:domaine.fr`.

## Découverte

À chaque lancement, le programme cherche de nouveaux flux et les ajoute à `config/sources_auto.yaml` et au `config/sources_decouvertes_*.yaml` du profil. Une URL déjà connue est ignorée. `--sans-decouverte` saute cette étape.

Les caches `config/decouverte_cache*.yaml` et `config/traduction_cache.json` restent sur le poste. Ils ne sont pas versionnés.

## Ajouter une source à la main

1. Vérifier que l’adresse répond en XML (RSS ou Atom), pas en page HTML ni en 404.
2. Choisir le fichier du tableau ci-dessus. Une source hors de ces catégories va dans `config/sources_auto.yaml`.
3. Ne pas réutiliser un `id` ni une URL déjà présents, y compris dans les `sources_decouvertes*.yaml`.
4. Mettre `filtre: mots_cles`, sauf si le flux ne parle que du sujet de la veille : alors `filtre: aucun`.
