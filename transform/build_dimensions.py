import logging
from datetime import date

import pandas as pd
from config.settings import FERIES_MAROC, RAMADAN_PERIODES, SEGMENT_GOLD, SEGMENT_SILVER

logger = logging.getLogger("mexora_etl")


# ─── DIM_TEMPS ────────────────────────────────────────────────────────────────

def build_dim_temps(date_debut: str, date_fin: str) -> pd.DataFrame:
    """
    Génère la dimension temporelle complète entre deux dates (inclusive).

    Colonnes produites :
      id_date          — entier YYYYMMDD (ex : 20240315), clé primaire
      jour, mois, trimestre, annee, semaine
      libelle_jour     — ex : "Lundi"
      libelle_mois     — ex : "Janvier"
      est_weekend      — True si samedi ou dimanche
      est_ferie_maroc  — True si jour férié officiel marocain
      periode_ramadan  — True si dans une période Ramadan

    Choix d'id_date en YYYYMMDD entier (et non DATE) :
    Les entiers se comparent et s'indexent plus vite en SQL.
    WHERE id_date BETWEEN 20240101 AND 20241231 est instantané.
    """
    JOURS_FR  = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
    MOIS_FR   = ["","Janvier","Février","Mars","Avril","Mai","Juin",
                 "Juillet","Août","Septembre","Octobre","Novembre","Décembre"]

    dates      = pd.date_range(start=date_debut, end=date_fin, freq="D")
    feries_set = set(FERIES_MAROC)

    df = pd.DataFrame({
        "id_date":         dates.strftime("%Y%m%d").astype(int),
        "date_complete":   dates,
        "jour":            dates.day.astype("int16"),
        "mois":            dates.month.astype("int16"),
        "trimestre":       dates.quarter.astype("int16"),
        "annee":           dates.year.astype("int16"),
        "semaine":         dates.isocalendar().week.astype("int16"),
        "libelle_jour":    [JOURS_FR[d.weekday()] for d in dates],
        "libelle_mois":    [MOIS_FR[d.month] for d in dates],
        "est_weekend":     dates.dayofweek >= 5,
        "est_ferie_maroc": dates.strftime("%Y-%m-%d").isin(feries_set),
        "periode_ramadan": False,
    })

    # Marquage Ramadan : on boucle sur chaque période définie dans settings.py
    for debut, fin in RAMADAN_PERIODES:
        masque = (df["date_complete"] >= debut) & (df["date_complete"] <= fin)
        df.loc[masque, "periode_ramadan"] = True

    df = df.drop(columns=["date_complete"])
    logger.info(
        f"[BUILD] dim_temps : {len(df)} jours générés "
        f"({date_debut} → {date_fin}) | "
        f"{df['est_ferie_maroc'].sum()} fériés | "
        f"{df['periode_ramadan'].sum()} jours Ramadan"
    )
    return df


# ─── DIM_PRODUIT (SCD Type 2) ─────────────────────────────────────────────────

def build_dim_produit(df_produits: pd.DataFrame) -> pd.DataFrame:
    """
    Construit dim_produit avec support SCD Type 2.

    SCD Type 2 justification :
    Quand un produit change de catégorie (ex : "Téléphones" → "Smartphones"),
    les ventes passées doivent RESTER classifiées dans l'ancienne catégorie.
    On crée une nouvelle ligne avec date_debut = date du changement et on
    marque l'ancienne ligne est_actif = False.

    Dans ce pipeline initial, on crée la version active de chaque produit.
    En production, un processus de MERGE comparerait avec la version en base.

    Colonnes SCD :
      id_produit_sk  — surrogate key (entier auto-incrémenté, clé du DWH)
      id_produit_nk  — natural key  (identifiant du système source, ex "P001")
      date_debut     — date de début de validité de cette version
      date_fin       — 9999-12-31 pour la version active
      est_actif      — True pour la version courante
    """
    df = df_produits.copy()
    df = df.reset_index(drop=True)
    df["id_produit_sk"]  = range(1, len(df) + 1)
    df["id_produit_nk"]  = df["id_produit"].astype(str)
    df["nom_produit"]    = df["nom"].astype(str)
    df["prix_standard"]  = df["prix_catalogue"]
    df["date_debut"]     = date.today().isoformat()
    df["date_fin"]       = "9999-12-31"
    df["est_actif"]      = True

    colonnes = [
        "id_produit_sk", "id_produit_nk", "nom_produit", "categorie",
        "sous_categorie", "marque", "fournisseur", "prix_standard",
        "origine_pays", "date_debut", "date_fin", "est_actif",
    ]
    dim = df[colonnes].copy()
    logger.info(f"[BUILD] dim_produit : {len(dim)} produits (SCD Type 2 initialisé)")
    return dim


# ─── DIM_CLIENT (SCD Type 2) ──────────────────────────────────────────────────

def build_dim_client(df_clients: pd.DataFrame,
                     df_segments: pd.DataFrame,
                     df_regions: pd.DataFrame) -> pd.DataFrame:
    """
    Construit dim_client avec support SCD Type 2.

    SCD Type 2 sur segment_client :
    Si un client passe de Bronze à Gold, on veut conserver l'historique
    pour analyser les parcours de fidélisation et mesurer l'efficacité
    des campagnes de montée en gamme.

    La région administrative est dénormalisée dans dim_client (pas de jointure
    supplémentaire dans les requêtes analytiques → performances meilleures).
    """
    df = df_clients.copy()

    # Jointure avec les segments calculés depuis les commandes
    df = df.merge(df_segments, on="id_client", how="left")
    df["segment_client"] = df["segment_client"].fillna("Bronze")
    df["ca_12m"]         = df["ca_12m"].fillna(0.0)

    # Dénormalisation de la région administrative depuis le référentiel
    regions_map = (
        df_regions[["nom_ville_standard", "region_admin"]]
        .rename(columns={"nom_ville_standard": "ville"})
    )
    df = df.merge(regions_map, on="ville", how="left")
    df["region_admin"] = df["region_admin"].fillna("Non renseignée")

    # Nom complet normalisé
    df["nom_complet"] = (
        df["prenom"].str.strip() + " " + df["nom"].str.strip()
    ).str.title()

    # Surrogate key et colonnes SCD
    df = df.reset_index(drop=True)
    df["id_client_sk"] = range(1, len(df) + 1)
    df["id_client_nk"] = df["id_client"].astype(str)
    df["date_debut"]   = date.today().isoformat()
    df["date_fin"]     = "9999-12-31"
    df["est_actif"]    = True

    colonnes = [
        "id_client_sk", "id_client_nk", "nom_complet", "tranche_age",
        "sexe", "ville", "region_admin", "segment_client",
        "canal_acquisition", "date_debut", "date_fin", "est_actif",
    ]
    dim = df[colonnes].copy()
    logger.info(f"[BUILD] dim_client  : {len(dim)} clients (SCD Type 2 initialisé)")
    return dim


# ─── DIM_REGION ───────────────────────────────────────────────────────────────

def build_dim_region(df_regions: pd.DataFrame) -> pd.DataFrame:
    """
    Construit dim_region depuis le référentiel géographique officiel.
    Cette dimension est STABLE — les régions administratives ne changent
    que lors de grandes réformes territoriales (pas de SCD nécessaire).
    """
    df = df_regions.copy()
    df = df.reset_index(drop=True)
    df["id_region"] = range(1, len(df) + 1)
    df["ville"]     = df["nom_ville_standard"].str.strip()
    df["pays"]      = "Maroc"

    colonnes = ["id_region", "ville", "province", "region_admin", "zone_geo", "pays"]
    dim = df[colonnes].copy()
    logger.info(f"[BUILD] dim_region  : {len(dim)} régions")
    return dim


# ─── DIM_LIVREUR ──────────────────────────────────────────────────────────────

def build_dim_livreur(df_commandes: pd.DataFrame) -> pd.DataFrame:
    """
    Construit dim_livreur depuis les IDs présents dans les commandes.
    Les détails des livreurs (nom, transport, zone) ne sont pas dans
    les sources — on génère des valeurs de placeholder.
    En production, ces données viendraient du système RH/Logistique.

    Le livreur id_nk = '-1' représente "Inconnu" (commandes sans livreur renseigné).
    """
    import random
    random.seed(42)  # reproductible

    ZONES      = ["Nord", "Centre", "Sud", "Est", "Ouest", "Centre-Nord", "Centre-Sud"]
    TRANSPORTS = ["Moto", "Véhicule léger", "Camionnette"]

    livreurs_nk = sorted(df_commandes["id_livreur"].dropna().unique())
    rows = []

    for sk, nk in enumerate(livreurs_nk, start=1):
        if str(nk) == "-1":
            rows.append({
                "id_livreur":    sk,
                "id_livreur_nk": "-1",
                "nom_livreur":   "Livreur inconnu",
                "type_transport":"Inconnu",
                "zone_couverture":"Inconnue",
            })
        else:
            rows.append({
                "id_livreur":    sk,
                "id_livreur_nk": str(nk),
                "nom_livreur":   f"Livreur {nk}",
                "type_transport": random.choice(TRANSPORTS),
                "zone_couverture": random.choice(ZONES),
            })

    dim = pd.DataFrame(rows)
    logger.info(f"[BUILD] dim_livreur : {len(dim)} livreurs (dont 1 'inconnu' id=-1)")
    return dim


# ─── FAIT_VENTES ──────────────────────────────────────────────────────────────

def build_fait_ventes(df_commandes: pd.DataFrame,
                      dim_temps:    pd.DataFrame,
                      dim_client:   pd.DataFrame,
                      dim_produit:  pd.DataFrame,
                      dim_region:   pd.DataFrame,
                      dim_livreur:  pd.DataFrame) -> pd.DataFrame:
    """
    Construit la table de faits FAIT_VENTES.

    ── Granularité ──────────────────────────────────────────────────────────────
    1 ligne = 1 ligne de commande = 1 produit, 1 client, 1 date.
    C'est le niveau le plus fin disponible dans les sources.
    Cette granularité permet toutes les agrégations analytiques requises.

    ── Mesures ──────────────────────────────────────────────────────────────────
    quantite_vendue      — ADDITIVE    (se somme dans toutes les dimensions)
    montant_ht           — ADDITIVE
    montant_ttc          — ADDITIVE    (mesure principale pour le CA)
    delai_livraison_jours— SEMI-ADD.   (moyenne significative, somme non pertinente)
    remise_pct           — NON-ADD.    (taux : ne jamais sommer des %)

    ── Résolution des surrogate keys ────────────────────────────────────────────
    Les données sources utilisent des clés naturelles (ex : "P001", "C00045").
    La table de faits doit utiliser les surrogate keys entières du DWH.
    On construit des dictionnaires {clé_naturelle → surrogate_key} pour le mapping.
    """
    df = df_commandes.copy()

    # ── id_date : format YYYYMMDD entier ─────────────────────────────────────
    df["id_date"] = pd.to_datetime(df["date_commande"]).dt.strftime("%Y%m%d").astype(int)

    # ── id_produit : natural key → surrogate key ──────────────────────────────
    prod_map = dim_produit.set_index("id_produit_nk")["id_produit_sk"].to_dict()
    df["id_produit"] = df["id_produit"].map(prod_map)
    nb_prod_manquants = df["id_produit"].isna().sum()
    if nb_prod_manquants > 0:
        logger.warning(f"[BUILD] {nb_prod_manquants} produits non résolus → fallback SK=1")
    df["id_produit"] = df["id_produit"].fillna(1).astype(int)

    # ── id_client : natural key → surrogate key ───────────────────────────────
    client_map = dim_client.set_index("id_client_nk")["id_client_sk"].to_dict()
    df["id_client"] = df["id_client"].map(client_map)
    df["id_client"] = df["id_client"].fillna(1).astype(int)

    # ── id_region : via ville_livraison ───────────────────────────────────────
    region_map = dim_region.set_index("ville")["id_region"].to_dict()
    df["id_region"] = df["ville_livraison"].map(region_map).fillna(1).astype(int)

    # ── id_livreur : natural key → surrogate key ──────────────────────────────
    livreur_map = dim_livreur.set_index("id_livreur_nk")["id_livreur"].to_dict()
    inconnu_sk  = dim_livreur.loc[
        dim_livreur["id_livreur_nk"] == "-1", "id_livreur"
    ].values[0]
    df["id_livreur_fk"] = df["id_livreur"].map(livreur_map).fillna(inconnu_sk).astype(int)

    # ── Construction de la table de faits ─────────────────────────────────────
    fait = pd.DataFrame({
        "id_date":                df["id_date"],
        "id_produit":             df["id_produit"],
        "id_client":              df["id_client"],
        "id_region":              df["id_region"],
        "id_livreur":             df["id_livreur_fk"],
        "quantite_vendue":        df["quantite"].astype(int),
        "montant_ht":             df["montant_ht"].round(2),
        "montant_ttc":            df["montant_ttc"].round(2),
        "cout_livraison":         None,          # pas disponible dans les sources
        "delai_livraison_jours":  pd.to_numeric(df["delai_livraison_jours"], errors="coerce"),
        "remise_pct":             0.0,           # pas disponible dans les sources
        "statut_commande":        df["statut"],
    })

    # ── Assertions d'intégrité minimale ───────────────────────────────────────
    assert fait["montant_ttc"].ge(0).all(),       "ERREUR : montants TTC négatifs détectés"
    assert fait["quantite_vendue"].gt(0).all(),   "ERREUR : quantités <= 0 dans les faits"

    # ── Résumé ────────────────────────────────────────────────────────────────
    dist = fait["statut_commande"].value_counts().to_dict()
    ca   = fait.loc[fait["statut_commande"] == "livré", "montant_ttc"].sum()
    logger.info(f"[BUILD] fait_ventes : {len(fait)} lignes | distribution : {dist}")
    logger.info(f"[BUILD] CA total TTC (livrées) : {ca:,.2f} MAD")
    return fait