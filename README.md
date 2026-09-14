# Mexora ETL — Data Warehouse Pipeline

Pipeline de Data Engineering de bout en bout : 4 sources brutes et "sales" →
nettoyage → modélisation en étoile (star schema) → chargement PostgreSQL ou CSV
→ contrôle qualité automatisé → orchestration Airflow → dashboard/reporting SQL.

Projet fictif basé sur **Mexora**, un e-commerçant marocain (siège Tanger).

---

## 1. Ce que fait le pipeline, en une phrase

`data/*.csv + *.json` (bruts, incohérents) → **Extract** → **Transform**
(17 règles de nettoyage métier documentées) → **Build** (5 dimensions + 1 table
de faits, modèle en étoile) → **Load** (CSV local *ou* PostgreSQL avec upsert
incrémental) → **Data Quality** (Great Expectations) → tables prêtes pour le
BI (`sql/analytics_queries.sql`, vues matérialisées).

## 2. Architecture

```
                 ┌─────────────┐
  4 fichiers  →  │   EXTRACT   │  lecture brute, tout en str (extractor.py)
  sources        └──────┬──────┘
  (CSV/JSON)            ▼
                 ┌─────────────┐
                 │  TRANSFORM  │  17 règles de nettoyage (R1..R9 commandes,
                 │             │  R1..R5 clients, R1..R3 produits)
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │    BUILD    │  5 dimensions (SCD Type 2 sur client/produit)
                 │             │  + 1 table de faits (grain = ligne de commande)
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │    LOAD     │  CSV (output/) — mode dev/dry-run
                 │             │  PostgreSQL — schémas staging/dwh/reporting,
                 │             │  upsert incrémental idempotent (ON CONFLICT)
                 └──────┬──────┘
                        ▼
                 ┌─────────────┐
                 │ DATA QUALITY│  Great Expectations : unicité, non-null,
                 │             │  plages de valeurs, valeurs autorisées
                 └─────────────┘

  Orchestration : Airflow DAG (dags/etl_dwh_dag.py) — ETL puis DQ, @daily
  Conteneurisation : Docker + docker-compose (app + DWH Postgres + Airflow Postgres)
  Tests : pytest sur les règles de transformation (tests/)
  CI : GitHub Actions — tests à chaque push/PR sur main
```

## 3. Modèle de données (star schema)

**Grain de la table de faits** : 1 ligne = 1 ligne de commande (1 produit,
1 client, 1 date, 1 statut).

| Table | Type | Points clés |
|---|---|---|
| `dim_temps` | Dimension | 1 ligne/jour 2020–2025, `id_date` en `YYYYMMDD` (int), jours fériés marocains, périodes Ramadan |
| `dim_produit` | Dimension SCD Type 2 | surrogate key `id_produit_sk`, natural key `id_produit_nk`, `date_debut`/`date_fin`/`est_actif` |
| `dim_client` | Dimension SCD Type 2 | segment Gold/Silver/Bronze, tranche d'âge, région dénormalisée (pas de jointure supplémentaire en requête) |
| `dim_region` | Dimension stable | référentiel géographique officiel (villes, provinces, régions admin) |
| `dim_livreur` | Dimension | générée depuis les `id_livreur` des commandes (placeholder RH/logistique), avec un livreur "Inconnu" (`sk=-1`) |
| `fait_ventes` | Fait | mesures additives (`montant_ht`, `montant_ttc`, `quantite_vendue`), semi-additive (`delai_livraison_jours`), non-additive (`remise_pct`) ; clé naturelle `id_commande` pour permettre l'upsert |

Trois schémas PostgreSQL : `staging_mexora`, `dwh_mexora`, `reporting_mexora`
(ce dernier contient 4 vues matérialisées pré-agrégées pour le dashboard).

## 4. Ce qui a été fait — détail complet

### 4.1 Extraction (`extract/extractor.py`)
- Lecture des 4 sources (`commandes_mexora.csv`, `clients_mexora.csv`,
  `produits_mexora.json`, `regions_maroc.csv`).
- Tout est lu en `dtype=str` avec `keep_default_na=False` : aucune conversion
  de type ni interprétation des valeurs vides n'est faite à l'extraction —
  cette responsabilité est repoussée entièrement à la phase Transform, pour
  garder une frontière nette entre "lire" et "nettoyer".
- Nettoyage des noms de colonnes (`strip()`).

### 4.2 Transformation — nettoyage des commandes (9 règles, `transform/clean_commandes.py`)
- **R1** — Déduplication sur `id_commande`, on garde la dernière occurrence.
- **R2** — Standardisation de 3 formats de dates hétérogènes (ISO, `JJ/MM/AAAA`,
  `Mon DD YYYY`) vers `YYYY-MM-DD`, suppression des dates non parsables.
- **R3** — Harmonisation des villes via un référentiel construit dynamiquement
  (`construire_mapping_villes`) : toutes les variantes de casse, codes courts,
  et fautes connues (`tnja`, `rbat`, `mrakech`...) sont mappées vers le nom
  standard ; le reste devient `"Non renseignée"`.
- **R4** — Standardisation des statuts (3 conventions sources → 4 valeurs
  cibles + `inconnu`).
- **R5** — Suppression des quantités ≤ 0 (erreurs de saisie).
- **R6** — Suppression des commandes "test" internes (`prix_unitaire = 0`).
- **R7** — Les livreurs manquants (~7 % des commandes) ne sont **pas**
  supprimés : remplacés par l'id `-1`, relié à un livreur virtuel "Inconnu"
  dans `dim_livreur` pour préserver l'intégrité référentielle.
- **R8** — Calcul de `montant_ht` et `montant_ttc` (TVA Maroc 20 %).
- **R9** — Calcul du délai de livraison en jours (uniquement pour les commandes
  livrées/retournées), avec nullification des valeurs aberrantes (< 0 ou > 60 j).

### 4.3 Transformation — nettoyage des clients (5 règles + segmentation, `transform/clean_clients.py`)
- **R1** — Déduplication sur email normalisé, conservation de l'inscription la
  plus récente (contexte : doublons issus d'une migration passée).
- **R2** — Standardisation du sexe depuis 3 conventions sources (`m/f`, `1/0`,
  `Homme/Femme`) vers `m/f/inconnu`.
- **R3** — Validation des dates de naissance (âge entre 16 et 100 ans) ;
  nullification (pas suppression) des dates invalides, calcul de l'âge et
  de la tranche d'âge (`<18` … `65+`).
- **R4** — Validation du format email par regex, nullification des invalides
  (client conservé, mais exclu du marketing email).
- **R5** — Harmonisation des villes (même logique que R3 commandes).
- **Segmentation Gold/Silver/Bronze** (`calculer_segments_clients`) : calculée
  séparément car elle dépend des commandes déjà nettoyées — CA cumulé sur les
  12 derniers mois **de commandes livrées uniquement**, avec seuils
  configurables (`SEGMENT_GOLD` = 15 000 MAD, `SEGMENT_SILVER` = 5 000 MAD).
  Le calcul se base sur la date max des données (pas `today()`), pour rester
  correct sur un jeu de données historique.

### 4.4 Transformation — nettoyage des produits (3 règles, `transform/clean_produits.py`)
- **R1** — Normalisation des catégories/sous-catégories/marques en Title Case.
- **R2** — Prix catalogue manquants → convention `-1.00` (distinct de `0`,
  qui pourrait être un vrai prix gratuit).
- **R3** — Les produits inactifs (`actif=false`) sont **conservés**
  (préparation SCD Type 2) car ils peuvent avoir des ventes historiques.

### 4.5 Construction des dimensions et des faits (`transform/build_dimensions.py`)
- `build_dim_temps` : calendrier complet avec jours fériés marocains et
  périodes de Ramadan (2020–2025) codés en dur dans `config/settings.py`.
- `build_dim_produit` / `build_dim_client` : SCD Type 2 initialisé (colonnes
  `date_debut`/`date_fin`/`est_actif`) — la version "historisation à chaque
  changement" n'est pas encore implémentée (voir section Limites).
- `build_dim_region` : directement dérivée du référentiel officiel.
- `build_dim_livreur` : générée depuis les `id_livreur` observés, avec
  attributs placeholder (zone, transport) tirés aléatoirement (seed fixe = 42
  pour reproductibilité), car ces données n'existent pas dans les sources.
- `build_fait_ventes` : résolution des clés naturelles → surrogate keys
  (dictionnaires de mapping), avec fallback sur SK=1 si une clé n'est pas
  trouvée (et log d'avertissement). Deux assertions d'intégrité bloquantes
  (`montant_ttc >= 0`, `quantite_vendue > 0`).

### 4.6 Chargement (`load/loader.py`)
- **Mode CSV** (`run_load_csv`) : export direct de chaque table dans
  `output/` — permet de faire tourner et valider tout le pipeline sans
  PostgreSQL installé (mode "dry run").
- **Mode PostgreSQL** (`run_load_postgres`) :
  - Dimensions chargées en stratégie **REPLACE** (`to_sql(if_exists="replace")`)
    — acceptable car petites tables et clés recalculées à chaque run.
  - Table de faits chargée en **UPSERT incrémental et idempotent**
    (`INSERT ... ON CONFLICT (id_commande) DO UPDATE`) : relancer le pipeline
    ne duplique rien, et un nouveau lot de commandes s'ajoute sans écraser
    l'historique. Chargement par batchs de 5 000 lignes.

### 4.7 Modélisation SQL (`sql/create_dwh.sql`)
- 3 schémas (`staging_mexora`, `dwh_mexora`, `reporting_mexora`).
- DDL complet des 5 dimensions + 1 fait, avec contraintes `CHECK`, clés
  étrangères, commentaires de colonnes.
- 5 index sur les clés étrangères de `fait_ventes`, plus 2 index composites
  ciblés (jointure date+région, et un **index partiel** sur les commandes
  livrées uniquement — optimisation pour ~60 % des lignes).
- 4 vues matérialisées dans `reporting_mexora` : CA mensuel, top produits
  (avec `RANK() OVER`), taux de retour (avec alerte couleur), performance
  livreurs.

### 4.8 Contrôle qualité (`data_quality/validate_dwh.py`)
- Basé sur **Great Expectations** (`PandasDataset`), exécuté automatiquement
  en fin de pipeline **en mode CSV** (`main.py` appelle `valider_dwh()` et
  lève une exception si un contrôle échoue).
- Règles : unicité des clés, non-nullité, appartenance à un ensemble de
  valeurs autorisées (statuts, segments), plages numériques (`montant_ttc
  >= 0`, `quantite_vendue >= 1`).
- Une version parallèle (`valider_dwh_postgres`) exécute les mêmes règles
  directement sur les tables PostgreSQL, pour les runs Airflow — elle
  n'est **pas** appelée automatiquement par `main.py` en mode `--postgres`
  (message d'avertissement invitant à lancer `sql/check_integrity.sql`
  manuellement).

### 4.9 Tests (`tests/`, 515 lignes)
- `test_clean_commandes.py`, `test_clean_clients.py`, `test_clean_produits.py`,
  `test_build_fait_ventes.py` : tests unitaires par règle de nettoyage,
  construits sur des petits DataFrames synthétiques (cas nominal + cas limite
  pour chaque règle).

### 4.10 Orchestration & Infra
- **Airflow** (`dags/etl_dwh_dag.py`) : DAG quotidien à 2 tâches
  (`run_etl_pipeline` → `data_quality_check`), retries configurés (2 tentatives,
  5 min d'intervalle).
- **Docker** : `Dockerfile` (image `python:3.11-slim`, lance
  `python main.py --postgres` au démarrage) + `docker-compose.yml` qui
  orchestre : Postgres du DWH métier, Postgres des métadonnées Airflow,
  webserver + scheduler Airflow, avec initialisation automatique du schéma
  (`sql/create_dwh.sql` monté en script d'init Postgres).
- **CI** (`.github/workflows/ci.yml`) : GitHub Actions, exécute `pytest
  tests/` sur chaque push/PR vers `main`.

### 4.11 Générateur de données (`data/generate_data.py`)
- Génère les 4 fichiers sources avec **injection contrôlée de defauts**
  (seed fixe = 42, donc reproductible) : doublons, formats de dates mixtes,
  variantes de casse/orthographe de villes, statuts hétérogènes, livreurs
  manquants, prix nuls — un vrai "sale dataset" pédagogique plutôt qu'un jeu
  de données déjà propre.

## 5. Chiffres clés (dernier run CSV présent dans `output/`)

| Table | Lignes |
|---|---|
| `dim_client` | 2 878 |
| `dim_livreur` | 51 |
| `dim_produit` | 20 |
| `dim_region` | 15 |
| `dim_temps` | 2 192 |
| `fait_ventes` | 49 189 |

## 6. Installation & exécution

```bash
pip install -r requirements.txt

# Mode CSV local (aucune base nécessaire) — écrit dans output/
python main.py

# Mode PostgreSQL (nécessite une base + schéma créé via sql/create_dwh.sql)
cp .env.example .env   # puis éditer DWH_HOST/DWH_USER/DWH_PASSWORD/...
python main.py --postgres

# Tests
pytest tests/ -v

# Stack complète avec Airflow (Docker)
docker compose up -d
# UI Airflow : http://localhost:8080 (admin/admin)
```

## 7. Limites connues / dette technique honnête

- **`main.py` contient actuellement une erreur d'indentation Python**
  (bloc `if use_postgres:` mal indenté juste avant l'appel au chargement) —
  le fichier ne s'exécute pas tel quel ; à corriger avant toute démo.
- Le SCD Type 2 sur `dim_client`/`dim_produit` n'historise pas réellement les
  changements à chaque run : chaque exécution régénère une version "active"
  unique plutôt que de comparer avec l'état précédent et créer une nouvelle
  ligne uniquement en cas de changement (le mécanisme de MERGE incrémental
  reste à implémenter).
- `dim_livreur` est en grande partie simulée (zone/transport tirés au hasard)
  faute de source réelle.
- La validation qualité automatique (`valider_dwh`) ne tourne qu'en mode CSV ;
  en mode PostgreSQL elle doit être lancée manuellement.
- Pas encore de gestion des reprises partielles (si le pipeline échoue en
  phase Load, il faut tout rejouer depuis Extract).

## 8. Stack technique

Python 3.11 · pandas · SQLAlchemy · PostgreSQL 15 · Great Expectations ·
Apache Airflow 2.9 · Docker / docker-compose · pytest · GitHub Actions.