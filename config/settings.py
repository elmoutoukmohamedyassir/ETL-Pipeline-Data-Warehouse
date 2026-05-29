# config/settings.py
# Paramètres centraux du pipeline ETL Mexora
# Modifiez DB_CONFIG selon votre environnement local PostgreSQL

import os

# ── Chemins fichiers sources ──────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR       = os.path.join(BASE_DIR, "data")

FILE_COMMANDES = os.path.join(DATA_DIR, "commandes_mexora.csv")
FILE_CLIENTS   = os.path.join(DATA_DIR, "clients_mexora.csv")
FILE_PRODUITS  = os.path.join(DATA_DIR, "produits_mexora.json")
FILE_REGIONS   = os.path.join(DATA_DIR, "regions_maroc.csv")

# ── Connexion PostgreSQL ──────────────────────────────────────────────────────
# Vous pouvez aussi utiliser des variables d'environnement :
#   export DWH_HOST=localhost  DWH_USER=postgres  DWH_PASSWORD=postgres
DB_CONFIG = {
    "host":     os.getenv("DWH_HOST",     "localhost"),
    "port":     os.getenv("DWH_PORT",     "5432"),
    "database": os.getenv("DWH_DATABASE", "mexora_dwh"),
    "user":     os.getenv("DWH_USER",     "postgres"),
    "password": os.getenv("DWH_PASSWORD", "postgres"),
}
DB_URL = (
    f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
)

# ── Schémas PostgreSQL ────────────────────────────────────────────────────────
SCHEMA_STAGING   = "staging_mexora"
SCHEMA_DWH       = "dwh_mexora"
SCHEMA_REPORTING = "reporting_mexora"

# ── Règles métier : segmentation client ──────────────────────────────────────
SEGMENT_GOLD   = 15_000   # MAD — CA 12 mois >= 15 000 → Gold
SEGMENT_SILVER =  5_000   # MAD — CA 12 mois >=  5 000 → Silver
                           #       CA 12 mois <   5 000 → Bronze

# ── Dimension Temps ───────────────────────────────────────────────────────────
DIM_TEMPS_START = "2020-01-01"
DIM_TEMPS_END   = "2025-12-31"

# ── Jours fériés marocains 2020-2025 ─────────────────────────────────────────
FERIES_MAROC = [
    "2020-01-01","2020-01-11","2020-05-01","2020-07-30",
    "2020-08-14","2020-08-20","2020-08-21","2020-11-06","2020-11-18",
    "2021-01-01","2021-01-11","2021-05-01","2021-07-30",
    "2021-08-14","2021-08-20","2021-08-21","2021-11-06","2021-11-18",
    "2022-01-01","2022-01-11","2022-05-01","2022-07-30",
    "2022-08-14","2022-08-20","2022-08-21","2022-11-06","2022-11-18",
    "2023-01-01","2023-01-11","2023-05-01","2023-07-30",
    "2023-08-14","2023-08-20","2023-08-21","2023-11-06","2023-11-18",
    "2024-01-01","2024-01-11","2024-05-01","2024-07-30",
    "2024-08-14","2024-08-20","2024-08-21","2024-11-06","2024-11-18",
    "2025-01-01","2025-01-11","2025-05-01","2025-07-30",
    "2025-08-14","2025-08-20","2025-08-21","2025-11-06","2025-11-18",
]

# ── Périodes Ramadan 2020-2025 ────────────────────────────────────────────────
RAMADAN_PERIODES = [
    ("2020-04-24", "2020-05-23"),
    ("2021-04-13", "2021-05-12"),
    ("2022-04-02", "2022-05-01"),
    ("2023-03-22", "2023-04-20"),
    ("2024-03-10", "2024-04-09"),
    ("2025-03-01", "2025-03-29"),
]