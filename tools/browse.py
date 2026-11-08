"""Ouvre des pages dans un vrai navigateur (développement du robot) : texte visible + réponses JSON."""
import hashlib, json, os, re
from pathlib import Path
from playwright.sync_api import sync_playwright
out = Path("raw"); out.mkdir(exist_ok=True); idx = {}
urls = os.environ.get("URLS", "").split()
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(locale="fr-FR", user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36")
    pg0 = None
    for u in urls:
        if u.startswith("click:") and pg0:
            txt = u[6:].replace("_", " ")
            try:
                pg0.get_by_text(txt, exact=False).first.click(timeout=15000); pg0.wait_for_timeout(6000)
                n = "click_" + re.sub(r"[^a-zA-Z0-9]+", "_", txt)[:30]
                (out / (n + ".html")).write_text(pg0.content()); (out / (n + ".txt")).write_text(pg0.inner_text("body"))
                idx[n] = {"url": pg0.url, "click": txt}
            except Exception as e:
                idx["click_err"] = {"err": str(e)}
            print(idx.get(n) if 'n' in dir() else e); continue
        if u.startswith("fetch:") and pg0:
            api = u[6:]; n = re.sub(r"[^a-zA-Z0-9]+", "_", api)[-50:] + "_" + hashlib.md5(api.encode()).hexdigest()[:6]
            try:
                body = pg0.evaluate("async (u) => { const r = await fetch(u); return r.status + '\\n' + await r.text(); }", api)
                (out / (n + ".fetch")).write_text(body); idx[n] = {"url": api, "len": len(body), "status": body[:3]}
            except Exception as e:
                idx[n] = {"url": api, "err": str(e)}
            print(n, idx[n]); continue
        n = re.sub(r"[^a-zA-Z0-9]+", "_", u)[-50:] + "_" + hashlib.md5(u.encode()).hexdigest()[:6]
        pg = ctx.new_page(); apis = []
        def on_resp(r, apis=apis):
            ct = r.headers.get("content-type", "")
            if "json" in ct or "/api" in r.url or r.request.resource_type in ("xhr", "fetch"):
                try: body = r.text()
                except Exception: body = ""
                apis.append({"url": r.url, "status": r.status, "method": r.request.method, "post": r.request.post_data, "headers": r.request.headers, "len": len(body), "body": body[:200000]})
        pg.on("response", on_resp)
        try:
            pg.goto(u, wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(7000)
            (out / (n + ".txt")).write_text(pg.inner_text("body"))
            (out / (n + ".html")).write_text(pg.content())
            idx[n] = {"url": u, "title": pg.title(), "apis": len(apis)}
        except Exception as e:
            idx[n] = {"url": u, "err": str(e)}
        (out / (n + ".api.json")).write_text(json.dumps(apis, ensure_ascii=False, indent=1))
        print(n, idx[n])
        if pg0: pg0.close()
        pg0 = pg
    if pg0: pg0.close()
    b.close()
(out / "index.json").write_text(json.dumps(idx, indent=1))
