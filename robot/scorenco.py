"""Basket et rugby, club par club, sur Score'n'co (scorenco.com, données publiques des fédérations).

Complète les sources fédérales quand elles bloquent le robot (FFBB) ou ne donnent que les scores du jour (FFR) :
la liste des clubs de nos 5 départements vient de Score'n'co lui-même, puis on lit les matchs de chaque club.
Seules les équipes seniors sont gardées, aux niveaux couverts (national et régional ; pré-régionale de basket
seulement pour l'Aisne).
"""
import re, time
from datetime import datetime

from common import PARIS, fdate, key_of, session

API = "https://graphql.scorenco.com/v1/graphql"
SITE = "https://scorenco.com"
HDR = {"Content-Type": "application/json", "x-hasura-role": "anonymous", "x-hasura-locale": "fr-FR",
       "Referer": "https://scorenco.com/", "Accept": "application/json"}
SPORTS = {"basket": "Basket", "rugby": "Rugby"}
SPORT = "Basket"  # pour le catalogue utilisé par le robot ; chaque entrée porte son propre sport
DEPS = ["51", "08", "10", "52", "02"]
CLUBS_Q = """query C($deps: [String!], $sports: [String!]) {
  clubs_club(where: {department: {code: {_in: $deps}}, sport: {slug: {_in: $sports}}}, limit: 3000) {
    id name department { code } sport { slug } } }"""
EV_Q = """query Ev($clubId: Int!, $f: Int!, $limit: Int = 25) {
  competitions_event_detail_by_club_id(args: {date_filter: $f, id: $clubId}, limit: $limit, order_by: [{date: %s}]) {
    id status date time url round { name competition { name } } teams level_name } }"""


def gql(query, variables):
    for i in range(3):
        try:
            r = session.post(API, json={"query": query, "variables": variables}, headers=HDR, timeout=40)
            if r.status_code == 200:
                d = r.json()
                if "data" in d: return d["data"]
        except Exception:
            pass
        time.sleep(5 * (i + 1))
    return None


def covered(level, comp, dep, sport):
    t = f"{level} {comp}"
    if re.search(r"\bU\s?\d{2}\b|moins de|jeunes|loisir|r[ée]serve|d[ée]partementale|inter-?d[ée]p", t, re.I): return None
    if sport == "Basket" and re.search(r"pr[ée][\s-]?r[ée]gionale", t, re.I):
        return "Régional" if dep == "02" else None
    if re.search(r"nationale|national|[ée]lite|lf2|pro\s?[ab]|f[ée]d[ée]rale|excellence b", t, re.I) and not re.search(r"pr[ée][\s-]?nationale", t, re.I):
        return "National"
    if re.search(r"r[ée]gional|pr[ée][\s-]?nationale|honneur|promotion|excellence|r[1-3]\b|territorial", t, re.I):
        return "Régional"
    return None


def comp_name(comp):
    c = re.sub(r"\s+", " ", comp or "").strip()
    c = re.sub(r"\s*-\s*(Poule|Groupe)\s+", r" · \1 ", c, flags=re.I)
    c = re.sub(r"\s+-\s+", " · ", c)
    c = " · ".join(x for x in c.split(" · ") if not re.fullmatch(r"(Championnat (Territorial|de France)|Qualification|Brassage|Phase \d|Seniors)", x.strip(), re.I))
    c = re.sub(r"\s+Seniors\b", "", c)
    return re.sub(r"\b(Masculine|Féminine|Masculin|Féminin|Feminine)\b", lambda m: m.group(1).lower().replace("feminine", "féminine"), c)


def clean(n):
    n = re.sub(r"^(IE|CTC)\s*-\s*", "", (n or "").strip(" -"))
    return n.title() if n.isupper() else n


def collect(D, Z_unused, W, report):
    from common import Zoner
    data = gql(CLUBS_Q, {"deps": DEPS, "sports": list(SPORTS)})
    if not data:
        report["erreurs"].append("Score'n'co : liste des clubs illisible"); return []
    clubs = {c["id"]: c for c in data["clubs_club"]}
    zoners = {sp: Zoner(D, sp) for sp in SPORTS.values()}
    out, seen, failed = {}, set(), 0
    for cid, c in clubs.items():
        sport = SPORTS[c["sport"]["slug"]]; Z = zoners[sport]; dep = c["department"]["code"]
        evs = []
        for f, order in ((-1, "desc"), (1, "asc")):
            d = gql(EV_Q % order, {"clubId": cid, "f": f})
            if d is None: failed += 1; continue
            evs += d["competitions_event_detail_by_club_id"]
        for e in evs:
            if e["id"] in seen: continue
            teams = e.get("teams") or []
            home = next((t for t in teams if t.get("role") == "home"), None)
            away = next((t for t in teams if t.get("role") == "away"), None)
            if not home or not away: continue
            ours = [t for t in (home, away) if t.get("club_id") in clubs]
            if not ours or not all(re.match(r"SENIOR", t.get("name_in_club") or "", re.I) for t in ours): continue
            comp_raw = ((e.get("round") or {}).get("competition") or {}).get("name") or e.get("level_name") or ""
            level = covered(e.get("level_name") or "", comp_raw, dep, sport)
            if not level: continue
            seen.add(e["id"])
            def name(t):
                tc = t.get("club_id")
                if tc in clubs:
                    base = Z.canon(clubs[tc]["name"]) or clean(clubs[tc]["name"])
                    m = re.search(r"(\d+)$", t.get("name_in_club") or "")
                    fem = re.search(r"\bF\d*$", t.get("name_in_club") or "")
                    s = base + (" (féminines)" if fem and "fémin" not in base.lower() else "")
                    return s + (f" {m.group(1)}" if m and m.group(1) != "1" else "")
                return clean(t.get("name_in_competition"))
            def zone(t):
                tc = t.get("club_id")
                return Z.zone_in_dep(clubs[tc]["name"], clubs[tc]["department"]["code"]) if tc in clubs else None
            try:
                dt = datetime.fromisoformat(e["time"]).astimezone(PARIS) if e.get("time") else datetime.fromisoformat(e["date"]).replace(tzinfo=PARIS)
            except ValueError:
                continue
            genre = "F" if re.search(r"f[ée]minin", comp_raw, re.I) or any(re.search(r"\bF\d*$", t.get("name_in_club") or "") for t in ours) else "M"
            comp = comp_name(comp_raw)
            j = re.search(r"(\d+)", (e.get("round") or {}).get("name") or "")
            key = key_of(comp)
            P = out.setdefault((sport, key), {"sport": sport, "key": key, "results": [], "agenda": [], "cl": None, "mode": "upsert"})
            base = {"sport": sport, "level": level, "genre": genre, "comp": comp + (f" · J{j.group(1)}" if j else ""),
                    "home": name(home), "hz": zone(home), "away": name(away), "az": zone(away),
                    "url": SITE + (e.get("url") or ""), "src": "scorenco", "mid": f"snc{e['id']}"}
            if e.get("status") == "finish" and home.get("score") is not None and away.get("score") is not None:
                if W.is_result(dt):
                    P["results"].append({**base, "date": fdate(dt), "sh": int(home["score"]), "sa": int(away["score"]), "note": ""})
            elif e.get("status") != "finish" and W.is_upcoming(dt):
                P["agenda"].append({**base, "day": fdate(dt), "time": dt.strftime("%H:%M") if e.get("time") else "", "place": ""})
    if failed: report["erreurs"].append(f"Score'n'co : {failed} lecture(s) de club refusée(s)")
    res = [P for P in out.values() if P["results"] or P["agenda"]]
    report["scorenco"] = f"{len(clubs)} clubs lus, {len(res)} compétitions"
    for P in res:
        print("POULE", P["sport"], P["key"], "(Score'n'co) |", len(P["results"]), "résultats", len(P["agenda"]), "à venir")
    return res
