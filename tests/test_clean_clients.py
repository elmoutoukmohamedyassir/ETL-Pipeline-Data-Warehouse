"""
tests/test_clean_clients.py
=============================
Tests unitaires pour transform/clean_clients.py — 5 règles de nettoyage
des données clients (R1-R5) + segmentation Gold/Silver/Bronze.
"""

import pandas as pd
import pytest

from transform.clean_clients import (
    r1_deduplication_email,
    r2_standardiser_sexe,
    r3_valider_dates_naissance,
    r4_valider_emails,
    r5_harmoniser_villes_clients,
    calculer_segments_clients,
)


# ── R1 : déduplication email ─────────────────────────────────────────────────

class TestR1DeduplicationEmail:

    def test_garde_inscription_la_plus_recente(self):
        df = pd.DataFrame({
            "id_client": [1, 2],
            "email": ["Test@Mail.com", "test@mail.com"],
            "date_inscription": ["2020-01-01", "2023-01-01"],
        })
        result = r1_deduplication_email(df)
        assert len(result) == 1
        assert result["id_client"].iloc[0] == 2  # la plus récente

    def test_emails_differents_non_dedupliques(self):
        df = pd.DataFrame({
            "id_client": [1, 2],
            "email": ["a@mail.com", "b@mail.com"],
            "date_inscription": ["2020-01-01", "2023-01-01"],
        })
        result = r1_deduplication_email(df)
        assert len(result) == 2


# ── R2 : standardisation sexe ────────────────────────────────────────────────

class TestR2StandardiserSexe:

    def test_systeme_lettres(self):
        df = pd.DataFrame({"sexe": ["m", "F"]})
        result = r2_standardiser_sexe(df)
        assert list(result["sexe"]) == ["m", "f"]

    def test_systeme_binaire(self):
        df = pd.DataFrame({"sexe": ["1", "0"]})
        result = r2_standardiser_sexe(df)
        assert list(result["sexe"]) == ["m", "f"]

    def test_systeme_mots(self):
        df = pd.DataFrame({"sexe": ["Homme", "Femme"]})
        result = r2_standardiser_sexe(df)
        assert list(result["sexe"]) == ["m", "f"]

    def test_valeur_non_reconnue_devient_inconnu(self):
        df = pd.DataFrame({"sexe": ["xyz"]})
        result = r2_standardiser_sexe(df)
        assert result["sexe"].iloc[0] == "inconnu"


# ── R3 : validation dates de naissance ───────────────────────────────────────

class TestR3ValiderDatesNaissance:

    def test_age_valide_conserve(self):
        df = pd.DataFrame({"date_naissance": ["1990-01-01"]})
        result = r3_valider_dates_naissance(df)
        assert result["date_naissance"].iloc[0] is not None
        assert not pd.isna(result["age"].iloc[0])

    def test_age_hors_bornes_nullifie(self):
        # un client né il y a 5 ans (âge 5, < 16 ans minimum légal) doit être nullifié
        annee_recente = pd.Timestamp.today().year - 5
        df = pd.DataFrame({"date_naissance": [f"{annee_recente}-01-01"]})
        result = r3_valider_dates_naissance(df)
        assert pd.isna(result["date_naissance"].iloc[0])
        assert pd.isna(result["age"].iloc[0])

    def test_age_supérieur_100_ans_nullifie(self):
        df = pd.DataFrame({"date_naissance": ["1900-01-01"]})
        result = r3_valider_dates_naissance(df)
        assert pd.isna(result["date_naissance"].iloc[0])

    def test_date_invalide_nullifiee(self):
        df = pd.DataFrame({"date_naissance": ["pas-une-date"]})
        result = r3_valider_dates_naissance(df)
        assert pd.isna(result["date_naissance"].iloc[0])


# ── R4 : validation emails ───────────────────────────────────────────────────

class TestR4ValiderEmails:

    def test_email_valide_conserve(self):
        df = pd.DataFrame({"email": ["test@example.com"]})
        result = r4_valider_emails(df)
        assert result["email"].iloc[0] == "test@example.com"

    def test_email_invalide_nullifie(self):
        df = pd.DataFrame({"email": ["pas-un-email"]})
        result = r4_valider_emails(df)
        assert pd.isna(result["email"].iloc[0])

    def test_email_sans_arobase_nullifie(self):
        df = pd.DataFrame({"email": ["test.example.com"]})
        result = r4_valider_emails(df)
        assert pd.isna(result["email"].iloc[0])


# ── R5 : harmonisation villes ────────────────────────────────────────────────

class TestR5HarmoniserVillesClients:

    def test_ville_connue_mappee(self):
        df = pd.DataFrame({"ville": ["CASA"]})
        mapping = {"casa": "Casablanca"}
        result = r5_harmoniser_villes_clients(df, mapping)
        assert result["ville"].iloc[0] == "Casablanca"

    def test_ville_inconnue_devient_non_renseignee(self):
        df = pd.DataFrame({"ville": ["VilleInexistante"]})
        mapping = {"casa": "Casablanca"}
        result = r5_harmoniser_villes_clients(df, mapping)
        assert result["ville"].iloc[0] == "Non renseignée"


# ── Segmentation Gold/Silver/Bronze ──────────────────────────────────────────

class TestCalculerSegmentsClients:

    def test_segment_gold(self):
        df = pd.DataFrame({
            "id_client": [1],
            "date_commande": ["2024-06-01"],
            "statut": ["livré"],
            "montant_ttc": [20000],
        })
        result = calculer_segments_clients(df)
        assert result["segment_client"].iloc[0] == "Gold"

    def test_segment_silver(self):
        df = pd.DataFrame({
            "id_client": [1],
            "date_commande": ["2024-06-01"],
            "statut": ["livré"],
            "montant_ttc": [7000],
        })
        result = calculer_segments_clients(df)
        assert result["segment_client"].iloc[0] == "Silver"

    def test_segment_bronze(self):
        df = pd.DataFrame({
            "id_client": [1],
            "date_commande": ["2024-06-01"],
            "statut": ["livré"],
            "montant_ttc": [1000],
        })
        result = calculer_segments_clients(df)
        assert result["segment_client"].iloc[0] == "Bronze"

    def test_limite_exacte_15000_est_gold(self):
        # règle : >= 15000 est Gold (limite inclusive)
        df = pd.DataFrame({
            "id_client": [1],
            "date_commande": ["2024-06-01"],
            "statut": ["livré"],
            "montant_ttc": [15000],
        })
        result = calculer_segments_clients(df)
        assert result["segment_client"].iloc[0] == "Gold"

    def test_commandes_non_livrees_exclues(self):
        df = pd.DataFrame({
            "id_client": [1],
            "date_commande": ["2024-06-01"],
            "statut": ["annulé"],
            "montant_ttc": [20000],
        })
        result = calculer_segments_clients(df)
        # aucune commande livrée => le client n'apparaît pas dans le résultat
        assert result.empty

    def test_commandes_hors_fenetre_12_mois_exclues(self):
        df = pd.DataFrame({
            "id_client": [1, 1],
            "date_commande": ["2024-06-01", "2020-01-01"],  # 2020 hors fenêtre
            "statut": ["livré", "livré"],
            "montant_ttc": [10000, 50000],
        })
        result = calculer_segments_clients(df)
        # seule la commande de 2024 doit compter => ca_12m = 10000, pas 60000
        assert result["ca_12m"].iloc[0] == 10000