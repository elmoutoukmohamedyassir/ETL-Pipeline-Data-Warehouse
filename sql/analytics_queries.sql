-- =============================================================================
-- analytics_queries.sql — Requêtes analytiques pour les 5 questions métier
-- Source : vues matérialisées du schéma reporting_mexora
-- =============================================================================


-- ─── QUESTION 1 : CA mensuel par région (avec comparaison N-1) ───────────────

WITH ca_n AS (
    SELECT annee, mois, libelle_mois, region_admin,
           SUM(ca_ttc) AS ca_ttc_n
    FROM reporting_mexora.mv_ca_mensuel
    GROUP BY annee, mois, libelle_mois, region_admin
),
ca_n1 AS (
    SELECT annee + 1 AS annee, mois, region_admin,
           SUM(ca_ttc) AS ca_ttc_n1
    FROM reporting_mexora.mv_ca_mensuel
    GROUP BY annee, mois, region_admin
)
SELECT
    n.annee, n.mois, n.libelle_mois, n.region_admin,
    ROUND(n.ca_ttc_n, 2)                   AS ca_ttc,
    ROUND(n1.ca_ttc_n1, 2)                 AS ca_ttc_n_moins_1,
    ROUND(
        (n.ca_ttc_n - n1.ca_ttc_n1) * 100.0
        / NULLIF(n1.ca_ttc_n1, 0), 1
    )                                       AS evolution_pct
FROM ca_n n
LEFT JOIN ca_n1 n1 USING (annee, mois, region_admin)
ORDER BY n.annee DESC, n.mois DESC, ca_ttc DESC;


-- ─── QUESTION 2 : Top 10 produits par trimestre à Tanger ─────────────────────

SELECT
    annee, trimestre, nom_produit, categorie, marque,
    qte_totale, ROUND(ca_total, 2) AS ca_total,
    nb_clients_distincts, rang_global
FROM reporting_mexora.mv_top_produits
WHERE ville = 'Tanger'
  AND rang_global <= 10
ORDER BY annee DESC, trimestre DESC, rang_global;


-- ─── QUESTION 3 : Panier moyen et CA par segment client ──────────────────────

SELECT
    c.segment_client,
    COUNT(DISTINCT f.id_client)             AS nb_clients,
    COUNT(DISTINCT f.id_vente)              AS nb_commandes,
    ROUND(SUM(f.montant_ttc), 2)            AS ca_total_ttc,
    ROUND(AVG(f.montant_ttc), 2)            AS panier_moyen_ttc,
    ROUND(SUM(f.montant_ttc) * 100.0
          / SUM(SUM(f.montant_ttc)) OVER (), 1) AS part_ca_pct
FROM dwh_mexora.fait_ventes f
JOIN dwh_mexora.dim_client c ON f.id_client = c.id_client_sk
WHERE f.statut_commande = 'livré'
  AND c.est_actif = TRUE
GROUP BY c.segment_client
ORDER BY panier_moyen_ttc DESC;


-- ─── QUESTION 4 : Taux de retour par catégorie ───────────────────────────────

SELECT
    annee, trimestre, categorie, sous_categorie,
    nb_livrees, nb_retournees, taux_retour_pct,
    alerte,
    -- Pour le dashboard : seuils visuels
    5.0 AS seuil_rouge,
    3.0 AS seuil_orange
FROM reporting_mexora.mv_taux_retour
ORDER BY annee DESC, trimestre DESC, taux_retour_pct DESC;


-- ─── QUESTION 5 : Effet Ramadan sur les ventes d'alimentation ────────────────

WITH stats_alimentation AS (
    SELECT
        periode_ramadan,
        annee,
        mois,
        libelle_mois,
        SUM(volume_vendu)   AS volume_total,
        SUM(ca_ttc)         AS ca_total,
        AVG(ca_ttc)         AS ca_moyen
    FROM reporting_mexora.mv_ca_mensuel
    WHERE categorie = 'Alimentation'
    GROUP BY periode_ramadan, annee, mois, libelle_mois
),
moyenne_globale AS (
    SELECT AVG(ca_total) AS ca_moy_global
    FROM stats_alimentation
    WHERE periode_ramadan = FALSE
)
SELECT
    s.annee, s.mois, s.libelle_mois,
    s.periode_ramadan,
    ROUND(s.ca_total, 2)    AS ca_alimentation_ttc,
    ROUND(s.volume_total)   AS volume_vendu,
    -- Indice de sur/sous-performance Ramadan vs moyenne hors-Ramadan
    ROUND(s.ca_total / NULLIF(m.ca_moy_global, 0) * 100, 1) AS indice_vs_moyenne
FROM stats_alimentation s
CROSS JOIN moyenne_globale m
ORDER BY s.annee, s.mois;