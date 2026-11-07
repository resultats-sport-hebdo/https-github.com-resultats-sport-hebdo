"""Outils partagés par les lecteurs du robot (football, volley, basket, rugby)."""
import json, re, time, unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 "
                    "ResultatsSportHebdo-robot/1.1 (+https://github.com/resultats-sport-hebdo)",
      "Accept-Language": "fr-FR,fr;q=0.9"}
PARIS = timezone(timedelta(hours=1))  # heure d'hiver ; les heures affichées viennent telles quelles des sources
JOURS = ["Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam.", "Dim."]
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
# Nos 5 départements : numéro → zone par défaut quand la ville du club n'est pas reconnue
DEPTS = {"51": "reims", "08": "charleville", "10": "troyes", "52": "chaumont", "02": "laon"}
DEP_LABEL = {"51": "Marne (51)", "08": "Ardennes (08)", "10": "Aube (10)", "52": "Haute-Marne (52)", "02": "Aisne (02)"}


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


STOP = set("fc us as es sc cs ca ac rc js om os ol o sp sf sl ent entente club football foot de du la le les l d st saint ste sainte "
           "sur sous en aux des les au lez pres the and et union sportive association olympique stade sporting usa asc fcf ec aj cso usag oam am prix "
           "vb volley ball volleyball bb basket basketball rugby xv hb handball".split())


def tokens(s):
    return [t for t in norm(s).split() if t not in STOP and not t.isdigit() and len(t) > 1]


def fdate(dt):
    d = dt.day
    return f"{JOURS[dt.weekday()]} {'1er' if d == 1 else d} {MOIS[dt.month - 1]}"


def season_of(dt):
    y = dt.year if dt.month >= 8 else dt.year - 1
    return y, y + 1


session = requests.Session(); session.headers.update(UA)


def get(url, tries=3, encoding=None, pause=0.0):
    for i in range(tries):
        try:
            r = session.get(url, timeout=40)
            if r.status_code == 200:
                if encoding: r.encoding = encoding
                if pause: time.sleep(pause)
                return r.text
            if r.status_code in (403, 404):
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
    k = re.sub(r"\s*·\s*J\d+.*$", "", comp or "")
    k = re.sub(r"\s+(Homiris|IHE [ÉE]nergies|Escates [^·]*|CFA du B[âa]timent 51|3 Brasseurs|Allianz Leseur)\b", "", k, flags=re.I)
    return re.sub(r"\s+", " ", k).strip()


# ------------------------------------------------------------------ zones
class Zoner:
    """Associe un nom d'équipe à une zone de nos 5 départements (ou None)."""
    def __init__(self, D, sport="Football", exclude=()):
        self.exclude = set(exclude)
        self.map, self.exact = {}, {}
        def add(name, z):
            if not z: return
            t = " ".join(tokens(name))
            if not t: return
            if z == "grandest": self.exact.setdefault(t, z)
            else: self.map.setdefault(t, z)
        for s in D.get("suivi", []):
            if s.get("sport") == sport: add(s["club"], s.get("zone"))
        for e in D.get("editions", []):
            for r in e.get("results", []) + e.get("agenda", []):
                if r.get("sport") == sport:
                    add(r.get("home"), r.get("hz")); add(r.get("away"), r.get("az"))
        self.villes = []
        self.dep_of = {}
        for z in D.get("zones", []):
            m = re.search(r"\((\d\d)\)", z.get("dep", ""))
            self.dep_of[z["k"]] = m.group(1) if m else None
            if z["k"] == "grandest": continue
            for v in z.get("villes", []) + [z["l"]]:
                for part in re.split(r"\s+[–-]\s+", v):  # « Romilly – Nogent-sur-Seine » : deux villes, pas trois
                    t = tokens(part)
                    if t: self.villes.append((t, z["k"]))

    def by_city(self, team, dep=None):
        ts = set(tokens(team))
        for vt, z in self.villes:
            if (dep is None or self.dep_of.get(z) == dep) and set(vt) <= ts and all(len(x) >= 3 for x in vt):
                return z
        return None

    def zone(self, team):
        if norm(team) in self.exclude: return None
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
        return self.by_city(team)

    def zone_in_dep(self, team, dep):
        """Zone d'une équipe dont on connaît le département (numéro de club fédéral)."""
        if dep not in DEPTS: return None
        z = self.zone(team)
        if z and z != "grandest": return z
        return self.by_city(team, dep) or DEPTS[dep]


# ------------------------------------------------------------------ fenêtre de dates
class Window:
    """Fenêtre des résultats et du programme, et édition visée."""
    def __init__(self, start, now, end, eid):
        self.start, self.now, self.end, self.eid = start, now, end, eid

    def is_result(self, dt):
        return self.start.date() <= dt.date() <= self.now.date()

    def is_upcoming(self, dt):
        return self.now.date() <= dt.date() <= self.end.date() and dt >= datetime.now(PARIS) - timedelta(hours=3)


def poule_entry(sport, level, comp, home, hz, away, az, url, extra=None):
    return {"sport": sport, "level": level, **(extra or {}), "comp": comp, "home": home, "hz": hz,
            "away": away, "az": az, "url": url}


# ------------------------------------------------------------------ navigateur (sites protégés)
class Browser:
    """Vrai navigateur (Playwright) pour les sites qui refusent les robots simples (FFBB)."""
    BLOCK = re.compile(r"you have been blocked|bunny\.net|403 Forbidden", re.I)

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._p = sync_playwright().start()
        self._b = self._p.chromium.launch()
        self._ctx = self._b.new_context(locale="fr-FR", user_agent=UA["User-Agent"].split(" ResultatsSportHebdo")[0])
        self.blocked = 0
        return self

    def get(self, url, tries=3, wait=4000):
        for i in range(tries):
            pg = self._ctx.new_page()
            try:
                pg.goto(url, wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(wait)
                html = pg.content()
                if not (len(html) < 60000 and self.BLOCK.search(html)):
                    return html
                self.blocked += 1
            except Exception:
                pass
            finally:
                pg.close()
            time.sleep(15 * (i + 1))
        return None

    def __exit__(self, *a):
        try:
            self._b.close(); self._p.stop()
        except Exception:
            pass
