// Builds the public Netlify site from app.html (the page published on Claude) and data.js.
// One pre-rendered page per sport + the home page + « le week-end prochain », so search engines and AI
// assistants read real results without running JavaScript. Also writes sitemap.xml, robots.txt and llms.txt.
// Usage (from the repository folder):  node build.js
const fs=require('fs'), path=require('path');
const {chromium}=require('playwright');
const ROOT=__dirname, SITE='https://resultats-sport-hebdo.netlify.app/';
const SPORTS=[['football','Football'],['basket','Basket'],['handball','Handball'],['volley','Volley'],['rugby','Rugby'],['futsal','Futsal'],['hockey-sur-glace','Hockey sur glace'],['roller-hockey','Roller hockey'],['water-polo','Water-polo']];
const ROUTES=['',...SPORTS.map(s=>s[0]),'week-end-prochain'];
(async()=>{
  const app=fs.readFileSync(path.join(ROOT,'app.html'),'utf8');
  const dataJs=fs.readFileSync(path.join(ROOT,'data.js'),'utf8');
  const DATA=JSON.parse(dataJs.replace(/^\s*window\.RSH_DATA\s*=\s*/,'').replace(/;\s*$/,''));
  const tmp=path.join(ROOT,'.prerender.html');
  const b=await chromium.launch();
  for(const r of ROUTES){
    const html=app.replace('<script id="t-datajs" src="data.js"></script>',`<script>window.RSH_STATIC=1;window.RSH_ROUTE=${JSON.stringify(r)};</script><script id="t-datajs" src="data.js"></script>`);
    fs.writeFileSync(tmp,html);
    const p=await b.newPage({viewport:{width:1280,height:900}});
    await p.route(/fonts\.(googleapis|gstatic)\.com/,x=>x.abort());
    await p.goto('file://'+tmp); await p.waitForFunction(()=>document.querySelector('#main')&&document.querySelector('#main').children.length>0,{timeout:15000});
    let out='<!doctype html>\n'+await p.evaluate(()=>document.documentElement.outerHTML);
    await p.close();
    out=out.replace(/<script>window\.RSH_STATIC=1;window\.RSH_ROUTE=[^<]*<\/script>/,'<script>window.RSH_STATIC=1;</script>')
           .replace('<script id="t-datajs" src="data.js"></script>','<script id="t-datajs" src="/data.js"></script>')
           .replace(/style="--sport:[^"]*"/,'');   // the page sets its colour again when it starts
    const dir=path.join(ROOT,r); fs.mkdirSync(dir,{recursive:true});
    fs.writeFileSync(path.join(dir,'index.html'),out);
    console.log('page', '/'+(r?r+'/':''));
  }
  await b.close(); fs.unlinkSync(tmp);
  const eds=(DATA.editions||[]).slice().sort((a,b)=>b.id.localeCompare(a.id)), cur=eds[0]||{results:[],agenda:[]};
  fs.writeFileSync(path.join(ROOT,'sitemap.xml'),'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+
    ROUTES.map(r=>`  <url><loc>${SITE}${r?r+'/':''}</loc><lastmod>${cur.id||''}</lastmod><changefreq>weekly</changefreq><priority>${r?'0.8':'1.0'}</priority></url>`).join('\n')+'\n</urlset>\n');
  fs.writeFileSync(path.join(ROOT,'robots.txt'),`User-agent: *\nAllow: /\nDisallow: /admin.html\n\nSitemap: ${SITE}sitemap.xml\n`);
  const L=[];
  L.push('# Résultats Sport Hebdo','',`> Résultats hebdomadaires des sports collectifs (football, basket, handball, volley, rugby, futsal, hockey, water-polo) des clubs de la Marne (51), des Ardennes (08), de l'Aube (10), de la Haute-Marne (52) et de l'Aisne (02), équipes seniors masculines et féminines, du niveau national au niveau régional, plus le Départemental 1 en football. Mis à jour chaque lundi matin.`,'');
  L.push('## Pages',''); L.push(`- [Accueil, à la une](${SITE})`); SPORTS.forEach(([sl,n])=>L.push(`- [Résultats ${n.toLowerCase()}](${SITE}${sl}/)`)); L.push(`- [Le week-end prochain : programme des 7 jours suivants](${SITE}week-end-prochain/)`,'');
  L.push(`## Résultats · ${cur.label||''}`,'');
  SPORTS.forEach(([sl,n])=>{ const rs=(cur.results||[]).filter(r=>r.sport===n); if(!rs.length) return; L.push(`### ${n}`,''); rs.forEach(r=>L.push(`- ${r.date} · ${r.comp} : ${r.home} ${r.sh}–${r.sa} ${r.away}${r.url?` (source : ${r.url})`:''}`)); L.push(''); });
  const ag=(cur.agenda||[]); if(ag.length){ L.push('## Le week-end prochain',''); ag.forEach(f=>L.push(`- ${f.day} ${f.time||''} · ${f.sport} · ${f.comp} : ${f.home} – ${f.away}${f.place?' ('+f.place+')':''}`)); L.push(''); }
  const CL=DATA.classements||[]; if(CL.length){ L.push('## Classements',''); CL.forEach(c=>{ L.push(`### ${c.sport} · ${c.key} (${c.maj||''})`,''); c.rows.forEach(x=>L.push(`${x.r}. ${x.team} — ${x.pts} pts, ${x.j} matchs joués`)); L.push(''); }); }
  L.push('## Sources',''); (DATA.sources||[]).forEach(s=>L.push(`- [${s.name}](${s.url})`));
  fs.writeFileSync(path.join(ROOT,'llms.txt'),L.join('\n')+'\n');
  // « le week-end prochain » of one sport is the same page as the sport, opened on the programme
  fs.writeFileSync(path.join(ROOT,'_redirects'),SPORTS.map(([sl])=>['week-end-prochain','classements'].map(v=>`/${sl}/${v}/  /${sl}/index.html  200\n/${sl}/${v}  /${sl}/index.html  200`).join('\n')).join('\n')+'\n');
  console.log('sitemap.xml, robots.txt, llms.txt, _redirects');
})().catch(e=>{console.error(e);process.exit(1);});
