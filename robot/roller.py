"""Roller hockey : calendriers et résultats des clubs sur Score'n'co (scorenco.com, données GraphQL publiques).

Score'n'co relaie les données de la fédération (FFRS) club par club.
"""
import re
from datetime import datetime

from common import PARIS, fdate, session

SPORT = "Roller hockey"
API = "https://graphql.scorenco.com/v1/graphql"
SITE = "https://scorenco.com"
# identifiant Score'n'co du club (fin de l'adresse de la page du club, en base 36) → nom de l'équipe première
CLUBS = {int("38v1", 36): "Bombardiers d'Épernay", int("38sg", 36): "Diables de Rethel",
         int("38sz", 36): "Rapaces de Reims", int("3b93", 36): "Troyes Roller"}
RESERVE = {"Rapaces de Reims": "Rapaces de Reims B"}
Q = """query Ev($clubId: Int!, $f: Int!, $limit: Int = 15) {
  competitions_event_detail_by_club_id(args: {date_filter: $f, id: $clubId}, limit: $limit, order_by: [{date: %s}]) {
    id status date time url round { name competition { name } } teams level_name
  }
}"""
HDR = {"Content-Type": "application/json", "x-hasura-role": "anonymous", "x-hasura-locale": "fr-FR",
       "Referer": "https://scorenco.com/", "Accept": "application/json"}


def events(club, f):
    try:
        r = session.post(API, json={"query": Q % ("desc" if f < 0 else "asc"), "variables": {"clubId": club, "f": f}},
                         headers=HDR, timeout=40)
        return r.json()["data"]["competitions_event_detail_by_club_id"] if r.status_code == 200 else None
    except Exception:
        return None


def comp_name(level, cname):
    c = cname or ""
    if re.search(r"elite", level or c, re.I): return "Ligue Élite"
    m = re.search(r"Nationale\s*(\d)", f"{level} {c}", re.I)
    if m:
        g = re.search(r"Groupe\s*(\w+)", c, re.I)
        return f"Nationale {m.group(1)}" + (" M" if m.group(1) != "4" else "") + (f" · Groupe {g.group(1)}" if g else "")
    return (level or c).strip()


def clean(n):
    n = re.sub(r"^\d{4,5}\s*-\s*", "", n or "").strip()
    return n.title() if n.isupper() else n


def collect(D, Z, W, report):
    by_key, seen, failed = {}, set(), 0
    for club, base in CLUBS.items():
        evs = (events(club, -1) or []) + (events(club, 1) or [])
        if not evs: failed += 1; continue
        for e in evs:
            if e["id"] in seen: continue
            seen.add(e["id"])
            teams = e.get("teams") or []
            home = next((t for t in teams if t.get("role") == "home"), None)
            away = next((t for t in teams if t.get("role") == "away"), None)
            if not home or not away: continue
            def name(t):
                cid = t.get("club_id")
                if cid in CLUBS:
                    b = CLUBS[cid]
                    return b if t.get("name_in_club", "").endswith("1") else RESERVE.get(b, b + " 2")
                return clean(t.get("name_in_competition"))
            def zone(t):
                return Z.zone(CLUBS[t["club_id"]]) if t.get("club_id") in CLUBS else None
            hn, an = name(home), name(away)
            try:
                dt = datetime.fromisoformat(e["time"]).astimezone(PARIS) if e.get("time") else datetime.fromisoformat(e["date"]).replace(tzinfo=PARIS)
            except ValueError:
                continue
            comp = comp_name(e.get("level_name"), ((e.get("round") or {}).get("competition") or {}).get("name"))
            j = re.search(r"(\d+)", (e.get("round") or {}).get("name") or "")
            P = by_key.setdefault(comp, {"sport": SPORT, "key": comp, "results": [], "agenda": [], "cl": None})
            base_e = {"sport": SPORT, "level": "National", "genre": "M", "comp": comp + (f" · J{j.group(1)}" if j else ""),
                      "home": hn, "hz": zone(home), "away": an, "az": zone(away), "url": SITE + (e.get("url") or ""), "src": "scorenco"}
            if e.get("status") == "finish" and home.get("score") is not None and away.get("score") is not None:
                if W.is_result(dt):
                    P["results"].append({**base_e, "date": fdate(dt), "sh": int(home["score"]), "sa": int(away["score"]), "note": ""})
            elif e.get("status") != "finish" and W.is_upcoming(dt):
                P["agenda"].append({**base_e, "day": fdate(dt), "time": dt.strftime("%H:%M") if e.get("time") else "", "place": ""})
    if failed: report["erreurs"].append(f"roller : {failed} club(s) illisible(s) sur Score'n'co")
    for P in by_key.values():
        P["mode"] = "upsert"  # source par club : on ajoute match par match sans effacer la poule
        for x in P["results"] + P["agenda"]: x["mid"] = "snc" + x["url"].rsplit("=", 1)[-1]
        print("POULE", SPORT, P["key"], "|", len(P["results"]), "résultats", len(P["agenda"]), "à venir")
    return list(by_key.values())
