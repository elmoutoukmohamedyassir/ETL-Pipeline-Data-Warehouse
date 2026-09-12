"""
tests/test_build_fait_ventes.py
=================================
Test d'intégration : vérifie que fait_ventes contient bien id_commande
(clé naturelle nécessaire à l'upsert incrémental côté loader) et qu'elle
est unique dans la table de faits produite.
"""

import pandas as pd
import pytest

from transform.build_dimensions import (
    build_dim_produit, build_dim_client, build_dim_region,
    build_dim_livreur, build_fait_ventes,
)


@pytest.fixture
def dimensions_et_commandes():
    df_produits = pd.DataFrame({
        "id_produit": ["P001"],
        "nom": ["iPhone"],
        "prix_catalogue": [8000.0],
        "categorie": ["Electronique"],
        "sous_categorie": ["Telephones"],
        "marque": ["Apple"],
        "fournisseur": ["FournA"],
        "origine_pays": ["Chine"],
    })

    df_regions = pd.DataFrame({
        "nom_ville_standard": ["Casablanca"],
        "province": ["Casablanca"],
        "region_admin": ["Casablanca-Settat"],
        "zone_geo": ["Nord"],
        "code_ville": ["CAS"],
    })

    df_clients = pd.DataFrame({
        "id_client": ["C001"],
        "prenom": ["Yassir"],
        "nom": ["Test"],
        "tranche_age": ["25-34"],
        "sexe": ["m"],
        "ville": ["Casablanca"],
        "canal_acquisition": ["Web"],
    })

    df_segments = pd.DataFrame({
        "id_client": ["C001"],
        "segment_client": ["Gold"],
        "ca_12m": [20000.0],
    })

    df_commandes = pd.DataFrame({
        "id_commande": ["CMD-001", "CMD-002"],
        "date_commande": ["2024-01-15", "2024-01-16"],
        "id_produit": ["P001", "P001"],
        "id_client": ["C001", "C001"],
        "ville_livraison": ["Casablanca", "Casablanca"],
        "id_livreur": ["-1", "-1"],
        "quantite": [1, 2],
        "montant_ht": [6666.67, 13333.33],
        "montant_ttc": [8000.0, 16000.0],
        "delai_livraison_jours": [3, 4],
        "statut": ["livré", "livré"],
    })

    dim_produit = build_dim_produit(df_produits)
    dim_client = build_dim_client(df_clients, df_segments, df_regions)
    dim_region = build_dim_region(df_regions)
    dim_livreur = build_dim_livreur(df_commandes)

    return df_commandes, dim_produit, dim_client, dim_region, dim_livreur


def test_fait_ventes_contient_id_commande(dimensions_et_commandes):
    """id_commande doit être présent : c'est la clé naturelle qui permet
    au loader de faire un upsert incrémental au lieu d'un full-reload."""
    df_commandes, dim_produit, dim_client, dim_region, dim_livreur = dimensions_et_commandes
    dim_temps = pd.DataFrame()  # non utilisé dans build_fait_ventes actuel

    fait = build_fait_ventes(
        df_commandes, dim_temps, dim_client, dim_produit, dim_region, dim_livreur
    )

    assert "id_commande" in fait.columns


def test_id_commande_unique_dans_fait_ventes(dimensions_et_commandes):
    """id_commande doit être unique : c'est ce qui garantit l'idempotence
    de l'upsert (ON CONFLICT (id_commande) DO UPDATE côté PostgreSQL)."""
    df_commandes, dim_produit, dim_client, dim_region, dim_livreur = dimensions_et_commandes
    dim_temps = pd.DataFrame()

    fait = build_fait_ventes(
        df_commandes, dim_temps, dim_client, dim_produit, dim_region, dim_livreur
    )

    assert fait["id_commande"].is_unique
    assert len(fait) == 2