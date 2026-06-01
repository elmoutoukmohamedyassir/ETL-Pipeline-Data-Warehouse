-- =============================================================================
-- create_dwh.sql — Création du Data Warehouse Mexora
-- Plateforme : PostgreSQL 15+
-- Schémas    : staging_mexora | dwh_mexora | reporting_mexora
-- =============================================================================

-- ─── Schémas ──────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS staging_mexora;
CREATE SCHEMA IF NOT EXISTS dwh_mexora;
CREATE SCHEMA IF NOT EXISTS reporting_mexora;

-- ─── Extensions utiles ────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;  -- monitoring des requêtes


-- =============================================================================
-- DIMENSION TEMPS
-- =============================================================================
DROP TABLE IF EXISTS dwh_mexora.dim_temps CASCADE;

CREATE TABLE dwh_mexora.dim_temps (
    id_date           INTEGER     PRIMARY KEY,  -- format YYYYMMDD (ex : 20240315)
    jour              SMALLINT    NOT NULL CHECK (jour BETWEEN 1 AND 31),
    mois              SMALLINT    NOT NULL CHECK (mois BETWEEN 1 AND 12),
    trimestre         SMALLINT    NOT NULL CHECK (trimestre BETWEEN 1 AND 4),
    annee             SMALLINT    NOT NULL,
    semaine           SMALLINT,
    libelle_jour      VARCHAR(20),              -- ex : "Lundi"
    libelle_mois      VARCHAR(20),              -- ex : "Janvier"
    est_weekend       BOOLEAN     DEFAULT FALSE,
    est_ferie_maroc   BOOLEAN     DEFAULT FALSE,
    periode_ramadan   BOOLEAN     DEFAULT FALSE
);

COMMENT ON TABLE dwh_mexora.dim_temps IS
    'Dimension temporelle — 1 ligne par jour entre 2020-01-01 et 2025-12-31';
COMMENT ON COLUMN dwh_mexora.dim_temps.id_date IS
    'Clé primaire au format YYYYMMDD pour faciliter les comparaisons numériques';


-- =============================================================================
-- DIMENSION PRODUIT (SCD Type 2)
-- =============================================================================
DROP TABLE IF EXISTS dwh_mexora.dim_produit CASCADE;

CREATE TABLE dwh_mexora.dim_produit (
    id_produit_sk     SERIAL      PRIMARY KEY,         -- surrogate key (auto-incrémentée)
    id_produit_nk     VARCHAR(20) NOT NULL,             -- natural key (clé du système source)
    nom_produit       VARCHAR(200) NOT NULL,
    categorie         VARCHAR(100),
    sous_categorie    VARCHAR(100),
    marque            VARCHAR(100),
    fournisseur       VARCHAR(100),
    prix_standard     DECIMAL(10,2),                   -- -1.00 = prix inconnu
    origine_pays      VARCHAR(50),
    -- Colonnes SCD Type 2 (gestion de l'historique des changements)
    date_debut        DATE        NOT NULL DEFAULT CURRENT_DATE,
    date_fin          DATE        NOT NULL DEFAULT '9999-12-31',
    est_actif         BOOLEAN     NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE dwh_mexora.dim_produit IS
    'Dimension produit avec SCD Type 2 — permet de conserver l''historique des changements de catégorie';
COMMENT ON COLUMN dwh_mexora.dim_produit.id_produit_sk IS
    'Surrogate key — ne jamais exposer aux utilisateurs métier';
COMMENT ON COLUMN dwh_mexora.dim_produit.date_fin IS
    'Date de fin de validité : 9999-12-31 = version courante';


-- =============================================================================
-- DIMENSION CLIENT (SCD Type 2)
-- =============================================================================
DROP TABLE IF EXISTS dwh_mexora.dim_client CASCADE;

CREATE TABLE dwh_mexora.dim_client (
    id_client_sk      SERIAL      PRIMARY KEY,
    id_client_nk      VARCHAR(20) NOT NULL,
    nom_complet       VARCHAR(200),
    tranche_age       VARCHAR(10),                     -- <18, 18-24, 25-34, etc.
    sexe              CHAR(1)     CHECK (sexe IN ('m','f','i')),
    ville             VARCHAR(100),
    region_admin      VARCHAR(100),
    segment_client    VARCHAR(20) CHECK (segment_client IN ('Gold','Silver','Bronze')),
    canal_acquisition VARCHAR(50),
    -- SCD Type 2
    date_debut        DATE        NOT NULL DEFAULT CURRENT_DATE,
    date_fin          DATE        NOT NULL DEFAULT '9999-12-31',
    est_actif         BOOLEAN     NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE dwh_mexora.dim_client IS
    'Dimension client avec SCD Type 2 — le segment Gold/Silver/Bronze peut évoluer';


-- =============================================================================
-- DIMENSION REGION
-- =============================================================================
DROP TABLE IF EXISTS dwh_mexora.dim_region CASCADE;

CREATE TABLE dwh_mexora.dim_region (
    id_region         SERIAL      PRIMARY KEY,
    ville             VARCHAR(100) NOT NULL UNIQUE,
    province          VARCHAR(100),
    region_admin      VARCHAR(100),
    zone_geo          VARCHAR(50),
    pays              VARCHAR(50)  DEFAULT 'Maroc'
);

COMMENT ON TABLE dwh_mexora.dim_region IS
    'Référentiel géographique officiel — stable, pas de SCD nécessaire';


-- =============================================================================
-- DIMENSION LIVREUR
-- =============================================================================
DROP TABLE IF EXISTS dwh_mexora.dim_livreur CASCADE;

CREATE TABLE dwh_mexora.dim_livreur (
    id_livreur        SERIAL      PRIMARY KEY,
    id_livreur_nk     VARCHAR(20) NOT NULL UNIQUE,
    nom_livreur       VARCHAR(100),
    type_transport    VARCHAR(50),
    zone_couverture   VARCHAR(100)
);

COMMENT ON TABLE dwh_mexora.dim_livreur IS
    'Dimension livreur — le livreur id_nk=-1 représente les cas inconnus';


-- =============================================================================
-- TABLE DE FAITS — FAIT_VENTES
-- Granularité : 1 ligne = 1 ligne de commande (1 produit, 1 client, 1 date)
-- =============================================================================
DROP TABLE IF EXISTS dwh_mexora.fait_ventes CASCADE;

CREATE TABLE dwh_mexora.fait_ventes (
    id_vente              BIGSERIAL   PRIMARY KEY,

    -- Clés étrangères vers les dimensions
    id_date               INTEGER     NOT NULL REFERENCES dwh_mexora.dim_temps(id_date),
    id_produit            INTEGER     NOT NULL REFERENCES dwh_mexora.dim_produit(id_produit_sk),
    id_client             INTEGER     NOT NULL REFERENCES dwh_mexora.dim_client(id_client_sk),
    id_region             INTEGER     NOT NULL REFERENCES dwh_mexora.dim_region(id_region),
    id_livreur            INTEGER              REFERENCES dwh_mexora.dim_livreur(id_livreur),

    -- Mesures ADDITIVES (se sommable dans toutes les dimensions)
    quantite_vendue       INTEGER     NOT NULL CHECK (quantite_vendue > 0),
    montant_ht            DECIMAL(12,2) NOT NULL CHECK (montant_ht >= 0),
    montant_ttc           DECIMAL(12,2) NOT NULL CHECK (montant_ttc >= 0),
    cout_livraison        DECIMAL(8,2),                -- NULL si non renseigné

    -- Mesure SEMI-ADDITIVE (moyenne utile, somme non pertinente)
    delai_livraison_jours SMALLINT,

    -- Mesure NON-ADDITIVE (taux — à recalculer dans les requêtes analytiques)
    remise_pct            DECIMAL(5,2)  DEFAULT 0.00,

    -- Métadonnées ETL
    statut_commande       VARCHAR(20)  CHECK (statut_commande IN ('livré','annulé','en_cours','retourné','inconnu')),
    date_chargement       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE dwh_mexora.fait_ventes IS
    'Table de faits principale — granularité : 1 ligne de commande';
COMMENT ON COLUMN dwh_mexora.fait_ventes.montant_ht IS
    'Mesure additive — TVA Maroc 20% exclue';
COMMENT ON COLUMN dwh_mexora.fait_ventes.montant_ttc IS
    'Mesure additive — TVA Maroc 20% incluse (prix catalogue × 1.20)';
COMMENT ON COLUMN dwh_mexora.fait_ventes.delai_livraison_jours IS
    'Mesure semi-additive — utiliser AVG(), non SUM()';
COMMENT ON COLUMN dwh_mexora.fait_ventes.remise_pct IS
    'Mesure non-additive — taux, ne jamais sommer directement';


-- =============================================================================
-- INDEX (optimisation des requêtes analytiques)
-- =============================================================================

-- Index sur les clés étrangères (accélèrent les jointures)
CREATE INDEX idx_fv_date     ON dwh_mexora.fait_ventes(id_date);
CREATE INDEX idx_fv_produit  ON dwh_mexora.fait_ventes(id_produit);
CREATE INDEX idx_fv_client   ON dwh_mexora.fait_ventes(id_client);
CREATE INDEX idx_fv_region   ON dwh_mexora.fait_ventes(id_region);
CREATE INDEX idx_fv_livreur  ON dwh_mexora.fait_ventes(id_livreur);

-- Index composites pour les requêtes analytiques fréquentes
-- Requête type : CA par région par mois
CREATE INDEX idx_fv_date_region  ON dwh_mexora.fait_ventes(id_date, id_region)
    INCLUDE (montant_ttc, quantite_vendue);

-- Index partiel : analyses sur les ventes livrées uniquement (60% des lignes)
CREATE INDEX idx_fv_statut_livre ON dwh_mexora.fait_ventes(id_date, id_produit)
    WHERE statut_commande = 'livré';

-- Index pour les analyses de retours
CREATE INDEX idx_fv_statut_all ON dwh_mexora.fait_ventes(statut_commande, id_produit);


-- =============================================================================
-- VUES MATÉRIALISÉES (reporting_mexora)
-- Pré-calculent les agrégats lourds pour le dashboard
-- =============================================================================

-- Vue 1 : CA mensuel par région et catégorie (Question 1 + effet Ramadan)
DROP MATERIALIZED VIEW IF EXISTS reporting_mexora.mv_ca_mensuel CASCADE;

CREATE MATERIALIZED VIEW reporting_mexora.mv_ca_mensuel AS
SELECT
    t.annee,
    t.mois,
    t.trimestre,
    t.libelle_mois,
    t.periode_ramadan,
    r.region_admin,
    r.zone_geo,
    r.ville,
    p.categorie,
    SUM(f.montant_ttc)              AS ca_ttc,
    SUM(f.montant_ht)               AS ca_ht,
    SUM(f.quantite_vendue)          AS volume_vendu,
    COUNT(DISTINCT f.id_client)     AS nb_clients_actifs,
    COUNT(DISTINCT f.id_vente)      AS nb_commandes,
    AVG(f.montant_ttc)              AS panier_moyen,
    -- CA N-1 calculé en joignant la même vue (décalage d'un an)
    -- En production : utiliser LAG() ou auto-jointure dans Power BI
    t.annee - 1                     AS annee_n1   -- repère pour jointure N-1
FROM dwh_mexora.fait_ventes f
JOIN dwh_mexora.dim_temps   t ON f.id_date    = t.id_date
JOIN dwh_mexora.dim_region  r ON f.id_region  = r.id_region
JOIN dwh_mexora.dim_produit p ON f.id_produit = p.id_produit_sk
WHERE f.statut_commande = 'livré'
GROUP BY
    t.annee, t.mois, t.trimestre, t.libelle_mois, t.periode_ramadan,
    r.region_admin, r.zone_geo, r.ville, p.categorie
WITH DATA;

CREATE INDEX ON reporting_mexora.mv_ca_mensuel(annee, mois);
CREATE INDEX ON reporting_mexora.mv_ca_mensuel(region_admin);
CREATE INDEX ON reporting_mexora.mv_ca_mensuel(categorie);
CREATE INDEX ON reporting_mexora.mv_ca_mensuel(periode_ramadan);

COMMENT ON MATERIALIZED VIEW reporting_mexora.mv_ca_mensuel IS
    'CA agrégé par mois × région × catégorie — rafraîchir après chaque run ETL';


-- Vue 2 : Top produits par trimestre (Question 2)
DROP MATERIALIZED VIEW IF EXISTS reporting_mexora.mv_top_produits CASCADE;

CREATE MATERIALIZED VIEW reporting_mexora.mv_top_produits AS
SELECT
    t.annee,
    t.trimestre,
    r.ville,
    p.id_produit_sk,
    p.nom_produit,
    p.categorie,
    p.marque,
    SUM(f.quantite_vendue)          AS qte_totale,
    SUM(f.montant_ttc)              AS ca_total,
    COUNT(DISTINCT f.id_client)     AS nb_clients_distincts,
    -- Rang dans la catégorie, par trimestre
    RANK() OVER (
        PARTITION BY t.annee, t.trimestre, r.ville, p.categorie
        ORDER BY SUM(f.montant_ttc) DESC
    )                               AS rang_dans_categorie,
    -- Rang global (toutes catégories confondues), par ville
    RANK() OVER (
        PARTITION BY t.annee, t.trimestre, r.ville
        ORDER BY SUM(f.montant_ttc) DESC
    )                               AS rang_global
FROM dwh_mexora.fait_ventes f
JOIN dwh_mexora.dim_temps   t ON f.id_date    = t.id_date
JOIN dwh_mexora.dim_produit p ON f.id_produit = p.id_produit_sk
JOIN dwh_mexora.dim_region  r ON f.id_region  = r.id_region
WHERE f.statut_commande = 'livré'
GROUP BY
    t.annee, t.trimestre, r.ville,
    p.id_produit_sk, p.nom_produit, p.categorie, p.marque
WITH DATA;

CREATE INDEX ON reporting_mexora.mv_top_produits(annee, trimestre);
CREATE INDEX ON reporting_mexora.mv_top_produits(ville);
CREATE INDEX ON reporting_mexora.mv_top_produits(rang_global);

COMMENT ON MATERIALIZED VIEW reporting_mexora.mv_top_produits IS
    'Classement des produits par trimestre et par ville (Questions 2 & 4)';


-- Vue 3 : Taux de retour par catégorie (Question 4)
DROP MATERIALIZED VIEW IF EXISTS reporting_mexora.mv_taux_retour CASCADE;

CREATE MATERIALIZED VIEW reporting_mexora.mv_taux_retour AS
SELECT
    t.annee,
    t.trimestre,
    p.categorie,
    p.sous_categorie,
    COUNT(*) FILTER (WHERE f.statut_commande = 'livré')   AS nb_livrees,
    COUNT(*) FILTER (WHERE f.statut_commande = 'retourné') AS nb_retournees,
    ROUND(
        COUNT(*) FILTER (WHERE f.statut_commande = 'retourné') * 100.0
        / NULLIF(COUNT(*) FILTER (WHERE f.statut_commande IN ('livré','retourné')), 0),
        2
    )                                                      AS taux_retour_pct,
    -- Indicateur d'alerte : vert < 3% | orange 3-5% | rouge > 5%
    CASE
        WHEN ROUND(COUNT(*) FILTER (WHERE f.statut_commande = 'retourné') * 100.0
             / NULLIF(COUNT(*) FILTER (WHERE f.statut_commande IN ('livré','retourné')), 0), 2) > 5
        THEN 'rouge'
        WHEN ROUND(COUNT(*) FILTER (WHERE f.statut_commande = 'retourné') * 100.0
             / NULLIF(COUNT(*) FILTER (WHERE f.statut_commande IN ('livré','retourné')), 0), 2) > 3
        THEN 'orange'
        ELSE 'vert'
    END                                                    AS alerte
FROM dwh_mexora.fait_ventes f
JOIN dwh_mexora.dim_temps   t ON f.id_date    = t.id_date
JOIN dwh_mexora.dim_produit p ON f.id_produit = p.id_produit_sk
WHERE f.statut_commande IN ('livré','retourné')
GROUP BY t.annee, t.trimestre, p.categorie, p.sous_categorie
WITH DATA;

CREATE INDEX ON reporting_mexora.mv_taux_retour(categorie);
CREATE INDEX ON reporting_mexora.mv_taux_retour(taux_retour_pct);

COMMENT ON MATERIALIZED VIEW reporting_mexora.mv_taux_retour IS
    'Taux de retour par catégorie avec alertes couleur (Question 4)';


-- Vue 4 (bonus) : Performance livreurs
DROP MATERIALIZED VIEW IF EXISTS reporting_mexora.mv_performance_livreurs CASCADE;

CREATE MATERIALIZED VIEW reporting_mexora.mv_performance_livreurs AS
SELECT
    l.nom_livreur,
    l.zone_couverture,
    t.annee,
    t.mois,
    COUNT(*)                                                AS nb_livraisons,
    AVG(f.delai_livraison_jours)                           AS delai_moyen_jours,
    COUNT(*) FILTER (WHERE f.delai_livraison_jours > 3)    AS nb_livraisons_retard,
    ROUND(
        COUNT(*) FILTER (WHERE f.delai_livraison_jours > 3) * 100.0
        / NULLIF(COUNT(*), 0),
        2
    )                                                       AS taux_retard_pct
FROM dwh_mexora.fait_ventes f
JOIN dwh_mexora.dim_livreur l ON f.id_livreur = l.id_livreur
JOIN dwh_mexora.dim_temps   t ON f.id_date    = t.id_date
WHERE f.statut_commande IN ('livré','retourné')
  AND f.delai_livraison_jours IS NOT NULL
  AND l.id_livreur_nk != '-1'   -- exclure le livreur "inconnu"
GROUP BY l.nom_livreur, l.zone_couverture, t.annee, t.mois
WITH DATA;

-- Commande de rafraîchissement (à ajouter dans le cron ETL)
-- REFRESH MATERIALIZED VIEW CONCURRENTLY reporting_mexora.mv_ca_mensuel;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY reporting_mexora.mv_top_produits;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY reporting_mexora.mv_taux_retour;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY reporting_mexora.mv_performance_livreurs;