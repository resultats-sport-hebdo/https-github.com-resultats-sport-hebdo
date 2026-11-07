"""Robot Résultats Sport Hebdo.

Met à jour data.js (et data.json) à partir des sources lisibles automatiquement :
  - Football : LiguesDeFoot.fr (format texte .md) — classements, résultats des 7 derniers jours,
    matchs des 7 prochains jours, pour toutes les poules où joue au moins un club de nos 5 départements.

Les données saisies à la main (autres sports, captures) ne sont jamais effacées, sauf pour une poule
que le robot sait lire entièrement : ses résultats, son programme et son classement sont alors remplacés.

Usage : python robot/robot.py [--dry-run] [--today AAAA-MM-JJ]
"""
import argparse, json, re, sys, time, unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "ResultatsSportHebdo-robot/1.0 (+https://github.com/resultats-sport-hebdo)",
      "Accept-Language": "fr-FR,fr;q=0.9"}
LDF = "https://www.liguesdefoot.fr"
SEASON = "2026-2027"
PARIS = timezone(timedelta(hours=1))  # heure d'hiver ; l'heure exacte vient des dates des sources
JOURS = ["Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam.", "Dim."]
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

# Districts de nos 5 départements : (région LiguesDeFoot, slug district, nom affiché, zone par défaut)
DISTRICTS = [
    ("grand-est", "marne", "District 1 Marne", "reims"),
    ("grand-est", "ardennes", "D1 Ardennes", "charleville"),
    ("grand-est", "aube", "Départemental 1 Aube", "troyes"),
    ("grand-est", "haute-marne", "Départemental 1 Haute-Marne", "chaumont"),
    ("hauts-de-france", "aisne", "Départemental 1 Aisne", "laon"),
]
# Pour ces compétitions, on ne garde que les matchs de nos clubs (les autres poules sont gardées entières).
ONLY_OURS = ("national", )
# Homonymes hors de nos départements, à ne jamais rattacher à une zone.
EXCLUDE = {"goal fc", "cs chaumontois"}

# ------------------------------------------------------------------ outils
def norm(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

STOP = set("fc us as es sc cs ca ac rc js om os ol o sp sf sl ent entente club football foot de du la le les l d st saint ste sainte "
           "sur sous en aux des les au lez pres the and et union sportive association olympique stade sporting usa asc fcf ec aj cso usag oam am prix".split())

def tokens(s):
    return [t for t in norm(s).split() if t not in STOP and not t.isdigit() and len(t) > 1]

def fdate(dt):
    d = dt.day
    return f"{JOURS[dt.weekday()]} {'1er' if d == 1 else d} {MOIS[dt.month - 1]}"

session = requests.Session(); session.headers.update(UA)
def get(url, tries=3):
    for i in range(tries):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(2 + 3 * i)
    return None

# ------------------------------------------------------------------ data.js
def load_data():
    txt = (ROOT / "data.js").read_text(encoding="utf-8")
    start = txt.index("{"); end = txt.rindex("}") + 1
    return json.loads(txt[start:end])

def save_data(D):
    js = "window.RSH_DATA = " + json.dumps(D, ensure_ascii=False, indent=1) + ";\n"
    (ROOT / "data.js").write_text(js, encoding="utf-8")
    (ROOT / "data.json").write_text(json.dumps(D, ensure_ascii=False, indent=1), encoding="utf-8")

def key_of(comp):
    """Même règle que le site : sans la journée ni les noms de sponsors."""
    k = re.sub(r"\s*·\s*J\d+.*$", "", comp)
    k = re.sub(r"\s+(Homiris|IHE [ÉE]nergies|Escates [^·]*|CFA du B[âa]timent 51|3 Brasseurs|Allianz Leseur)\b", "", k, flags=re.I)
    return re.sub(r"\s+", " ", k).strip()

# ------------------------------------------------------------------ zones
class Zoner:
    """Associe un nom d'équipe à une zone de nos 5 départements (ou None)."""
    def __init__(self, D):
        self.map = {}
        self.exact = {}
        def add(name, z):
            if not z: return
            t = " ".join(tokens(name))
            if not t: return
            if z == "grandest": self.exact.setdefault(t, z)
            else: self.map.setdefault(t, z)
        for s in D.get("suivi", []):
            if s.get("sport") == "Football": add(s["club"], s.get("zone"))
        for e in D.get("editions", []):
            for r in e.get("results", []) + e.get("agenda", []):
                if r.get("sport") == "Football":
                    add(r.get("home"), r.get("hz")); add(r.get("away"), r.get("az"))
        self.villes = []
        for z in D.get("zones", []):
            if z["k"] == "grandest": continue
            for v in z.get("villes", []) + [z["l"]]:
                for part in re.split(r"[–-]", v) if "–" in v else [v]:
                    t = tokens(part)
                    if t: self.villes.append((t, z["k"]))
    def zone(self, team):
        if norm(team) in EXCLUDE: return None
        t = tokens(team)
        if not t: return None
        j = " ".join(t)
        if j in self.map: return self.map[j]
        if j in self.exact: return self.exact[j]
        ts = set(t)
        best = None
        for k, z in self.map.items():
            ks = set(k.split())
            if ks and ks <= ts and all(len(x) >= 3 for x in ks):
                if not best or len(k) > len(best[0]): best = (k, z)
        if best: return best[1]
        for vt, z in self.villes:
            if set(vt) <= ts and all(len(x) >= 3 for x in vt): return z
        return None

# ------------------------------------------------------------------ LiguesDeFoot
ROW = re.compile(r"^\|(.+)\|\s*$")
LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")

def md_tables(md):
    """Renvoie {titre de section: [lignes (liste de cellules)]}."""
    out, sec = {}, ""
    rows = out.setdefault("", [])
    for line in md.splitlines():
        if line.startswith("## "):
            sec = line[3:].strip(); rows = out.setdefault(sec, [])
            continue
        m = ROW.match(line)
        if m and rows is not None:
            cells = [c.strip() for c in m.group(1).split("|")]
            if cells and set(cells[0]) <= set("- "): continue
            rows.append(cells)
    return out

SLUGS = {}
def cell_text(c):
    m = LINK.search(c)
    if m and "/clubs/" in m.group(2):
        SLUGS[m.group(1).strip()] = m.group(2).rsplit("/", 1)[-1].replace(".md", "").replace("-", " ")
    return (m.group(1) if m else c).strip()

def parse_matches(rows):
    res = []
    for c in rows:
        if len(c) < 4 or c[0] == "Date": continue
        try:
            dt = datetime.fromisoformat(c[0])
        except ValueError:
            continue
        score = cell_text(c[2])
        m = re.match(r"^\s*(\d+)\s*-\s*(\d+)", score)
        res.append({"dt": dt, "home": cell_text(c[1]), "away": cell_text(c[3]),
                    "sh": int(m.group(1)) if m else None, "sa": int(m.group(2)) if m else None,
                    "status": score if (score and not m) else ""})
    return res

def parse_table(rows):
    out = []
    for c in rows:
        if len(c) < 12 or c[0] == "#": continue
        try:
            out.append({"r": int(c[0]), "team": cell_text(c[1]), "pts": int(c[7]), "j": int(c[2]),
                        "g": int(c[3]), "n": int(c[4]), "p": int(c[5]), "bp": int(c[8]), "bc": int(c[9]),
                        "diff": c[10]})
        except ValueError:
            continue
    return out

def list_links(md, pattern):
    return sorted(set(m.group(1) for m in re.finditer(r"\((/en/championnats/" + SEASON + r"/" + pattern + r")\.md\)", md)))

def competitions():
    """Toutes les poules à examiner : (chemin, nom affiché, niveau, division, défaut de zone, seulement nos matchs)."""
    comps = []
    nat = get(f"{LDF}/en/championnats/{SEASON}/national.md") or ""
    for p in list_links(nat, r"national/[a-z0-9-]+"):
        slug = p.rsplit("/", 1)[1]
        if slug.startswith("ligue-"):
            name, div = f"Ligue {slug.split('-')[1]}", "National"
        elif re.fullmatch(r"[12][a-z]", slug):
            name, div = f"National {slug[0]} · Poule {slug[1].upper()}", "National"
        else:
            continue
        comps.append((p, name, "National", div, None, True))
    for reg, label in (("grand-est", ""), ("hauts-de-france", " Hauts-de-France")):
        md = get(f"{LDF}/en/championnats/{SEASON}/{reg}.md") or ""
        for p in list_links(md, reg + r"/regional/[123][a-z]"):
            slug = p.rsplit("/", 1)[1]
            comps.append((p, f"Régional {slug[0]}{label} · Poule {slug[1].upper()}", "Régional", f"R{slug[0]}", None, False))
    for reg, dist, name, dz in DISTRICTS:
        md = get(f"{LDF}/en/championnats/{SEASON}/{reg}/{dist}.md") or ""
        d1 = [p for p in list_links(md, f"{reg}/{dist}/1[a-z]")]
        for p in d1:
            slug = p.rsplit("/", 1)[1]
            nm = name if len(d1) == 1 else f"{name} · Poule {slug[1].upper()}"
            comps.append((p, nm, "Régional", "D1", dz, False))
    return comps

# ------------------------------------------------------------------ principal
def run(today, dry):
    D = load_data()
    Z = Zoner(D)
    now = today
    start, end = now - timedelta(days=7), now + timedelta(days=7)
    E = D["editions"][0]
    # Dimanche soir et lundi : on prépare l'édition du lundi (même id que la tâche du lundi matin).
    if now.weekday() in (6, 0):
        monday = (now + timedelta(days=1)) if now.weekday() == 6 else now
        mon = monday.date()
        start = datetime.combine(mon - timedelta(days=7), datetime.min.time(), PARIS)
        end = datetime.combine(mon + timedelta(days=6), datetime.min.time(), PARIS)
        now = datetime.combine(mon - timedelta(days=1), datetime.min.time(), PARIS)  # fin des résultats : dimanche
        eid = mon.isoformat()
        E = next((e for e in D["editions"] if e.get("id") == eid), None)
        if E is None:
            a, b = mon - timedelta(days=7), mon - timedelta(days=1)
            E = {"id": eid, "label": f"Semaine du {a.day} {MOIS[a.month-1]} au {b.day} {MOIS[b.month-1]}",
                 "edito": "", "results": [], "agenda": []}
            D["editions"].insert(0, E)
            del D["editions"][8:]
    report = {"poules": 0, "gardées": 0, "résultats": 0, "à venir": 0, "classements": 0, "erreurs": []}
    new_res, new_ag, new_cl, owned = [], [], [], set()

    for path, name, level, div, dz, only_ours in competitions():
        report["poules"] += 1
        url_md = f"{LDF}{path}.md"
        league = get(url_md)
        if not league:
            report["erreurs"].append(f"illisible : {url_md}"); continue
        tabs = md_tables(league)
        table = parse_table(tabs.get("League table", []))
        cal = get(f"{LDF}{path}/calendrier.md") or ""
        matches = parse_matches(tabs.get("Results", [])) + parse_matches(sum(md_tables(cal).values(), []))
        teams = {r["team"] for r in table} | {m["home"] for m in matches} | {m["away"] for m in matches}
        zones = {t: (None if norm(t) in EXCLUDE else (Z.zone(t) or (Z.zone(SLUGS[t]) if t in SLUGS else None) or dz)) for t in teams}
        ours = [t for t, z in zones.items() if z and z != "grandest"]
        if not any(zones.values()):
            continue  # aucune équipe de nos départements
        if level == "Régional" and not dz and len(ours) < 2:
            continue  # une seule correspondance dans une poule lointaine : sans doute un homonyme
        report["gardées"] += 1
        print("POULE", name, "|", ", ".join(sorted(f"{t} [{z}]" for t, z in zones.items() if z)))
        key = key_of(name); owned.add(key)
        page = f"{LDF}{path}/"
        extra = {"div": div} if div != "National" else {}
        if div == "D1": extra["genre"] = "M"
        seen = set()
        for m in sorted(matches, key=lambda x: x["dt"]):
            k = (m["dt"].date(), m["home"], m["away"])
            if k in seen: continue
            seen.add(k)
            hz, az = zones.get(m["home"]), zones.get(m["away"])
            if only_ours and not (hz or az): continue
            loc = m["dt"].astimezone(PARIS)
            base = {"sport": "Football", "level": level, **extra, "comp": name, "home": m["home"], "hz": hz,
                    "away": m["away"], "az": az, "url": page, "src": "ldf"}
            if m["sh"] is not None and start.date() <= loc.date() <= now.date():
                new_res.append({**base, "date": fdate(loc), "sh": m["sh"], "sa": m["sa"], "note": ""})
            elif m["sh"] is None and now.date() <= loc.date() <= end.date() and not m["status"] and loc >= datetime.now(PARIS) - timedelta(hours=3):
                new_ag.append({**base, "day": fdate(loc), "time": loc.strftime("%H:%M"), "place": ""})
        if table:
            new_cl.append({"sport": "Football", "level": level, **({"div": div} if div != "National" else {}),
                           "key": key, "maj": f"{now.day} {MOIS[now.month-1]} {now.year} · LiguesDeFoot", "url": page,
                           "rows": table, "src": "ldf"})

    # fusion : on remplace tout ce qui concerne les poules lues par le robot
    def keep(r):
        return not (r.get("sport") == "Football" and key_of(r.get("comp", "")) in owned)
    E["results"] = [r for r in E["results"] if keep(r)] + new_res
    E["agenda"] = [a for a in E["agenda"] if keep(a)] + new_ag
    D["classements"] = [c for c in D["classements"] if not (c.get("sport") == "Football" and c.get("key") in owned)] + new_cl
    report.update({"résultats": len(new_res), "à venir": len(new_ag), "classements": len(new_cl)})

    report["édition"] = E.get("id"); report["fenêtre"] = f"{start.date()} → {now.date()} / programme jusqu'au {end.date()}"
    print(json.dumps(report, ensure_ascii=False, indent=1))
    for r in new_res[:15]: print("R", r["date"], r["comp"], "|", r["home"], r["sh"], "-", r["sa"], r["away"], "|", r["hz"], r["az"])
    for a in new_ag[:15]: print("A", a["day"], a["time"], a["comp"], "|", a["home"], "-", a["away"], "|", a["hz"], a["az"])
    unz = sorted({t for c in new_cl for t in [x["team"] for x in c["rows"]] if not Z.zone(t)})
    print("Équipes sans zone (hors départements ou à associer) :", len(unz))
    if not dry:
        save_data(D)
    return report

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--today")
    a = ap.parse_args()
    today = datetime.fromisoformat(a.today).replace(tzinfo=PARIS) if a.today else datetime.now(PARIS)
    rep = run(today, a.dry_run)
    sys.exit(0)
