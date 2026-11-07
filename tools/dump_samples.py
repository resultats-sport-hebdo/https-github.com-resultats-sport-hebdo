"""Affiche des extraits bruts de chaque source pour concevoir les lecteurs du robot."""
import re, sys, requests
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36","Accept-Language":"fr-FR,fr;q=0.9"}
URLS=sys.argv[1:]
def links(html):
    out=[]
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',html,re.S):
        t=re.sub(r"<[^>]+>|\s+"," ",m.group(2)).strip()
        out.append(f"{m.group(1)} :: {t[:60]}")
    return out
for u in URLS:
    print("="*20,u)
    try:
        r=requests.get(u,headers=UA,timeout=30);b=r.text
        print("HTTP",r.status_code,r.headers.get("content-type"),len(b))
        if "markdown" in r.headers.get("content-type","") or u.endswith(".md"):
            print(b[:9000]);continue
        nd=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',b,re.S)
        if nd: print("NEXT_DATA:",nd.group(1)[:3000])
        apis=sorted(set(re.findall(r'https?://[a-z0-9.-]*api[a-z0-9.-]*/[^"\'\s<>]{0,80}',b)))[:30]
        print("API-like:",apis)
        body=re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>"," ",b)
        L=links(body);print("LINKS(%d):"%len(L));print("\n".join(L[:120]))
        txt=re.sub(r"\s+"," ",re.sub(r"(?s)<[^>]+>"," ",body))
        print("TEXT:",txt[:5000])
    except Exception as e: print("ERR",e)
