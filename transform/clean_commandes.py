import logging
import pandas as pd
from utils.logger import log_step

logger = logging.getLogger("mexora_etl")


# ─── Mapping des villes ───────────────────────────────────────────────────────

def construire_mapping_villes(df_regions: pd.DataFrame) -> dict:
    """
    Construit un dictionnaire de normalisation des villes depuis le référentiel
    officiel regions_maroc.csv. Ce fichier est la seule source de vérité.

    Le dictionnaire mappe toute variante connue → nom standard.
    Ex : "tanger", "TNG", "TANGER", "Tnja" → "Tanger"
    """
    mapping = {}

    for _, row in df_regions.iterrows():
        std = row["nom_ville_standard"].strip()
        # On indexe chaque variante de casse possible
        for variante in [std, std.lower(), std.upper(), std.title()]:
            mapping[variante.strip()] = std
        # Code court (ex : TNG → Tanger)
        mapping[row["code_ville"].strip().lower()] = std
        mapping[row["code_ville"].strip().upper()] = std

    # Variantes connues non couvertes automatiquement
    extras = {
        "tnja": "Tanger", "tng": "Tanger",
        "casa": "Casablanca", "casablanca ": "Casablanca",
        "rbat": "Rabat",
        "fes": "Fès", "fez": "Fès",
        "mrakech": "Marrakech", "marrakesh": "Marrakech",
        "agdir": "Agadir",
        "meknes": "Meknès",
        "kenitra": "Kenitra", "kénitra": "Kenitra",
        "tetouan": "Tétouan",
        "beni mellal": "Béni Mellal",
        "eljadida": "El Jadida",
    }
    mapping.update(extras)
    logger.debug(f"[REFERENTIEL] {len(mapping)} entrées de mapping villes construites")
    return mapping


# ─── Règles de nettoyage ──────────────────────────────────────────────────────

def r1_supprimer_doublons(df: pd.DataFrame) -> pd.DataFrame:
    """
    R1 — Suppression des doublons sur id_commande.
    Règle métier : en cas de doublon, on conserve la DERNIÈRE occurrence
    (hypothèse : la saisie la plus récente est la correction de l'erreur).
    Environ 3% des lignes sont concernées.
    """
    avant = len(df)
    df = df.drop_duplicates(subset=["id_commande"], keep="last")
    log_step(logger, "R1 — Doublons id_commande", avant, len(df))
    return df


def r2_standardiser_dates(df: pd.DataFrame) -> pd.DataFrame:
    """
    R2 — Standardisation des dates au format YYYY-MM-DD.
    Les 3 formats détectés dans les sources :
      - YYYY-MM-DD  (système A, ISO)
      - DD/MM/YYYY  (système B, format français)
      - Mon DD YYYY (système C, format anglais textuel)
    Les dates non parsables sont supprimées (une commande sans date est inutilisable).
    """
    avant = len(df)
    df["date_commande"] = pd.to_datetime(
        df["date_commande"], format="mixed", dayfirst=True, errors="coerce"
    )
    nb_invalides = df["date_commande"].isna().sum()
    df = df.dropna(subset=["date_commande"])
    df["date_commande"] = df["date_commande"].dt.strftime("%Y-%m-%d")

    # date_livraison : optionnelle, peut être vide (commandes non encore livrées)
    mask_non_vide = df["date_livraison"].str.strip() != ""
    if mask_non_vide.any():
        df.loc[mask_non_vide, "date_livraison"] = pd.to_datetime(
            df.loc[mask_non_vide, "date_livraison"],
            format="mixed", dayfirst=True, errors="coerce"
        ).dt.strftime("%Y-%m-%d")

    log_step(logger, "R2 — Standardisation dates", avant, len(df),
             f"{nb_invalides} dates non parsables supprimées")
    return df


def r3_harmoniser_villes(df: pd.DataFrame, mapping_villes: dict) -> pd.DataFrame:
    """
    R3 — Harmonisation des noms de villes via le référentiel officiel.
    Toute ville non reconnue → "Non renseignée".
    """
    avant = len(df)
    df["ville_livraison_clean"] = df["ville_livraison"].str.strip().str.lower()
    df["ville_livraison"] = (
        df["ville_livraison_clean"]
        .map(mapping_villes)
        .fillna("Non renseignée")
    )
    df = df.drop(columns=["ville_livraison_clean"])
    nb_non_reconnus = (df["ville_livraison"] == "Non renseignée").sum()
    log_step(logger, "R3 — Harmonisation villes", avant, len(df),
             f"{nb_non_reconnus} villes non reconnues → 'Non renseignée'")
    return df


def r4_standardiser_statuts(df: pd.DataFrame) -> pd.DataFrame:
    """
    R4 — Standardisation des statuts de commande.
    Valeurs sources → valeurs cibles :
      livré/livre/LIVRE/DONE → livré
      annulé/annule/KO       → annulé
      en_cours/OK            → en_cours
      retourné/retourne      → retourné
      tout le reste          → inconnu
    """
    avant = len(df)
    mapping = {
        "livré": "livré", "livre": "livré", "LIVRE": "livré", "DONE": "livré",
        "annulé": "annulé", "annule": "annulé", "KO": "annulé",
        "en_cours": "en_cours", "OK": "en_cours",
        "retourné": "retourné", "retourne": "retourné",
    }
    df["statut"] = df["statut"].map(mapping)
    nb_inconnus = df["statut"].isna().sum()
    if nb_inconnus > 0:
        logger.warning(f"[TRANSFORM] R4 — {nb_inconnus} statuts non reconnus → 'inconnu'")
    df["statut"] = df["statut"].fillna("inconnu")
    log_step(logger, "R4 — Standardisation statuts", avant, len(df))
    return df


def r5_supprimer_quantites_invalides(df: pd.DataFrame) -> pd.DataFrame:
    """
    R5 — Suppression des lignes avec quantité <= 0.
    Règle métier : une quantité négative ou nulle est une erreur de saisie opérateur.
    Sans connaître la valeur réelle, la ligne ne peut pas alimenter les KPIs.
    """
    avant = len(df)
    df["quantite"] = pd.to_numeric(df["quantite"], errors="coerce")
    df = df[df["quantite"] > 0].copy()
    log_step(logger, "R5 — Quantités invalides (≤ 0)", avant, len(df))
    return df


def r6_supprimer_commandes_test(df: pd.DataFrame) -> pd.DataFrame:
    """
    R6 — Suppression des commandes test (prix_unitaire = 0).
    Règle métier : Mexora crée des commandes à prix nul pour tester son système
    de paiement. Ces lignes fausseraient tous les KPIs de chiffre d'affaires.
    """
    avant = len(df)
    df["prix_unitaire"] = pd.to_numeric(df["prix_unitaire"], errors="coerce")
    df = df[df["prix_unitaire"] > 0].copy()
    log_step(logger, "R6 — Commandes test (prix = 0)", avant, len(df))
    return df


def r7_gerer_livreurs_manquants(df: pd.DataFrame) -> pd.DataFrame:
    """
    R7 — Remplacement des id_livreur manquants par '-1'.
    Règle métier : 7% des commandes n'ont pas de livreur renseigné (sous-traitance
    non tracée ou oubli de saisie). On ne supprime pas ces lignes car elles
    représentent de vraies ventes. Un livreur virtuel id='-1' ("Inconnu") est
    créé dans dim_livreur pour ne pas casser l'intégrité référentielle.
    """
    nb_manquants = (df["id_livreur"].str.strip() == "").sum()
    df["id_livreur"] = df["id_livreur"].replace("", "-1").fillna("-1")
    logger.info(
        f"[TRANSFORM] R7 — Livreurs manquants                "
        f"| {nb_manquants:>6} remplacés par id = -1"
    )
    return df


def r8_calculer_montants(df: pd.DataFrame) -> pd.DataFrame:
    """
    R8 — Calcul des montants HT et TTC.
    TVA Maroc : taux standard = 20%.
    Règle métier : le prix_unitaire dans la source est exprimé HORS TAXES.
    Les deux montants sont nécessaires :
      - montant_ht  → analyses fournisseurs et marges
      - montant_ttc → analyses client-facing et CA décisionnel
    """
    TVA = 0.20
    df["montant_ht"]  = (df["quantite"] * df["prix_unitaire"]).round(2)
    df["montant_ttc"] = (df["montant_ht"] * (1 + TVA)).round(2)
    logger.debug("[TRANSFORM] R8 — Colonnes montant_ht et montant_ttc calculées (TVA 20%)")
    return df


def r9_calculer_delai_livraison(df: pd.DataFrame) -> pd.DataFrame:
    """
    R9 — Calcul du délai de livraison en jours.
    Uniquement pour les commandes livrées ou retournées (les autres n'ont pas
    de date_livraison renseignée). Les délais négatifs (erreur de saisie) et
    les délais > 60 jours (valeur aberrante) sont nullifiés.
    """
    df["delai_livraison_jours"] = None
    mask = (
        df["statut"].isin(["livré", "retourné"])
        & (df["date_livraison"].str.strip() != "")
        & df["date_livraison"].notna()
    )
    if mask.any():
        delais = (
            pd.to_datetime(df.loc[mask, "date_livraison"])
            - pd.to_datetime(df.loc[mask, "date_commande"])
        ).dt.days
        df.loc[mask, "delai_livraison_jours"] = delais
        # Invalider les valeurs aberrantes
        df.loc[df["delai_livraison_jours"] < 0,  "delai_livraison_jours"] = None
        df.loc[df["delai_livraison_jours"] > 60, "delai_livraison_jours"] = None
    nb_calcules = mask.sum()
    logger.debug(f"[TRANSFORM] R9 — Délais calculés pour {nb_calcules} commandes livrées/retournées")
    return df


# ─── Orchestration ────────────────────────────────────────────────────────────

def transform_commandes(df_raw: pd.DataFrame, df_regions: pd.DataFrame) -> pd.DataFrame:
    """
    Applique les 9 règles de nettoyage dans l'ordre correct.
    Retourne le DataFrame propre, prêt pour la construction des dimensions.
    """
    initial = len(df_raw)
    logger.info(f"[TRANSFORM] ══ COMMANDES début ({initial} lignes brutes) ══")

    mapping_villes = construire_mapping_villes(df_regions)

    df = r1_supprimer_doublons(df_raw.copy())
    df = r2_standardiser_dates(df)
    df = r3_harmoniser_villes(df, mapping_villes)
    df = r4_standardiser_statuts(df)
    df = r5_supprimer_quantites_invalides(df)
    df = r6_supprimer_commandes_test(df)
    df = r7_gerer_livreurs_manquants(df)
    df = r8_calculer_montants(df)
    df = r9_calculer_delai_livraison(df)

    logger.info(
        f"[TRANSFORM] ══ COMMANDES fin   "
        f"({initial} → {len(df)} lignes, {initial - len(df)} supprimées) ══"
    )
    return df