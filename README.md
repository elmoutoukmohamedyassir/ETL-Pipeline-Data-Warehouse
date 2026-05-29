# Mexora ETL — Data Warehouse Pipeline

Projet de Data Engineering — Mexora Analytics, Tanger.

## Prérequis

- Python 3.11+
- pandas (`pip install pandas`)
- PostgreSQL 15+ (optionnel — le pipeline tourne aussi en mode CSV local)

```bash
pip install pandas sqlalchemy psycopg2-binary
```

## Structure du projet

```
mexora_etl/
├── config/
│   └── settings.py           # paramètres de connexion, chemins, constantes
├── data/
│   ├── generate_data.py       # générateur des 4 fichiers sources
│   ├── commandes_mexora.csv   # 51 500 lignes brutes (avec problèmes)
│   ├── clients_mexora.csv     # 3 000 clients bruts
│   ├── produits_mexora.json   # 20 produits bruts
│   └── regions_maroc.csv      # référentiel géographique (propre)
├── extract/
│   └── extractor.py           # lecture brute des 4 sources
├── transform/
│   ├── clean_commandes.py     # 9 règles de nettoyage commandes
│   ├── clean_clients.py       # 5 règles de nettoyage clients + segmentation
│   ├── clean_produits.py      # 3 règles de nettoyage produits
│   └── build_dimensions.py    # construction des 5 dimensions + table de faits
├── load/
│   └── loader.py              # chargement CSV local ou PostgreSQL
├── utils/
│   └── logger.py              # logging uniforme avant/après chaque règle
├── sql/
│   ├── create_dwh.sql         # DDL complet : schémas, tables, index, vues mat.
│   ├── check_integrity.sql    # contrôles qualité post-chargement
│   └── analytics_queries.sql  # 5 requêtes pour les KPIs du dashboard
├── output/                    # CSV produits après un run (gitignorés)
├── logs/                      # fichiers de log horodatés (gitignorés)
├── docs/
│   ├── rapport_modelisation.md
│   └── rapport_transformations.md
├── main.py                    # point d'entrée du pipeline
└── README.md
```

## Lancer le pipeline

### Étape 0 — Générer les données sources

```bash
cd mexora_etl
python3 data/generate_data.py
```

Produit : `data/commandes_mexora.csv` (51 500 lignes), `data/clients_mexora.csv`,
`data/produits_mexora.json`, `data/regions_maroc.csv`.

### Étape 1 — Mode CSV local (sans PostgreSQL)

```bash
python3 main.py
```

Les tables nettoyées sont exportées dans `output/` :
`dim_temps.csv`, `dim_produit.csv`, `dim_client.csv`, `dim_region.csv`,
`dim_livreur.csv`, `fait_ventes.csv`.

Les logs détaillés sont dans `logs/etl_YYYYMMDD_HHMMSS.log`.

### Étape 2 — Mode PostgreSQL

1. Créer la base de données :

```sql
CREATE DATABASE mexora_dwh;
```

2. Créer les schémas et tables :

```bash
psql -U postgres -d mexora_dwh -f sql/create_dwh.sql
```

3. Lancer le pipeline avec chargement PostgreSQL :

```bash
python3 main.py --postgres
```

4. Vérifier l'intégrité :

```bash
psql -U postgres -d mexora_dwh -f sql/check_integrity.sql
```

### Variables d'environnement (PostgreSQL)

```bash
export DWH_HOST=localhost
export DWH_PORT=5432
export DWH_DATABASE=mexora_dwh
export DWH_USER=postgres
export DWH_PASSWORD=postgres
```

## Ce que fait le pipeline

```
[EXTRACT]   51 500 commandes brutes lues
[TRANSFORM] R1 : 1 500 doublons id_commande supprimés
            R2 : dates standardisées (3 formats → YYYY-MM-DD)
            R3 : villes harmonisées via référentiel officiel
            R4 : statuts standardisés (8 variantes → 4 valeurs)
            R5 : 458 lignes à quantité négative supprimées
            R6 : 255 commandes test (prix=0) supprimées
            R7 : 3 414 livreurs manquants → id=-1
            R8 : montants HT et TTC calculés (TVA 20%)
            R9 : délais de livraison calculés en jours
[BUILD]     5 dimensions + 1 table de faits construites
[LOAD]      49 287 faits exportés en 2.7 secondes
```

## Lancer les vérifications d'intégrité

```bash
# Après chargement PostgreSQL
psql -U postgres -d mexora_dwh -f sql/check_integrity.sql

# Requêtes analytiques (5 questions métier)
psql -U postgres -d mexora_dwh -f sql/analytics_queries.sql
```