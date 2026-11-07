import os
import json
import requests
from datetime import datetime

# Structure des données
data_output = {
    "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "matches": []
}

def fetch_data():
    print("Récupération des données en cours...")
    # Exemple de données récupérées pour la Marne / Grand Est
    data_output["matches"] = [
        {
            "id": "m1",
            "sport": "Handball",
            "league": "Nationale 1 M",
            "homeTeam": "Beaune Handball",
            "awayTeam": "AS St Brice",
            "homeScore": 26,
            "awayScore": 25,
            "status": "Terminé",
            "date": "Samedi 24 Oct."
        },
        {
            "id": "m2",
            "sport": "Football",
            "league": "Coupe de France Féminine",
            "homeTeam": "AS Taissy",
            "awayTeam": "ESTAC Troyes",
            "homeScore": 4,
            "awayScore": 6,
            "status": "Terminé",
            "date": "Dimanche 1 Nov."
        }
    ]

def main():
    fetch_data()
    os.makedirs("data", exist_ok=True)
    with open("data/results.json", "w", encoding="utf-8") as f:
        json.dump(data_output, f, ensure_ascii=False, indent=2)
    print("Fichier data/results.json mis à jour avec succès !")

if __name__ == "__main__":
    main()
