"""Rugby : application Mon Club House de la FFR (api-web.monclubhouse.ffr.fr).

Le site ne laisse lire au robot que les matchs du jour même : le robot relève donc les scores le soir
(vendredi, samedi, dimanche) et les ajoute à l'édition, match par match, sans effacer ceux des jours
précédents. Le programme et les classements restent fournis par la tâche du lundi.
"""
import json, re
from datetime import datetime, timedelta

from common import PARIS, fdate, key_of, session

SPORT = "Rugby"
API = "https://api-web.monclubhouse.ffr.fr/monclub/allmatches/"
HDR = {"Referer": "https://monclubhouse.ffr.fr/", "Origin": "https://monclubhouse.ffr.fr", "Accept": "application/json, text/plain, */*"}
ORGAS = {"FFR": "National", "GRAND EST": "Régional", "HAUTS DE FRANCE": "Régional"}


def clean(n):
    return re.sub(r"\s*\([0-9A-Z]+\)\s*$", "", n or "").strip()


def day_matches(d):
    try:
        r = session.get(API + d.isoformat(), headers=HDR, timeout=60)
        if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
            return r.json().get("data", {}).get("Rencontres", [])
    except Exception:
        pass
    return None


def collect(D, Z, W, report):
    out, read, refused = {}, 0, 0
    d = W.start.date()
    last = min(W.now.date(), datetime.now(PARIS).date())
    while d <= last:
        rs = day_matches(d)
        d += timedelta(days=1)
        if rs is None:
            refused += 1; continue
        read += 1
        for r in rs:
            c = r.get("competitionId") or {}
            orga = ((c.get("structureOrganisatriceId") or {}).get("nom") or "").upper()
            cat = ((c.get("competitionCategorieId") or {}).get("nom") or "")
            if orga not in ORGAS or "Senior" not in cat or re.search(r"R[ée]serve", c.get("nom") or ""): continue
            loc, vis = r.get("competitionEquipeLocaleId") or {}, r.get("competitionEquipeVisiteuseId") or {}
            home = loc.get("nomEdito") or clean(loc.get("nom")); away = vis.get("nomEdito") or clean(vis.get("nom"))
            hz, az = Z.zone(home) or Z.zone(clean(loc.get("nom"))), Z.zone(away) or Z.zone(clean(vis.get("nom")))
            if hz == "grandest": hz = None
            if az == "grandest": az = None
            if not (hz or az): continue
            level = ORGAS[orga]
            phase = r.get("competitionPhaseId") or {}
            name = re.sub(r"\s*-\s*Championnat Territorial", "", c.get("nom") or "Rugby", flags=re.I).strip()
            if level == "Régional": name += " Grand Est" if orga == "GRAND EST" else " Hauts-de-France"
            if phase.get("multipoule") and (r.get("pouleId") or {}).get("ordre"): name += f" · Poule {r['pouleId']['ordre']}"
            if "Féminin" in cat or "Feminin" in cat: genre = "F"
            else: genre = "M"
            j = re.search(r"(\d+)", ((r.get("competitionJourId") or {}).get("nom") or ""))
            comp = name + (f" · J{j.group(1)}" if j else "")
            try:
                dt = datetime.fromisoformat(r["dateEffective"].replace("Z", "+00:00")).astimezone(PARIS)
            except (KeyError, ValueError):
                continue
            url = "https://monclubhouse.ffr.fr" + (r.get("url_monclubhouse") or "")
            base = {"sport": SPORT, "level": level, "genre": genre, "comp": comp, "home": home, "hz": hz,
                    "away": away, "az": az, "url": url, "src": "ffr", "mid": f"ffr{r.get('id')}"}
            P = out.setdefault(key_of(name), {"sport": SPORT, "key": key_of(name), "results": [], "agenda": [], "cl": None, "mode": "upsert"})
            rl, rv = r.get("rencontreResultatLocaleId") or {}, r.get("rencontreResultatVisiteuseId") or {}
            if r.get("etatMixte") == "terminé" and rl.get("pointsDeMarque") is not None and rv.get("pointsDeMarque") is not None:
                if W.is_result(dt):
                    P["results"].append({**base, "date": fdate(dt), "sh": int(rl["pointsDeMarque"]), "sa": int(rv["pointsDeMarque"]), "note": ""})
            elif r.get("etatMixte") == "à venir" and W.is_upcoming(dt):
                P["agenda"].append({**base, "day": fdate(dt), "time": dt.strftime("%H:%M"), "place": ""})
    report["poules"] += len(out)
    report.setdefault("rugby", {})["jours lus"] = read
    report["rugby"]["jours refusés"] = refused
    for P in out.values():
        print("POULE", SPORT, P["key"], "|", len(P["results"]), "résultats", len(P["agenda"]), "à venir")
    return list(out.values())
