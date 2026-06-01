-- =============================================================================
-- check_integrity.sql — Vérification de l'intégrité référentielle du DWH Mexora
-- À exécuter après chaque run ETL pour valider la qualité des données chargées.
-- =============================================================================

-- ─── 1. Comptage des tables ───────────────────────────────────────────────────
SELECT 'dim_temps'    AS table_name, COUNT(*) AS nb_lignes FROM dwh_mexora.dim_temps
UNION ALL
SELECT 'dim_produit',  COUNT(*) FROM dwh_mexora.dim_produit
UNION ALL
SELECT 'dim_client',   COUNT(*) FROM dwh_mexora.dim_client
UNION ALL
SELECT 'dim_region',   COUNT(*) FROM dwh_mexora.dim_region
UNION ALL
SELECT 'dim_livreur',  COUNT(*) FROM dwh_mexora.dim_livreur
UNION ALL
SELECT 'fait_ventes',  COUNT(*) FROM dwh_mexora.fait_ventes
ORDER BY table_name;


-- ─── 2. Vérification des clés étrangères orphelines ──────────────────────────
-- Lignes de fait_ventes sans correspondance dans dim_temps
SELECT 'FK orphelines : fait → dim_temps' AS check_name,
       COUNT(*) AS nb_orphelines
FROM dwh_mexora.fait_ventes f
LEFT JOIN dwh_mexora.dim_temps t ON f.id_date = t.id_date
WHERE t.id_date IS NULL;

-- Lignes de fait_ventes sans correspondance dans dim_produit
SELECT 'FK orphelines : fait → dim_produit' AS check_name,
       COUNT(*) AS nb_orphelines
FROM dwh_mexora.fait_ventes f
LEFT JOIN dwh_mexora.dim_produit p ON f.id_produit = p.id_produit_sk
WHERE p.id_produit_sk IS NULL;

-- Lignes de fait_ventes sans correspondance dans dim_client
SELECT 'FK orphelines : fait → dim_client' AS check_name,
       COUNT(*) AS nb_orphelines
FROM dwh_mexora.fait_ventes f
LEFT JOIN dwh_mexora.dim_client c ON f.id_client = c.id_client_sk
WHERE c.id_client_sk IS NULL;

-- Lignes de fait_ventes sans correspondance dans dim_region
SELECT 'FK orphelines : fait → dim_region' AS check_name,
       COUNT(*) AS nb_orphelines
FROM dwh_mexora.fait_ventes f
LEFT JOIN dwh_mexora.dim_region r ON f.id_region = r.id_region
WHERE r.id_region IS NULL;


-- ─── 3. Contrôles de qualité des mesures ─────────────────────────────────────
-- Montants négatifs (ne doit jamais exister)
SELECT 'Montants TTC négatifs' AS check_name,
       COUNT(*) AS nb_anomalies
FROM dwh_mexora.fait_ventes
WHERE montant_ttc < 0;

-- Quantités <= 0 (ne doit jamais exister après nettoyage)
SELECT 'Quantités <= 0' AS check_name,
       COUNT(*) AS nb_anomalies
FROM dwh_mexora.fait_ventes
WHERE quantite_vendue <= 0;

-- Délais de livraison aberrants
SELECT 'Délais > 60 jours' AS check_name,
       COUNT(*) AS nb_anomalies
FROM dwh_mexora.fait_ventes
WHERE delai_livraison_jours > 60;

-- Statuts non standards
SELECT 'Statuts non standards' AS check_name,
       COUNT(*) AS nb_anomalies
FROM dwh_mexora.fait_ventes
WHERE statut_commande NOT IN ('livré','annulé','en_cours','retourné','inconnu');


-- ─── 4. Distribution des statuts ─────────────────────────────────────────────
SELECT
    statut_commande,
    COUNT(*)                            AS nb_commandes,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
FROM dwh_mexora.fait_ventes
GROUP BY statut_commande
ORDER BY nb_commandes DESC;


-- ─── 5. Vérification des SCD Type 2 ──────────────────────────────────────────
-- Il ne doit y avoir qu'une seule version active par natural key
SELECT 'dim_produit : nb NK avec > 1 version active' AS check_name,
       COUNT(*) AS nb_anomalies
FROM (
    SELECT id_produit_nk, COUNT(*) AS nb_versions
    FROM dwh_mexora.dim_produit
    WHERE est_actif = TRUE
    GROUP BY id_produit_nk
    HAVING COUNT(*) > 1
) sub;

SELECT 'dim_client : nb NK avec > 1 version active' AS check_name,
       COUNT(*) AS nb_anomalies
FROM (
    SELECT id_client_nk, COUNT(*) AS nb_versions
    FROM dwh_mexora.dim_client
    WHERE est_actif = TRUE
    GROUP BY id_client_nk
    HAVING COUNT(*) > 1
) sub;


-- ─── 6. KPIs de validation rapides ───────────────────────────────────────────
SELECT
    'CA Total TTC (livrées)'        AS kpi,
    TO_CHAR(SUM(montant_ttc), 'FM999,999,999,999.00') || ' MAD' AS valeur
FROM dwh_mexora.fait_ventes
WHERE statut_commande = 'livré'
UNION ALL
SELECT
    'Nb clients distincts (faits)',
    COUNT(DISTINCT id_client)::TEXT
FROM dwh_mexora.fait_ventes
UNION ALL
SELECT
    'Taux de retour global',
    ROUND(
        COUNT(*) FILTER (WHERE statut_commande = 'retourné') * 100.0
        / NULLIF(COUNT(*) FILTER (WHERE statut_commande IN ('livré','retourné')), 0),
        2
    )::TEXT || '%'
FROM dwh_mexora.fait_ventes
UNION ALL
SELECT
    'Panier moyen TTC (livrées)',
    TO_CHAR(AVG(montant_ttc) FILTER (WHERE statut_commande = 'livré'), 'FM999,999.00') || ' MAD'
FROM dwh_mexora.fait_ventes;