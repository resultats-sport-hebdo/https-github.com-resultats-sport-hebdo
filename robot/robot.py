"""Robot Résultats Sport Hebdo.

Met à jour data.js (et data.json) à partir des sources lisibles automatiquement, pour toutes les poules
où joue au moins une équipe de nos 5 départements :
  - Football : LiguesDeFoot.fr (foot.py)
  - Volley   : FFVolley, ffvbbeach.org (volley.py)
  - Basket   : FFBB (basket.py), si le site laisse passer le robot
  - Rugby    : FFR (rugby.py), si le site laisse passer le robot
Pour chaque poule lue : résultats de la semaine, matchs à venir, classement.

Les données saisies à la main (autres sports, autres poules) ne sont jamais effacées, sauf pour une poule
que le robot sait lire entièrement : ses résultats, son programme et son classement sont alors remplacés.

Quand il tourne du vendredi au lundi, il prépare l'édition du lundi suivant (même id que la tâche du lundi
matin) et y reporte les matchs encore à venir de l'édition précédente, pour que « Le week-end prochain »
reste complet.

Usage : python robot/robot.py [--dry-run] [--today AAAA-MM-JJ] [--only foot,volley,...]
"""
import argparse, json, re, sys, traceback
from datetime import datetime, timedelta

from common import MOIS, PARIS, Window, key_of, load_data, save_data, tokens, Zoner
import footnational, foot, volley, hockey, scr

READERS = {"footnational": footnational, "foot": foot, "volley": volley, "hockey": hockey}
for _name in ("basket", "rugby"):
    try:
        READERS[_name] = __import__(_name)
    except ImportError:
        pass
OWN_SRC = {"fn", "ldf", "ffvb", "ffbb", "ffr", "ffhg", "ffn"}
MOIS_N = {m: i + 1 for i, m in enumerate(MOIS)}


def parse_day(s, ref):
    """« Sam. 7 nov. » → date (année déduite de la date de référence)."""
    m = re.search(r"(\d+)(?:er)?\s+([a-zéû]+\.?)", s or "")
    if not m or m.group(2) not in MOIS_N: return None
    mo = MOIS_N[m.group(2)]; y = ref.year
    if mo < ref.month - 6: y += 1
    elif mo > ref.month + 6: y -= 1
    try:
        return datetime(y, mo, int(m.group(1))).date()
    except ValueError:
        return None


def window_and_edition(D, today):
    wd = today.weekday()
    if wd in (4, 5, 6, 0):
        mon = (today + timedelta(days=(7 - wd) % 7)).date()
        start = datetime.combine(mon - timedelta(days=7), datetime.min.time(), PARIS)
        end = datetime.combine(mon + timedelta(days=6), datetime.min.time(), PARIS)
        now = today if wd != 0 else datetime.combine(mon - timedelta(days=1), datetime.min.time(), PARIS)
        eid = mon.isoformat()
        E = next((e for e in D["editions"] if e.get("id") == eid), None)
        if E is None:
            a, b = mon - timedelta(days=7), mon - timedelta(days=1)
            E = {"id": eid, "label": f"Semaine du {a.day} {MOIS[a.month-1]} au {b.day} {MOIS[b.month-1]}",
                 "edito": "", "results": [], "agenda": []}
            prev = D["editions"][0] if D["editions"] else None
            D["editions"].insert(0, E)
            del D["editions"][8:]
            # report des matchs encore à venir saisis à la main dans l'édition précédente
            if prev:
                for a_ in prev.get("agenda", []):
                    d = parse_day(a_.get("day"), today)
                    if a_.get("src") not in OWN_SRC and d and d >= today.date():
                        E["agenda"].append({**a_, "report": prev.get("id")})
        E["enCours"] = wd != 0  # du vendredi au dimanche, la semaine n'est pas finie ; le lundi, l'édition est complète
        return Window(start, now, end, eid), E
    W = Window(today - timedelta(days=7), today, today + timedelta(days=7), D["editions"][0].get("id"))
    return W, D["editions"][0]


def run(today, dry, only=None):
    D = load_data()
    W, E = window_and_edition(D, today)
    # les matchs reportés devenus passés n'ont plus rien à faire dans le programme
    E["agenda"] = [a for a in E["agenda"] if not (a.get("report") and (parse_day(a.get("day"), today) or today.date()) < today.date())]
    report = {"poules": 0, "gardées": 0, "erreurs": [], "par sport": {}}
    owned, new_res, new_ag, new_cl, upsert_sports = set(), [], [], [], set()
    for name, mod in READERS.items():
        if only and name not in only and not (name == "footnational" and "foot" in only): continue
        Z = Zoner(D, mod.SPORT)
        W.skip = set(owned)  # poules déjà lues par une source prioritaire (Foot-National avant LiguesDeFoot)
        try:
            got = mod.collect(D, Z, W, report)
        except Exception as e:  # un site en panne ne doit pas empêcher les autres sports
            traceback.print_exc()
            report["erreurs"].append(f"{name} : {type(e).__name__} {e}")
            continue
        s = report["par sport"].setdefault(mod.SPORT, {"poules": 0, "résultats": 0, "à venir": 0, "classements": 0})
        for P in got:
            if P.get("mode") == "upsert":  # ajout match par match (source partielle) : rien d'autre n'est effacé
                upsert_sports.add(P["sport"])
                mids = {x["mid"] for x in P["results"] + P["agenda"]}
                E["results"] = [r for r in E["results"] if r.get("mid") not in mids]
                E["agenda"] = [a for a in E["agenda"] if a.get("mid") not in mids]
            else:
                owned.add((P["sport"], P["key"]))
            new_res += P["results"]; new_ag += P["agenda"]
            if P["cl"]: new_cl.append(P["cl"])
            s["poules"] += 1; s["résultats"] += len(P["results"]); s["à venir"] += len(P["agenda"]); s["classements"] += bool(P["cl"])
        report["gardées"] += len(got)

    # fusion : on remplace tout ce qui concerne les poules lues par le robot
    def keep(r):
        return (r.get("sport"), key_of(r.get("comp", ""))) not in owned
    read_sports = {sp for sp, _ in owned} | upsert_sports
    def tk(t): return frozenset(tokens(t))
    def same(a, b, day):
        return (a.get("sport") == b.get("sport") and a.get(day) == b.get(day)
                and (tk(a.get("home")) & tk(b.get("home"))) and (tk(a.get("away")) & tk(b.get("away"))))
    def dup(r, news, day):
        # même match déjà fourni par le robot sous un autre nom de compétition (saisie manuelle)
        return r.get("src") not in OWN_SRC and r.get("sport") in read_sports and any(same(r, n, day) for n in news)
    # un score saisi à la main est gardé tant que la source du robot ne l'a pas encore (ex. Ligue 2 du vendredi)
    def manual_kept(r):
        return r.get("src") not in OWN_SRC and r.get("sh") is not None
    E["results"] = [r for r in E["results"] if (keep(r) or manual_kept(r)) and not dup(r, new_res, "date")] + new_res
    E["agenda"] = [a for a in E["agenda"] if keep(a) and not dup(a, new_ag, "day")] + new_ag
    # classements saisis à la main sous une autre clé et désormais lus par le robot
    robot_teams = {}
    for c in new_cl:
        robot_teams.setdefault(c["sport"], []).append({tk(x["team"]) for x in c["rows"]})
    def superseded(c):
        if c.get("src") in OWN_SRC or c.get("sport") not in robot_teams or not c.get("rows"): return False
        mine = [tk(x.get("team")) for x in c["rows"]]
        return any(sum(1 for t in mine if t in ts) * 2 >= len(mine) for ts in robot_teams[c["sport"]])
    cl_keys = {(c["sport"], c["key"]) for c in new_cl}  # un classement n'est remplacé que si le robot en fournit un
    old_cl = [c for c in D["classements"] if (c.get("sport"), c.get("key")) not in cl_keys]
    report["classements remplacés"] = [c["key"] for c in old_cl if superseded(c)]
    D["classements"] = [c for c in old_cl if not superseded(c)] + new_cl

    scr.enrich(new_res, W, report)  # liens vers sportclub-reims.fr quand l'article existe
    report["édition"] = E.get("id")
    report["fenêtre"] = f"{W.start.date()} → {W.now.date()} / programme jusqu'au {W.end.date()}"
    report["reportés"] = sum(1 for a in E["agenda"] if a.get("report"))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    for r in new_res[:40]: print("R", r["sport"], r["date"], r["comp"], "|", r["home"], r["sh"], "-", r["sa"], r["away"], "|", r["hz"], r["az"], "|", r.get("note", ""))
    for a in new_ag[:40]: print("A", a["sport"], a["day"], a["time"], a["comp"], "|", a["home"], "-", a["away"], "|", a["hz"], a["az"], "|", a.get("place", ""))
    if not dry:
        save_data(D)
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--today")
    ap.add_argument("--only", help="liste de lecteurs : foot,volley,basket,rugby")
    a = ap.parse_args()
    if a.today:
        t = datetime.fromisoformat(a.today)
        today = (t if t.tzinfo else t.replace(tzinfo=PARIS))
        if len(a.today) <= 10: today = today.replace(hour=23, minute=30)
    else:
        today = datetime.now(PARIS)
    run(today, a.dry_run, set(a.only.split(",")) if a.only else None)
    sys.exit(0)
