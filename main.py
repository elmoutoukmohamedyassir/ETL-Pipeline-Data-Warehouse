#!/usr/bin/env python3
import os
import sys
import logging
from datetime import datetime

# Rendre les modules du projet importables depuis n'importe où
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.logger import setup_logger

from extract.extractor import (
    extract_commandes, extract_clients,
    extract_produits, extract_regions,
)
from transform.clean_commandes import transform_commandes, construire_mapping_villes
from transform.clean_clients   import transform_clients, calculer_segments_clients
from transform.clean_produits  import transform_produits
from transform.build_dimensions import (
    build_dim_temps, build_dim_produit, build_dim_client,
    build_dim_region, build_dim_livreur, build_fait_ventes,
)
from load.loader import run_load_csv, run_load_postgres
from config.settings import (
    FILE_COMMANDES, FILE_CLIENTS, FILE_PRODUITS, FILE_REGIONS,
    DB_URL, DIM_TEMPS_START, DIM_TEMPS_END,
)


def run_pipeline(use_postgres: bool = False) -> dict:
    """
    Exécute le pipeline ETL complet en 3 phases.
    Retourne un dictionnaire avec toutes les tables produites.
    """
    logger = setup_logger("mexora_etl")
    start  = datetime.now()

    logger.info("=" * 65)
    logger.info("  DÉMARRAGE PIPELINE ETL MEXORA")
    logger.info(f"  Mode  : {'PostgreSQL' if use_postgres else 'CSV local (dry run)'}")
    logger.info(f"  Heure : {start.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 65)

    try:
        # ══════════════════════════════════════════════════════════════
        # PHASE 1 — EXTRACT
        # ══════════════════════════════════════════════════════════════
        logger.info("\n─── PHASE 1 : EXTRACT ───────────────────────────────────────")

        df_commandes_raw = extract_commandes(FILE_COMMANDES)
        df_clients_raw   = extract_clients(FILE_CLIENTS)
        df_produits_raw  = extract_produits(FILE_PRODUITS)
        df_regions_raw   = extract_regions(FILE_REGIONS)

        # ══════════════════════════════════════════════════════════════
        # PHASE 2 — TRANSFORM
        # ══════════════════════════════════════════════════════════════
        logger.info("\n─── PHASE 2 : TRANSFORM ─────────────────────────────────────")

        # 2a. Nettoyage des 3 sources
        df_commandes = transform_commandes(df_commandes_raw, df_regions_raw)
        df_produits  = transform_produits(df_produits_raw)

        # Le mapping villes est partagé entre commandes et clients
        mapping_villes = construire_mapping_villes(df_regions_raw)
        df_clients     = transform_clients(df_clients_raw, mapping_villes)

        # 2b. Segmentation clients (nécessite les commandes déjà nettoyées)
        df_segments = calculer_segments_clients(df_commandes)

        # 2c. Construction des 5 dimensions
        logger.info("\n  ── Construction des dimensions ──")
        dim_temps   = build_dim_temps(DIM_TEMPS_START, DIM_TEMPS_END)
        dim_produit = build_dim_produit(df_produits)
        dim_region  = build_dim_region(df_regions_raw)
        dim_client  = build_dim_client(df_clients, df_segments, df_regions_raw)
        dim_livreur = build_dim_livreur(df_commandes)

        # 2d. Construction de la table de faits (EN DERNIER — elle dépend des dims)
        logger.info("\n  ── Construction de la table de faits ──")
        fait_ventes = build_fait_ventes(
            df_commandes, dim_temps, dim_client,
            dim_produit, dim_region, dim_livreur,
        )

        # ══════════════════════════════════════════════════════════════
        # PHASE 3 — LOAD
        # ══════════════════════════════════════════════════════════════
        logger.info("\n─── PHASE 3 : LOAD ──────────────────────────────────────────")

        dims = {
            "dim_temps":   dim_temps,
            "dim_produit": dim_produit,
            "dim_client":  dim_client,
            "dim_region":  dim_region,
            "dim_livreur": dim_livreur,
        }

        if use_postgres:
            run_load_postgres(dims, fait_ventes, DB_URL)
        else:
            run_load_csv(dims, fait_ventes)

        # ══════════════════════════════════════════════════════════════
        # RÉSUMÉ
        # ══════════════════════════════════════════════════════════════
        duree = (datetime.now() - start).total_seconds()
        logger.info("\n" + "=" * 65)
        logger.info("  PIPELINE TERMINÉ AVEC SUCCÈS ✓")
        logger.info(f"  Durée          : {duree:.1f} secondes")
        logger.info(f"  Faits produits : {len(fait_ventes):,} lignes")
        logger.info(f"  Clients        : {len(dim_client):,} uniques")
        logger.info(f"  Produits       : {len(dim_produit):,}")
        logger.info(f"  Jours calendrier : {len(dim_temps):,} ({DIM_TEMPS_START} → {DIM_TEMPS_END})")
        logger.info("=" * 65)

        return {
            "dim_temps":   dim_temps,
            "dim_produit": dim_produit,
            "dim_client":  dim_client,
            "dim_region":  dim_region,
            "dim_livreur": dim_livreur,
            "fait_ventes": fait_ventes,
        }

    except Exception as e:
        logger.error(f"\n❌ ERREUR PIPELINE : {e}", exc_info=True)
        raise


if __name__ == "__main__":
    use_pg = "--postgres" in sys.argv
    run_pipeline(use_postgres=use_pg)