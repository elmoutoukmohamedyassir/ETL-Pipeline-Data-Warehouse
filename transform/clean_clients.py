import logging
import re
from datetime import date, timedelta

import pandas as pd
from utils.logger import log_step

logger = logging.getLogger("mexora_etl")


def r1_deduplication_email(df: pd.DataFrame) -> pd.DataFrame:
    """
    R1 — Déduplication sur email normalisé.
    Contexte : une migration passée a créé des doublons (même email,
    id_client différent). L'email est l'identifiant de confiance.
    On conserve l'inscription la plus RÉCENTE.
    """
    avant = len(df)
    df["email_norm"] = df["email"].str.lower().str.strip()
    df["date_inscription"] = pd.to_datetime(df["date_inscription"], errors="coerce")
    df = (
        df.sort_values("date_inscription")
          .drop_duplicates(subset=["email_norm"], keep="last")
          .copy()
    )
    log_step(logger, "R1 — Doublons email clients", avant, len(df))
    return df


def r2_standardiser_sexe(df: pd.DataFrame) -> pd.DataFrame:
    """
    R2 — Standardisation du sexe vers 'm' / 'f' / 'inconnu'.
    Trois systèmes sources avec trois conventions différentes :
      Système A : 'm' / 'f'
      Système B : '1' / '0'
      Système C : 'Homme' / 'Femme'
    """
    mapping = {
        "m": "m", "M": "m", "male": "m", "homme": "m", "h": "m", "1": "m",
        "f": "f", "F": "f", "female": "f", "femme": "f", "0": "f",
    }
    df["sexe"] = df["sexe"].str.lower().str.strip().map(mapping).fillna("inconnu")
    nb_inconnus = (df["sexe"] == "inconnu").sum()
    logger.info(f"[TRANSFORM] R2 — Sexe standardisé | {nb_inconnus} valeurs → 'inconnu'")
    return df


def r3_valider_dates_naissance(df: pd.DataFrame) -> pd.DataFrame:
    """
    R3 — Validation des dates de naissance.
    Plage acceptée : âge entre 16 ans (légal e-commerce Maroc) et 100 ans.
    Les dates invalides sont NULLIFIÉES (pas supprimées : on garde le client,
    simplement sans date de naissance fiable).
    """
    df["date_naissance"] = pd.to_datetime(df["date_naissance"], errors="coerce")
    today = pd.Timestamp(date.today())

    age_days = (today - df["date_naissance"]).dt.days
    df["age"] = (age_days / 365.25).where(age_days.notna()).astype(float)

    masque_invalide = (~df["age"].isna()) & ((df["age"] < 16) | (df["age"] > 100))
    nb_invalides = masque_invalide.sum()
    df.loc[masque_invalide, ["date_naissance", "age"]] = None

    # Calcul des tranches d'âge pour dim_client
    df["tranche_age"] = pd.cut(
        df["age"].fillna(0).astype(float),
        bins=[0, 18, 25, 35, 45, 55, 65, 200],
        labels=["<18", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
        right=False,
    ).astype(str).replace("nan", "Inconnu")

    logger.info(
        f"[TRANSFORM] R3 — Dates naissance | "
        f"{nb_invalides} invalides (âge hors 16-100) nullifiées"
    )
    return df


def r4_valider_emails(df: pd.DataFrame) -> pd.DataFrame:
    """
    R4 — Validation du format email.
    Les emails invalides sont NULLIFIÉS : le client reste dans le DWH mais
    est exclu des campagnes email marketing.
    Regex : format standard RFC 5322 simplifié.
    """
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    masque_invalide = ~df["email"].str.match(pattern, na=False)
    nb_invalides = masque_invalide.sum()
    df.loc[masque_invalide, "email"] = None
    logger.info(f"[TRANSFORM] R4 — Emails invalides | {nb_invalides} nullifiés")
    return df


def r5_harmoniser_villes_clients(df: pd.DataFrame, mapping_villes: dict) -> pd.DataFrame:
    """
    R5 — Harmonisation des villes clients via le référentiel officiel.
    Même logique que pour les commandes (R3 dans clean_commandes.py).
    """
    avant = len(df)
    df["ville_clean"] = df["ville"].str.strip().str.lower()
    df["ville"] = df["ville_clean"].map(mapping_villes).fillna("Non renseignée")
    df = df.drop(columns=["ville_clean"])
    nb_non_rec = (df["ville"] == "Non renseignée").sum()
    log_step(logger, "R5 — Villes clients harmonisées", avant, len(df),
             f"{nb_non_rec} non reconnues → 'Non renseignée'")
    return df


def transform_clients(df_raw: pd.DataFrame, mapping_villes: dict) -> pd.DataFrame:
    """
    Orchestre les 5 règles de nettoyage des clients.
    Note : la segmentation Gold/Silver/Bronze est calculée séparément via
    calculer_segments_clients(), car elle nécessite les commandes nettoyées.
    """
    initial = len(df_raw)
    logger.info(f"[TRANSFORM] ══ CLIENTS début ({initial} lignes brutes) ══")

    df = r1_deduplication_email(df_raw.copy())
    df = r2_standardiser_sexe(df)
    df = r3_valider_dates_naissance(df)
    df = r4_valider_emails(df)
    df = r5_harmoniser_villes_clients(df, mapping_villes)

    logger.info(
        f"[TRANSFORM] ══ CLIENTS fin   "
        f"({initial} → {len(df)} lignes, {initial - len(df)} doublons supprimés) ══"
    )
    return df


def calculer_segments_clients(df_commandes: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule le segment Gold / Silver / Bronze pour chaque client.
    Basé sur le CA cumulé des 12 derniers mois sur commandes LIVRÉES uniquement.

    Règles métier Mexora :
      Gold   : CA 12 mois >= 15 000 MAD
      Silver : CA 12 mois >=  5 000 MAD
      Bronze : CA 12 mois <   5 000 MAD

    Note : on utilise la date max des données (pas today) pour éviter que
    tous les clients tombent en Bronze si les données datent de 2022-2024.
    """
    max_date = pd.to_datetime(df_commandes["date_commande"]).max()
    date_limite = max_date - pd.Timedelta(days=365)

    df_recents = df_commandes[
        (pd.to_datetime(df_commandes["date_commande"]) >= date_limite)
        & (df_commandes["statut"] == "livré")
    ].copy()

    if df_recents.empty:
        logger.warning("[TRANSFORM] Segmentation : aucune commande dans la fenêtre 12 mois")
        return pd.DataFrame(columns=["id_client", "segment_client", "ca_12m"])

    ca = (
        df_recents.groupby("id_client")["montant_ttc"]
        .sum()
        .reset_index()
        .rename(columns={"montant_ttc": "ca_12m"})
    )

    def _segmenter(ca_val: float) -> str:
        if ca_val >= 15_000:
            return "Gold"
        if ca_val >= 5_000:
            return "Silver"
        return "Bronze"

    ca["segment_client"] = ca["ca_12m"].apply(_segmenter)
    dist = ca["segment_client"].value_counts().to_dict()
    logger.info(f"[TRANSFORM] Segments calculés : {dist}")
    return ca[["id_client", "segment_client", "ca_12m"]]