"""
tests/test_clean_commandes.py
===============================
Tests unitaires pour transform/clean_commandes.py — 7 règles de nettoyage
des commandes (R1-R7) + construction du mapping villes.
"""

import pandas as pd
import pytest

from transform.clean_commandes import (
    construire_mapping_villes,
    r1_supprimer_doublons,
    r2_standardiser_dates,
    r3_harmoniser_villes,
    r4_standardiser_statuts,
    r5_supprimer_quantites_invalides,
    r6_supprimer_commandes_test,
    r7_gerer_livreurs_manquants,
)


# ── construire_mapping_villes ────────────────────────────────────────────────

def test_construire_mapping_villes_variantes_casse():
    df_regions = pd.DataFrame({
        "nom_ville_standard": ["Tanger"],
        "code_ville": ["TNG"],
    })
    mapping = construire_mapping_villes(df_regions)
    assert mapping["tanger"] == "Tanger"
    assert mapping["TANGER"] == "Tanger"
    assert mapping["tng"] == "Tanger"


# ── R1 : doublons id_commande ────────────────────────────────────────────────

class TestR1SupprimerDoublons:

    def test_garde_derniere_occurrence(self):
        df = pd.DataFrame({
            "id_commande": [1, 1],
            "valeur": ["ancienne", "nouvelle"],
        })
        result = r1_supprimer_doublons(df)
        assert len(result) == 1
        assert result["valeur"].iloc[0] == "nouvelle"


# ── R2 : standardisation dates ───────────────────────────────────────────────

class TestR2StandardiserDates:

    def test_format_iso(self):
        df = pd.DataFrame({"date_commande": ["2024-01-15"], "date_livraison": [""]})
        result = r2_standardiser_dates(df)
        assert result["date_commande"].iloc[0] == "2024-01-15"

    def test_date_non_parsable_supprimee(self):
        df = pd.DataFrame({
            "date_commande": ["2024-01-15", "pas-une-date"],
            "date_livraison": ["", ""],
        })
        result = r2_standardiser_dates(df)
        assert len(result) == 1  # la ligne invalide est supprimée


# ── R3 : harmonisation villes ────────────────────────────────────────────────

class TestR3HarmoniserVilles:

    def test_ville_connue(self):
        df = pd.DataFrame({"ville_livraison": ["TANGER"]})
        mapping = {"tanger": "Tanger"}
        result = r3_harmoniser_villes(df, mapping)
        assert result["ville_livraison"].iloc[0] == "Tanger"

    def test_ville_inconnue(self):
        df = pd.DataFrame({"ville_livraison": ["VilleXYZ"]})
        mapping = {"tanger": "Tanger"}
        result = r3_harmoniser_villes(df, mapping)
        assert result["ville_livraison"].iloc[0] == "Non renseignée"


# ── R4 : standardisation statuts ─────────────────────────────────────────────

class TestR4StandardiserStatuts:

    def test_variantes_livre(self):
        df = pd.DataFrame({"statut": ["livre", "LIVRE", "DONE"]})
        result = r4_standardiser_statuts(df)
        assert (result["statut"] == "livré").all()

    def test_variantes_annule(self):
        df = pd.DataFrame({"statut": ["annule", "KO"]})
        result = r4_standardiser_statuts(df)
        assert (result["statut"] == "annulé").all()

    def test_statut_non_reconnu(self):
        df = pd.DataFrame({"statut": ["xyz_inconnu"]})
        result = r4_standardiser_statuts(df)
        assert result["statut"].iloc[0] == "inconnu"


# ── R5 : quantités invalides ─────────────────────────────────────────────────

class TestR5SupprimerQuantitesInvalides:

    def test_quantite_positive_conservee(self):
        df = pd.DataFrame({"quantite": [5]})
        result = r5_supprimer_quantites_invalides(df)
        assert len(result) == 1

    def test_quantite_zero_supprimee(self):
        df = pd.DataFrame({"quantite": [0]})
        result = r5_supprimer_quantites_invalides(df)
        assert len(result) == 0

    def test_quantite_negative_supprimee(self):
        df = pd.DataFrame({"quantite": [-3]})
        result = r5_supprimer_quantites_invalides(df)
        assert len(result) == 0


# ── R6 : commandes test (prix = 0) ───────────────────────────────────────────

class TestR6SupprimerCommandesTest:

    def test_prix_zero_supprime(self):
        df = pd.DataFrame({"prix_unitaire": [0]})
        result = r6_supprimer_commandes_test(df)
        assert len(result) == 0

    def test_prix_positif_conserve(self):
        df = pd.DataFrame({"prix_unitaire": [100]})
        result = r6_supprimer_commandes_test(df)
        assert len(result) == 1


# ── R7 : livreurs manquants ──────────────────────────────────────────────────

class TestR7GererLivreursManquants:

    def test_livreur_manquant_devient_moins_un(self):
        df = pd.DataFrame({"id_livreur": [None]})
        result = r7_gerer_livreurs_manquants(df)
        assert result["id_livreur"].iloc[0] == "-1"

    def test_livreur_renseigne_conserve(self):
        df = pd.DataFrame({"id_livreur": ["L42"]})
        result = r7_gerer_livreurs_manquants(df)
        assert result["id_livreur"].iloc[0] == "L42"