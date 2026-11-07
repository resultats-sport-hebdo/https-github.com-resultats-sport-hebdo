"""Teste quelles sources de résultats sportifs un robot GitHub peut lire.
Aucune donnée n'est enregistrée dans le dépôt : le rapport s'affiche dans le résumé de l'exécution."""
import os, re, time, requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "fr-FR,fr;q=0.9"}

# (sport, source, url, mot attendu dans une page réellement remplie)
SOURCES = [
 ("Football", "FFF épreuves (site)", "https://epreuves.fff.fr/", "comp"),
 ("Football", "FFF interface de données (DOFA)", "https://api-dofa.fff.fr/api/compets?page=1", "cp_no"),
 ("Football", "Ligue Grand Est (site)", "https://lgef.fff.fr/", "Ligue"),
 ("Football", "Foot National N2 E", "https://www.foot-national.com/data/calendrier-national2-groupe-e.html", "Charleville"),
 ("Football", "LiguesDeFoot R1 Grand Est", "https://www.liguesdefoot.fr/en/championnats/2026-2027/grand-est/regional/1a.md", "Reims"),
 ("Football", "SportCorico R1 Grand Est", "https://www.sportcorico.com/championnat/grand-est-regional-1-homiris-5/phase-lgef/poule-a", "Reims"),
 ("Basket", "FFBB compétitions", "https://competitions.ffbb.com/", "ffbb"),
 ("Basket", "FFBB recherche", "https://www.ffbb.com/", "basket"),
 ("Handball", "FFHandball compétitions", "https://www.ffhandball.fr/competitions/", "comp"),
 ("Volley", "FFVolley poule PN M Grand Est", "https://www.ffvbbeach.org/ffvbapp/resu/vbspo_calendrier.php?saison=2026/2027&codent=LILO&poule=PGA", "CHAUMONT"),
 ("Volley", "FFVolley programme national", "https://www.ffvbbeach.org/ffvbapp/resu/planning_volley.php", "REIMS"),
 ("Rugby", "FFR compétitions", "https://competitions.ffr.fr/", "rugby"),
 ("Rugby", "Rugby Amateur R1 Grand Est", "https://rugbyamateur.fr/regionales/grand-est/regionale-1/calendrier-resultats/", "Reims"),
 ("Roller hockey", "Rolskanet (FFRS)", "https://rolskanet.fr/sportif/synthese/rencontres/LH", "Rethel"),
 ("Hockey sur glace", "Hockey France", "https://www.hockeyfrance.com/", "hockey"),
 ("Water-polo", "Extranat (FFN)", "https://www.extranat.fr/", "natation"),
 ("Multisport", "Score'n'co", "https://scorenco.com/", "score"),
 ("Multisport", "Sport Club Reims", "https://www.sportclub-reims.fr/", "Reims"),
]

def visible_text(html):
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html)).strip()

rows = []
for sport, name, url, kw in SOURCES:
    try:
        t = time.time()
        r = requests.get(url, headers=UA, timeout=25)
        ms = int((time.time() - t) * 1000)
        body = r.text or ""
        txt = visible_text(body) if "html" in r.headers.get("content-type", "") else body
        ok_kw = kw.lower() in body.lower()
        if r.status_code >= 400:
            verdict = f"Bloqué ({r.status_code})"
        elif re.search(r"captcha|cf-chl|challenge-platform|Just a moment|verify you are human", body, re.I):
            verdict = "Bloqué (anti-robot)"
        elif len(txt) < 800 and not ok_kw:
            verdict = "Page vide (contenu chargé en JavaScript)"
        elif ok_kw:
            verdict = "Lisible"
        else:
            verdict = "Répond, contenu à vérifier"
        rows.append((sport, name, r.status_code, r.headers.get("content-type", "").split(";")[0], len(body), len(txt), ok_kw, ms, verdict, url))
    except Exception as e:
        rows.append((sport, name, "—", "", 0, 0, False, 0, f"Erreur : {type(e).__name__}", url))

lines = ["# Test des sources de résultats", "",
         "| Sport | Source | Verdict | HTTP | Type | Taille | Texte visible | Mot attendu | Temps |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
for s, n, code, ct, size, tl, kw, ms, v, url in rows:
    lines.append(f"| {s} | [{n}]({url}) | **{v}** | {code} | {ct} | {size} o | {tl} car. | {'oui' if kw else 'non'} | {ms} ms |")
report = "\n".join(lines)
print(report)
summary = os.environ.get("GITHUB_STEP_SUMMARY")
if summary:
    with open(summary, "a", encoding="utf-8") as f:
        f.write(report + "\n")
