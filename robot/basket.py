"""Basket : site des compétitions de la FFBB (competitions.ffbb.com), lu avec un vrai navigateur.

La page de chaque championnat national contient toutes ses poules, leurs classements et tous leurs matchs.
Le code fédéral de chaque club (ex. GES0051…) donne sa ligue et son comité, donc son département.
"""
import json, re
from datetime import datetime

from common import MOIS, PARIS, Browser, fdate, key_of

SPORT = "Basket"
BASE = "https://competitions.ffbb.com/competitions/"
# (slug, nom affiché, genre)
COMPETITIONS = [
    ("betclic-e", "Betclic Élite", "M"), ("prob", "Élite 2", "M"),
    ("nm1", "Nationale masculine 1", "M"), ("nm2", "Nationale masculine 2", "M"), ("nm3", "Nationale masculine 3", "M"),
    ("lf2", "LF2", "F"), ("nf1", "Nationale féminine 1", "F"), ("nf2", "Nationale féminine 2", "F"), ("nf3", "Nationale féminine 3", "F"),
]
OUR_LIGUES = ("GES", "HDF")
OUR_DEPS = ("51", "08", "10", "52", "02")


def rsc(html):
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
    return "".join(json.loads('"' + c + '"') for c in chunks)


def phases(s):
    dec = json.JSONDecoder()
    for m in re.finditer(r'"phases":\[\{"id"', s):
        try:
            arr, _ = dec.raw_decode(s, m.start() + len('"phases":'))
        except ValueError:
            continue
        if arr and isinstance(arr[0], dict) and "poules" in arr[0] and arr[0]["poules"] and isinstance(arr[0]["poules"][0], dict):
            return arr
    return []


def dep_of_url(u):
    m = re.search(r"/ligues/([a-z]{3})/comites/(\d{4})/", u or "")
    if m and m.group(1).upper() in OUR_LIGUES and m.group(2)[2:] in OUR_DEPS: return m.group(2)[2:]
    return None


def team_name(nom, num):
    num = (num or "").strip(); nom = (nom or "").replace(" - ", " ")
    return f"{nom} {num}" if num and num not in ("1",) else nom


def strip_num(n):
    return re.sub(r"\s+-\s+1$", "", n or "").replace(" - ", " ")


def collect(D, Z, W, report):
    out = []
    with Browser() as B:
        for slug, label, genre in COMPETITIONS:
            report["poules"] += 1
            url = BASE + slug
            html = B.get(url)
            if not html:
                report["erreurs"].append(f"bloqué ou illisible : {url}"); continue
            ph = phases(rsc(html))
            if not ph:
                report["erreurs"].append(f"données absentes : {url}"); continue
            for pi, phase in enumerate(ph):
                multi = len(phase["poules"]) > 1
                for poule in phase["poules"]:
                    name = label + (" · Phase 2" if pi else "") + (f" · {poule['nom']}" if multi else "")
                    zones = {}
                    for c in poule.get("classements", []):
                        e = c.get("idEngagement") or {}
                        t = team_name(e.get("nom"), e.get("numeroEquipe"))
                        d = dep_of_url(e.get("url_competition"))
                        zones[t] = Z.zone_in_dep(t, d) if d else None
                    for r in poule.get("rencontres", []):
                        for k in ("1", "2"):
                            e = r.get("idEngagementEquipe" + k) or {}
                            t = strip_num(r.get("nomEquipe" + k))
                            d = dep_of_url(e.get("url_competition"))
                            if t not in zones or (d and not zones[t]): zones[t] = Z.zone_in_dep(t, d) if d else zones.get(t)
                    if not any(zones.values()): continue
                    print("POULE", SPORT, name, "|", ", ".join(sorted(f"{t} [{z}]" for t, z in zones.items() if z)))
                    P = {"sport": SPORT, "key": key_of(name), "results": [], "agenda": [], "cl": None}
                    for r in poule.get("rencontres", []):
                        home, away = strip_num(r.get("nomEquipe1")), strip_num(r.get("nomEquipe2"))
                        hz, az = zones.get(home), zones.get(away)
                        if not (hz or az): continue
                        try:
                            dt = datetime.fromisoformat(r["date_rencontre"][:19]).replace(tzinfo=PARIS)
                        except (KeyError, ValueError, TypeError):
                            continue
                        comp = name + (f" · J{r['numeroJournee']}" if r.get("numeroJournee") else "")
                        base = {"sport": SPORT, "level": "National", "genre": genre, "comp": comp, "home": home, "hz": hz,
                                "away": away, "az": az, "url": "https://competitions.ffbb.com" + (r.get("url_competition") or "/competitions/" + slug),
                                "src": "ffbb"}
                        sh, sa = r.get("resultatEquipe1"), r.get("resultatEquipe2")
                        if r.get("joue") and str(sh).isdigit() and str(sa).isdigit():
                            if W.is_result(dt):
                                P["results"].append({**base, "date": fdate(dt), "sh": int(sh), "sa": int(sa), "note": ""})
                        elif W.is_upcoming(dt):
                            salle = (r.get("salle") or {})
                            ville = ((salle.get("cartographie") or {}).get("ville") or "")
                            place = " · ".join(x for x in [(salle.get("libelle") or "").title(), ville] if x)
                            P["agenda"].append({**base, "day": fdate(dt), "time": dt.strftime("%H:%M"), "place": place})
                    rows = []
                    for c in sorted(poule.get("classements", []), key=lambda c: int(c.get("position") or 99)):
                        e = c.get("idEngagement") or {}
                        try:
                            bp, bc = int(c.get("paniersMarques") or 0), int(c.get("paniersEncaisses") or 0)
                            rows.append({"r": int(c["position"]), "team": team_name(e.get("nom"), e.get("numeroEquipe")),
                                         "pts": int(c.get("points") or 0), "j": int(c.get("matchJoues") or 0),
                                         "g": int(c.get("gagnes") or 0), "p": int(c.get("perdus") or 0),
                                         "bp": bp, "bc": bc, "diff": f"{bp - bc:+d}"})
                        except (KeyError, ValueError):
                            continue
                    if rows:
                        P["cl"] = {"sport": SPORT, "level": "National", **({"genre": "F"} if genre == "F" else {}), "key": P["key"],
                                   "maj": f"{W.now.day} {MOIS[W.now.month-1]} {W.now.year} · FFBB", "url": url + "/classement", "rows": rows, "src": "ffbb"}
                    out.append(P)
        if B.blocked: report["erreurs"].append(f"FFBB : {B.blocked} refus du pare-feu (nouvel essai fait)")
    return out
