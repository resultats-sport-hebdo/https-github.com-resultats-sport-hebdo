"""Requête GraphQL Score'n'co (développement du robot) : QUERY et VARS en variables d'environnement."""
import json, os, requests
from pathlib import Path
out = Path("raw"); out.mkdir(exist_ok=True)
r = requests.post("https://graphql.scorenco.com/v1/graphql", json={"query": os.environ["QUERY"], "variables": json.loads(os.environ.get("VARS") or "{}")},
                  headers={"Content-Type": "application/json", "x-hasura-role": "anonymous", "x-hasura-locale": "fr-FR", "Referer": "https://scorenco.com/"}, timeout=60)
(out / "gql.json").write_text(r.text); (out / "index.json").write_text(json.dumps({"gql": {"status": r.status_code, "len": len(r.text)}}))
print(r.status_code, r.text[:3000])
