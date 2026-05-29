import json
import logging
import pandas as pd

logger = logging.getLogger("mexora_etl")


def extract_commandes(filepath: str) -> pd.DataFrame:
    """
    Lit le fichier CSV des commandes brutes.
    dtype=str : on garde tout en texte, les transformations de types
                se font dans la phase Transform, jamais ici.
    keep_default_na=False : empêche pandas de convertir les cellules
                            vides/"NA"/"NULL" en NaN silencieusement.
    """
    df = pd.read_csv(
        filepath,
        encoding="utf-8",
        dtype=str,
        keep_default_na=False,
    )
    df.columns = df.columns.str.strip()  # supprime les espaces autour des noms de colonnes
    logger.info(f"[EXTRACT] commandes_mexora.csv   | {len(df):>6} lignes extraites")
    return df


def extract_clients(filepath: str) -> pd.DataFrame:
    """Lit le fichier CSV des clients bruts."""
    df = pd.read_csv(
        filepath,
        encoding="utf-8",
        dtype=str,
        keep_default_na=False,
    )
    df.columns = df.columns.str.strip()
    logger.info(f"[EXTRACT] clients_mexora.csv     | {len(df):>6} lignes extraites")
    return df


def extract_produits(filepath: str) -> pd.DataFrame:
    """
    Lit le fichier JSON des produits.
    La structure JSON attendue : {"produits": [ {...}, {...} ]}
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data["produits"])
    logger.info(f"[EXTRACT] produits_mexora.json   | {len(df):>6} produits extraits")
    return df


def extract_regions(filepath: str) -> pd.DataFrame:
    """
    Lit le référentiel géographique officiel.
    Ce fichier est propre par définition — il sert de table de correspondance
    pour harmoniser les villes dans les autres fichiers.
    """
    df = pd.read_csv(
        filepath,
        encoding="utf-8",
        dtype=str,
        keep_default_na=False,
    )
    df.columns = df.columns.str.strip()
    logger.info(f"[EXTRACT] regions_maroc.csv      | {len(df):>6} régions extraites")
    return df