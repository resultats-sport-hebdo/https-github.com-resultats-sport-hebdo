"""Football national : Foot-National (foot-national.com), source de référence pour la Ligue 1, la Ligue 2,
le National 1 et le National 2. LiguesDeFoot (foot.py) ne sert plus que de secours pour ces poules.
"""
import html as H, re
from datetime import datetime, timedelta

from common import MOIS, PARIS, fdate, get, key_of

SPORT = "Football"
BASE = "https://www.foot-national.com/data/"
# (slug Foot-National, nom affiché, identique aux noms de LiguesDeFoot pour garder les mêmes classements)
COMPETITIONS = [("ligue1", "Ligue 1"), ("ligue2", "Ligue 2")] + \
    [(f"national1-groupe-{p}", f"National 1 · Poule {p.upper()}") for p in "abc"] + \
    [(f"national2-groupe-{p}", f"National 2 · Poule {p.upper()}") for p in "abcdefgh"]
MOIS_FR = {m: i + 1 for i, m in enumerate(["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
                                           "septembre", "octobre", "novembre", "decembre"])}


def deacc(s):
    import unicodedata
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()


def page(slug):
    t = get(BASE + slug + ".html", encoding="latin-1", pause=0.3)
    return t or ""


def parse_matches(b):
    """Lignes de match d'une page de journée, avec la date de l'en-tête qui les précède."""
    out, day = [], None
    for m in re.finditer(r'widget-sub-title center">([^<]+)<|<div class="row ">(.*?)bt-info', b, re.S):
        if m.group(1):
            d = re.search(r"(\d{1,2})\s+([A-Za-zéûÉÛ]+)\s+(\d{4})", H.unescape(m.group(1)))
            day = None
            if d and deacc(d.group(2)).lower() in MOIS_FR:
                day = (int(d.group(3)), MOIS_FR[deacc(d.group(2)).lower()], int(d.group(1)))
            continue
        row = m.group(2)
        teams = re.findall(r'title="([^"]*)" class="uncolored">\s*(?:<span>([^<]*)</span>|<img[^>]*>\s*<span>([^<]*)</span>)', row)
        sc = re.search(r'href="(match-foot-[^"]+)" class="uncolored"><b>\s*([^<]*)</b>', row)
        tm = re.search(r"<strong>(\d{1,2}):(\d{2})</strong>", row)
        if len(teams) < 2 or not day: continue
        names = [H.unescape(t[0]).strip() or H.unescape(t[1] or t[2]).strip() for t in teams[:2]]  # nom complet
        short = [H.unescape(t[1] or t[2]).strip() for t in teams[:2]]
        hh, mm = (int(tm.group(1)), int(tm.group(2))) if tm else (0, 0)
        dt = datetime(day[0], day[1], day[2], hh, mm, tzinfo=PARIS)
        s = re.match(r"\s*(\d+)\s*-\s*(\d+)", sc.group(2)) if sc else None
        out.append({"dt": dt, "home": names[0], "away": names[1], "short": short,
                    "sh": int(s.group(1)) if s else None, "sa": int(s.group(2)) if s else None,
                    "url": BASE + sc.group(1) if sc else ""})
    return out


def parse_table(b):
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", b[b.find("<table"):], re.S):
        tds = [H.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        ttl = re.search(r'title="([^"]+)"', tr)
        if len(tds) < 11 or not tds[0].isdigit(): continue
        try:
            rows.append({"r": int(tds[0]), "team": H.unescape(ttl.group(1)) if ttl and ttl.group(1) else tds[2],
                         "pts": int(tds[3]), "j": int(tds[4]), "g": int(tds[5]), "n": int(tds[6]), "p": int(tds[7]),
                         "bp": int(tds[8]), "bc": int(tds[9]), "diff": f"{int(tds[10]):+d}"})
        except ValueError:
            continue
    return rows


def collect(D, Z, W, report):
    out = []
    now = datetime.now(PARIS)
    for slug, name in COMPETITIONS:
        report["poules"] += 1
        res = page("resultat-" + slug)
        if not res:
            report["erreurs"].append(f"illisible : {BASE}resultat-{slug}.html"); continue
        cur = re.search(r'<option value="(\d+)"\s*selected', res)
        j = int(cur.group(1)) if cur else None
        pages = {j: res} if j else {}
        if j:
            for k in (j - 1, j + 1, j + 2):
                if k >= 1: pages[k] = page(f"calendrier-{slug}-{k}")
        table = parse_table(page("classement-" + slug))
        matches = []
        for k, b in pages.items():
            for m in parse_matches(b):
                m["j"] = k; matches.append(m)
        reserve_ok = not name.startswith("National")  # en N1/N2, les réserves des clubs pros du Grand Est ne sont pas suivies
        def zone(t, s):
            z = Z.zone(t) or Z.zone(s)
            return None if (z == "grandest" and not reserve_ok) else z
        disp = {}
        for m in matches:
            for full, sh in ((m["home"], m["short"][0]), (m["away"], m["short"][1])):
                c = Z.canon(full, sh) if zone(full, sh) else None
                if c and re.search(r"\s(B|2|II)$", sh or ""): c += " 2"
                disp[full] = c or sh or full
        for m in matches:
            m["zh"], m["za"] = zone(m["home"], m["short"][0]), zone(m["away"], m["short"][1])
            m["home"], m["away"] = disp[m["home"]], disp[m["away"]]
        teams = {}
        for m in matches:
            teams[m["home"]] = m["zh"]; teams[m["away"]] = m["za"]
        for r in table:
            r["team"] = disp.get(r["team"]) or Z.canon(r["team"]) or r["team"]
            teams.setdefault(r["team"], zone(r["team"], r["team"]))
        if not any(teams.values()): continue
        print("POULE", SPORT, name, "(Foot-National) |", ", ".join(sorted(f"{t} [{z}]" for t, z in teams.items() if z)))
        P = {"sport": SPORT, "key": key_of(name), "results": [], "agenda": [], "cl": None}
        seen = set()
        for m in sorted(matches, key=lambda x: x["dt"]):
            k = (m["dt"].date(), m["home"], m["away"])
            if k in seen: continue
            seen.add(k)
            hz, az = teams.get(m["home"]), teams.get(m["away"])
            if not (hz or az): continue
            base = {"sport": SPORT, "level": "National", "comp": f"{name} · J{m['j']}", "home": m["home"], "hz": hz,
                    "away": m["away"], "az": az, "url": m["url"] or f"{BASE}resultat-{slug}.html", "src": "fn"}
            finished = m["dt"] + timedelta(hours=2, minutes=15) <= now
            if m["sh"] is not None and finished and W.is_result(m["dt"]):
                P["results"].append({**base, "date": fdate(m["dt"]), "sh": m["sh"], "sa": m["sa"], "note": ""})
            elif not finished and W.is_upcoming(m["dt"]):
                P["agenda"].append({**base, "day": fdate(m["dt"]), "time": m["dt"].strftime("%H:%M") if m["dt"].hour else "", "place": ""})
        if table:
            P["cl"] = {"sport": SPORT, "level": "National", "key": P["key"],
                       "maj": f"{W.now.day} {MOIS[W.now.month-1]} {W.now.year} · Foot-National",
                       "url": f"{BASE}classement-{slug}.html", "rows": table, "src": "fn"}
        out.append(P)
    return out
