"""Résultats des clubs rémois d'après Sport Club Reims (sportclub-reims.fr).

Chaque dimanche soir, Sport Club publie « RESULTATS – Week-end du … » avec tous les scores des clubs de Reims et
des environs, souvent bien avant les sites fédéraux (le foot amateur du dimanche n'arrive sur LiguesDeFoot que
dans la nuit). Le jour de chaque match vient de l'article « AGENDA – Week-end du … » de la même semaine.

Source partielle (autour de Reims seulement) : ajout match par match (« upsert »). Un match déjà fourni par une
source fédérale est ignoré, et quand la source fédérale l'apporte plus tard, c'est elle qui remplace celui-ci.
"""
import html, json, re
from datetime import datetime, timedelta

from common import PARIS, MOIS, fdate, get, key_of, norm

SPORT = "Football"  # pour le catalogue du robot ; chaque entrée porte son sport
API = "https://www.sportclub-reims.fr/wp-json/wp/v2/posts"
SPORTS = {"FOOTBALL": "Football", "FUTSAL": "Futsal", "BASKET": "Basket", "VOLLEY": "Volley", "HANDBALL": "Handball",
          "RUGBY": "Rugby", "ROLLER HOCKEY": "Roller hockey", "HOCKEY SUR GLACE": "Hockey sur glace", "WATER-POLO": "Water-polo",
          "WATER POLO": "Water-polo"}
SKIP = re.compile(r"coupe|sourds|amical|tournoi|challenge|troph", re.I)
JOURS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6}
MOIS_FR = {m: i + 1 for i, m in enumerate(["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
                                            "septembre", "octobre", "novembre", "decembre"])}
# libellés de Sport Club → nom de compétition affiché et niveau
FOOT = {"R1M": "Régional 1", "R2M": "Régional 2", "R3M": "Régional 3", "R1F": "Régional 1 féminin", "R2F": "Régional 2 féminin",
        "D1M": "Départemental 1", "D1": "Départemental 1"}
# libellés courts des autres sports (utilisés seulement si aucune source fédérale n'a déjà le match)
NAMES = {(None, "N1M"): "Nationale 1 masculine", (None, "N2M"): "Nationale 2 masculine", (None, "N3M"): "Nationale 3 masculine",
         (None, "N1F"): "Nationale 1 féminine", (None, "N2F"): "Nationale 2 féminine", (None, "N3F"): "Nationale 3 féminine",
         (None, "PNM"): "Prénationale masculine", (None, "PNF"): "Prénationale féminine",
         ("Volley", "D2M"): "Ligue BM", ("Volley", "D1M"): "Ligue AM", ("Hockey sur glace", "D2"): "Division 2",
         ("Futsal", "R1F"): "Régional 1 féminin", ("Futsal", "R1M"): "Régional 1", ("Rugby", "R1M"): "Régionale 1",
         ("Rugby", "FED 2 F"): "Fédérale 2 féminine", ("Rugby", "FED 3"): "Fédérale 3", ("Roller hockey", "N3M"): "Nationale 3",
         ("Roller hockey", "N2M"): "Nationale 2", ("Roller hockey", "N1M"): "Nationale 1"}
DIV = {"Régional 1": "R1", "Régional 2": "R2", "Régional 3": "R3", "Régional 1 féminin": "R1", "Régional 2 féminin": "R2",
       "Départemental 1": "D1"}


def text_of(fragment):
    t = re.sub(r"<img[^>]*alt=\"([^\"]*)\"[^>]*>", r"\1", fragment)
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return [re.sub(r"\s+", " ", x).strip("  ") for x in t.split("\n")]


def blocks(content):
    """[(sport, libellé, [lignes])] : un bloc par <li>, le sport vient du dernier intertitre."""
    out, sport = [], None
    for m in re.finditer(r"<blockquote>(.*?)</blockquote>|<li>(.*?)</li>", content, re.S):
        if m.group(1):
            head = norm(" ".join(text_of(m.group(1)))).upper()
            sport = next((v for k, v in SPORTS.items() if norm(k).upper() in head), None)
            continue
        if not sport: continue
        lines = [l for l in text_of(m.group(2)) if l]
        if not lines: continue
        first = lines[0]
        if ":" not in first: continue
        label, rest = first.split(":", 1)
        lines = ([rest.strip()] if rest.strip() else []) + lines[1:]
        out.append((sport, label.strip(), lines))
    return out


def comp_of(sport, label):
    """« R1M (J10) » → (« Régional 1 · J10 », niveau, genre) ; None pour ce qu'on ne couvre pas."""
    if SKIP.search(label): return None
    j = re.search(r"\(J(\d+)", label)
    base = re.sub(r"\s*\(.*$", "", label).strip()
    genre = "F" if re.search(r"F\b|f[ée]m|^LF", base) else "M"
    if sport == "Football" and base.upper() in FOOT:
        name, level = FOOT[base.upper()], "Régional"
    elif re.fullmatch(r"R\d[MF]?|PN[MF]?|PR[MF]?|Pr[ée]-?nationale.*|R[ée]gionale?.*", base, re.I):
        name, level = base, "Régional"
    else:
        name, level = base, "National"
    name = NAMES.get((sport, base.upper()), NAMES.get((None, base.upper()), name))
    if sport == "Football" and level == "National": return None  # Foot-National et LiguesDeFoot le couvrent déjà
    return name + (f" · J{j.group(1)}" if j else ""), level, genre


SCORE = re.compile(r"^[–\-•]?\s*(.+?)\s+(\d{1,3})\s*-\s*(\d{1,3})\s+(.+?)\s*(\(.*\))?\s*$")
VERSUS = re.compile(r"^[–\-•]?\s*(.+?)\s+(?:🆚|–|-)\s+(.+?)\s*$")
DAY = re.compile(r"(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+(\d{1,2})(?:er)?\s+([a-zéû]+)", re.I)


SMALL = {"de", "du", "des", "la", "le", "les", "et", "sur", "en", "aux", "au", "lès", "les", "sous", "d", "l"}
KEEP_UP = {"fc", "as", "es", "us", "sc", "cs", "fco", "rc", "bf", "ch", "oam", "ac", "ca", "hb", "vb", "bc", "ab", "b", "c", "ii"}
ACCENTS = {}


def learn_accents(D):
    """Mots accentués déjà connus (noms des clubs dans les données) : « BETHENY » redevient « Bétheny »."""
    names = [c.get("club", "") for c in D.get("suivi", [])]
    for E in D.get("editions", [])[:3]:
        for r in E.get("results", []) + E.get("agenda", []):
            names += [r.get("home", ""), r.get("away", "")]
    for c in D.get("classements", []):
        names += [x.get("team", "") for x in c.get("rows", [])]
    for n in names:
        for w in re.findall(r"[A-Za-zÀ-ÿ’']+", n or ""):
            if w != norm(w) and not w.isupper() and len(w) > 2 and norm(w).replace(" ", "") not in ACCENTS:
                ACCENTS[norm(w).replace(" ", "")] = w[0].upper() + w[1:]


def clean(team):
    t = re.sub(r"\s+", " ", team).strip(" .,;")
    if not t.isupper(): return t
    out = []
    for i, w in enumerate(re.split(r"(\s+|-)", t)):
        k = norm(w).replace(" ", "")
        if not k or w.isspace() or w == "-": out.append(w); continue
        if k in KEEP_UP: out.append(w.upper())
        elif i and k in SMALL: out.append(w.lower())
        else: out.append(ACCENTS.get(k) or w.capitalize())
    return "".join(out)


def agenda_days(content, year):
    """{(sport, libellé normalisé): [(date, domicile, extérieur)]} d'après l'article AGENDA."""
    out = {}
    for sport, label, lines in blocks(content):
        d = None
        for l in lines:
            m = DAY.search(l)
            if m and norm(m.group(3)) in MOIS_FR:
                try:
                    d = datetime(year, MOIS_FR[norm(m.group(3))], int(m.group(2)), tzinfo=PARIS)
                except ValueError:
                    pass
        if not d: continue
        pairs = []
        for l in lines:
            if DAY.search(l): continue
            v = VERSUS.match(l)
            if v: pairs.append((v.group(1), v.group(2)))
        out.setdefault((sport, norm(label)), []).append((d, pairs))
    return out


def same_team(a, b):
    ta, tb = set(norm(a).split()) - {"b", "c", "2", "3"}, set(norm(b).split()) - {"b", "c", "2", "3"}
    return bool(ta & tb)


def latest(kind, after):
    t = get(f"{API}?search={kind}&per_page=5&after={after:%Y-%m-%dT00:00:00}&_fields=date,link,title,content")
    try:
        posts = json.loads(t or "[]")
    except ValueError:
        return None
    for p in posts:
        title = html.unescape(re.sub(r"<[^>]+>", "", p["title"]["rendered"]))
        if title.upper().startswith(kind):
            return {"title": title, "link": p["link"], "content": p["content"]["rendered"],
                    "date": datetime.fromisoformat(p["date"]).replace(tzinfo=PARIS)}
    return None


def collect(D, Z_unused, W, report):
    from common import Zoner
    learn_accents(D)
    after = W.start - timedelta(days=1)
    rec = latest("RESULTATS", after)
    if not rec:
        report["sportclub-reims (résultats)"] = "pas encore de récapitulatif"; return []
    ag = latest("AGENDA", after - timedelta(days=4))
    days = agenda_days(ag["content"], rec["date"].year) if ag else {}
    zoners = {}
    out, n, nodate = {}, 0, 0
    for sport, label, lines in blocks(rec["content"]):
        c = comp_of(sport, label)
        if not c: continue
        comp, level, genre = c
        Z = zoners.setdefault(sport, Zoner(D, sport))
        cand = days.get((sport, norm(label)), [])
        for l in lines:
            m = SCORE.match(l)
            if not m: continue
            home, away = clean(m.group(1)), clean(m.group(4))
            if re.search(r"\d+e,|pts\)|\dV-\dD", l): continue  # ligne de classement
            d = None
            for dd, pairs in cand:
                if any(same_team(h, home) and same_team(a, away) for h, a in pairs): d = dd; break
            if d is None and len(cand) == 1: d = cand[0][0]
            if d is None or not W.is_result(d):
                nodate += d is None; continue
            hz, az = Z.zone(home), Z.zone(away)
            if not (hz or az): continue
            key = key_of(comp.split(" · J")[0])
            P = out.setdefault((sport, key), {"sport": sport, "key": key, "results": [], "agenda": [], "cl": None, "mode": "upsert"})
            P["results"].append({"sport": sport, "level": level, **({"genre": "F"} if genre == "F" else {}),
                                 **({"div": DIV[comp.split(" · ")[0]]} if comp.split(" · ")[0] in DIV else {}),
                                 "comp": comp, "date": fdate(d), "home": home, "hz": hz, "away": away, "az": az,
                                 "sh": int(m.group(2)), "sa": int(m.group(3)), "note": "", "url": rec["link"],
                                 "src": "scr", "mid": f"scr-{d:%Y%m%d}-{norm(home)}-{norm(away)}".replace(" ", "")})
            n += 1
    report["sportclub-reims (résultats)"] = f"{n} scores lus dans « {rec['title']} »" + (f", {nodate} sans date" if nodate else "")
    res = list(out.values())
    for P in res:
        print("POULE", P["sport"], P["key"], "(Sport Club Reims) |", len(P["results"]), "résultats")
    return res
