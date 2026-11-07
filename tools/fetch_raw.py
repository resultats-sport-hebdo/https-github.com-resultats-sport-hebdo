"""Télécharge des pages brutes (développement du robot) dans le dossier raw/."""
import hashlib, json, re, sys, requests
from pathlib import Path
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36","Accept-Language":"fr-FR,fr;q=0.9","Accept":"*/*"}
out=Path("raw");out.mkdir(exist_ok=True);idx={}
for u in sys.argv[1:]:
    n=re.sub(r"[^a-zA-Z0-9]+","_",u)[-60:]+"_"+hashlib.md5(u.encode()).hexdigest()[:6]
    try:
        r=requests.get(u,headers=UA,timeout=40)
        b=r.content
        (out/n).write_bytes(b); idx[n]={"url":u,"status":r.status_code,"type":r.headers.get("content-type"),"len":len(b),"final":r.url}
    except Exception as e: idx[n]={"url":u,"err":str(e)}
    print(n,idx[n])
(out/"index.json").write_text(json.dumps(idx,indent=1))
