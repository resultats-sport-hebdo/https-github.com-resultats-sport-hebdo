"""Liens vers les articles de Sport Club Reims (sportclub-reims.fr), à privilégier quand ils existent.

Pour chaque résultat du robot, on cherche un article publié entre le jour du match et 4 jours après qui cite
l'adversaire et donne le score : article de match d'abord, sinon le récapitulatif « RESULTATS – Week-end du … ».
"""
import html, json, re
from datetime import datetime, timedelta

from common import PARIS, get, norm, tokens

API = "https://www.sportclub-reims.fr/wp-json/wp/v2/posts"
SKIP = re.compile(r"retour en images|replay|agenda|podcast|talk|mag", re.I)
GENERIC = {"reims", "champagne", "grand", "est", "ardennes", "marne", "aube", "aisne", "volley", "basket", "hockey",
           "rugby", "futsal", "handball", "feminin", "feminines", "feminine", "masculin", "club", "sport"}


def posts(after):
    out = []
    for p in range(1, 4):
        t = get(f"{API}?per_page=50&page={p}&after={after:%Y-%m-%dT00:00:00}&_fields=date,link,title,content")
        if not t: break
        try:
            batch = json.loads(t)
        except ValueError:
            break
        for x in batch:
            title = html.unescape(re.sub(r"<[^>]+>", "", x["title"]["rendered"]))
            if SKIP.search(title): continue
            body = html.unescape(re.sub(r"<[^>]+>", " ", x["content"]["rendered"]))
            out.append({"date": datetime.fromisoformat(x["date"]).replace(tzinfo=PARIS), "link": x["link"],
                        "title": norm(title), "text": " " + norm(title + " " + body) + " ",
                        "recap": title.upper().startswith("RESULTATS")})
        if len(batch) < 50: break
    return out


def distinctive(team):
    return [t for t in tokens(team) if len(t) >= 4 and t not in GENERIC]


def score_in(text, a, b):
    return re.search(rf"\b{a}\s+{b}\b", text) or re.search(rf"\b{b}\s+{a}\b", text)  # « 3-2 » devient « 3 2 » une fois normalisé


def match_date(r):
    from robot import parse_day
    return parse_day(r.get("date"), datetime.now(PARIS))


def enrich(results, W, report):
    try:
        P = posts(W.start - timedelta(days=1))
    except Exception:
        P = []
    if not P:
        report["sportclub-reims"] = "illisible"; return
    n = 0
    for r in results:
        if r.get("sh") is None: continue
        d = match_date(r)
        if not d: continue
        th, ta = distinctive(r["home"]), distinctive(r["away"])
        if not (th or ta): continue
        best = None
        for p in P:
            if not (d <= p["date"].date() <= d + timedelta(days=4)): continue
            if not score_in(p["text"], r["sh"], r["sa"]): continue
            hit_h = any(f" {t} " in p["text"] for t in th) if th else True
            hit_a = any(f" {t} " in p["text"] for t in ta) if ta else True
            if not (hit_h and hit_a): continue
            in_title = any(f" {t} " in f" {p['title']} " for t in th + ta)
            rank = 0 if (in_title and not p["recap"]) else (1 if not p["recap"] else 2)
            if not best or rank < best[0]: best = (rank, p)
        if best:
            if r.get("url") and r["url"] != best[1]["link"]: r["source"] = r["url"]
            r["url"] = best[1]["link"]; n += 1
    report["sportclub-reims"] = f"{n} liens vers des articles"
