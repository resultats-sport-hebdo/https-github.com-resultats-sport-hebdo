"""Hockey sur glace : calendrier et résultats de la FFHG (hockeyfrance.com, données JSON du site)."""
import json
from datetime import datetime

from common import PARIS, fdate, get

SPORT = "Hockey sur glace"
AJAX = "https://www.hockeyfrance.com/competitions/wp-admin/admin-ajax.php"
PAGE = "https://www.hockeyfrance.com/competitions/championnats-seniors/d2/saison-reguliere/calendrier-resultats-d2/?journee=&equipe=&poule={phase}"
# (compétition, phase, nom affiché, niveau) — Division 2 : Phénix de Reims et Gaulois de Châlons
PHASES = [(242, 728, "Division 2", "National")]


def collect(D, Z, W, report):
    out = []
    for comp_id, phase, name, level in PHASES:
        report["poules"] += 1
        t = get(f"{AJAX}?action=get_rencontres&page=&equipe_id=&competition_id={comp_id}&phase_id={phase}"
                f"&date_min=&date_max=&par_page=400&journee=&limite=0")
        try:
            rs = json.loads(t)["data"]["data"] if t else None
        except (ValueError, KeyError, TypeError):
            rs = None
        if not rs:
            report["erreurs"].append(f"hockey illisible : phase {phase}"); continue
        P = {"sport": SPORT, "key": name, "results": [], "agenda": [], "cl": None}
        for r in rs:
            rec, vis = r.get("receveur") or {}, r.get("visiteur") or {}
            home, away = rec.get("libelle_complet") or rec.get("libelle_court"), vis.get("libelle_complet") or vis.get("libelle_court")
            hz, az = Z.zone(home), Z.zone(away)
            if hz == "grandest": hz = None
            if az == "grandest": az = None
            if not (hz or az): continue
            home, away = Z.canon(home) or home, Z.canon(away) or away
            try:
                dt = datetime.strptime(r["date_rencontre"][:16], "%Y-%m-%d %H:%M").replace(tzinfo=PARIS)
            except (KeyError, ValueError, TypeError):
                continue
            comp = name + (f" · J{r['tour']}" if r.get("tour") else "")
            base = {"sport": SPORT, "level": level, "genre": "M", "comp": comp, "home": home, "hz": hz, "away": away, "az": az,
                    "url": PAGE.format(phase=phase), "src": "ffhg"}
            sc = {x.get("equipe_id"): x.get("score") for x in (r.get("score") or [])}
            if r.get("etat") == "T" and rec.get("id") in sc and vis.get("id") in sc:
                if W.is_result(dt):
                    note = {"P": "Victoire en prolongation.", "T": "Victoire aux tirs au but."}.get(r.get("victoire_par"), "")
                    P["results"].append({**base, "date": fdate(dt), "sh": int(sc[rec["id"]]), "sa": int(sc[vis["id"]]), "note": note})
            elif not r.get("etat") and W.is_upcoming(dt):
                P["agenda"].append({**base, "day": fdate(dt), "time": dt.strftime("%H:%M"),
                                    "place": (r.get("lieu_de_pratique") or {}).get("nom", "")})
        print("POULE", SPORT, name, "|", len(P["results"]), "résultats", len(P["agenda"]), "à venir")
        out.append(P)
    return out
