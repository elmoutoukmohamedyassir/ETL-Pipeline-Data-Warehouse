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
    Charge la table de faits dans PostgreSQL en UPSERT incrémental et idempotent.

    Stratégie : INSERT ... ON CONFLICT (id_commande) DO UPDATE.
      - Une commande jamais vue avant (nouvel id_commande)  → INSERT
      - Une commande déjà présente (ex : correction de statut,
        recalcul de montant) → UPDATE de la ligne existante
      - Relancer le pipeline avec les mêmes données ne crée AUCUN doublon
        (idempotence), et un nouveau batch de commandes s'ajoute sans
        écraser l'historique déjà chargé (incrémental).

    Remplace l'ancienne stratégie TRUNCATE + APPEND, qui perdait tout
    l'historique à chaque run et empêchait le chargement incrémental.
    """
    import sqlalchemy
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    table = sqlalchemy.Table(
        "fait_ventes", sqlalchemy.MetaData(schema=schema),
        autoload_with=engine,
    )

    colonnes = df.columns.tolist()
    lignes = df.to_dict(orient="records")

    CHUNK = 5000
    total_upserted = 0
    try:
        with engine.begin() as conn:
            for i in range(0, len(lignes), CHUNK):
                batch = lignes[i:i + CHUNK]
                stmt = pg_insert(table).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id_commande"],
                    set_={col: getattr(stmt.excluded, col) for col in colonnes if col != "id_commande"},
                )
                conn.execute(stmt)
                total_upserted += len(batch)
        logger.info(f"[LOAD PG]  fait_ventes               | {total_upserted:>6} lignes (upsert incrémental)")
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