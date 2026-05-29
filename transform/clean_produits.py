import logging
import pandas as pd
from utils.logger import log_step

logger = logging.getLogger("mexora_etl")


def transform_produits(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Applique les 3 règles de nettoyage sur le catalogue produits Mexora.

    R1 — Standardisation des catégories (casse → Title Case)
    R2 — Gestion des prix catalogue nuls (-1 = prix inconnu)
    R3 — Marquage des produits inactifs pour SCD Type 2
    """
    initial = len(df_raw)
    logger.info(f"[TRANSFORM] ══ PRODUITS début ({initial} lignes) ══")
    df = df_raw.copy()

    # R1 — Standardisation des catégories
    # Problème : "electronique", "Electronique", "ELECTRONIQUE" coexistent
    # dans le fichier source selon les équipes qui ont alimenté le catalogue.
    df["categorie"]      = df["categorie"].str.strip().str.title()
    df["sous_categorie"] = df["sous_categorie"].str.strip().str.title()
    df["marque"]         = df["marque"].str.strip()
    df["fournisseur"]    = df["fournisseur"].str.strip()
    logger.info("[TRANSFORM] R1 — Catégories normalisées en Title Case")

    # R2 — Prix catalogue nuls
    # Certains produits anciens n'ont pas de prix catalogue renseigné.
    # On remplace None/null par -1.00 (convention : "inconnu").
    # On n'utilise PAS 0 car 0 MAD pourrait être interprété comme un prix réel.
    df["prix_catalogue"] = pd.to_numeric(df["prix_catalogue"], errors="coerce")
    nb_nuls = df["prix_catalogue"].isna().sum()
    df["prix_catalogue"] = df["prix_catalogue"].fillna(-1.0)
    logger.info(f"[TRANSFORM] R2 — Prix nuls : {nb_nuls} remplacés par -1.00")

    # R3 — Produits inactifs (SCD Type 2)
    # Les produits marqués actif=false ont des commandes historiques associées.
    # On les CONSERVE avec leur flag pour garantir la cohérence historique.
    # Ex : iPhone P001 inactif mais vendu en 2023 → doit rester dans dim_produit.
    df["actif"] = df["actif"].astype(bool)
    nb_inactifs = (~df["actif"]).sum()
    logger.info(
        f"[TRANSFORM] R3 — Produits inactifs : {nb_inactifs} conservés "
        f"(SCD Type 2 — historique préservé)"
    )

    logger.info(f"[TRANSFORM] ══ PRODUITS fin   ({initial} → {len(df)} lignes) ══")
    return df