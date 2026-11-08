"""Contrôle club par club : chaque équipe suivie de niveau national a-t-elle un résultat ou un match à venir
dans l'édition en cours ? Affiche la liste des équipes sans rien, à vérifier une par une."""
import json, re, sys, unicodedata
def norm(s): return re.sub(r"[^a-z0-9 ]"," ",unicodedata.normalize("NFD",s or "").encode("ascii","ignore").decode().lower())
D=json.load(open(sys.argv[1] if len(sys.argv)>1 else "data.json"))
E=D["editions"][0]; lvl=sys.argv[2] if len(sys.argv)>2 else "National"
rows=[(r,"R") for r in E["results"]]+[(a,"A") for a in E["agenda"]]
miss=[]
for c in D["suivi"]:
    if c.get("level")!=lvl: continue
    n=norm(c["club"]); toks=[t for t in n.split() if len(t)>3]
    hit=[k for r,k in rows if r["sport"]==c["sport"] and (n in norm(r["home"]) or n in norm(r["away"]) or (toks and all(t in norm(r["home"]+" "+r["away"]) for t in toks)))]
    if "R" not in hit: miss.append((c["sport"],c["club"],"à venir seulement" if hit else "RIEN"))
print(f"Édition {E['id']} — équipes {lvl} sans résultat : {len(miss)}")
for m in sorted(miss): print(" ",*m,sep=" | ")
