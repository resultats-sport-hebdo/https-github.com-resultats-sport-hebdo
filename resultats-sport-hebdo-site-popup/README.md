# Résultats Sport Hebdo

Résultats hebdomadaires des sports collectifs (niveaux régional et national) de la Marne, des Ardennes, de l’Aube, de la Haute-Marne et de l’Aisne.

- `index.html` : la newsletter (filtres par département, zone, niveau, sport, division et club).
- `data.js` / `data.json` : le contenu (clubs, zones, éditions). Mis à jour chaque lundi.

Site publié : https://resultats-sport-hebdo.netlify.app/

Mise à jour automatique : chaque lundi matin (newsletter dans Claude, puis ce dépôt, puis Netlify).

## Construction du site (depuis novembre 2026)

`app.html` est la page publiée sur Claude. `node build.js` génère les pages statiques (accueil, une page par sport, le week-end prochain), `sitemap.xml`, `robots.txt`, `llms.txt` et `_redirects` pour Netlify. À relancer après chaque mise à jour de `data.js`.
