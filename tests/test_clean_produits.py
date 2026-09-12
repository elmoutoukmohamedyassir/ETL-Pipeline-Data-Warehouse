"""
tests/test_clean_produits.py
==============================
Tests unitaires pour transform/clean_produits.py — 3 règles de nettoyage
du catalogue produits (R1-R3).
"""

import pandas as pd
import pytest

from transform.clean_produits import transform_produits


class TestTransformProduits:

    def test_r1_categorie_title_case(self):
        df = pd.DataFrame({
            "categorie": ["electronique"],
            "sous_categorie": ["telephones"],
            "marque": ["Samsung"],
            "fournisseur": ["Fournisseur A"],
            "prix_catalogue": [1000],
            "actif": [True],
        })
        result = transform_produits(df)
        assert result["categorie"].iloc[0] == "Electronique"

    def test_r2_prix_nul_devient_moins_un(self):
        df = pd.DataFrame({
            "categorie": ["Meubles"],
            "sous_categorie": ["Chaises"],
            "marque": ["MarqueX"],
            "fournisseur": ["FournA"],
            "prix_catalogue": [None],
            "actif": [True],
        })
        result = transform_produits(df)
        assert result["prix_catalogue"].iloc[0] == -1.0

    def test_r2_prix_valide_conserve(self):
        df = pd.DataFrame({
            "categorie": ["Meubles"],
            "sous_categorie": ["Chaises"],
            "marque": ["MarqueX"],
            "fournisseur": ["FournA"],
            "prix_catalogue": [499.99],
            "actif": [True],
        })
        result = transform_produits(df)
        assert result["prix_catalogue"].iloc[0] == 499.99

    def test_r3_produit_inactif_conserve(self):
        # règle métier : les produits inactifs doivent être GARDÉS
        # (SCD Type 2 — historique préservé), pas supprimés
        df = pd.DataFrame({
            "categorie": ["Electronique"],
            "sous_categorie": ["Telephones"],
            "marque": ["Apple"],
            "fournisseur": ["FournA"],
            "prix_catalogue": [8000],
            "actif": [False],
        })
        result = transform_produits(df)
        assert len(result) == 1  # toujours présent
        assert result["actif"].iloc[0] == False