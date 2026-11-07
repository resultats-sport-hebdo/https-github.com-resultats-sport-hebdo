"""Volley : site de gestion sportive de la FFVolley (ffvbbeach.org).

Chaque poule a une page avec son classement et tout son calendrier. Le numéro fédéral de chaque club
commence par son département (0 + numéro) : on reconnaît ainsi sans erreur les clubs de nos 5 départements.
"""
import html, re
from datetime import datetime

from common import DEPTS, MOIS, PARIS, fdate, get, key_of, season_of

SPORT = "Volley"
BASE = "https://www.ffvbbeach.org/ffvbapp/resu"
# (code de l'organisateur, région ajoutée au nom, niveau, seulement nos matchs)
ENTITES = [
    ("AALNV", "", "National", True),        # Ligue nationale de volley (Ligue A, Ligue B)
    ("ABCCS", "", "National", True),        # championnats nationaux FFVolley (Élite, N2, N3)
    ("LILO", " Grand Est", "Régional", False),
    ("LIFL", " Hauts-de-France", "Régional", False),
]
SKIP = re.compile(r"\bM\s?1[0-9]\b|\bM\s?2[01]\b|JUNIOR|CADET|MINIME|BENJAMIN|LOISIR|CORPO|TEST|INTERNATIONAU|D[ÉE]L[ÉE]GATION|ULTRAMARIN|BEACH|4X4|COUPE", re.I)
LNV = {"D1M": "Ligue AM", "D1F": "Ligue AF", "D2M": "Ligue BM"}


def deacc(s):
    import unicodedata
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()


def comp_name(code, label, region):
    """« PRE NATIONALE MASCULINE Poule A » → « Prénationale masculine Grand Est · Poule A »."""
    if code in LNV: return LNV[code]
    u = re.sub(r"\s+", " ", deacc(label).upper())
    g = "féminine" if "FEMININ" in u else "masculine"
    G = r"(?:\s*-?\s*(?:MASCULIN|FEMININ)\w*)?"
    bases = [(r"ELITE AVENIR" + G, "Élite Avenir"), (r"ELITE" + G, f"Élite {g}"),
             (r"(?<!PRE )(?<!PRE-)NATIONALE ?2" + G, f"Nationale 2 {g}"), (r"(?<!PRE )(?<!PRE-)NATIONALE ?3" + G, f"Nationale 3 {g}"),
             (r"PRE[ -]?NATIONALE" + G, f"Prénationale {g}{region}"), (r"REGIONALE ?1" + G, f"Régionale 1 {g}{region}"),
             (r"REGIONALE ?2" + G, f"Régionale 2 {g}{region}"), (r"REGIONALE" + G, f"Régionale {g}{region}")]
    for pat, base in bases:
        m = re.search(pat, u)
        if m: break
    else:
        return None
    rest = (u[:m.start()] + " - " + u[m.end():])
    rest = re.sub(r"\bHDF\b", "", rest)
    parts = []
    for p in re.split(r"\s+-\s+|^-\s*|\s*-$", rest):
        p = re.sub(r"\s+", " ", p).strip(" -")
        if not p: continue
        mp = re.fullmatch(r"POULE ([A-Z0-9]{1,2})", p)
        if mp: parts.append(f"Poule {mp.group(1)}")
        else:
            mp = re.match(r"(.*?)\s*POULE ([A-Z0-9]{1,2})$", p)
            if mp and mp.group(1): parts += [mp.group(1).capitalize(), f"Poule {mp.group(2)}"]
            else: parts.append(p.capitalize())
    return " · ".join([base] + parts)


def poules(codent, season):
    page = get(f"{BASE}/vbspo_home.php?saison={season}&codent={codent}", encoding="latin-1") or ""
    seen, out = set(), []
    for m in re.finditer(r"href=['\"]?vbspo_calendrier\.php\?saison=[^&]+&codent=" + codent + r"&poule=([A-Z0-9]+)['\"]?[^>]*>([^<]+)<", page):
        code, label = m.group(1), html.unescape(m.group(2)).strip()
        label = re.sub(r"^" + code + r"\s+", "", label)
        if code in seen or not label or SKIP.search(label): continue
        seen.add(code); out.append((code, label))
    return out


def cells(tr):
    return [html.unescape(re.sub(r"<[^>]+>", "", x)).replace("\xa0", " ").strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]


def parse_poule(page):
    """Renvoie (classement, {équipe: département}, matchs)."""
    table, dep, matches, journee = [], {}, [], None
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        c = cells(tr)
        if not c: continue
        mj = re.fullmatch(r"Journ[ée]e\s+0*(\d+)", c[0])
        if mj and len(c) == 1:
            journee = int(mj.group(1)); continue
        if re.fullmatch(r"\d+\.", c[0]) and len(c) > 5:
            try:
                row = {"r": int(c[0][:-1]), "team": c[1], "pts": int(c[2] or 0), "j": int(c[3] or 0),
                       "g": int(c[4] or 0), "p": int(c[5] or 0)}
            except ValueError:
                continue
            table.append(row)
            m = re.search(r"name=cnclub value=['\"]?(\d{7})", tr)
            if m: dep[c[1]] = m.group(1)[1:3]
            continue
        if len(c) >= 7 and re.fullmatch(r"[A-Z0-9]{3}\d{3}", c[0]) and re.fullmatch(r"\d\d/\d\d/\d\d", c[1]):
            try:
                dt = datetime.strptime(f"{c[1]} {c[2] or '00:00'}", "%d/%m/%y %H:%M").replace(tzinfo=PARIS)
            except ValueError:
                continue
            played = c[6].isdigit() and c[7].isdigit()
            matches.append({"dt": dt, "home": c[3], "away": c[5], "j": journee,
                            "sh": int(c[6]) if played else None, "sa": int(c[7]) if played else None,
                            "sets": c[8] if played and len(c) > 8 else "",
                            "place": "" if played else (c[7] if len(c) > 7 else "")})
    return table, dep, matches


def collect(D, Z, W, report):
    a, b = season_of(W.now)
    season = f"{a}/{b}"
    out = []
    for codent, region, level, only_ours in ENTITES:
        for code, label in poules(codent, season):
            name = comp_name(code, label, region)
            if not name: continue
            report["poules"] += 1
            url = f"{BASE}/vbspo_calendrier.php?saison={season}&codent={codent}&poule={code}"
            page = get(url, encoding="latin-1", pause=0.3)
            if not page:
                report["erreurs"].append(f"illisible : {url}"); continue
            table, dep, matches = parse_poule(page)
            teams = {r["team"] for r in table} | {m["home"] for m in matches} | {m["away"] for m in matches}
            zones = {}
            for t in teams:
                d = dep.get(t)
                zones[t] = Z.zone_in_dep(t, d) if d else (None if dep else Z.zone(t))
            if not any(zones.values()):
                continue
            print("POULE", SPORT, name, "|", ", ".join(sorted(f"{t} [{z}]" for t, z in zones.items() if z)))
            genre = "F" if "féminine" in name or name == "Ligue AF" else "M"
            P = {"sport": SPORT, "key": key_of(name), "results": [], "agenda": [], "cl": None}
            for m in sorted(matches, key=lambda x: x["dt"]):
                hz, az = zones.get(m["home"]), zones.get(m["away"])
                if only_ours and not (hz or az): continue
                comp = name + (f" · J{m['j']}" if m["j"] else "")
                base = {"sport": SPORT, "level": level, "genre": genre, "comp": comp, "home": m["home"], "hz": hz,
                        "away": m["away"], "az": az, "url": url, "src": "ffvb"}
                if m["sh"] is not None and W.is_result(m["dt"]):
                    sets = ", ".join(s.replace(":", "-") for s in re.split(r",\s*", m["sets"]) if s)
                    P["results"].append({**base, "date": fdate(m["dt"]), "sh": m["sh"], "sa": m["sa"],
                                         "note": f"Sets : {sets}." if sets else ""})
                elif m["sh"] is None and W.is_upcoming(m["dt"]):
                    P["agenda"].append({**base, "day": fdate(m["dt"]), "time": m["dt"].strftime("%H:%M"),
                                        "place": m["place"].title() if m["place"] else ""})
            if table and any(r.get("j") for r in table):
                P["cl"] = {"sport": SPORT, "level": level, **({"genre": "F"} if genre == "F" else {}), "key": P["key"],
                           "maj": f"{W.now.day} {MOIS[W.now.month-1]} {W.now.year} · FFVolley", "url": url,
                           "rows": table, "src": "ffvb"}
            out.append(P)
    return out
