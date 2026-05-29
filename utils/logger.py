import logging
import os
from datetime import datetime


def setup_logger(name: str = "mexora_etl") -> logging.Logger:
    """
    Initialise et retourne le logger principal du pipeline.
    Crée deux handlers : un fichier horodaté + la console.
    """
    os.makedirs("logs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Évite de dupliquer les handlers si setup_logger est appelé plusieurs fois
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler fichier — garde tout (DEBUG et au-dessus)
    fh = logging.FileHandler(f"logs/etl_{timestamp}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # Handler console — INFO et au-dessus seulement
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger


def log_step(logger: logging.Logger, etape: str, avant: int, apres: int, detail: str = ""):
    """
    Helper uniforme pour logger chaque étape de transformation.
    Affiche : nom de l'étape | lignes avant → après | lignes supprimées | détail optionnel
    """
    supprimes = avant - apres
    msg = (
        f"[TRANSFORM] {etape:<35} | "
        f"{avant:>6} → {apres:>6} lignes"
        f" ({supprimes:>5} supprimées)"
    )
    if detail:
        msg += f" | {detail}"

    if supprimes > 0:
        logger.info(msg)
    else:
        logger.debug(msg)