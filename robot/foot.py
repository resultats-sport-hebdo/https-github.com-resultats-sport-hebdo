"""Football : LiguesDeFoot.fr (pages texte .md)."""
import re
from datetime import datetime

from common import PARIS, MOIS, fdate, get, key_of, norm, season_of

LDF = "https://www.liguesdefoot.fr"
SPORT = "Football"
# Districts de nos 5 départements : (région LiguesDeFoot, slug district, nom affiché, zone par défaut)
DISTRICTS = [
    ("grand-est", "marne", "District 1 Marne", "reims"),
    ("grand-est", "ardennes", "D1 Ardennes", "charleville"),
    ("grand-est", "aube", "Départemental 1 Aube", "troyes"),
    ("grand-est", "haute-marne", "Départemental 1 Haute-Marne", "chaumont"),
    ("hauts-de-france", "aisne", "Départemental 1 Aisne", "laon"),
]
# Homonymes hors de nos départements, à ne jamais rattacher à une zone.
EXCLUDE = {"goal fc", "cs chaumontois"}

ROW = re.compile(r"^\|(.+)\|\s*$")
LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
SLUGS = {}


def md_tables(md):
    """Renvoie {titre de section: [lignes (liste de cellules)]}."""
    out, sec = {}, ""
    rows = out.setdefault("", [])
    for line in md.splitlines():
        if line.startswith("## "):
            sec = line[3:].strip(); rows = out.setdefault(sec, [])
            continue
        m = ROW.match(line)
        if m:
            cells = [c.strip() for c in m.group(1).split("|")]
            if cells and set(cells[0]) <= set("- "): continue
            rows.append(cells)
    return out


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


def competitions(season):
    """Toutes les poules à examiner : (chemin, nom affiché, niveau, division, zone par défaut, seulement nos matchs)."""
    def links(md, pattern):
        return sorted(set(m.group(1) for m in re.finditer(r"\((/en/championnats/" + season + r"/" + pattern + r")\.md\)", md)))
    comps = []
    nat = get(f"{LDF}/en/championnats/{season}/national.md") or ""
    for p in links(nat, r"national/[a-z0-9-]+"):
        slug = p.rsplit("/", 1)[1]
        if slug.startswith("ligue-"):
            name = f"Ligue {slug.split('-')[1]}"
        elif re.fullmatch(r"[12][a-z]", slug):
            name = f"National {slug[0]} · Poule {slug[1].upper()}"
        else:
            continue
        comps.append((p, name, "National", "National", None, True))
    for reg, label in (("grand-est", ""), ("hauts-de-france", " Hauts-de-France")):
        md = get(f"{LDF}/en/championnats/{season}/{reg}.md") or ""
        for p in links(md, reg + r"/regional/[123][a-z]"):
            slug = p.rsplit("/", 1)[1]
            comps.append((p, f"Régional {slug[0]}{label} · Poule {slug[1].upper()}", "Régional", f"R{slug[0]}", None, False))
    for reg, dist, name, dz in DISTRICTS:
        md = get(f"{LDF}/en/championnats/{season}/{reg}/{dist}.md") or ""
        d1 = links(md, f"{reg}/{dist}/1[a-z]")
        for p in d1:
            slug = p.rsplit("/", 1)[1]
            nm = name if len(d1) == 1 else f"{name} · Poule {slug[1].upper()}"
            comps.append((p, nm, "Régional", "D1", dz, False))
    return comps


def collect(D, Z, W, report):
    Z.exclude |= EXCLUDE
    a, b = season_of(W.now)
    out = []
    for path, name, level, div, dz, only_ours in competitions(f"{a}-{b}"):
        if (SPORT, key_of(name)) in getattr(W, "skip", set()): continue  # déjà lue sur Foot-National
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
        print("POULE", SPORT, name, "|", ", ".join(sorted(f"{t} [{z}]" for t, z in zones.items() if z)))
        page = f"{LDF}{path}/"
        extra = {"div": div} if div != "National" else {}
        if div == "D1": extra["genre"] = "M"
        P = {"sport": SPORT, "key": key_of(name), "results": [], "agenda": [], "cl": None}
        seen = set()
        for m in sorted(matches, key=lambda x: x["dt"]):
            k = (m["dt"].date(), m["home"], m["away"])
            if k in seen: continue
            seen.add(k)
            hz, az = zones.get(m["home"]), zones.get(m["away"])
            if only_ours and not (hz or az): continue
            loc = m["dt"].astimezone(PARIS)
            base = {"sport": SPORT, "level": level, **extra, "comp": name, "home": m["home"], "hz": hz,
                    "away": m["away"], "az": az, "url": page, "src": "ldf"}
            if m["sh"] is not None and W.is_result(loc):
                P["results"].append({**base, "date": fdate(loc), "sh": m["sh"], "sa": m["sa"], "note": ""})
            elif m["sh"] is None and not m["status"] and W.is_upcoming(loc):
                P["agenda"].append({**base, "day": fdate(loc), "time": loc.strftime("%H:%M"), "place": ""})
        if table:
            P["cl"] = {"sport": SPORT, "level": level, **({"div": div} if div != "National" else {}),
                       "key": P["key"], "maj": f"{W.now.day} {MOIS[W.now.month-1]} {W.now.year} · LiguesDeFoot", "url": page,
                       "rows": table, "src": "ldf"}
        out.append(P)
    return out
