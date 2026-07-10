"""
Scraper de prix composants PC (LDLC + Boulanger).
Ecrit le resultat dans data/prices.json avec un historique cumulatif.

Usage: python scraper.py
Prevu pour tourner via GitHub Actions (cron), mais fonctionne en local.
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

DATA_FILE = Path("data/prices.json")
REQUEST_DELAY_SECONDS = 3  # respecte les serveurs, evite le rate-limit / ban IP

# Liste des produits a suivre. Ajoute/retire des entrees ici.
WATCHLIST = [
    {
        "id": "ram32",
        "name": "Kingston FURY Beast 32Go 6000 CL30",
        "cat": "RAM",
        "target": 400,
        "sources": [
            {"site": "LDLC", "url": "https://www.ldlc.com/fiche/PB00654376.html"},
            {"site": "Boulanger", "url": "https://www.boulanger.com/ref/9000601853"},
        ],
    },
    {
        "id": "ram64",
        "name": "Kingston FURY Beast 64Go 6000 CL30",
        "cat": "RAM",
        "target": 800,
        "sources": [
            {"site": "LDLC", "url": "https://www.ldlc.com/fiche/PB00630887.html"},
        ],
    },
    {
        "id": "ram32_corsair",
        "name": "Corsair Vengeance 32Go 6000 CL30",
        "cat": "RAM",
        "target": 380,
        "sources": [
            {"site": "Boulanger", "url": "https://www.boulanger.com/ref/9000613200"},
        ],
    },
]


def fetch_html(url):
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def parse_price_ldlc(html):
    """
    LDLC affiche le prix en texte brut, format '589€95'.
    On cherche le premier motif prix a proximite du bloc d'achat.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    match = re.search(r"(\d[\d\s]{0,6})\s?€\s?(\d{2})", text)
    if not match:
        return None
    euros = match.group(1).replace(" ", "").replace("\u202f", "")
    cents = match.group(2)
    return float(f"{euros}.{cents}")


def parse_price_boulanger(html):
    """
    Boulanger affiche le prix format '642,81€'.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    match = re.search(r"(\d[\d\s]{0,6}),(\d{2})\s?€", text)
    if not match:
        return None
    euros = match.group(1).replace(" ", "").replace("\u202f", "")
    cents = match.group(2)
    return float(f"{euros}.{cents}")


PARSERS = {
    "LDLC": parse_price_ldlc,
    "Boulanger": parse_price_boulanger,
}


def load_existing_data():
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"components": {}}


def save_data(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def scrape_component(component, existing_history):
    results = []
    for source in component["sources"]:
        site = source["site"]
        url = source["url"]
        parser = PARSERS.get(site)
        if not parser:
            print(f"[!] Pas de parseur defini pour {site}, ignore.")
            continue
        try:
            html = fetch_html(url)
            price = parser(html)
            if price is None:
                print(f"[!] Prix introuvable pour {component['id']} sur {site} "
                      f"({url}) -- le site a peut-etre change de structure.")
                continue
            results.append({"site": site, "url": url, "price": price})
            print(f"[ok] {component['id']} @ {site}: {price} EUR")
        except requests.RequestException as e:
            print(f"[!] Erreur reseau pour {component['id']} sur {site}: {e}")
        time.sleep(REQUEST_DELAY_SECONDS)

    if not results:
        return None

    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "timestamp": now,
        "suppliers": results,
        "min_price": min(r["price"] for r in results),
    }
    return entry


def main():
    data = load_existing_data()
    components_data = data.setdefault("components", {})

    for component in WATCHLIST:
        cid = component["id"]
        bucket = components_data.setdefault(cid, {
            "name": component["name"],
            "cat": component["cat"],
            "target": component["target"],
            "history": [],
        })
        # Permet de mettre a jour ces champs si modifies dans WATCHLIST
        bucket["name"] = component["name"]
        bucket["cat"] = component["cat"]
        bucket["target"] = component["target"]

        entry = scrape_component(component, bucket["history"])
        if entry:
            bucket["history"].append(entry)
            # Garde un historique raisonnable (ex: 500 derniers points)
            bucket["history"] = bucket["history"][-500:]

    data["last_run"] = datetime.now(timezone.utc).isoformat()
    save_data(data)
    print(f"\nDonnees ecrites dans {DATA_FILE}")


if __name__ == "__main__":
    main()
