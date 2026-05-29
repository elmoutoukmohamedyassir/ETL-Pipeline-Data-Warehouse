import logging
import os

import pandas as pd

logger = logging.getLogger("mexora_etl")


# ─── Mode CSV local (développement / tests) ───────────────────────────────────

def charger_csv(df: pd.DataFrame, nom_table: str, output_dir: str = "output") -> str:
    """
    Exporte un DataFrame en CSV dans le dossier output/.
    Utilisé pour valider le pipeline sans avoir PostgreSQL installé.
    """
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{nom_table}.csv")
    df.to_csv(path, index=False, encoding="utf-8")
    logger.info(f"[LOAD CSV] {nom_table:<30} | {len(df):>6} lignes → {path}")
    return path


def run_load_csv(dims: dict, fait_ventes: pd.DataFrame) -> dict:
    """
    Exporte toutes les tables (dimensions + faits) en CSV locaux.
    Retourne un dictionnaire {nom_table: chemin_fichier}.
    """
    paths = {}
    for nom, df in dims.items():
        paths[nom] = charger_csv(df, nom)
    paths["fait_ventes"] = charger_csv(fait_ventes, "fait_ventes")
    logger.info(f"[LOAD CSV] {len(paths)} tables exportées dans output/")
    return paths


# ─── Mode PostgreSQL (production) ─────────────────────────────────────────────

def charger_dimension(df: pd.DataFrame, nom_table: str, engine,
                      schema: str = "dwh_mexora") -> None:
    """
    Charge une dimension dans PostgreSQL.
    Stratégie REPLACE : on vide et recharge entièrement à chaque run ETL.
    Acceptable pour les dimensions car elles sont petites (< 10 000 lignes)
    et les surrogate keys sont recalculées à chaque run.
    """
    try:
        df.to_sql(
            name=nom_table,
            con=engine,
            schema=schema,
            if_exists="replace",
            index=False,
            method="multi",
            chunksize=1000,
        )
        logger.info(f"[LOAD PG]  {nom_table:<30} | {len(df):>6} lignes (replace)")
    except Exception as e:
        logger.error(f"[LOAD PG]  ERREUR {nom_table} : {e}")
        raise


def charger_faits(df: pd.DataFrame, engine, schema: str = "dwh_mexora") -> None:
    """
    Charge la table de faits dans PostgreSQL.
    Stratégie : TRUNCATE + APPEND (vider puis recharger).
    En production avec gros volumes, utiliser un UPSERT par batch via
    sqlalchemy.dialects.postgresql.insert avec on_conflict_do_update.
    """
    import sqlalchemy

    # Tronquer d'abord pour éviter les doublons entre runs
    try:
        with engine.connect() as conn:
            conn.execute(
                sqlalchemy.text(
                    f"TRUNCATE TABLE {schema}.fait_ventes RESTART IDENTITY CASCADE"
                )
            )
            conn.commit()
        logger.info("[LOAD PG]  fait_ventes tronquée avant rechargement")
    except Exception:
        logger.warning("[LOAD PG]  Impossible de tronquer fait_ventes (table inexistante ?)")

    try:
        df.to_sql(
            name="fait_ventes",
            con=engine,
            schema=schema,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=5000,
        )
        logger.info(f"[LOAD PG]  fait_ventes               | {len(df):>6} lignes (append)")
    except Exception as e:
        logger.error(f"[LOAD PG]  ERREUR fait_ventes : {e}")
        raise


def run_load_postgres(dims: dict, fait_ventes: pd.DataFrame, db_url: str) -> None:
    """
    Charge toutes les tables dans PostgreSQL.
    Les dimensions sont chargées en premier (les faits les référencent).
    """
    import sqlalchemy

    engine = sqlalchemy.create_engine(db_url)
    logger.info("[LOAD PG]  Connexion PostgreSQL établie")

    for nom, df in dims.items():
        charger_dimension(df, nom, engine)

    charger_faits(fait_ventes, engine)
    logger.info("[LOAD PG]  Chargement PostgreSQL terminé")