"""
data_quality/validate_dwh.py
==============================
Validation de la qualité des tables produites par le pipeline ETL
(dimensions + fait_ventes), avant qu'elles ne soient considérées fiables
pour les rapports analytiques.

Fonctionne sur les CSV exportés (output/) — cohérent avec le mode "dry run"
CSV local du pipeline. En production PostgreSQL, valider_dwh_postgres()
exécute les mêmes règles directement sur les tables du schéma dwh_mexora.

Usage :
    python -m data_quality.validate_dwh
"""

import sys
from pathlib import Path

import pandas as pd
from great_expectations.dataset import PandasDataset


def _valider(df: pd.DataFrame, regles: list, nom_table: str) -> bool:
    resultats = [regle(df) for regle in regles]
    nb_ok = sum(1 for r in resultats if r["success"])
    print(f"\n[DQ] {nom_table} : {nb_ok}/{len(resultats)} règles passées")
    for r in resultats:
        statut = "✓ OK" if r["success"] else "✗ ÉCHEC"
        print(f"  {statut}  {r['expectation_config']['expectation_type']}")
    return nb_ok == len(resultats)


def valider_dwh(output_dir: str = "output") -> bool:
    output_path = Path(output_dir)
    if not output_path.exists():
        print(f"[DQ] Dossier introuvable : {output_path} (lancer d'abord le pipeline ETL)")
        return False

    tout_ok = True

    # ── dim_client ───────────────────────────────────────────────────────
    chemin = output_path / "dim_client.csv"
    if chemin.exists():
        df = pd.read_csv(chemin)
        ok = _valider(df, [
            lambda d: PandasDataset(d).expect_column_values_to_not_be_null("id_client_nk"),
            lambda d: PandasDataset(d).expect_column_values_to_be_unique("id_client_sk"),
            lambda d: PandasDataset(d).expect_column_values_to_be_in_set(
                "segment_client", ["Gold", "Silver", "Bronze"]
            ),
        ], "dim_client")
        tout_ok = tout_ok and ok

    # ── dim_produit ──────────────────────────────────────────────────────
    chemin = output_path / "dim_produit.csv"
    if chemin.exists():
        df = pd.read_csv(chemin)
        ok = _valider(df, [
            lambda d: PandasDataset(d).expect_column_values_to_be_unique("id_produit_sk"),
            lambda d: PandasDataset(d).expect_column_values_to_not_be_null("id_produit_nk"),
        ], "dim_produit")
        tout_ok = tout_ok and ok

    # ── fait_ventes ──────────────────────────────────────────────────────
    chemin = output_path / "fait_ventes.csv"
    if chemin.exists():
        df = pd.read_csv(chemin)
        ok = _valider(df, [
            # id_commande unique : condition nécessaire pour l'upsert incrémental
            lambda d: PandasDataset(d).expect_column_values_to_be_unique("id_commande"),
            lambda d: PandasDataset(d).expect_column_values_to_not_be_null("id_commande"),
            lambda d: PandasDataset(d).expect_column_values_to_be_between(
                "montant_ttc", min_value=0
            ),
            lambda d: PandasDataset(d).expect_column_values_to_be_between(
                "quantite_vendue", min_value=1
            ),
            lambda d: PandasDataset(d).expect_column_values_to_be_in_set(
                "statut_commande", ["livré", "annulé", "en_cours", "retourné", "inconnu"]
            ),
        ], "fait_ventes")
        tout_ok = tout_ok and ok

    print(f"\n{'='*60}")
    print(f"[DQ] Résultat global : {'✓ TOUT OK' if tout_ok else '✗ ÉCHEC — voir détails ci-dessus'}")
    print(f"{'='*60}")
    return tout_ok


def valider_dwh_postgres(schema: str = "dwh_mexora") -> bool:
    """
    Version PostgreSQL de la validation qualité : exécute les mêmes règles
    directement sur les tables du schéma DWH via SQLAlchemy, pour les runs
    Airflow qui chargent en base plutôt qu'en CSV local.
    """
    import sqlalchemy
    from config.settings import DB_URL

    engine = sqlalchemy.create_engine(DB_URL)
    tout_ok = True

    with engine.connect() as conn:
        df_client = pd.read_sql(f"SELECT * FROM {schema}.dim_client", conn)
        df_produit = pd.read_sql(f"SELECT * FROM {schema}.dim_produit", conn)
        df_faits = pd.read_sql(f"SELECT * FROM {schema}.fait_ventes", conn)

    if not df_client.empty:
        tout_ok &= _valider(df_client, [
            lambda d: PandasDataset(d).expect_column_values_to_not_be_null("id_client_nk"),
            lambda d: PandasDataset(d).expect_column_values_to_be_unique("id_client_sk"),
        ], "dim_client (PostgreSQL)")

    if not df_produit.empty:
        tout_ok &= _valider(df_produit, [
            lambda d: PandasDataset(d).expect_column_values_to_be_unique("id_produit_sk"),
        ], "dim_produit (PostgreSQL)")

    if not df_faits.empty:
        tout_ok &= _valider(df_faits, [
            lambda d: PandasDataset(d).expect_column_values_to_be_unique("id_commande"),
            lambda d: PandasDataset(d).expect_column_values_to_be_between("montant_ttc", min_value=0),
        ], "fait_ventes (PostgreSQL)")

    return bool(tout_ok)


if __name__ == "__main__":
    ok = valider_dwh()
    sys.exit(0 if ok else 1)