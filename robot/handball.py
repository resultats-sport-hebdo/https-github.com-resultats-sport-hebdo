"""Handball : site des compétitions de la FFHandball (ffhandball.fr).

Les pages contiennent leurs données (équipes, poules, rencontres d'une journée, classement) dans les attributs
des composants « smartfire » : pas besoin de navigateur.
"""
import html as H, json, re
from datetime import datetime

from common import MOIS, PARIS, fdate, get, key_of, season_of

SPORT = "Handball"
SITE = "https://www.ffhandball.fr"
SKIP = re.compile(r"\b1[0-9]\b|ans|u1\d|u2\d|handfauteuil|intercomit|troph[ée]e|coupe|beach|loisir|hand-?fit|baby", re.I)
LIGUES = [("o-ligue-grand-est-de-handball-2", "Grand Est"), ("o-ligue-hauts-de-france-12", "Hauts-de-France")]


def components(page):
    out = []
    for m in re.finditer(r"<smartfire-component\b([^>]*)>", page or ""):
        at = re.search(r'attributes="([^"]*)"', m.group(1))
        if not at: continue
        try:
            out.append(json.loads(H.unescape(at.group(1))))
        except ValueError:
            pass
    return out


def find(comps, key):
    for c in comps:
        if isinstance(c, dict) and key in c and c[key]: return c
    return {}


def slugify(t):
    import unicodedata
    t = unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def comp_links(path, kind):
    """Compétitions listées dans les données de la page (les liens n'existent qu'une fois la page affichée)."""
    page = get(SITE + path) or ""
    comps = find(components(page), "competitions").get("competitions", [])
    links = [f"{path}{slugify(c['libelle'])}-{c['ext_competitionId']}/".replace(f"/{path.strip('/').split('/')[-1]}/", "/") if False else
             re.sub(r"/regional/[^/]+/$", "/regional/", path) + f"{slugify(c['libelle'])}-{c['ext_competitionId']}/"
             for c in comps if c.get("libelle") and c.get("ext_competitionId")]
    links += re.findall(r'href="(/competitions/saison-[^/]+/' + kind + r'/[a-z0-9-]+-\d{4,6}/)"', page)
    return sorted({l for l in links if not SKIP.search(l.rstrip("/").rsplit("/", 1)[-1])})


def nice_name(slug, region):
    s = slug.lower()
    g = "féminine" if re.search(r"fem", s) else "masculine"
    if "starligue" in s: return "Liqui Moly Starligue" if "liqui" in s else "Starligue", "M"
    if "proligue" in s: return "Proligue", "M"
    if "butagaz" in s: return "Ligue Butagaz Énergie", "F"
    if re.search(r"d2-fem", s): return "D2 féminine", "F"
    m = re.search(r"nationale-(\d)-(masculine|feminine)", s)
    if m and "territoriale" not in s:
        return f"Nationale {m.group(1)} {'féminine' if m.group(2).startswith('fem') else 'masculine'}", "F" if m.group(2).startswith("fem") else "M"
    if "territoriale" in s: return f"Nationale 3 territoriale féminine {region}".strip(), "F"
    if "prenational" in s: return f"Prénationale {g} {region}", g[0].upper()
    if "excellence" in s: return f"Excellence {g} {region}", g[0].upper()
    if "honneur" in s: return f"Honneur {g} {region}", g[0].upper()
    words = re.sub(r"^\d+-\d+-|-\d+$", "", s).replace("-", " ")
    return f"{words.capitalize()} {region}".strip(), "F" if "fem" in s else "M"


def collect(D, Z, W, report):
    a, b = season_of(W.now)
    saison = None
    nat = get(f"{SITE}/competitions/") or ""
    m = re.search(r"/competitions/(saison-%d-%d-\d+)/" % (a, b), nat)
    saison = m.group(1) if m else f"saison-{a}-{b}-{a - 2004}"
    todo = [(l, "", "National") for l in comp_links(f"/competitions/{saison}/national/", "national")]
    for slug, region in LIGUES:
        todo += [(l, region, "Régional") for l in comp_links(f"/competitions/{saison}/regional/{slug}/", "regional")]
    out = []
    for path, region, level in todo:
        cslug = path.rstrip("/").rsplit("/", 1)[-1]
        base_name, genre = nice_name(cslug, region)
        if "Nationale" in base_name:
            if level == "Régional" and region and region not in base_name: base_name += f" {region}"
            level = "National"
        comps = components(get(SITE + path, pause=0.2))
        eq = find(comps, "equipes").get("equipes", [])
        pl = find(comps, "poules").get("poules", [])
        if not eq or not pl: continue
        report["poules"] += len(pl)
        names = {e["id"]: H.unescape(e.get("libelle", "")).strip() for e in eq}
        by_poule = {}
        for e in eq: by_poule.setdefault(e.get("pouleId"), []).append(names[e["id"]])
        for p in pl:
            teams = by_poule.get(p["id"], [])
            zones = {t: Z.zone(t) for t in teams}
            zones = {t: (None if z == "grandest" else z) for t, z in zones.items()}
            if not any(zones.values()): continue
            multi = len(pl) > 1
            mp = re.search(r"POULE\s*([A-Z0-9]+)", (p.get("libelle") or "").upper())
            name = base_name + ((f" · Poule {mp.group(1)}" if mp else f" · {p['libelle'].title()}") if multi else "")
            url = f"{SITE}{path}poule-{p['ext_pouleId']}/"
            first = components(get(url, pause=0.2))
            rc = find(first, "rencontres"); cl = find(first, "classements")
            try:
                jsel = int(rc.get("selected_numero_journee") or 0)
            except ValueError:
                jsel = 0
            pages = {jsel: rc.get("rencontres", [])}
            for j in (jsel - 1, jsel + 1):
                if j >= 1:
                    pages[j] = find(components(get(f"{url}journee-{j}/", pause=0.2)), "rencontres").get("rencontres", [])
            print("POULE", SPORT, name, "|", ", ".join(sorted(f"{t} [{z}]" for t, z in zones.items() if z)))
            P = {"sport": SPORT, "key": key_of(name), "results": [], "agenda": [], "cl": None}
            seen = set()
            for j, rs in pages.items():
                for r in rs or []:
                    if r.get("id") in seen: continue
                    seen.add(r.get("id"))
                    home, away = names.get(r.get("equipe1Id")), names.get(r.get("equipe2Id"))
                    if not home or not away or not r.get("date"): continue
                    hz, az = zones.get(home), zones.get(away)
                    if level == "National" and not (hz or az): continue
                    try:
                        dt = datetime.fromisoformat(r["date"]).astimezone(PARIS)
                    except ValueError:
                        continue
                    bse = {"sport": SPORT, "level": level, "genre": genre, "comp": f"{name} · J{j}", "home": home, "hz": hz,
                           "away": away, "az": az, "url": f"{url}rencontre-{r.get('ext_rencontreId')}/", "src": "ffhb"}
                    s1, s2 = r.get("equipe1Score"), r.get("equipe2Score")
                    if s1 not in (None, "") and s2 not in (None, ""):
                        if W.is_result(dt):
                            mt = (r.get("equipe1ScoreMT"), r.get("equipe2ScoreMT"))
                            note = f"Mi-temps : {mt[0]}-{mt[1]}." if None not in mt and "" not in mt else ""
                            P["results"].append({**bse, "date": fdate(dt), "sh": int(s1), "sa": int(s2), "note": note})
                    elif W.is_upcoming(dt):
                        P["agenda"].append({**bse, "day": fdate(dt), "time": dt.strftime("%H:%M"), "place": ""})
            rows = []
            for c in sorted(cl.get("classements", []), key=lambda c: int(c.get("place") or 99)):
                try:
                    rows.append({"r": int(c["place"]), "team": H.unescape(c.get("equipe_libelle", "")).strip(), "pts": int(c.get("point") or 0),
                                 "j": int(c.get("joue") or 0), "g": int(c.get("gagne") or 0), "n": int(c.get("nul") or 0),
                                 "p": int(c.get("perdu") or 0), "bp": int(c.get("butPlus") or 0), "bc": int(c.get("butMoins") or 0),
                                 "diff": f"{int(c.get('diff') or 0):+d}"})
                except (KeyError, ValueError):
                    continue
            if rows:
                P["cl"] = {"sport": SPORT, "level": level, **({"genre": "F"} if genre == "F" else {}), "key": P["key"],
                           "maj": f"{W.now.day} {MOIS[W.now.month-1]} {W.now.year} · FFHandball", "url": f"{url}classements/",
                           "rows": rows, "src": "ffhb"}
            out.append(P)
    return out
