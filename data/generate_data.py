#!/usr/bin/env python3
import csv
import json
import os
import random
from datetime import date, timedelta

random.seed(42)  # résultats reproductibles


# ─── Helpers ──────────────────────────────────────────────────────────────────

def rand_date(start="2022-01-01", end="2024-12-31") -> date:
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    return s + timedelta(days=random.randint(0, (e - s).days))


def rand_date_str(start="2022-01-01", end="2024-12-31") -> str:
    """Retourne une date dans l'un des 3 formats mixtes de l'énoncé."""
    d = rand_date(start, end)
    fmt = random.choices(["iso", "fr", "en"], weights=[40, 40, 20])[0]
    if fmt == "iso": return d.strftime("%Y-%m-%d")
    if fmt == "fr":  return d.strftime("%d/%m/%Y")
    return d.strftime("%b %d %Y")  # Nov 15 2024


# ─── Référentiel villes ───────────────────────────────────────────────────────

VILLES = [
    "Tanger","Casablanca","Rabat","Fès","Marrakech",
    "Agadir","Oujda","Meknès","Kenitra","Tétouan",
    "Nador","Béni Mellal","El Jadida","Safi","Errachidia",
]

VILLES_BRUIT = {
    "Tanger":      ["tanger","TNG","TANGER","Tnja","tanger "],
    "Casablanca":  ["casablanca","CASA","Casa","casablanca "],
    "Rabat":       ["rabat","RABAT","Rbat"],
    "Fès":         ["fes","FES","Fès","Fez"],
    "Marrakech":   ["marrakech","MARRAKECH","Mrakech","Marrakesh"],
    "Agadir":      ["agadir","AGADIR","Agdir"],
    "Oujda":       ["oujda","OUJDA","Oujda "],
    "Meknès":      ["meknes","MEKNES","Meknès"],
    "Kenitra":     ["kenitra","KENITRA","kénitra"],
    "Tétouan":     ["tetouan","TETOUAN","Tétouan"],
    "Nador":       ["nador","NADOR"],
    "Béni Mellal": ["beni mellal","BENI MELLAL","Beni Mellal"],
    "El Jadida":   ["el jadida","EL JADIDA","Eljadida"],
    "Safi":        ["safi","SAFI"],
    "Errachidia":  ["errachidia","ERRACHIDIA"],
}


def ville_bruitee(v: str) -> str:
    return random.choice(VILLES_BRUIT.get(v, [v]))


# ─── Données produits ─────────────────────────────────────────────────────────

PRODUITS = [
    ("P001","iPhone 16 Pro 256Go","Electronique","Smartphones","Apple","Apple MENA",12999.0,"USA"),
    ("P002","Samsung Galaxy S24","Electronique","Smartphones","Samsung","Samsung MENA",9999.0,"Corée du Sud"),
    ("P003","MacBook Pro M3","Electronique","Ordinateurs","Apple","Apple MENA",24999.0,"USA"),
    ("P004","Dell XPS 15","Electronique","Ordinateurs","Dell","Dell Africa",18999.0,"USA"),
    ("P005","iPad Air M2","Electronique","Tablettes","Apple","Apple MENA",7999.0,"USA"),
    ("P006","AirPods Pro","Electronique","Audio","Apple","Apple MENA",2999.0,"USA"),
    ("P007","Sony WH-1000XM5","Electronique","Audio","Sony","Sony MENA",3499.0,"Japon"),
    ("P008","Nike Air Max 270","Mode","Chaussures","Nike","Nike EMEA",1299.0,"Vietnam"),
    ("P009","Adidas Ultraboost 23","Mode","Chaussures","Adidas","Adidas EMEA",1599.0,"Allemagne"),
    ("P010","Zara Veste Homme","Mode","Vêtements","Zara","Inditex MENA",699.0,"Espagne"),
    ("P011","H&M Robe Femme","Mode","Vêtements","H&M","H&M Africa",399.0,"Bangladesh"),
    ("P012","Huile Olive Volubilis 1L","Alimentation","Épicerie","Volubilis","Volubilis SA",89.0,"Maroc"),
    ("P013","Thé Menthe 200g","Alimentation","Boissons","Atay","Atay Maroc",45.0,"Maroc"),
    ("P014","Couscous Royal 5kg","Alimentation","Épicerie","Royal","Royal Foods",120.0,"Maroc"),
    ("P015","Argan Bio 100ml","Alimentation","Bio","Tifawin","Tifawin Bio",350.0,"Maroc"),
    ("P016","PS5 Console","Electronique","Jeux vidéo","Sony","Sony MENA",5999.0,"Japon"),
    ("P017","Xbox Series X","Electronique","Jeux vidéo","Microsoft","Microsoft MENA",5499.0,"Chine"),
    ("P018","LG OLED 55\"","Electronique","TV","LG","LG Africa",14999.0,"Corée du Sud"),
    ("P019","Cafetière Nespresso","Electronique","Cuisine","Nespresso","Nespresso MENA",1299.0,"Suisse"),
    ("P020","Robot Aspirateur Xiaomi","Electronique","Maison","Xiaomi","Xiaomi EMEA",2499.0,"Chine"),
]

CATS_BRUIT = {
    "Electronique": ["electronique","Electronique","ELECTRONIQUE","Électronique"],
    "Mode":         ["mode","Mode","MODE"],
    "Alimentation": ["alimentation","Alimentation","ALIMENTATION"],
}


# ─── Données clients ──────────────────────────────────────────────────────────

NOMS = ["Alami","Benali","Chaoui","Drissi","El Mansouri","Fassi","Gharbi","Hajji",
        "Idrissi","Jamai","Karimi","Lahlou","Moussaoui","Naciri","Ouali",
        "Rachidi","Senhaji","Tazi","Ziani","Bensaid","Chraibi","Filali"]
PRENOMS_H = ["Mohammed","Ahmed","Youssef","Omar","Hassan","Karim","Amine",
             "Rachid","Mehdi","Tariq","Samir","Nabil","Adil","Hicham","Ayoub"]
PRENOMS_F = ["Fatima","Aisha","Sara","Leila","Nadia","Sanaa","Houda","Zineb",
             "Meryem","Khadija","Rim","Hajar","Soukaina","Imane","Yasmine"]
CANAUX    = ["organic","social_media","email","paid_search","referral","direct","influencer"]
DOMAINES  = ["gmail.com","yahoo.fr","hotmail.com","menara.ma","outlook.com"]


# ─── Générateurs ──────────────────────────────────────────────────────────────

def gen_regions():
    rows = [
        ("TNG","Tanger","Fahs-Anjra","Tanger-Tétouan-Al Hoceïma","Nord",1065601,"90000"),
        ("CAS","Casablanca","Casablanca","Casablanca-Settat","Centre",4270750,"20000"),
        ("RBT","Rabat","Rabat","Rabat-Salé-Kénitra","Centre",1655753,"10000"),
        ("FES","Fès","Fès","Fès-Meknès","Centre-Nord",1112072,"30000"),
        ("MRK","Marrakech","Marrakech","Marrakech-Safi","Centre-Sud",1070838,"40000"),
        ("AGA","Agadir","Agadir-Ida-Ou-Tanane","Souss-Massa","Sud",916101,"80000"),
        ("OUJ","Oujda","Oujda-Angad","Oriental","Est",609207,"60000"),
        ("MEK","Meknès","El Hajeb","Fès-Meknès","Centre-Nord",698350,"50000"),
        ("KEN","Kenitra","Kenitra","Rabat-Salé-Kénitra","Centre",431282,"14000"),
        ("TET","Tétouan","Tétouan","Tanger-Tétouan-Al Hoceïma","Nord",380787,"93000"),
        ("NAD","Nador","Nador","Oriental","Nord-Est",201000,"62000"),
        ("BNM","Béni Mellal","Béni Mellal","Béni Mellal-Khénifra","Centre",185579,"23000"),
        ("ELJ","El Jadida","El Jadida","Casablanca-Settat","Centre-Ouest",194934,"24000"),
        ("SAF","Safi","Safi","Marrakech-Safi","Centre-Sud",308508,"46000"),
        ("ERR","Errachidia","Errachidia","Drâa-Tafilalet","Sud",94000,"52000"),
    ]
    os.makedirs("data", exist_ok=True)
    with open("data/regions_maroc.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["code_ville","nom_ville_standard","province","region_admin",
                    "zone_geo","population","code_postal"])
        w.writerows(rows)
    print(f"✓ regions_maroc.csv : {len(rows)} lignes")


def gen_clients(n=3000):
    rows      = []
    emails_vu = []

    for i in range(1, n + 1):
        sexe_r  = random.choice(["m", "f"])
        prenom  = random.choice(PRENOMS_H if sexe_r == "m" else PRENOMS_F)
        nom     = random.choice(NOMS)
        email   = f"{prenom.lower()}.{nom.lower()}{random.randint(1,999)}@{random.choice(DOMAINES)}"

        # Problème intentionnel : ~3% doublons email
        if i > 100 and random.random() < 0.03 and emails_vu:
            email = random.choice(emails_vu)
        emails_vu.append(email)

        # Problème intentionnel : ~2% emails mal formatés
        if random.random() < 0.02:
            email = random.choice([
                email.replace("@", ""),
                email.replace(".com", ""),
                "invalide_sans_arobase",
            ])

        # Problème intentionnel : ~5% âges invalides (< 16 ou > 100 ans)
        age_cible = random.randint(14, 105)
        dob = date(2025, 1, 1) - timedelta(days=int(age_cible * 365.25))

        # Problème intentionnel : sexe codé de 3 façons différentes
        sexe_map = {
            "m": random.choice(["m", "1", "Homme", "male", "h"]),
            "f": random.choice(["f", "0", "Femme", "female", "F"]),
        }
        sexe_noisy = sexe_map[sexe_r]
        ville = random.choice(VILLES)

        rows.append([
            f"C{i:05d}", nom, prenom, email,
            dob.strftime("%Y-%m-%d"), sexe_noisy,
            ville_bruitee(ville),
            f"06{random.randint(10000000, 99999999)}",
            rand_date_str("2020-01-01", "2024-06-01"),
            random.choice(CANAUX),
        ])

    with open("data/clients_mexora.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id_client","nom","prenom","email","date_naissance","sexe",
                    "ville","telephone","date_inscription","canal_acquisition"])
        w.writerows(rows)
    print(f"✓ clients_mexora.csv : {len(rows)} lignes")
    return [r[0] for r in rows]


def gen_produits():
    produits = []
    for i, (pid, nom, cat, scat, marque, fourn, prix, pays) in enumerate(PRODUITS):
        # Problème intentionnel : casse incohérente des catégories
        cat_bruitee = random.choice(CATS_BRUIT.get(cat, [cat]))
        # Problème intentionnel : produits inactifs avec commandes
        actif = i % 7 != 0
        # Problème intentionnel : ~5% prix null
        prix_val = None if random.random() < 0.05 else prix

        produits.append({
            "id_produit":    pid,
            "nom":           nom,
            "categorie":     cat_bruitee,
            "sous_categorie":scat,
            "marque":        marque,
            "fournisseur":   fourn,
            "prix_catalogue":prix_val,
            "origine_pays":  pays,
            "date_creation": rand_date_str("2020-01-01", "2024-01-01"),
            "actif":         actif,
        })

    with open("data/produits_mexora.json", "w", encoding="utf-8") as f:
        json.dump({"produits": produits}, f, ensure_ascii=False, indent=2)
    print(f"✓ produits_mexora.json : {len(produits)} produits")
    return [p["id_produit"] for p in produits]


def gen_commandes(client_ids, produit_ids, n=50000):
    STATUTS = {
        "livré": 0.60, "annulé": 0.10, "en_cours": 0.20, "retourné": 0.10
    }
    STATUTS_BRUIT = {
        "livré":    ["livré","livre","LIVRE","DONE"],
        "annulé":   ["annulé","annule","KO"],
        "en_cours": ["en_cours","OK"],
        "retourné": ["retourné","retourne"],
    }
    PAIEMENTS = ["carte","virement","cash","PayPal","CMI"]
    LIVREURS  = [f"L{i:03d}" for i in range(1, 51)]

    rows = []

    for i in range(1, n + 1):
        statut_r = random.choices(list(STATUTS), weights=list(STATUTS.values()))[0]
        statut   = random.choice(STATUTS_BRUIT[statut_r])

        d_cmd = rand_date()
        # Problème intentionnel : 3 formats de dates mélangés
        date_cmd = rand_date_str()

        if statut_r in ("livré", "retourné"):
            d_liv    = d_cmd + timedelta(days=random.randint(1, 7))
            date_liv = d_liv.strftime("%Y-%m-%d")
        else:
            date_liv = ""

        qte  = random.randint(1, 10)
        prix = round(random.uniform(50, 15000), 2)

        # Problème intentionnel : ~1% quantités négatives
        if random.random() < 0.01: qte = -qte
        # Problème intentionnel : ~0.5% prix à 0 (commandes test)
        if random.random() < 0.005: prix = 0.0
        # Problème intentionnel : ~7% livreurs manquants
        livreur = random.choice(LIVREURS) if random.random() > 0.07 else ""

        rows.append([
            f"ORD{i:06d}",
            random.choice(client_ids),
            random.choice(produit_ids),
            date_cmd, qte, prix, statut,
            ville_bruitee(random.choice(VILLES)),
            random.choice(PAIEMENTS),
            livreur, date_liv,
        ])

    # Problème intentionnel : ~3% doublons sur id_commande
    n_dupl = int(n * 0.03)
    for r in random.sample(rows, n_dupl):
        dup = list(r)
        dup[5] = round(r[5] * random.uniform(0.95, 1.05), 2)
        rows.append(dup)

    random.shuffle(rows)

    with open("data/commandes_mexora.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id_commande","id_client","id_produit","date_commande","quantite",
                    "prix_unitaire","statut","ville_livraison","mode_paiement",
                    "id_livreur","date_livraison"])
        w.writerows(rows)
    print(f"✓ commandes_mexora.csv : {len(rows)} lignes (dont ~{n_dupl} doublons)")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Génération des fichiers de données Mexora...")
    gen_regions()
    client_ids  = gen_clients(3000)
    produit_ids = gen_produits()
    gen_commandes(client_ids, produit_ids, 50000)
    print("\nTous les fichiers générés dans data/")
    print("Lancez ensuite : python3 main.py")